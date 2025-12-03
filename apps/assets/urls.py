"""
URL routing for IP Asset API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    IPAssetViewSet,
    RoyaltyPaymentViewSet,
    # AI endpoints
    generate_title,
    enhance_description,
    analyze_content,
    suggest_license,
    analyze_derivative,
    # Analytics endpoints
    ai_usage_stats,
    ai_platform_stats,
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'assets', IPAssetViewSet, basename='asset')
router.register(r'royalties', RoyaltyPaymentViewSet, basename='royalty')

# AI endpoints
ai_urlpatterns = [
    path('generate-title/', generate_title, name='ai-generate-title'),
    path('enhance-description/', enhance_description, name='ai-enhance-description'),
    path('analyze-content/', analyze_content, name='ai-analyze-content'),
    path('suggest-license/', suggest_license, name='ai-suggest-license'),
    path('analyze-derivative/', analyze_derivative, name='ai-analyze-derivative'),
    # Analytics
    path('usage-stats/', ai_usage_stats, name='ai-usage-stats'),
    path('platform-stats/', ai_platform_stats, name='ai-platform-stats'),  # Admin only
]

urlpatterns = [
    path('', include(router.urls)),
    path('ai/', include(ai_urlpatterns)),
]

# Available endpoints:
# GET    /api/assets/                    - List all IP assets
# POST   /api/assets/                    - Create new IP asset
# GET    /api/assets/{id}/               - Get IP asset details
# PUT    /api/assets/{id}/               - Update IP asset
# DELETE /api/assets/{id}/               - Delete IP asset
#
# POST   /api/assets/create_derivative/  - Create derivative of an asset
# GET    /api/assets/{id}/derivatives/   - Get derivatives of an asset
# POST   /api/assets/{id}/claim_royalties/ - Claim royalties for an asset
# GET    /api/assets/{id}/royalty_balance/ - Get royalty balance
#
# GET    /api/royalties/                 - List royalty payments for current user
# GET    /api/royalties/{id}/            - Get royalty payment details
