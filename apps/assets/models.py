from django.db import models
from django.conf import settings


class IPAsset(models.Model):
    """
    Represents an intellectual property asset registered on Story Protocol.
    Can be original content or a derivative (remix/spin-off).
    """
    story_ip_id = models.CharField(
        max_length=66,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text="Story Protocol IP Asset ID (on-chain)"
    )

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assets',
        help_text="User who created this asset"
    )

    title = models.CharField(
        max_length=255,
        help_text="Asset title"
    )

    description = models.TextField(
        help_text="Asset description/lore"
    )

    media_url = models.URLField(
        help_text="URL to media file (Azure Blob Storage)"
    )

    metadata_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="IPFS hash of metadata JSON"
    )

    is_derivative = models.BooleanField(
        default=False,
        help_text="Whether this asset is a derivative/remix"
    )

    parent_asset = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derivatives',
        help_text="Parent asset if this is a derivative"
    )

    royalty_percentage = models.IntegerField(
        default=50,
        help_text="Royalty percentage for derivatives (0-100)"
    )

    allow_derivatives = models.BooleanField(
        default=True,
        help_text="Allow others to create derivatives"
    )

    commercial_rights = models.BooleanField(
        default=False,
        help_text="Allow commercial use"
    )

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when asset was deleted"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "IP Asset"
        verbose_name_plural = "IP Assets"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_deleted', '-created_at']),
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['is_derivative', '-created_at']),
            models.Index(fields=['allow_derivatives', '-created_at']),
            models.Index(fields=['commercial_rights', '-created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['story_ip_id']),
        ]

    def __str__(self):
        return f"{self.title} by {self.creator.display_name}"

    @property
    def derivative_count(self):
        """Count of spin-offs/derivatives"""
        # Use cached count if available
        if hasattr(self, '_derivative_count_cache'):
            return self._derivative_count_cache
        # Query with filter for deleted assets
        count = self.derivatives.filter(is_deleted=False).count()
        # Cache for this instance
        self._derivative_count_cache = count
        return count


class RoyaltyPayment(models.Model):
    """
    Tracks royalty payments from the blockchain.
    Indexed by Celery workers listening to Story Protocol events.
    """
    asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='royalty_payments',
        help_text="Asset that generated this royalty"
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='royalty_received',
        help_text="User receiving the royalty"
    )

    amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        help_text="Royalty amount in ETH"
    )

    transaction_hash = models.CharField(
        max_length=66,
        unique=True,
        help_text="Blockchain transaction hash"
    )

    block_number = models.IntegerField(
        help_text="Block number where payment occurred"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Royalty Payment"
        verbose_name_plural = "Royalty Payments"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.amount} ETH to {self.recipient.display_name}"


# ===== AI-Related Models =====

class AIGenerationLog(models.Model):
    """
    Audit trail for all AI generation requests.
    Tracks what was requested, what was generated, and performance metrics.
    """
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
    CONTENT_TYPE_CHOICES = [
        ('title', 'Title'),
        ('description', 'Description'),
        ('tags', 'Tags/Categories'),
        ('license', 'License Terms'),
    ]

    # Asset relationship
    asset = models.ForeignKey(
        IPAsset,
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


class Collection(models.Model):
    """
    A curated collection of IP assets created by users.
    Users can organize their favorite assets into collections.
    """
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='collections',
        help_text="User who created this collection"
    )

    title = models.CharField(
        max_length=255,
        help_text="Collection title"
    )

    description = models.TextField(
        blank=True,
        help_text="Collection description"
    )

    cover_image_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL to collection cover image"
    )

    is_public = models.BooleanField(
        default=True,
        help_text="Whether collection is publicly visible"
    )

    assets = models.ManyToManyField(
        'IPAsset',
        related_name='collections',
        blank=True,
        help_text="IP assets in this collection"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['is_public', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} by {self.creator.display_name}"

    @property
    def asset_count(self):
        """Get number of assets in collection."""
        return self.assets.filter(is_deleted=False).count()


class Favorite(models.Model):
    """
    User favorites/bookmarks for IP assets.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
        help_text="User who favorited the asset"
    )

    asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='favorites',
        help_text="Asset that was favorited"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"
        ordering = ['-created_at']
        unique_together = [['user', 'asset']]  # Prevent duplicate favorites
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['asset', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.display_name} favorited {self.asset.title}"
