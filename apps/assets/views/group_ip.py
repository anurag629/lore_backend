"""
Group IP Views - API endpoints for Story Protocol Group IPs
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.shortcuts import get_object_or_404
from django.db import transaction
from decimal import Decimal
import logging

from apps.assets.models import GroupIP, GroupIPMembership, IPAsset, GroupRoyaltyDistribution
from apps.assets.serializers import (
    GroupIPListSerializer,
    GroupIPDetailSerializer,
    GroupIPCreateSerializer,
    AddMemberToGroupSerializer,
    GroupIPMembershipSerializer,
    GroupRoyaltyDistributionSerializer
)
from apps.assets.services.group_ip_service import get_group_ip_service
from apps.assets.services.story_service import get_story_service

logger = logging.getLogger(__name__)


class GroupIPViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Group IPs.

    Endpoints:
    - GET /api/groups/ - List all groups
    - POST /api/groups/ - Create a new group
    - GET /api/groups/{uuid}/ - Get group details
    - PUT/PATCH /api/groups/{uuid}/ - Update group
    - DELETE /api/groups/{uuid}/ - Deactivate group
    - POST /api/groups/{uuid}/register/ - Register group on-chain
    - POST /api/groups/{uuid}/add_member/ - Add member to group
    - POST /api/groups/{uuid}/remove_member/ - Remove member from group
    - GET /api/groups/{uuid}/statistics/ - Get group statistics
    """

    queryset = GroupIP.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'uuid'

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return GroupIPListSerializer
        elif self.action == 'create':
            return GroupIPCreateSerializer
        elif self.action in ['add_member', 'remove_member']:
            return AddMemberToGroupSerializer
        else:
            return GroupIPDetailSerializer

    def get_queryset(self):
        """Filter queryset based on query params."""
        queryset = super().get_queryset()

        # Filter by creator
        creator = self.request.query_params.get('creator')
        if creator:
            queryset = queryset.filter(creator__wallet_address=creator)

        # Filter by status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        registration_status = self.request.query_params.get('registration_status')
        if registration_status:
            queryset = queryset.filter(registration_status=registration_status)

        return queryset.select_related('creator').prefetch_related('members__asset')

    def create(self, request, *args, **kwargs):
        """
        Create a new Group IP.

        POST /api/groups/
        {
            "name": "My Collection",
            "description": "A collection of related IP assets",
            "total_royalty_percentage": 10
        }
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get group IP service
        group_service = get_group_ip_service()

        try:
            # Create group
            group = group_service.create_group(
                name=serializer.validated_data['name'],
                description=serializer.validated_data['description'],
                creator_user=request.user,
                royalty_percentage=serializer.validated_data.get('total_royalty_percentage', 10)
            )

            # Return created group
            output_serializer = GroupIPDetailSerializer(group)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Failed to create group: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def register(self, request, uuid=None):
        """
        Register a Group IP on the blockchain.

        POST /api/groups/{uuid}/register/
        {
            "creator_address": "0x..."
        }
        """
        group = self.get_object()

        # Check ownership
        if group.creator != request.user:
            return Response(
                {'error': 'Only the group creator can register it'},
                status=status.HTTP_403_FORBIDDEN
            )

        creator_address = request.data.get('creator_address')
        if not creator_address:
            # Use user's wallet address
            creator_address = request.user.wallet_address

        # Get services
        story_service = get_story_service()
        group_service = get_group_ip_service(story_service=story_service)

        try:
            result = group_service.register_group_on_chain(
                group=group,
                creator_address=creator_address
            )

            return Response({
                'message': 'Group IP registered successfully',
                'story_group_id': result['story_group_id'],
                'transaction_hash': result['transaction_hash']
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Failed to register group {uuid}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_member(self, request, uuid=None):
        """
        Add a member to a Group IP.

        POST /api/groups/{uuid}/add_member/
        {
            "asset_id": "...",
            "revenue_share_percentage": 25.50
        }
        """
        group = self.get_object()

        # Check ownership
        if group.creator != request.user:
            return Response(
                {'error': 'Only the group creator can add members'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = AddMemberToGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get asset
        asset = get_object_or_404(IPAsset, uuid=serializer.validated_data['asset_id'])

        # Get service
        group_service = get_group_ip_service()

        try:
            membership = group_service.add_member_to_group(
                group=group,
                asset=asset,
                revenue_share_percentage=serializer.validated_data['revenue_share_percentage'],
                added_by_user=request.user
            )

            output_serializer = GroupIPMembershipSerializer(membership)
            return Response({
                'message': f'Added {asset.title} to {group.name}',
                'membership': output_serializer.data
            }, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to add member to group {uuid}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def remove_member(self, request, uuid=None):
        """
        Remove a member from a Group IP.

        POST /api/groups/{uuid}/remove_member/
        {
            "membership_id": "..."
        }
        """
        group = self.get_object()

        # Check ownership
        if group.creator != request.user:
            return Response(
                {'error': 'Only the group creator can remove members'},
                status=status.HTTP_403_FORBIDDEN
            )

        membership_id = request.data.get('membership_id')
        if not membership_id:
            return Response(
                {'error': 'membership_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get membership
        membership = get_object_or_404(
            GroupIPMembership,
            uuid=membership_id,
            group=group
        )

        # Get service
        group_service = get_group_ip_service()

        try:
            group_service.remove_member_from_group(membership)

            return Response({
                'message': f'Removed {membership.asset.title} from {group.name}'
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to remove member from group {uuid}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def statistics(self, request, uuid=None):
        """
        Get statistics for a Group IP.

        GET /api/groups/{uuid}/statistics/
        """
        group = self.get_object()
        group_service = get_group_ip_service()

        try:
            stats = group_service.get_group_statistics(group)
            return Response(stats, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Failed to get statistics for group {uuid}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def distributions(self, request, uuid=None):
        """
        Get royalty distributions for a Group IP.

        GET /api/groups/{uuid}/distributions/
        """
        group = self.get_object()

        distributions = GroupRoyaltyDistribution.objects.filter(
            group=group
        ).select_related('membership__asset', 'group').order_by('-distributed_at')

        serializer = GroupRoyaltyDistributionSerializer(distributions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """
        Deactivate a Group IP (soft delete).

        DELETE /api/groups/{uuid}/
        """
        group = self.get_object()

        # Check ownership
        if group.creator != request.user:
            return Response(
                {'error': 'Only the group creator can deactivate it'},
                status=status.HTTP_403_FORBIDDEN
            )

        group.is_active = False
        group.save(update_fields=['is_active'])

        return Response({
            'message': f'Group "{group.name}" deactivated successfully'
        }, status=status.HTTP_200_OK)
