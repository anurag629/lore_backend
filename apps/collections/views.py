"""
Views for Collections and Favorites features.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django.db.models import Count, Q
from django.db import transaction

from .models import Collection, Favorite
from .serializers import (
    CollectionListSerializer,
    CollectionDetailSerializer,
    CollectionCreateSerializer,
    CollectionUpdateSerializer,
    FavoriteSerializer,
    FavoriteCreateSerializer,
)
from apps.assets.cache import invalidate_user_profile_cache

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
        
        from apps.assets.models import IPAsset
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
        
        from apps.assets.models import IPAsset
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


class FavoriteViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Favorite CRUD operations.
    """
    queryset = Favorite.objects.select_related('user', 'asset', 'asset__creator').all()
    permission_classes = [IsAuthenticated]
    serializer_class = FavoriteSerializer

    def get_queryset(self):
        """Get queryset filtered by current user."""
        queryset = super().get_queryset()
        
        # Filter by user
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        else:
            # Default to current user's favorites
            queryset = queryset.filter(user=self.request.user)
        
        return queryset.order_by('-created_at')

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a favorite (toggle if already exists)."""
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        asset_id = serializer.validated_data['asset_id']
        from apps.assets.models import IPAsset
        asset = IPAsset.objects.get(id=asset_id, is_deleted=False)
        
        # Check if already favorited
        favorite, created = Favorite.objects.get_or_create(
            user=request.user,
            asset=asset
        )
        
        if created:
            invalidate_user_profile_cache(request.user.wallet_address)
            return Response(
                FavoriteSerializer(favorite).data,
                status=status.HTTP_201_CREATED
            )
        else:
            # Already favorited, return existing
            return Response(
                FavoriteSerializer(favorite).data,
                status=status.HTTP_200_OK
            )

    @action(detail=False, methods=['post'], url_path='toggle')
    def toggle_favorite(self, request):
        """Toggle favorite status for an asset."""
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        asset_id = serializer.validated_data['asset_id']
        from apps.assets.models import IPAsset
        asset = IPAsset.objects.get(id=asset_id, is_deleted=False)
        
        try:
            favorite = Favorite.objects.get(user=request.user, asset=asset)
            favorite.delete()
            invalidate_user_profile_cache(request.user.wallet_address)
            return Response(
                {'favorited': False, 'message': 'Removed from favorites'},
                status=status.HTTP_200_OK
            )
        except Favorite.DoesNotExist:
            favorite = Favorite.objects.create(user=request.user, asset=asset)
            invalidate_user_profile_cache(request.user.wallet_address)
            return Response(
                {
                    'favorited': True,
                    'message': 'Added to favorites',
                    'favorite': FavoriteSerializer(favorite).data
                },
                status=status.HTTP_201_CREATED
            )

    @action(detail=False, methods=['get'], url_path='check')
    def check_favorite(self, request):
        """Check if an asset is favorited by current user."""
        asset_id = request.query_params.get('asset_id')
        if not asset_id:
            return Response(
                {'error': 'asset_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from apps.assets.models import IPAsset
        try:
            asset = IPAsset.objects.get(id=asset_id, is_deleted=False)
            is_favorited = Favorite.objects.filter(
                user=request.user,
                asset=asset
            ).exists()
            
            return Response(
                {'favorited': is_favorited},
                status=status.HTTP_200_OK
            )
        except IPAsset.DoesNotExist:
            return Response(
                {'error': 'Asset not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Remove favorite."""
        favorite = self.get_object()
        
        # Check permission
        if favorite.user != request.user:
            return Response(
                {'error': 'You can only remove your own favorites'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        invalidate_user_profile_cache(request.user.wallet_address)
        favorite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

