import uuid
from django.db import models
from django.conf import settings


class IPAsset(models.Model):
    """
    Represents an intellectual property asset registered on Story Protocol.
    Can be original content or a derivative (remix/spin-off).
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

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

    # Creation step tracking for retry functionality
    CREATION_STEPS = [
        ('media_upload', 'Media Upload to IPFS'),
        ('db_save', 'Database Save'),
        ('metadata_upload', 'Metadata Upload to IPFS'),
        ('story_registration', 'Story Protocol Registration'),
        ('license_attachment', 'License Terms Attachment'),
        ('completed', 'Completed'),
    ]
    
    creation_step = models.CharField(
        max_length=30,
        choices=CREATION_STEPS,
        default='media_upload',
        db_index=True,
        help_text="Current step in the creation process"
    )
    
    failed_at_step = models.CharField(
        max_length=30,
        choices=CREATION_STEPS,
        null=True,
        blank=True,
        db_index=True,
        help_text="Step where creation failed (if any)"
    )
    
    media_ipfs_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="IPFS hash of the media file (for retry purposes)"
    )
    
    step_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores intermediate results from each creation step (IPFS URLs, hashes, etc.)"
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

    # Story Protocol registration tracking
    registration_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Registration'),
            ('registered', 'Registered'),
            ('failed', 'Registration Failed'),
            ('retrying', 'Retrying Registration'),
        ],
        default='pending',
        db_index=True,
        help_text="Status of Story Protocol registration"
    )
    registration_error = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if registration failed"
    )
    registration_attempts = models.IntegerField(
        default=0,
        help_text="Number of registration attempts"
    )
    last_registration_attempt = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last registration attempt"
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
            models.Index(fields=['registration_status', '-created_at']),
            models.Index(fields=['creation_step', 'registration_status']),
            models.Index(fields=['failed_at_step']),
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
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

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


