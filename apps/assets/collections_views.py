"""
Views for Collections feature.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django.db.models import Count, Q
from django.db import transaction

from .models import Collection
from .collections_serializers import (
    CollectionListSerializer,
    CollectionDetailSerializer,
    CollectionCreateSerializer,
    CollectionUpdateSerializer,
)
from .cache import invalidate_user_profile_cache

logger = logging.getLogger(__name__)


class CollectionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Collection CRUD operations.
    """
    queryset = Collection.objects.select_related('creator').prefetch_related('assets').all()
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return CollectionCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CollectionUpdateSerializer
        elif self.action == 'retrieve':
            return CollectionDetailSerializer
        else:
            return CollectionListSerializer

    def get_queryset(self):
        """Get queryset with optimizations."""
        queryset = super().get_queryset()
        
        # Filter by creator if requested
        creator_id = self.request.query_params.get('creator')
        if creator_id:
            queryset = queryset.filter(creator_id=creator_id)
        
        # Filter by public/private based on user
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(is_public=True)
        elif not self.request.user.is_staff:
            # Show public collections or user's own collections
            queryset = queryset.filter(
                Q(is_public=True) | Q(creator=self.request.user)
            )
        
        # Annotate asset count
        queryset = queryset.annotate(
            asset_count=Count('assets', filter=Q(assets__is_deleted=False))
        )
        
        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        """Create collection with creator."""
        serializer.save(creator=self.request.user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create collection with cache invalidation."""
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            # Invalidate user profile cache
            invalidate_user_profile_cache(request.user.wallet_address)
        return response

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """Update collection with cache invalidation."""
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            collection = self.get_object()
            invalidate_user_profile_cache(collection.creator.wallet_address)
        return response

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Delete collection with cache invalidation."""
        collection = self.get_object()
        creator_address = collection.creator.wallet_address
        collection.delete()
        invalidate_user_profile_cache(creator_address)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_asset(self, request, pk=None):
        """Add an asset to the collection."""
        collection = self.get_object()
        
        # Check permission
        if collection.creator != request.user:
            return Response(
                {'error': 'You can only modify your own collections'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        asset_id = request.data.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .models import IPAsset
        try:
            asset = IPAsset.objects.get(id=asset_id, is_deleted=False)
            collection.assets.add(asset)
            invalidate_user_profile_cache(request.user.wallet_address)
            return Response({'success': True}, status=status.HTTP_200_OK)
        except IPAsset.DoesNotExist:
            return Response(
                {'error': 'Asset not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def remove_asset(self, request, pk=None):
        """Remove an asset from the collection."""
        collection = self.get_object()
        
        # Check permission
        if collection.creator != request.user:
            return Response(
                {'error': 'You can only modify your own collections'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        asset_id = request.data.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .models import IPAsset
        try:
            asset = IPAsset.objects.get(id=asset_id)
            collection.assets.remove(asset)
            invalidate_user_profile_cache(request.user.wallet_address)
            return Response({'success': True}, status=status.HTTP_200_OK)
        except IPAsset.DoesNotExist:
            return Response(
                {'error': 'Asset not found'},
                status=status.HTTP_404_NOT_FOUND
            )

