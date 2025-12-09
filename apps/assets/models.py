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
        help_text="URL to media file (IPFS via Pinata)"
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

    # Legacy single parent field - kept for backward compatibility
    # New derivatives should use parent_assets ManyToMany instead
    parent_asset = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='legacy_derivatives',
        help_text="[DEPRECATED] Legacy single parent - use parent_assets instead"
    )

    # Multi-parent support
    parent_assets = models.ManyToManyField(
        'self',
        through='DerivativeRelationship',
        through_fields=('child_asset', 'parent_asset'),
        symmetrical=False,
        related_name='derivatives',
        blank=True,
        help_text="Parent assets for multi-parent derivatives"
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

    # Idempotency and transaction tracking
    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Idempotency key for preventing duplicate blockchain transactions"
    )
    transaction_nonce = models.IntegerField(
        null=True,
        blank=True,
        help_text="Blockchain transaction nonce for replay protection"
    )
    transaction_hash = models.CharField(
        max_length=66,
        null=True,
        blank=True,
        db_index=True,
        help_text="Primary blockchain transaction hash for this asset"
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
            models.Index(fields=['idempotency_key']),
            models.Index(fields=['transaction_hash']),
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


class GroupIP(models.Model):
    """
    Represents a Group IP on Story Protocol.
    Allows multiple IP assets to be pooled together for collective royalty distribution.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    story_group_id = models.CharField(
        max_length=66,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text="Story Protocol Group IP ID (on-chain)"
    )

    name = models.CharField(
        max_length=255,
        help_text="Group name"
    )

    description = models.TextField(
        help_text="Group description"
    )

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_groups',
        help_text="User who created this group"
    )

    royalty_pool_address = models.CharField(
        max_length=42,
        blank=True,
        null=True,
        help_text="On-chain address of royalty pool contract"
    )

    total_royalty_percentage = models.IntegerField(
        default=10,
        help_text="Total royalty percentage for the group (0-100)"
    )

    # Registration tracking
    registration_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Registration'),
            ('registered', 'Registered'),
            ('failed', 'Registration Failed'),
        ],
        default='pending',
        db_index=True,
        help_text="Status of Story Protocol registration"
    )

    registration_transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Transaction hash of group registration"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the group is active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Group IP"
        verbose_name_plural = "Group IPs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['creator', '-created_at']),
            models.Index(fields=['registration_status', '-created_at']),
            models.Index(fields=['is_active', '-created_at']),
        ]

    def __str__(self):
        return f"Group: {self.name}"

    @property
    def member_count(self):
        """Count of member IPs in this group"""
        return self.members.filter(is_active=True).count()

    @property
    def total_revenue_share(self):
        """Total revenue share percentage allocated"""
        from django.db.models import Sum
        result = self.members.filter(is_active=True).aggregate(
            total=Sum('revenue_share_percentage')
        )
        return result['total'] or 0


class GroupIPMembership(models.Model):
    """
    Represents membership of an IP asset in a Group IP.
    Tracks revenue share allocation for each member.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    group = models.ForeignKey(
        GroupIP,
        on_delete=models.CASCADE,
        related_name='members',
        help_text="Group this membership belongs to"
    )

    asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='group_memberships',
        help_text="IP asset that is a member"
    )

    revenue_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage of group revenue allocated to this member (0-100)"
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='group_additions',
        help_text="User who added this member to the group"
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this membership is active"
    )

    added_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this member was removed from the group"
    )

    transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Blockchain transaction hash for adding member"
    )

    class Meta:
        verbose_name = "Group IP Membership"
        verbose_name_plural = "Group IP Memberships"
        ordering = ['-added_at']
        unique_together = [['group', 'asset']]
        indexes = [
            models.Index(fields=['group', 'is_active']),
            models.Index(fields=['asset', 'is_active']),
        ]

    def __str__(self):
        return f"{self.asset.title} in {self.group.name} ({self.revenue_share_percentage}%)"


class GroupRoyaltyDistribution(models.Model):
    """
    Tracks royalty distributions from a Group IP to its members.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    group = models.ForeignKey(
        GroupIP,
        on_delete=models.CASCADE,
        related_name='distributions',
        help_text="Group from which royalties were distributed"
    )

    membership = models.ForeignKey(
        GroupIPMembership,
        on_delete=models.CASCADE,
        related_name='distributions',
        help_text="Member receiving the distribution"
    )

    amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        help_text="Amount distributed in ETH or token"
    )

    transaction_hash = models.CharField(
        max_length=66,
        unique=True,
        db_index=True,
        help_text="Blockchain transaction hash"
    )

    block_number = models.IntegerField(
        help_text="Block number where distribution occurred"
    )

    distributed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Group Royalty Distribution"
        verbose_name_plural = "Group Royalty Distributions"
        ordering = ['-distributed_at']
        indexes = [
            models.Index(fields=['group', '-distributed_at']),
            models.Index(fields=['membership', '-distributed_at']),
        ]

    def __str__(self):
        return f"{self.amount} to {self.membership.asset.title} from {self.group.name}"


class Dispute(models.Model):
    """
    Represents a dispute raised against an IP asset on Story Protocol.
    Allows users to challenge IP assets for various reasons (copyright infringement, etc.).
    """
    # Dispute status choices
    STATUS_PENDING = 'pending'
    STATUS_UNDER_REVIEW = 'under_review'
    STATUS_RESOLVED = 'resolved'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Dispute result choices
    RESULT_UPHELD = 'upheld'
    RESULT_REJECTED = 'rejected'
    RESULT_SETTLED = 'settled'

    RESULT_CHOICES = [
        (RESULT_UPHELD, 'Upheld - Dispute valid'),
        (RESULT_REJECTED, 'Rejected - Dispute invalid'),
        (RESULT_SETTLED, 'Settled - Parties agreed'),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    story_dispute_id = models.CharField(
        max_length=66,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Story Protocol Dispute ID (on-chain)"
    )

    target_asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='disputes_against',
        help_text="IP asset being disputed"
    )

    disputer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='disputes_raised',
        help_text="User who raised the dispute"
    )

    reason = models.TextField(
        help_text="Reason for the dispute"
    )

    evidence_ipfs_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="IPFS hash of initial evidence"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Current status of the dispute"
    )

    result = models.CharField(
        max_length=20,
        choices=RESULT_CHOICES,
        null=True,
        blank=True,
        help_text="Final result of the dispute"
    )

    resolution_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes from the dispute resolution"
    )

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='disputes_resolved',
        help_text="User/admin who resolved the dispute"
    )

    raise_transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Transaction hash when dispute was raised"
    )

    resolve_transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Transaction hash when dispute was resolved"
    )

    raised_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the dispute was resolved"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dispute"
        verbose_name_plural = "Disputes"
        ordering = ['-raised_at']
        indexes = [
            models.Index(fields=['target_asset', '-raised_at']),
            models.Index(fields=['disputer', '-raised_at']),
            models.Index(fields=['status', '-raised_at']),
            models.Index(fields=['result']),
        ]

    def __str__(self):
        return f"Dispute against {self.target_asset.title} by {self.disputer.display_name}"

    @property
    def is_resolved(self):
        """Check if dispute is resolved"""
        return self.status in [self.STATUS_RESOLVED, self.STATUS_CANCELLED]

    @property
    def evidence_count(self):
        """Count of evidence submissions"""
        return self.evidence.count()


class DisputeEvidence(models.Model):
    """
    Evidence submitted for a dispute.
    Both disputer and asset owner can submit evidence.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    dispute = models.ForeignKey(
        Dispute,
        on_delete=models.CASCADE,
        related_name='evidence',
        help_text="Dispute this evidence is for"
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dispute_evidence_submitted',
        help_text="User who submitted this evidence"
    )

    description = models.TextField(
        help_text="Description of the evidence"
    )

    evidence_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL to evidence file (IPFS or external)"
    )

    evidence_ipfs_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="IPFS hash of evidence file"
    )

    transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Blockchain transaction hash"
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dispute Evidence"
        verbose_name_plural = "Dispute Evidence"
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['dispute', '-submitted_at']),
            models.Index(fields=['submitted_by', '-submitted_at']),
        ]

    def __str__(self):
        return f"Evidence for {self.dispute} by {self.submitted_by.display_name}"


class DerivativeRelationship(models.Model):
    """
    Through model for multi-parent derivative relationships.
    Tracks attribution percentages and license terms for each parent.
    """
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Public UUID for API access"
    )

    child_asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='parent_relationships',
        help_text="Derivative asset (child)"
    )

    parent_asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='child_relationships',
        help_text="Parent asset being derived from"
    )

    attribution_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        help_text="Attribution percentage for this parent (0-100). Must sum to 100 across all parents."
    )

    license_terms_id = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Story Protocol license terms ID used for this relationship"
    )

    transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        null=True,
        help_text="Blockchain transaction hash for this relationship"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Derivative Relationship"
        verbose_name_plural = "Derivative Relationships"
        ordering = ['-created_at']
        unique_together = [['child_asset', 'parent_asset']]
        indexes = [
            models.Index(fields=['child_asset', '-created_at']),
            models.Index(fields=['parent_asset', '-created_at']),
        ]

    def __str__(self):
        return f"{self.child_asset.title} derived from {self.parent_asset.title} ({self.attribution_percentage}%)"

    def clean(self):
        """Validate attribution percentage."""
        from django.core.exceptions import ValidationError
        if not 0 <= self.attribution_percentage <= 100:
            raise ValidationError("Attribution percentage must be between 0 and 100")


# ===== IP Account Permissions =====

class IPAccountPermission(models.Model):
    """
    IP Account Permissions - Control access to IP asset operations.

    Represents permissions granted to addresses for performing actions on IP assets.
    Based on Story Protocol's IPAccount permission system.
    """

    PERMISSION_TYPES = [
        ('execute', 'Execute Transactions'),
        ('transfer_erc20', 'Transfer ERC20 Tokens'),
        ('set_metadata', 'Set Metadata'),
        ('attach_license', 'Attach License Terms'),
        ('register_derivative', 'Register Derivatives'),
        ('collect_royalty', 'Collect Royalties'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    asset = models.ForeignKey(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='permissions',
        help_text="IP asset this permission applies to"
    )
    grantee_address = models.CharField(
        max_length=42,
        help_text="Wallet address of the grantee (lowercase)"
    )
    permission_type = models.CharField(
        max_length=20,
        choices=PERMISSION_TYPES,
        help_text="Type of permission granted"
    )
    is_granted = models.BooleanField(
        default=True,
        help_text="Whether permission is currently granted (True) or revoked (False)"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this permission expires (null = no expiration)"
    )

    # Blockchain tracking
    transaction_hash = models.CharField(
        max_length=66,
        blank=True,
        help_text="Transaction hash from blockchain"
    )
    block_number = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Block number where permission was set"
    )

    # Metadata
    notes = models.TextField(
        blank=True,
        help_text="Internal notes about this permission"
    )
    granted_by = models.ForeignKey(
        'core.LoreUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='permissions_granted',
        help_text="User who granted this permission"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assets_ipaccountpermission'
        verbose_name = 'IP Account Permission'
        verbose_name_plural = 'IP Account Permissions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['asset', 'grantee_address'], name='assets_ipac_asset_g_idx'),
            models.Index(fields=['asset', 'permission_type'], name='assets_ipac_asset_p_idx'),
            models.Index(fields=['grantee_address', '-created_at'], name='assets_ipac_grantee_idx'),
            models.Index(fields=['is_granted', '-created_at'], name='assets_ipac_granted_idx'),
            models.Index(fields=['expires_at'], name='assets_ipac_expires_idx'),
        ]
        unique_together = [('asset', 'grantee_address', 'permission_type')]

    def __str__(self):
        status = "granted" if self.is_granted else "revoked"
        return f"{self.get_permission_type_display()} for {self.asset.title} to {self.grantee_address[:10]}... ({status})"

    @property
    def is_active(self):
        """Check if permission is currently active (granted and not expired)."""
        if not self.is_granted:
            return False

        if self.expires_at:
            from django.utils import timezone
            return timezone.now() < self.expires_at

        return True

    @property
    def is_expired(self):
        """Check if permission has expired."""
        if not self.expires_at:
            return False

        from django.utils import timezone
        return timezone.now() >= self.expires_at

    def clean(self):
        """Validate permission data."""
        from django.core.exceptions import ValidationError
        from apps.core.utils import normalize_wallet_address

        # Normalize wallet address
        if self.grantee_address:
            try:
                self.grantee_address = normalize_wallet_address(self.grantee_address)
            except Exception as e:
                raise ValidationError(f"Invalid grantee address: {e}")

        # Validate expiration is in the future
        if self.expires_at:
            from django.utils import timezone
            if self.expires_at <= timezone.now():
                raise ValidationError("Expiration time must be in the future")


