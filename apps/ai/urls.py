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
)

app_name = 'ai'

urlpatterns = [
    path('generate-title/', generate_title, name='ai-generate-title'),
    path('enhance-description/', enhance_description, name='ai-enhance-description'),
    path('analyze-content/', analyze_content, name='ai-analyze-content'),
    path('suggest-license/', suggest_license, name='ai-suggest-license'),
    path('analyze-derivative/', analyze_derivative, name='ai-analyze-derivative'),
    path('usage-stats/', ai_usage_stats, name='ai-usage-stats'),
    path('platform-stats/', ai_platform_stats, name='ai-platform-stats'),
]

