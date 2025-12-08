"""
Permission Views - API endpoints for IP Account Permissions
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
import logging

from apps.assets.models import IPAccountPermission, IPAsset
from apps.assets.serializers import (
    IPAccountPermissionSerializer,
    SetPermissionSerializer,
    SetAllPermissionsSerializer,
    PermissionSummarySerializer
)
from apps.assets.services.permission_service import get_permission_service
from apps.assets.services.story_service import get_story_service

logger = logging.getLogger(__name__)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for managing IP Account Permissions.

    Endpoints:
    - GET /api/permissions/ - List all permissions (for user's assets)
    - GET /api/permissions/{uuid}/ - Get permission details
    - POST /api/permissions/set_permission/ - Set a single permission
    - POST /api/permissions/set_all_permissions/ - Set all permissions
    - POST /api/permissions/revoke_permission/ - Revoke a permission
    - POST /api/permissions/revoke_all_permissions/ - Revoke all permissions
    - GET /api/permissions/for_asset/{asset_uuid}/ - Get permissions for an asset
    - GET /api/permissions/check_permission/ - Check if address has permission
    - GET /api/permissions/permission_summary/ - Get permission summary for address
    """

    queryset = IPAccountPermission.objects.all()
    serializer_class = IPAccountPermissionSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter permissions based on user's assets."""
        queryset = super().get_queryset()

        # Filter to permissions on user's assets
        queryset = queryset.filter(
            asset__creator=self.request.user
        ).select_related('asset', 'granted_by')

        # Filter by asset if specified
        asset_id = self.request.query_params.get('asset')
        if asset_id:
            queryset = queryset.filter(asset__uuid=asset_id)

        # Filter by grantee if specified
        grantee = self.request.query_params.get('grantee')
        if grantee:
            queryset = queryset.filter(grantee_address=grantee.lower())

        # Filter by permission type if specified
        permission_type = self.request.query_params.get('type')
        if permission_type:
            queryset = queryset.filter(permission_type=permission_type)

        # Filter active only if specified
        active_only = self.request.query_params.get('active_only')
        if active_only and active_only.lower() == 'true':
            from django.utils import timezone
            from django.db.models import Q
            queryset = queryset.filter(
                is_granted=True
            ).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
            )

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def set_permission(self, request):
        """
        Set a single permission for an asset.

        POST /api/permissions/set_permission/
        {
            "asset_id": "uuid",
            "grantee_address": "0x...",
            "permission_type": "execute|transfer_erc20|set_metadata|attach_license|register_derivative|collect_royalty",
            "is_granted": true,
            "expires_at": "2024-12-31T23:59:59Z",  // optional
            "notes": "..."  // optional
        }
        """
        # Get asset
        asset_id = request.data.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Check if user is the creator
        if asset.creator != request.user:
            return Response(
                {'error': 'Only the asset creator can manage permissions'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Validate input
        serializer = SetPermissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get services
        story_service = get_story_service()
        permission_service = get_permission_service(story_service=story_service)

        try:
            permission = permission_service.set_permission(
                asset=asset,
                grantee_address=serializer.validated_data['grantee_address'],
                permission_type=serializer.validated_data['permission_type'],
                is_granted=serializer.validated_data.get('is_granted', True),
                expires_at=serializer.validated_data.get('expires_at'),
                granted_by_user=request.user,
                notes=serializer.validated_data.get('notes', '')
            )

            output_serializer = IPAccountPermissionSerializer(permission)
            return Response({
                'message': f'Permission {permission.get_permission_type_display()} set successfully',
                'permission': output_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to set permission: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def set_all_permissions(self, request):
        """
        Set all permissions for an asset to the same state.

        POST /api/permissions/set_all_permissions/
        {
            "asset_id": "uuid",
            "grantee_address": "0x...",
            "is_granted": true,
            "expires_at": "2024-12-31T23:59:59Z",  // optional
            "notes": "..."  // optional
        }
        """
        # Get asset
        asset_id = request.data.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Check if user is the creator
        if asset.creator != request.user:
            return Response(
                {'error': 'Only the asset creator can manage permissions'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Validate input
        serializer = SetAllPermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get services
        story_service = get_story_service()
        permission_service = get_permission_service(story_service=story_service)

        try:
            permissions = permission_service.set_all_permissions(
                asset=asset,
                grantee_address=serializer.validated_data['grantee_address'],
                is_granted=serializer.validated_data.get('is_granted', True),
                expires_at=serializer.validated_data.get('expires_at'),
                granted_by_user=request.user,
                notes=serializer.validated_data.get('notes', '')
            )

            output_serializer = IPAccountPermissionSerializer(permissions, many=True)
            action_word = "granted" if serializer.validated_data.get('is_granted', True) else "revoked"
            return Response({
                'message': f'All permissions {action_word} successfully',
                'permissions': output_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to set all permissions: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def revoke_permission(self, request):
        """
        Revoke a specific permission.

        POST /api/permissions/revoke_permission/
        {
            "asset_id": "uuid",
            "grantee_address": "0x...",
            "permission_type": "execute"
        }
        """
        # Get asset
        asset_id = request.data.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Check if user is the creator
        if asset.creator != request.user:
            return Response(
                {'error': 'Only the asset creator can manage permissions'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get required fields
        grantee_address = request.data.get('grantee_address')
        permission_type = request.data.get('permission_type')

        if not grantee_address or not permission_type:
            return Response(
                {'error': 'grantee_address and permission_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get services
        story_service = get_story_service()
        permission_service = get_permission_service(story_service=story_service)

        try:
            permission = permission_service.revoke_permission(
                asset=asset,
                grantee_address=grantee_address,
                permission_type=permission_type,
                granted_by_user=request.user
            )

            output_serializer = IPAccountPermissionSerializer(permission)
            return Response({
                'message': f'Permission {permission.get_permission_type_display()} revoked successfully',
                'permission': output_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to revoke permission: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def revoke_all_permissions(self, request):
        """
        Revoke all permissions for an address.

        POST /api/permissions/revoke_all_permissions/
        {
            "asset_id": "uuid",
            "grantee_address": "0x..."
        }
        """
        # Get asset
        asset_id = request.data.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Check if user is the creator
        if asset.creator != request.user:
            return Response(
                {'error': 'Only the asset creator can manage permissions'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get grantee address
        grantee_address = request.data.get('grantee_address')
        if not grantee_address:
            return Response(
                {'error': 'grantee_address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get services
        story_service = get_story_service()
        permission_service = get_permission_service(story_service=story_service)

        try:
            permissions = permission_service.revoke_all_permissions(
                asset=asset,
                grantee_address=grantee_address,
                granted_by_user=request.user
            )

            output_serializer = IPAccountPermissionSerializer(permissions, many=True)
            return Response({
                'message': 'All permissions revoked successfully',
                'permissions': output_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to revoke all permissions: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def for_asset(self, request):
        """
        Get all permissions for a specific asset.

        GET /api/permissions/for_asset/?asset_id={uuid}&active_only=true
        """
        asset_id = request.query_params.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Get services
        permission_service = get_permission_service()

        active_only = request.query_params.get('active_only', '').lower() == 'true'

        permissions = permission_service.get_permissions(
            asset=asset,
            active_only=active_only
        )

        serializer = IPAccountPermissionSerializer(permissions, many=True)
        return Response({
            'asset_id': str(asset.uuid),
            'asset_title': asset.title,
            'permissions': serializer.data,
            'total_count': len(permissions)
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def check_permission(self, request):
        """
        Check if an address has a specific permission.

        GET /api/permissions/check_permission/?asset_id={uuid}&grantee_address={address}&permission_type={type}
        """
        asset_id = request.query_params.get('asset_id')
        grantee_address = request.query_params.get('grantee_address')
        permission_type = request.query_params.get('permission_type')

        if not all([asset_id, grantee_address, permission_type]):
            return Response(
                {'error': 'asset_id, grantee_address, and permission_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Get services
        permission_service = get_permission_service()

        has_permission = permission_service.check_permission(
            asset=asset,
            grantee_address=grantee_address,
            permission_type=permission_type
        )

        return Response({
            'asset_id': str(asset.uuid),
            'grantee_address': grantee_address.lower(),
            'permission_type': permission_type,
            'has_permission': has_permission
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def permission_summary(self, request):
        """
        Get a summary of all permissions for an address on an asset.

        GET /api/permissions/permission_summary/?asset_id={uuid}&grantee_address={address}
        """
        asset_id = request.query_params.get('asset_id')
        grantee_address = request.query_params.get('grantee_address')

        if not all([asset_id, grantee_address]):
            return Response(
                {'error': 'asset_id and grantee_address are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Get services
        permission_service = get_permission_service()

        summary = permission_service.get_permission_summary(
            asset=asset,
            grantee_address=grantee_address
        )

        active_count = sum(1 for is_active in summary.values() if is_active)

        return Response({
            'asset_id': str(asset.uuid),
            'asset_title': asset.title,
            'grantee_address': grantee_address.lower(),
            'permissions': summary,
            'active_count': active_count,
            'total_count': len(summary)
        }, status=status.HTTP_200_OK)
