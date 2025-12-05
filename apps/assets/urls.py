"""
URL routing for IP Asset API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IPAssetViewSet, RoyaltyPaymentViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'assets', IPAssetViewSet, basename='asset')
router.register(r'royalties', RoyaltyPaymentViewSet, basename='royalty')

urlpatterns = [
    path('', include(router.urls)),
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
