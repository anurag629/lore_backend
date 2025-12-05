"""
Django admin configuration for assets app.
"""
from django.contrib import admin
from .models import IPAsset, RoyaltyPayment


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
