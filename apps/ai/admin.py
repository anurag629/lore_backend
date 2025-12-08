from django.contrib import admin
from .models import (
    AIGenerationLog, AIAssetMetadata, AIUsageStats,
    CopyrightAnalysisResult, QualityAnalysisResult,
    PricingAnalysisResult, ValidationWorkflowResult
)


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


# ====================  AI AGENT RESULT ADMINS  ====================

@admin.register(CopyrightAnalysisResult)
class CopyrightAnalysisResultAdmin(admin.ModelAdmin):
    """Admin interface for Copyright Analysis Results."""
    list_display = ['id', 'asset', 'risk_level', 'similarity_score', 'is_likely_original', 'confidence', 'analyzed_at']
    list_filter = ['risk_level', 'is_likely_original', 'analyzed_at']
    search_fields = ['asset__title']
    readonly_fields = ['asset', 'is_likely_original', 'similarity_score', 'risk_level', 'potential_matches', 'recommendations', 'confidence', 'processing_time', 'analyzed_at']
    ordering = ['-analyzed_at']
    raw_id_fields = ['asset']

    def has_add_permission(self, request):
        return False  # Results are auto-generated


@admin.register(QualityAnalysisResult)
class QualityAnalysisResultAdmin(admin.ModelAdmin):
    """Admin interface for Quality Analysis Results."""
    list_display = ['id', 'asset', 'overall_score', 'market_appeal', 'metadata_completeness', 'confidence', 'analyzed_at']
    list_filter = ['analyzed_at']
    search_fields = ['asset__title']
    readonly_fields = ['asset', 'overall_score', 'technical_quality', 'description_quality', 'metadata_completeness', 'market_appeal', 'improvement_suggestions', 'strengths', 'confidence', 'processing_time', 'analyzed_at']
    ordering = ['-analyzed_at']
    raw_id_fields = ['asset']

    def has_add_permission(self, request):
        return False  # Results are auto-generated


@admin.register(PricingAnalysisResult)
class PricingAnalysisResultAdmin(admin.ModelAdmin):
    """Admin interface for Pricing Analysis Results."""
    list_display = ['id', 'asset', 'market_average', 'similar_assets_count', 'demand_prediction', 'confidence', 'analyzed_at']
    list_filter = ['analyzed_at']
    search_fields = ['asset__title']
    readonly_fields = ['asset', 'suggested_tiers', 'market_average', 'similar_assets_count', 'demand_prediction', 'confidence', 'reasoning', 'processing_time', 'analyzed_at']
    ordering = ['-analyzed_at']
    raw_id_fields = ['asset']

    def has_add_permission(self, request):
        return False  # Results are auto-generated


@admin.register(ValidationWorkflowResult)
class ValidationWorkflowResultAdmin(admin.ModelAdmin):
    """Admin interface for Validation Workflow Results."""
    list_display = ['id', 'asset', 'workflow_status', 'overall_verdict', 'total_processing_time', 'started_at', 'completed_at']
    list_filter = ['workflow_status', 'overall_verdict', 'started_at']
    search_fields = ['asset__title']
    readonly_fields = ['asset', 'workflow_status', 'steps_completed', 'overall_verdict', 'agent_results', 'warnings', 'blockers', 'total_processing_time', 'started_at', 'completed_at']
    ordering = ['-started_at']
    raw_id_fields = ['asset']

    def has_add_permission(self, request):
        return False  # Results are auto-generated
