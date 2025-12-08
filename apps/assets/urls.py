"""
URL routing for IP Asset API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IPAssetViewSet, RoyaltyPaymentViewSet
from .views.group_ip import GroupIPViewSet
from .views.dispute import DisputeViewSet
from .views.permissions import PermissionViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'assets', IPAssetViewSet, basename='asset')
router.register(r'royalties', RoyaltyPaymentViewSet, basename='royalty')
router.register(r'groups', GroupIPViewSet, basename='group')
router.register(r'disputes', DisputeViewSet, basename='dispute')
router.register(r'permissions', PermissionViewSet, basename='permission')

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
# POST   /api/assets/create_derivative/  - Create derivative of an asset (single parent)
# POST   /api/assets/create_multi_parent_derivative/ - Create derivative with multiple parents (1-10)
# GET    /api/assets/{id}/derivatives/   - Get derivatives of an asset
# POST   /api/assets/{id}/claim_royalties/ - Claim royalties for an asset
# GET    /api/assets/{id}/royalty_balance/ - Get royalty balance
#
# GET    /api/royalties/                 - List royalty payments for current user
# GET    /api/royalties/{id}/            - Get royalty payment details
#
# Group IP endpoints:
# GET    /api/groups/                    - List all groups
# POST   /api/groups/                    - Create new group
# GET    /api/groups/{id}/               - Get group details
# PUT    /api/groups/{id}/               - Update group
# DELETE /api/groups/{id}/               - Deactivate group
# POST   /api/groups/{id}/register/      - Register group on-chain
# POST   /api/groups/{id}/add_member/    - Add member to group
# POST   /api/groups/{id}/remove_member/ - Remove member from group
# GET    /api/groups/{id}/statistics/    - Get group statistics
# GET    /api/groups/{id}/distributions/ - Get group distributions
#
# Dispute endpoints:
# GET    /api/disputes/                  - List all disputes
# POST   /api/disputes/raise_dispute/    - Raise a new dispute
# GET    /api/disputes/{id}/             - Get dispute details
# POST   /api/disputes/{id}/submit_evidence/ - Submit evidence
# POST   /api/disputes/{id}/resolve/     - Resolve dispute (admin)
# POST   /api/disputes/{id}/cancel/      - Cancel dispute (disputer)
# GET    /api/disputes/{id}/evidence/    - Get dispute evidence
# GET    /api/disputes/statistics/       - Get dispute statistics
#
# Permission endpoints:
# GET    /api/permissions/               - List permissions for user's assets
# GET    /api/permissions/{id}/          - Get permission details
# POST   /api/permissions/set_permission/ - Set a single permission
# POST   /api/permissions/set_all_permissions/ - Set all permissions
# POST   /api/permissions/revoke_permission/ - Revoke a permission
# POST   /api/permissions/revoke_all_permissions/ - Revoke all permissions
# GET    /api/permissions/for_asset/     - Get permissions for an asset
# GET    /api/permissions/check_permission/ - Check if address has permission
# GET    /api/permissions/permission_summary/ - Get permission summary
