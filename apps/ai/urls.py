"""
URL routing for AI API endpoints.
"""
from django.urls import path
from .views import (
    generate_title,
    enhance_description,
    analyze_content,
    suggest_license,
    analyze_derivative,
    ai_usage_stats,
    ai_platform_stats,
    validate_asset_before_mint,
    run_copyright_check,
    run_quality_analysis,
    run_pricing_analysis,
)

app_name = 'ai'

urlpatterns = [
    # AI Generation endpoints
    path('generate-title/', generate_title, name='ai-generate-title'),
    path('enhance-description/', enhance_description, name='ai-enhance-description'),
    path('analyze-content/', analyze_content, name='ai-analyze-content'),
    path('suggest-license/', suggest_license, name='ai-suggest-license'),
    path('analyze-derivative/', analyze_derivative, name='ai-analyze-derivative'),

    # Analytics endpoints
    path('usage-stats/', ai_usage_stats, name='ai-usage-stats'),
    path('platform-stats/', ai_platform_stats, name='ai-platform-stats'),

    # Validation endpoints (AI Agents)
    path('validate/<uuid:asset_uuid>/', validate_asset_before_mint, name='ai-validate-asset'),
    path('copyright/<uuid:asset_uuid>/', run_copyright_check, name='ai-copyright-check'),
    path('quality/<uuid:asset_uuid>/', run_quality_analysis, name='ai-quality-analysis'),
    path('pricing/<uuid:asset_uuid>/', run_pricing_analysis, name='ai-pricing-analysis'),
]

