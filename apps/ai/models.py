import uuid
from django.db import models
from django.conf import settings


class AIGenerationLog(models.Model):
    """
    Audit trail for all AI generation requests.
    Tracks what was requested, what was generated, and performance metrics.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    OPERATION_CHOICES = [
        ('title', 'Title Generation'),
        ('description', 'Description Enhancement'),
        ('analysis', 'Content Analysis'),
        ('license', 'License Suggestion'),
        ('derivative', 'Derivative Analysis'),
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('rate_limited', 'Rate Limited'),
    ]

    # Request metadata
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_requests',
        help_text="User who made the request"
    )

    operation_type = models.CharField(
        max_length=20,
        choices=OPERATION_CHOICES,
        db_index=True,
        help_text="Type of AI operation"
    )

    # Input/Output data (stored as JSON)
    input_data = models.JSONField(
        help_text="Input parameters passed to AI"
    )

    output_data = models.JSONField(
        null=True,
        blank=True,
        help_text="AI-generated output"
    )

    # AI model info
    model_used = models.CharField(
        max_length=100,
        help_text="LLM model that processed the request"
    )

    model_tier = models.CharField(
        max_length=20,
        default='fast',
        help_text="Model tier (fast/quality)"
    )

    # Performance metrics
    response_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Response time in milliseconds"
    )

    tokens_used = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total tokens consumed (if available)"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='success',
        db_index=True
    )

    error_message = models.TextField(
        blank=True,
        help_text="Error message if failed"
    )

    # Cache info
    cache_hit = models.BooleanField(
        default=False,
        help_text="Whether result was from cache"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "AI Generation Log"
        verbose_name_plural = "AI Generation Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['operation_type', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.operation_type} by {self.user.display_name} - {self.status}"


class AIAssetMetadata(models.Model):
    """
    Stores AI-generated metadata that was accepted and used for an asset.
    Links to IPAsset to track which AI-generated content was actually used.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    CONTENT_TYPE_CHOICES = [
        ('title', 'Title'),
        ('description', 'Description'),
        ('tags', 'Tags/Categories'),
        ('license', 'License Terms'),
    ]

    # Asset relationship
    asset = models.ForeignKey(
        'assets.IPAsset',
        on_delete=models.CASCADE,
        related_name='ai_metadata',
        help_text="Asset this metadata belongs to"
    )

    # Content type
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        help_text="Type of AI-generated content"
    )

    # Original vs AI-generated
    original_content = models.TextField(
        blank=True,
        help_text="User's original input (if any)"
    )

    ai_generated_content = models.TextField(
        help_text="AI-generated content"
    )

    # AI model info
    model_used = models.CharField(
        max_length=100,
        help_text="LLM model that generated this"
    )

    generation_log = models.ForeignKey(
        AIGenerationLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_content',
        help_text="Link to generation log"
    )

    # User feedback
    accepted = models.BooleanField(
        default=True,
        help_text="Whether user accepted this suggestion"
    )

    modified_by_user = models.BooleanField(
        default=False,
        help_text="Whether user edited AI-generated content"
    )

    final_content = models.TextField(
        blank=True,
        help_text="Final content after user modifications (if any)"
    )

    # Quality tracking
    user_rating = models.IntegerField(
        null=True,
        blank=True,
        help_text="User rating of AI output (1-5 stars)"
    )

    feedback_text = models.TextField(
        blank=True,
        help_text="User feedback on AI output quality"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Asset Metadata"
        verbose_name_plural = "AI Asset Metadata"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['asset', 'content_type']),
            models.Index(fields=['accepted', '-created_at']),
        ]

    def __str__(self):
        return f"{self.content_type} for {self.asset.title}"


class AIUsageStats(models.Model):
    """
    Daily aggregated statistics for AI usage.
    Updated via Celery periodic task for analytics dashboard.
    """
    # Date
    date = models.DateField(
        unique=True,
        db_index=True,
        help_text="Date of statistics"
    )

    # Request counts by operation
    total_requests = models.IntegerField(default=0)
    title_requests = models.IntegerField(default=0)
    description_requests = models.IntegerField(default=0)
    analysis_requests = models.IntegerField(default=0)
    license_requests = models.IntegerField(default=0)
    derivative_requests = models.IntegerField(default=0)

    # Success/failure counts
    successful_requests = models.IntegerField(default=0)
    failed_requests = models.IntegerField(default=0)
    rate_limited_requests = models.IntegerField(default=0)

    # Cache performance
    cache_hits = models.IntegerField(default=0)
    cache_misses = models.IntegerField(default=0)

    # Cost tracking
    total_tokens_used = models.IntegerField(default=0)
    estimated_cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="Estimated API cost in USD"
    )

    # Performance metrics
    avg_response_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Average response time"
    )

    # User engagement
    unique_users = models.IntegerField(
        default=0,
        help_text="Unique users who used AI features"
    )

    acceptance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percentage of AI content accepted by users"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Usage Statistics"
        verbose_name_plural = "AI Usage Statistics"
        ordering = ['-date']

    def __str__(self):
        return f"AI Stats for {self.date}"

    @property
    def cache_hit_rate(self):
        """Calculate cache hit rate percentage"""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0
        return (self.cache_hits / total) * 100


# ====================  AI AGENT ANALYSIS RESULTS  ====================

class CopyrightAnalysisResult(models.Model):
    """
    Stores copyright/plagiarism detection results.

    Used to identify potential copyright issues before minting.
    """
    asset = models.OneToOneField(
        'assets.IPAsset',
        on_delete=models.CASCADE,
        related_name='copyright_analysis',
        help_text="Asset being analyzed"
    )

    is_likely_original = models.BooleanField(
        default=True,
        help_text="Whether the asset appears to be original content"
    )

    similarity_score = models.FloatField(
        default=0.0,
        help_text="Overall similarity score (0.0-1.0)"
    )

    risk_level = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low Risk'),
            ('medium', 'Medium Risk'),
            ('high', 'High Risk'),
        ],
        default='low',
        help_text="Copyright risk assessment"
    )

    potential_matches = models.JSONField(
        default=list,
        help_text="List of potential matching assets"
    )

    recommendations = models.JSONField(
        default=list,
        help_text="Actionable recommendations for the creator"
    )

    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence in the analysis (0.0-1.0)"
    )

    processing_time = models.FloatField(
        default=0.0,
        help_text="Time taken for analysis in seconds"
    )

    analyzed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was performed"
    )

    class Meta:
        verbose_name = "Copyright Analysis Result"
        verbose_name_plural = "Copyright Analysis Results"
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Copyright Analysis: {self.asset.title} ({self.risk_level})"


class QualityAnalysisResult(models.Model):
    """
    Stores quality scoring results.

    Analyzes technical quality, description quality, and market appeal.
    """
    asset = models.OneToOneField(
        'assets.IPAsset',
        on_delete=models.CASCADE,
        related_name='quality_analysis',
        help_text="Asset being analyzed"
    )

    overall_score = models.FloatField(
        help_text="Overall quality score (0-100)"
    )

    technical_quality = models.JSONField(
        help_text="Technical quality metrics (resolution, sharpness, etc.)"
    )

    description_quality = models.JSONField(
        help_text="Description quality metrics (length, clarity, SEO)"
    )

    metadata_completeness = models.FloatField(
        help_text="Completeness of metadata (0-100)"
    )

    market_appeal = models.FloatField(
        help_text="Predicted market appeal (0-100)"
    )

    improvement_suggestions = models.JSONField(
        default=list,
        help_text="Suggestions for improving quality"
    )

    strengths = models.JSONField(
        default=list,
        help_text="Identified strengths of the asset"
    )

    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence in the analysis (0.0-1.0)"
    )

    processing_time = models.FloatField(
        default=0.0,
        help_text="Time taken for analysis in seconds"
    )

    analyzed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was performed"
    )

    class Meta:
        verbose_name = "Quality Analysis Result"
        verbose_name_plural = "Quality Analysis Results"
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Quality Analysis: {self.asset.title} (score: {self.overall_score:.1f})"


class PricingAnalysisResult(models.Model):
    """
    Stores smart pricing recommendations.

    Suggests royalty percentages based on market analysis.
    """
    asset = models.OneToOneField(
        'assets.IPAsset',
        on_delete=models.CASCADE,
        related_name='pricing_analysis',
        help_text="Asset being analyzed"
    )

    suggested_tiers = models.JSONField(
        help_text="Three pricing tiers (conservative, balanced, aggressive)"
    )

    market_average = models.FloatField(
        help_text="Market average royalty percentage"
    )

    similar_assets_count = models.IntegerField(
        default=0,
        help_text="Number of similar assets analyzed"
    )

    demand_prediction = models.FloatField(
        help_text="Predicted demand score (0-100)"
    )

    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence in the recommendations (0.0-1.0)"
    )

    reasoning = models.TextField(
        help_text="Explanation of pricing recommendations"
    )

    processing_time = models.FloatField(
        default=0.0,
        help_text="Time taken for analysis in seconds"
    )

    analyzed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was performed"
    )

    class Meta:
        verbose_name = "Pricing Analysis Result"
        verbose_name_plural = "Pricing Analysis Results"
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Pricing Analysis: {self.asset.title}"


class ValidationWorkflowResult(models.Model):
    """
    Stores results from multi-agent pre-mint validation workflow.

    Combines results from multiple agents for comprehensive validation.
    """
    asset = models.OneToOneField(
        'assets.IPAsset',
        on_delete=models.CASCADE,
        related_name='validation_result',
        help_text="Asset being validated"
    )

    workflow_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending',
        help_text="Overall workflow status"
    )

    steps_completed = models.JSONField(
        default=list,
        help_text="List of completed validation steps"
    )

    overall_verdict = models.CharField(
        max_length=20,
        choices=[
            ('approved', 'Approved'),
            ('warning', 'Approved with Warnings'),
            ('rejected', 'Rejected'),
        ],
        null=True,
        blank=True,
        help_text="Final recommendation"
    )

    agent_results = models.JSONField(
        default=dict,
        help_text="Results from each agent"
    )

    warnings = models.JSONField(
        default=list,
        help_text="Warnings raised during validation"
    )

    blockers = models.JSONField(
        default=list,
        help_text="Issues that should block minting"
    )

    total_processing_time = models.FloatField(
        default=0.0,
        help_text="Total time for all agents"
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When validation started"
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When validation completed"
    )

    class Meta:
        verbose_name = "Validation Workflow Result"
        verbose_name_plural = "Validation Workflow Results"
        ordering = ['-started_at']

    def __str__(self):
        return f"Validation: {self.asset.title} ({self.workflow_status})"

