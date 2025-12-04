"""
Django admin configuration for assets app.
"""
from django.contrib import admin
from .models import IPAsset, RoyaltyPayment, AIGenerationLog, AIAssetMetadata, AIUsageStats, Collection, Favorite


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


@admin.register(AIGenerationLog)
class AIGenerationLogAdmin(admin.ModelAdmin):
    """Admin interface for AI Generation Logs."""
    list_display = ['id', 'user', 'operation_type', 'status', 'model_used', 'response_time_ms', 'cache_hit', 'created_at']
    list_filter = ['operation_type', 'status', 'model_used', 'model_tier', 'cache_hit', 'created_at']
    search_fields = ['user__wallet_address', 'user__display_name', 'model_used']
    readonly_fields = ['id', 'user', 'operation_type', 'input_data', 'output_data', 'model_used', 'model_tier', 'response_time_ms', 'tokens_used', 'status', 'error_message', 'cache_hit', 'created_at']
    ordering = ['-created_at']
    raw_id_fields = ['user']

    def has_add_permission(self, request):
        return False  # Logs are auto-created

    def has_change_permission(self, request, obj=None):
        return False  # Read-only


@admin.register(AIAssetMetadata)
class AIAssetMetadataAdmin(admin.ModelAdmin):
    """Admin interface for AI Asset Metadata."""
    list_display = ['id', 'asset', 'content_type', 'model_used', 'accepted', 'modified_by_user', 'user_rating', 'created_at']
    list_filter = ['content_type', 'accepted', 'modified_by_user', 'user_rating', 'created_at']
    search_fields = ['asset__title', 'model_used']
    readonly_fields = ['asset', 'content_type', 'original_content', 'ai_generated_content', 'model_used', 'generation_log', 'created_at', 'updated_at']
    ordering = ['-created_at']
    raw_id_fields = ['asset', 'generation_log']


@admin.register(AIUsageStats)
class AIUsageStatsAdmin(admin.ModelAdmin):
    """Admin interface for AI Usage Statistics."""
    list_display = ['date', 'total_requests', 'successful_requests', 'failed_requests', 'cache_hit_rate_display', 'unique_users', 'acceptance_rate']
    list_filter = ['date']
    readonly_fields = ['date', 'total_requests', 'title_requests', 'description_requests', 'analysis_requests', 'license_requests', 'derivative_requests', 'successful_requests', 'failed_requests', 'rate_limited_requests', 'cache_hits', 'cache_misses', 'total_tokens_used', 'estimated_cost_usd', 'avg_response_time_ms', 'unique_users', 'acceptance_rate', 'created_at', 'updated_at']
    ordering = ['-date']

    def cache_hit_rate_display(self, obj):
        """Display cache hit rate as percentage."""
        return f"{obj.cache_hit_rate:.2f}%"
    cache_hit_rate_display.short_description = 'Cache Hit Rate'

    def has_add_permission(self, request):
        return False  # Stats are auto-generated

    def has_change_permission(self, request, obj=None):
        return False  # Read-only


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    """Admin interface for Collections."""
    list_display = ['id', 'title', 'creator', 'asset_count', 'is_public', 'created_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['title', 'description', 'creator__wallet_address']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['creator']
    filter_horizontal = ['assets']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Admin interface for Favorites."""
    list_display = ['id', 'user', 'asset', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__wallet_address', 'user__display_name', 'asset__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'asset']
