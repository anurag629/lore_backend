from django.contrib import admin
from .models import AIGenerationLog, AIAssetMetadata, AIUsageStats


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
