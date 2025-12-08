"""
Quality Scoring Agent

Analyzes IP assets for quality metrics including:
- Technical quality (resolution, sharpness, noise)
- Description quality (length, clarity, readability)
- Metadata completeness
- Market appeal prediction
- Actionable improvement suggestions
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
import io
import re
import requests
from PIL import Image
import cv2
import numpy as np
from django.core.files.storage import default_storage

from apps.assets.models import IPAsset
from apps.ai.models import QualityAnalysisResult
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class QualityAgent(BaseAgent):
    """
    Agent for comprehensive quality analysis of IP assets.

    Evaluates multiple dimensions:
    1. Technical quality (images)
    2. Description quality (text)
    3. Metadata completeness
    4. Market appeal
    """

    # Scoring weights
    WEIGHTS = {
        'technical': 0.30,
        'description': 0.25,
        'metadata': 0.25,
        'market_appeal': 0.20,
    }

    def get_name(self) -> str:
        return "QualityAgent"

    def analyze(self, asset_id: int, **kwargs) -> AgentResult:
        """
        Analyze an asset for quality metrics.

        Args:
            asset_id: ID of the IPAsset to analyze

        Returns:
            AgentResult with quality analysis data
        """
        # Validate input
        error = self.validate_input(['asset_id'], asset_id=asset_id)
        if error:
            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                errors=[error]
            )

        try:
            # Get the asset
            asset = IPAsset.objects.select_related('creator').get(id=asset_id)
        except IPAsset.DoesNotExist:
            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                errors=[f"Asset with id {asset_id} not found"]
            )

        warnings = []

        # 1. Technical Quality Analysis (if image)
        technical_quality = self._analyze_technical_quality(asset)

        # 2. Description Quality Analysis
        description_quality = self._analyze_description_quality(asset)

        # 3. Metadata Completeness
        metadata_completeness = self._analyze_metadata_completeness(asset)

        # 4. Market Appeal Prediction
        market_appeal = self._predict_market_appeal(
            asset,
            technical_quality,
            description_quality,
            metadata_completeness
        )

        # 5. Calculate Overall Score
        overall_score = self._calculate_overall_score(
            technical_quality.get('overall_score', 0),
            description_quality.get('overall_score', 0),
            metadata_completeness,
            market_appeal
        )

        # 6. Generate Improvement Suggestions
        improvement_suggestions = self._generate_improvements(
            asset,
            technical_quality,
            description_quality,
            metadata_completeness
        )

        # 7. Identify Strengths
        strengths = self._identify_strengths(
            asset,
            technical_quality,
            description_quality,
            metadata_completeness
        )

        # 8. Calculate Confidence
        confidence = self._calculate_confidence(asset, technical_quality)

        # Build result data
        data = {
            'overall_score': round(overall_score, 2),
            'technical_quality': technical_quality,
            'description_quality': description_quality,
            'metadata_completeness': round(metadata_completeness, 2),
            'market_appeal': round(market_appeal, 2),
            'improvement_suggestions': improvement_suggestions,
            'strengths': strengths,
            'confidence': round(confidence, 2),
        }

        # Save result to database
        QualityAnalysisResult.objects.update_or_create(
            asset=asset,
            defaults={
                'overall_score': overall_score,
                'technical_quality': technical_quality,
                'description_quality': description_quality,
                'metadata_completeness': metadata_completeness,
                'market_appeal': market_appeal,
                'improvement_suggestions': improvement_suggestions,
                'strengths': strengths,
                'confidence': confidence,
            }
        )

        return AgentResult(
            success=True,
            data=data,
            confidence=confidence,
            warnings=warnings
        )

    def _analyze_technical_quality(self, asset: IPAsset) -> Dict[str, Any]:
        """
        Analyze technical quality of the image asset.

        Args:
            asset: The asset to analyze

        Returns:
            Dictionary with technical quality metrics
        """
        result = {
            'overall_score': 0,
            'has_image': False,
            'resolution_score': 0,
            'sharpness_score': 0,
            'noise_score': 0,
            'analysis_performed': False,
        }

        if not asset.media_url:
            return result

        try:
            # Download image
            image = self._load_image(asset.media_url)
            if image is None:
                return result

            result['has_image'] = True
            result['analysis_performed'] = True

            # Convert to numpy array for OpenCV
            img_array = np.array(image)

            # 1. Resolution Score (based on dimensions)
            width, height = image.size
            pixels = width * height
            result['width'] = width
            result['height'] = height
            result['megapixels'] = round(pixels / 1_000_000, 2)

            # Score based on resolution
            if pixels >= 8_000_000:  # 8MP+
                result['resolution_score'] = 100
            elif pixels >= 4_000_000:  # 4MP+
                result['resolution_score'] = 85
            elif pixels >= 2_000_000:  # 2MP+
                result['resolution_score'] = 70
            elif pixels >= 1_000_000:  # 1MP+
                result['resolution_score'] = 50
            else:
                result['resolution_score'] = 30

            # 2. Sharpness Score (Laplacian variance)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            result['laplacian_variance'] = round(laplacian_var, 2)

            # Score based on sharpness
            if laplacian_var >= 500:
                result['sharpness_score'] = 100
            elif laplacian_var >= 200:
                result['sharpness_score'] = 80
            elif laplacian_var >= 100:
                result['sharpness_score'] = 60
            else:
                result['sharpness_score'] = 40

            # 3. Noise Score (estimate based on standard deviation)
            noise_estimate = np.std(gray)
            result['noise_estimate'] = round(float(noise_estimate), 2)

            # Lower noise is better
            if noise_estimate <= 20:
                result['noise_score'] = 100
            elif noise_estimate <= 40:
                result['noise_score'] = 80
            elif noise_estimate <= 60:
                result['noise_score'] = 60
            else:
                result['noise_score'] = 40

            # Calculate overall technical score
            result['overall_score'] = (
                result['resolution_score'] * 0.4 +
                result['sharpness_score'] * 0.4 +
                result['noise_score'] * 0.2
            )

        except Exception as e:
            logger.error(f"Error in technical quality analysis: {e}")
            result['error'] = str(e)

        return result

    def _analyze_description_quality(self, asset: IPAsset) -> Dict[str, Any]:
        """
        Analyze quality of text content (title + description).

        Args:
            asset: The asset to analyze

        Returns:
            Dictionary with description quality metrics
        """
        result = {
            'overall_score': 0,
            'length_score': 0,
            'clarity_score': 0,
            'seo_score': 0,
            'word_count': 0,
        }

        # Combine title and description
        text = f"{asset.title} {asset.description or ''}"
        words = text.split()
        result['word_count'] = len(words)

        # 1. Length Score
        desc_length = len(asset.description or '')
        if desc_length >= 300:
            result['length_score'] = 100
        elif desc_length >= 150:
            result['length_score'] = 80
        elif desc_length >= 50:
            result['length_score'] = 60
        else:
            result['length_score'] = 30

        # 2. Clarity Score (based on readability)
        clarity = self._calculate_readability(asset.description or asset.title)
        result['clarity_score'] = clarity
        result['reading_ease'] = clarity  # Flesch reading ease approximation

        # 3. SEO Score (keywords, uniqueness)
        seo_score = self._calculate_seo_score(asset)
        result['seo_score'] = seo_score

        # Calculate overall description score
        result['overall_score'] = (
            result['length_score'] * 0.4 +
            result['clarity_score'] * 0.3 +
            result['seo_score'] * 0.3
        )

        return result

    def _analyze_metadata_completeness(self, asset: IPAsset) -> float:
        """
        Calculate metadata completeness score.

        Args:
            asset: The asset to analyze

        Returns:
            Completeness score (0-100)
        """
        score = 0
        total_fields = 8

        # Required fields
        if asset.title and len(asset.title) >= 3:
            score += 1
        if asset.description and len(asset.description) >= 20:
            score += 1
        if asset.media_url:
            score += 1
        if getattr(asset, 'asset_type', None):
            score += 1

        # Optional but recommended fields
        if asset.license_type:
            score += 1
        if asset.tags:
            score += 1
        if asset.royalty_percentage is not None:
            score += 1
        if hasattr(asset, 'creator') and asset.creator:
            score += 1

        return (score / total_fields) * 100

    def _predict_market_appeal(
        self,
        asset: IPAsset,
        technical_quality: Dict[str, Any],
        description_quality: Dict[str, Any],
        metadata_completeness: float
    ) -> float:
        """
        Predict market appeal based on various factors.

        Args:
            asset: The asset
            technical_quality: Technical quality metrics
            description_quality: Description quality metrics
            metadata_completeness: Metadata completeness score

        Returns:
            Market appeal score (0-100)
        """
        appeal = 50  # Base score

        # High technical quality boosts appeal
        if technical_quality.get('overall_score', 0) >= 80:
            appeal += 15
        elif technical_quality.get('overall_score', 0) >= 60:
            appeal += 5

        # Good description boosts appeal
        if description_quality.get('overall_score', 0) >= 70:
            appeal += 15
        elif description_quality.get('overall_score', 0) >= 50:
            appeal += 5

        # Complete metadata boosts appeal
        if metadata_completeness >= 80:
            appeal += 10
        elif metadata_completeness >= 60:
            appeal += 5

        # Having derivatives suggests popularity
        if hasattr(asset, 'derivatives') and asset.derivatives.count() > 0:
            appeal += 10

        return min(appeal, 100)

    def _calculate_overall_score(
        self,
        technical_score: float,
        description_score: float,
        metadata_score: float,
        appeal_score: float
    ) -> float:
        """
        Calculate weighted overall quality score.

        Args:
            technical_score: Technical quality score
            description_score: Description quality score
            metadata_score: Metadata completeness score
            appeal_score: Market appeal score

        Returns:
            Overall score (0-100)
        """
        return (
            technical_score * self.WEIGHTS['technical'] +
            description_score * self.WEIGHTS['description'] +
            metadata_score * self.WEIGHTS['metadata'] +
            appeal_score * self.WEIGHTS['market_appeal']
        )

    def _generate_improvements(
        self,
        asset: IPAsset,
        technical_quality: Dict[str, Any],
        description_quality: Dict[str, Any],
        metadata_completeness: float
    ) -> List[str]:
        """
        Generate actionable improvement suggestions.

        Args:
            asset: The asset
            technical_quality: Technical quality metrics
            description_quality: Description quality metrics
            metadata_completeness: Metadata completeness score

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Technical improvements
        if technical_quality.get('resolution_score', 0) < 70:
            suggestions.append(
                "📸 Consider uploading a higher resolution image (2MP+ recommended)"
            )

        if technical_quality.get('sharpness_score', 0) < 60:
            suggestions.append(
                "🔍 Image appears blurry. Try using a sharper, more focused image"
            )

        # Description improvements
        desc_len = len(asset.description or '')
        if desc_len < 50:
            suggestions.append(
                "📝 Add a detailed description (150+ characters recommended) to help "
                "users understand your asset better"
            )
        elif desc_len < 150:
            suggestions.append(
                "📝 Expand your description to at least 150 characters for better SEO"
            )

        # Metadata improvements
        if metadata_completeness < 70:
            if not asset.tags:
                suggestions.append("🏷️ Add relevant tags to improve discoverability")
            if not asset.license_type:
                suggestions.append("📜 Specify a license type for clarity")
            if asset.royalty_percentage is None:
                suggestions.append("💰 Set royalty percentage for derivatives")

        # SEO improvements
        if description_quality.get('seo_score', 0) < 60:
            suggestions.append(
                "🔎 Improve SEO by including relevant keywords in your title and description"
            )

        # General improvements
        if not suggestions:
            suggestions.append(
                "✨ Your asset quality is good! Consider promoting it to increase visibility"
            )

        return suggestions[:6]  # Limit to top 6 suggestions

    def _identify_strengths(
        self,
        asset: IPAsset,
        technical_quality: Dict[str, Any],
        description_quality: Dict[str, Any],
        metadata_completeness: float
    ) -> List[str]:
        """
        Identify strengths of the asset.

        Args:
            asset: The asset
            technical_quality: Technical quality metrics
            description_quality: Description quality metrics
            metadata_completeness: Metadata completeness score

        Returns:
            List of strengths
        """
        strengths = []

        if technical_quality.get('resolution_score', 0) >= 80:
            strengths.append("High resolution image")

        if technical_quality.get('sharpness_score', 0) >= 80:
            strengths.append("Sharp and clear visuals")

        if description_quality.get('overall_score', 0) >= 70:
            strengths.append("Well-written description")

        if description_quality.get('length_score', 0) >= 80:
            strengths.append("Comprehensive description")

        if metadata_completeness >= 80:
            strengths.append("Complete metadata")

        if getattr(asset, 'tags', None) and len(asset.tags) > 0:
            strengths.append("Good use of tags")

        if len(asset.title) >= 10:
            strengths.append("Descriptive title")

        return strengths[:5]  # Limit to top 5 strengths

    def _calculate_readability(self, text: str) -> float:
        """
        Calculate readability score (simplified Flesch reading ease).

        Args:
            text: Text to analyze

        Returns:
            Readability score (0-100, higher is better)
        """
        if not text or len(text) < 10:
            return 30

        # Count sentences (approximation)
        sentences = len(re.split(r'[.!?]+', text))
        if sentences == 0:
            sentences = 1

        # Count words
        words = len(text.split())
        if words == 0:
            return 30

        # Count syllables (very rough approximation)
        syllables = sum(self._count_syllables(word) for word in text.split())

        # Simplified Flesch reading ease
        # Score = 206.835 - 1.015 * (words/sentences) - 84.6 * (syllables/words)
        try:
            score = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
            # Normalize to 0-100
            score = max(0, min(100, score))
        except:
            score = 50

        return score

    def _count_syllables(self, word: str) -> int:
        """
        Count syllables in a word (rough approximation).

        Args:
            word: Word to count syllables in

        Returns:
            Syllable count
        """
        word = word.lower()
        vowels = 'aeiouy'
        syllable_count = 0
        previous_was_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel

        # Adjust for silent 'e'
        if word.endswith('e'):
            syllable_count -= 1

        # Ensure at least 1 syllable
        return max(1, syllable_count)

    def _calculate_seo_score(self, asset: IPAsset) -> float:
        """
        Calculate SEO optimization score.

        Args:
            asset: The asset

        Returns:
            SEO score (0-100)
        """
        score = 50  # Base score

        # Title length
        title_len = len(asset.title)
        if 10 <= title_len <= 60:
            score += 15
        elif title_len >= 5:
            score += 5

        # Description length
        desc_len = len(asset.description or '')
        if desc_len >= 150:
            score += 15
        elif desc_len >= 50:
            score += 10

        # Has keywords/tags
        if getattr(asset, 'tags', None) and len(asset.tags) > 0:
            score += 10

        # Title and description have good variation (not repetitive)
        if asset.description and asset.title.lower() not in asset.description.lower():
            score += 10

        return min(score, 100)

    def _calculate_confidence(
        self,
        asset: IPAsset,
        technical_quality: Dict[str, Any]
    ) -> float:
        """
        Calculate confidence score for the analysis.

        Args:
            asset: The asset
            technical_quality: Technical quality metrics

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.5  # Base confidence

        # More confidence if we analyzed image
        if technical_quality.get('analysis_performed', False):
            confidence += 0.3

        # More confidence if we have good text data
        if asset.description and len(asset.description) >= 50:
            confidence += 0.2

        return min(confidence, 1.0)

    def _load_image(self, image_url: str) -> Optional[Image.Image]:
        """
        Load an image from URL or file path.

        Args:
            image_url: URL or path to image

        Returns:
            PIL Image or None if failed
        """
        try:
            if image_url.startswith('http'):
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content))
            else:
                with default_storage.open(image_url, 'rb') as f:
                    image = Image.open(f)
                    image.load()

            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            return image

        except Exception as e:
            logger.warning(f"Error loading image {image_url}: {e}")
            return None
