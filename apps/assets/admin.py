"""
Django admin configuration for assets app.
"""
from django.contrib import admin
from .models import (
    IPAsset, RoyaltyPayment, GroupIP, GroupIPMembership, GroupRoyaltyDistribution,
    Dispute, DisputeEvidence, DerivativeRelationship, IPAccountPermission
)


@admin.register(IPAsset)
class IPAssetAdmin(admin.ModelAdmin):
    """Admin interface for IP Assets."""
    list_display = ['id', 'title', 'creator', 'is_derivative', 'allow_derivatives', 'created_at']
    list_filter = ['is_derivative', 'allow_derivatives', 'commercial_rights', 'created_at']
    search_fields = ['title', 'description', 'story_ip_id', 'creator__wallet_address']
    readonly_fields = ['story_ip_id', 'metadata_hash', 'created_at', 'updated_at']
    raw_id_fields = ['creator', 'parent_asset']


@admin.register(RoyaltyPayment)
class RoyaltyPaymentAdmin(admin.ModelAdmin):
    """Admin interface for Royalty Payments."""
    list_display = ['id', 'asset', 'recipient', 'amount', 'created_at']
    list_filter = ['created_at']
    search_fields = ['transaction_hash', 'recipient__wallet_address']
    readonly_fields = ['asset', 'recipient', 'amount', 'transaction_hash', 'block_number', 'created_at']
    raw_id_fields = ['asset', 'recipient']

    def has_add_permission(self, request):
        return False  # Payments are auto-created by blockchain listeners


@admin.register(GroupIP)
class GroupIPAdmin(admin.ModelAdmin):
    """Admin interface for Group IPs."""
    list_display = ['id', 'name', 'creator', 'member_count', 'registration_status', 'is_active', 'created_at']
    list_filter = ['registration_status', 'is_active', 'created_at']
    search_fields = ['name', 'description', 'story_group_id', 'creator__wallet_address']
    readonly_fields = ['story_group_id', 'registration_transaction_hash', 'royalty_pool_address', 'created_at', 'updated_at']
    raw_id_fields = ['creator']

    def member_count(self, obj):
        """Display member count"""
        return obj.member_count
    member_count.short_description = 'Members'


@admin.register(GroupIPMembership)
class GroupIPMembershipAdmin(admin.ModelAdmin):
    """Admin interface for Group IP Memberships."""
    list_display = ['id', 'group', 'asset', 'revenue_share_percentage', 'is_active', 'added_at']
    list_filter = ['is_active', 'added_at']
    search_fields = ['group__name', 'asset__title']
    readonly_fields = ['transaction_hash', 'added_at', 'removed_at']
    raw_id_fields = ['group', 'asset', 'added_by']


@admin.register(GroupRoyaltyDistribution)
class GroupRoyaltyDistributionAdmin(admin.ModelAdmin):
    """Admin interface for Group Royalty Distributions."""
    list_display = ['id', 'group', 'membership', 'amount', 'distributed_at']
    list_filter = ['distributed_at']
    search_fields = ['transaction_hash', 'group__name']
    readonly_fields = ['group', 'membership', 'amount', 'transaction_hash', 'block_number', 'distributed_at']
    raw_id_fields = ['group', 'membership']

    def has_add_permission(self, request):
        return False  # Distributions are auto-created by royalty distribution logic


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    """Admin interface for Disputes."""
    list_display = ['id', 'target_asset', 'disputer', 'status', 'result', 'evidence_count', 'raised_at']
    list_filter = ['status', 'result', 'raised_at']
    search_fields = ['story_dispute_id', 'target_asset__title', 'disputer__wallet_address', 'reason']
    readonly_fields = [
        'story_dispute_id', 'raise_transaction_hash', 'resolve_transaction_hash',
        'raised_at', 'resolved_at', 'updated_at'
    ]
    raw_id_fields = ['target_asset', 'disputer', 'resolved_by']

    fieldsets = (
        ('Dispute Information', {
            'fields': ('story_dispute_id', 'target_asset', 'disputer', 'reason', 'evidence_ipfs_hash')
        }),
        ('Status', {
            'fields': ('status', 'result', 'resolution_notes', 'resolved_by')
        }),
        ('Blockchain', {
            'fields': ('raise_transaction_hash', 'resolve_transaction_hash')
        }),
        ('Timestamps', {
            'fields': ('raised_at', 'resolved_at', 'updated_at')
        }),
    )

    def evidence_count(self, obj):
        """Display evidence count"""
        return obj.evidence_count
    evidence_count.short_description = 'Evidence'


@admin.register(DisputeEvidence)
class DisputeEvidenceAdmin(admin.ModelAdmin):
    """Admin interface for Dispute Evidence."""
    list_display = ['id', 'dispute', 'submitted_by', 'submitted_at']
    list_filter = ['submitted_at']
    search_fields = ['dispute__story_dispute_id', 'submitted_by__wallet_address', 'description']
    readonly_fields = ['transaction_hash', 'submitted_at']
    raw_id_fields = ['dispute', 'submitted_by']


@admin.register(DerivativeRelationship)
class DerivativeRelationshipAdmin(admin.ModelAdmin):
    """Admin interface for Derivative Relationships."""
    list_display = ['id', 'child_asset', 'parent_asset', 'attribution_percentage', 'created_at']
    list_filter = ['created_at']
    search_fields = ['child_asset__title', 'parent_asset__title']
    readonly_fields = ['transaction_hash', 'created_at']
    raw_id_fields = ['child_asset', 'parent_asset']

    fieldsets = (
        ('Relationship', {
            'fields': ('child_asset', 'parent_asset', 'attribution_percentage')
        }),
        ('License', {
            'fields': ('license_terms_id',)
        }),
        ('Blockchain', {
            'fields': ('transaction_hash',)
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )


@admin.register(IPAccountPermission)
class IPAccountPermissionAdmin(admin.ModelAdmin):
    """Admin interface for IP Account Permissions."""
    list_display = ['id', 'asset', 'grantee_address_short', 'permission_type', 'is_granted', 'is_active_status', 'expires_at', 'created_at']
    list_filter = ['permission_type', 'is_granted', 'created_at']
    search_fields = ['asset__title', 'grantee_address', 'notes']
    readonly_fields = ['transaction_hash', 'block_number', 'created_at', 'updated_at', 'is_active', 'is_expired']
    raw_id_fields = ['asset', 'granted_by']

    fieldsets = (
        ('Permission', {
            'fields': ('asset', 'grantee_address', 'permission_type', 'is_granted')
        }),
        ('Expiration', {
            'fields': ('expires_at', 'is_active', 'is_expired')
        }),
        ('Blockchain', {
            'fields': ('transaction_hash', 'block_number')
        }),
        ('Metadata', {
            'fields': ('notes', 'granted_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def grantee_address_short(self, obj):
        """Display shortened grantee address."""
        return f"{obj.grantee_address[:10]}..."
    grantee_address_short.short_description = 'Grantee'

    def is_active_status(self, obj):
        """Display active status with icon."""
        return "✓" if obj.is_active else "✗"
    is_active_status.short_description = 'Active'
    is_active_status.boolean = True
