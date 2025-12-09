"""
AI Service Layer for OpenRouter integration via LiteLLM.
Handles content generation, analysis, and recommendations using free LLM models.
"""
from typing import Dict, Optional, Any, List, Tuple
from django.conf import settings
from django.core.cache import cache
import litellm
import logging
import hashlib
import json
import time
import re

logger = logging.getLogger(__name__)


class PromptSanitizer:
    """
    Sanitize user input to prevent prompt injection attacks.
    Removes potentially dangerous patterns while preserving legitimate content.
    """

    # Patterns that could be used for prompt injection
    DANGEROUS_PATTERNS = [
        r'ignore\s+previous\s+instructions',
        r'disregard\s+all\s+previous',
        r'you\s+are\s+now',
        r'forget\s+everything',
        r'new\s+instructions?:',
        r'system\s*:',
        r'assistant\s*:',
        r'</s>',
        r'<\|endoftext\|>',
        r'<\|im_start\|>',
        r'<\|im_end\|>',
        r'\[INST\]',
        r'\[/INST\]',
    ]

    @staticmethod
    def sanitize(text: str, max_length: int = 2000) -> str:
        """
        Sanitize user input for use in AI prompts.

        Args:
            text: User-provided text
            max_length: Maximum allowed length

        Returns:
            Sanitized text safe for prompts
        """
        if not text:
            return ""

        # Truncate to max length
        text = text[:max_length]

        # Remove dangerous patterns (case-insensitive)
        for pattern in PromptSanitizer.DANGEROUS_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Remove control characters except newlines and tabs
        text = ''.join(
            char for char in text
            if char.isprintable() or char in '\n\t'
        )

        # Remove excessive newlines (more than 3 in a row)
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        # Remove excessive whitespace
        text = re.sub(r' {3,}', '  ', text)

        return text.strip()


class JSONResponseParser:
    """
    Robust parser for AI-generated JSON responses.
    Handles various formats: markdown code blocks, plain JSON, malformed JSON.
    """

    @staticmethod
    def extract_json(response_text: str) -> dict:
        """
        Extract JSON from AI response, handling various formats.

        Handles:
        - Markdown code blocks (```json ... ```)
        - Plain JSON
        - JSON with explanation text
        - Minor formatting issues

        Args:
            response_text: Raw AI response text

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If no valid JSON can be extracted
        """
        if not response_text:
            raise ValueError("Empty response text")

        # Remove markdown code blocks
        if '```' in response_text:
            # Extract content between ```json and ``` or ``` and ```
            matches = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
            if matches:
                response_text = matches[0]

        # Try to find JSON object or array
        json_pattern = r'(\{[^}]*(?:\{[^}]*\}[^}]*)*\}|\[[^\]]*(?:\[[^\]]*\][^\]]*)*\])'
        json_matches = re.findall(json_pattern, response_text, re.DOTALL)

        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Try direct parse
        try:
            return json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            logger.debug(f"Response text (first 500 chars): {response_text[:500]}")
            raise ValueError(f"Could not extract valid JSON from response")

    @staticmethod
    def parse_with_fallback(response_text: str, fallback: dict) -> dict:
        """
        Parse JSON with fallback on failure.

        Args:
            response_text: Raw AI response text
            fallback: Dictionary to return if parsing fails

        Returns:
            Parsed JSON dictionary or fallback
        """
        try:
            return JSONResponseParser.extract_json(response_text)
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Using fallback response due to parse error: {e}")
            return fallback


class AIService:
    """Service for AI-powered content generation using OpenRouter via LiteLLM."""

    def __init__(self):
        """Initialize LiteLLM with OpenRouter configuration"""
        self.api_key = settings.OPENROUTER_API_KEY
        self.models = settings.AI_MODELS
        self.default_model = settings.DEFAULT_AI_MODEL
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE
        self.timeout = settings.AI_REQUEST_TIMEOUT
        self.cache_enabled = settings.AI_CACHE_ENABLED
        self.cache_ttl = settings.AI_CACHE_TTL
        self._initialize_client()

    def _initialize_client(self):
        """Configure LiteLLM for OpenRouter"""
        if self.api_key:
            litellm.api_key = self.api_key
            litellm.drop_params = True
            logger.info("AI service initialized with OpenRouter")
        else:
            logger.warning("No OpenRouter API key configured")

    def is_ready(self) -> bool:
        """Check if service is properly configured"""
        return bool(self.api_key)

    def _complete_with_fallback(
        self,
        prompt: str,
        model_tier: str = 'fast',
        **kwargs
    ) -> Tuple[str, str, int, Optional[int]]:
        """
        LLM completion with fallback logic for rate limiting.

        Args:
            prompt: The prompt to send to the LLM
            model_tier: Model tier to use ('fast' or 'quality')
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            Tuple of (response_text, model_used, response_time_ms, tokens_used)
        """
        models = self.models.get(model_tier, self.models['fast'])
        start_time = time.time()

        for model in models:
            try:
                # Check if model is rate limited
                if self._is_rate_limited(model):
                    logger.info(f"Skipping rate-limited model: {model}")
                    continue

                logger.info(f"Attempting AI request with model: {model}")

                response = litellm.completion(
                    model=f"openrouter/{model}",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=kwargs.get('max_tokens', self.max_tokens),
                    temperature=kwargs.get('temperature', self.temperature),
                    timeout=self.timeout,
                )

                response_time_ms = int((time.time() - start_time) * 1000)
                tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else None

                logger.info(f"AI request successful with {model} in {response_time_ms}ms")

                return (
                    response.choices[0].message.content,
                    model,
                    response_time_ms,
                    tokens_used
                )

            except litellm.RateLimitError as e:
                logger.warning(f"Rate limit hit for {model}: {e}")
                self._mark_rate_limited(model)
                continue
            except litellm.AuthenticationError as e:
                logger.error(f"Authentication error with {model}: {e}")
                raise Exception("AI service authentication failed")
            except litellm.APIConnectionError as e:
                logger.warning(f"Connection error with {model}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error with {model}: {e}")
                continue

        # All models failed
        raise Exception("All AI models unavailable or rate limited")

    def _is_rate_limited(self, model: str) -> bool:
        """Check if model is currently rate limited"""
        return cache.get(f"ai_rate_limit_{model}") is not None

    def _mark_rate_limited(self, model: str, duration: int = 300):
        """Mark model as rate limited for specified duration (seconds, default: 300s = 5 minutes)"""
        cache.set(f"ai_rate_limit_{model}", True, duration)
        logger.info(f"Marked {model} as rate limited for {duration}s")

    def _generate_cache_key(self, operation: str, **kwargs) -> str:
        """
        Generate cache key from operation and parameters.
        Uses MD5 hash for consistent, collision-resistant keys.
        """
        sorted_items = sorted(kwargs.items())
        content = f"{operation}:" + ":".join(f"{k}={v}" for k, v in sorted_items)
        hash_digest = hashlib.md5(content.encode()).hexdigest()
        return f"ai_cache_{operation}_{hash_digest}"

    # ===== PUBLIC API METHODS =====

    def generate_title(
        self,
        description: str,
        context: Optional[Dict] = None
    ) -> Tuple[List[str], str, int, Optional[int], bool]:
        """
        Generate 3-4 title suggestions from description.

        Args:
            description: Brief description of the asset
            context: Optional context (asset_type, etc.)

        Returns:
            Tuple of (titles, model_used, response_time_ms, tokens_used, cache_hit)
        """
        # Sanitize user input to prevent prompt injection
        description = PromptSanitizer.sanitize(description, max_length=1000)
        asset_type = ''
        if context and context.get('asset_type'):
            asset_type = PromptSanitizer.sanitize(context['asset_type'], max_length=50)

        cache_key = self._generate_cache_key('title', description=description, context=context)
        cache_hit = False

        # Check cache first
        if self.cache_enabled:
            cached = cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for title generation")
                cache_hit = True
                return (
                    cached['titles'],
                    cached.get('model_used', self.default_model),
                    0,  # No response time for cache hit
                    0,  # No tokens for cache hit
                    True  # cache_hit=True
                )

        # Build prompt with sanitized input
        prompt = f"""Generate 4 creative, SEO-friendly titles (50-70 characters each) for:

Description: {description}
{f'Asset Type: {asset_type}' if asset_type else ''}

Return ONLY the titles, one per line, without numbering."""

        # Call AI
        response_text, model_used, response_time_ms, tokens_used = self._complete_with_fallback(
            prompt,
            model_tier='fast'
        )

        # Parse titles
        titles = [line.strip() for line in response_text.split('\n') if line.strip()]

        # Cache result
        if self.cache_enabled:
            cache.set(cache_key, {
                'titles': titles,
                'model_used': model_used
            }, self.cache_ttl)

        return (titles, model_used, response_time_ms, tokens_used, cache_hit)

    def enhance_description(
        self,
        description: str,
        title: Optional[str] = None,
        asset_type: Optional[str] = None
    ) -> Tuple[str, str, int, Optional[int], bool]:
        """
        Expand brief description into detailed narrative (150-200 words).

        Args:
            description: Brief description to enhance
            title: Optional asset title
            asset_type: Optional asset type

        Returns:
            Tuple of (enhanced_description, model_used, response_time_ms, tokens_used, cache_hit)
        """
        # Sanitize all user inputs to prevent prompt injection
        description = PromptSanitizer.sanitize(description, max_length=1000)
        if title:
            title = PromptSanitizer.sanitize(title, max_length=200)
        if asset_type:
            asset_type = PromptSanitizer.sanitize(asset_type, max_length=50)

        cache_key = self._generate_cache_key(
            'description',
            description=description,
            title=title,
            asset_type=asset_type
        )
        cache_hit = False

        if self.cache_enabled:
            cached = cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for description enhancement")
                return (
                    cached['enhanced'],
                    cached.get('model_used', self.default_model),
                    0,
                    0,
                    True
                )

        prompt = f"""Expand this brief description into an engaging 150-200 word narrative:

{f'Title: {title}' if title else ''}
{f'Asset Type: {asset_type}' if asset_type else ''}
Brief Description: {description}

Use vivid language, capture the mood, and appeal to collectors. Return only the enhanced description."""

        response_text, model_used, response_time_ms, tokens_used = self._complete_with_fallback(
            prompt,
            model_tier='fast'
        )

        enhanced = response_text.strip()

        if self.cache_enabled:
            cache.set(cache_key, {
                'enhanced': enhanced,
                'model_used': model_used
            }, self.cache_ttl)

        return (enhanced, model_used, response_time_ms, tokens_used, cache_hit)

    def analyze_content(
        self,
        title: str,
        description: str,
        media_url: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str, int, Optional[int], bool]:
        """
        Extract categories, tags, and metadata from content.

        Args:
            title: Asset title
            description: Asset description
            media_url: Optional media URL

        Returns:
            Tuple of (analysis_dict, model_used, response_time_ms, tokens_used, cache_hit)
        """
        # Sanitize all user inputs to prevent prompt injection
        title = PromptSanitizer.sanitize(title, max_length=200)
        description = PromptSanitizer.sanitize(description, max_length=2000)

        cache_key = self._generate_cache_key(
            'analysis',
            title=title,
            description=description
        )
        cache_hit = False

        if self.cache_enabled:
            cached = cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for content analysis")
                return (
                    cached['analysis'],
                    cached.get('model_used', self.default_model),
                    0,
                    0,
                    True
                )

        prompt = f"""Analyze this asset and extract metadata:

Title: {title}
Description: {description}

Return this EXACT JSON format (valid JSON only, no markdown):
{{
  "category": "digital_art|music|writing|video|3d_model|game_asset|photography",
  "tags": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "art_style": "style if applicable or null",
  "theme": "primary theme",
  "genre": "genre if applicable or null"
}}"""

        response_text, model_used, response_time_ms, tokens_used = self._complete_with_fallback(
            prompt,
            model_tier='quality'
        )

        # Parse JSON with robust fallback handling
        analysis = JSONResponseParser.parse_with_fallback(
            response_text,
            fallback={
                'category': 'digital_art',
                'tags': [],
                'art_style': None,
                'theme': None,
                'genre': None
            }
        )

        if self.cache_enabled:
            cache.set(cache_key, {
                'analysis': analysis,
                'model_used': model_used
            }, self.cache_ttl)

        return (analysis, model_used, response_time_ms, tokens_used, cache_hit)

    def suggest_license(
        self,
        asset_type: str,
        description: str,
        intended_use: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str, int, Optional[int], bool]:
        """
        Recommend optimal license terms for asset.

        Args:
            asset_type: Type of asset
            description: Asset description
            intended_use: Optional intended use case

        Returns:
            Tuple of (suggestions_dict, model_used, response_time_ms, tokens_used, cache_hit)
        """
        # Sanitize all user inputs to prevent prompt injection
        asset_type = PromptSanitizer.sanitize(asset_type, max_length=50)
        description = PromptSanitizer.sanitize(description, max_length=1000)
        if intended_use:
            intended_use = PromptSanitizer.sanitize(intended_use, max_length=200)

        cache_key = self._generate_cache_key(
            'license',
            asset_type=asset_type,
            description=description,
            intended_use=intended_use
        )
        cache_hit = False

        if self.cache_enabled:
            cached = cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for license suggestion")
                return (
                    cached['suggestions'],
                    cached.get('model_used', self.default_model),
                    0,
                    0,
                    True
                )

        prompt = f"""Recommend license terms for:

Asset Type: {asset_type}
Description: {description}
{f'Intended Use: {intended_use}' if intended_use else ''}

Consider Story Protocol standards (5-20% royalties typical).

Return this EXACT JSON (valid JSON only, no markdown):
{{
  "royalty_percentage": <number 0-50>,
  "allow_derivatives": <true/false>,
  "commercial_rights": <true/false>,
  "reasoning": "<2-3 sentences>"
}}"""

        response_text, model_used, response_time_ms, tokens_used = self._complete_with_fallback(
            prompt,
            model_tier='fast'
        )

        # Parse JSON response with robust parser
        suggestions = JSONResponseParser.parse_with_fallback(
            response_text,
            fallback={
                'royalty_percentage': 10,
                'allow_derivatives': True,
                'commercial_rights': False,
                'reasoning': 'Default balanced terms'
            }
        )

        if self.cache_enabled:
            cache.set(cache_key, {
                'suggestions': suggestions,
                'model_used': model_used
            }, self.cache_ttl)

        return (suggestions, model_used, response_time_ms, tokens_used, cache_hit)

    def analyze_derivative(
        self,
        parent_title: str,
        parent_description: str,
        derivative_description: str,
        derivative_title: Optional[str] = None
    ) -> Tuple[Dict[str, Any], str, int, Optional[int], bool]:
        """
        Analyze relationship between parent and derivative assets.

        Args:
            parent_title: Parent asset title
            parent_description: Parent asset description
            derivative_description: Derivative asset description
            derivative_title: Optional derivative title

        Returns:
            Tuple of (analysis_dict, model_used, response_time_ms, tokens_used, cache_hit)
        """
        # Sanitize all user inputs to prevent prompt injection
        parent_title = PromptSanitizer.sanitize(parent_title, max_length=200)
        parent_description = PromptSanitizer.sanitize(parent_description, max_length=1000)
        derivative_description = PromptSanitizer.sanitize(derivative_description, max_length=1000)
        if derivative_title:
            derivative_title = PromptSanitizer.sanitize(derivative_title, max_length=200)

        cache_key = self._generate_cache_key(
            'derivative',
            parent_title=parent_title,
            parent_description=parent_description,
            derivative_description=derivative_description,
            derivative_title=derivative_title
        )
        cache_hit = False

        if self.cache_enabled:
            cached = cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for derivative analysis")
                return (
                    cached['analysis'],
                    cached.get('model_used', self.default_model),
                    0,
                    0,
                    True
                )

        prompt = f"""Analyze parent-derivative relationship:

PARENT: {parent_title}
{parent_description}

DERIVATIVE: {derivative_title or '(untitled)'}
{derivative_description}

Return this EXACT JSON (valid JSON only, no markdown):
{{
  "similarity_score": <0.0-1.0>,
  "transformation_type": "direct_copy|minor_edit|stylistic_remix|significant_transformation|completely_original",
  "suggested_attribution": "attribution text",
  "key_differences": ["diff1", "diff2", "diff3"]
}}"""

        response_text, model_used, response_time_ms, tokens_used = self._complete_with_fallback(
            prompt,
            model_tier='quality'
        )

        # Parse JSON response with robust parser
        analysis = JSONResponseParser.parse_with_fallback(
            response_text,
            fallback={
                'similarity_score': 0.5,
                'transformation_type': 'stylistic_remix',
                'suggested_attribution': f'Inspired by "{parent_title}"',
                'key_differences': []
            }
        )

        if self.cache_enabled:
            cache.set(cache_key, {
                'analysis': analysis,
                'model_used': model_used
            }, self.cache_ttl)

        return (analysis, model_used, response_time_ms, tokens_used, cache_hit)


# Singleton instance
_ai_service_instance = None


def get_ai_service() -> AIService:
    """Get singleton instance of AIService."""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    return _ai_service_instance

