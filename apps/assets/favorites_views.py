"""
Views for Favorites feature.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.db import transaction

from .models import Favorite, IPAsset
from .favorites_serializers import FavoriteSerializer, FavoriteCreateSerializer
from .cache import invalidate_user_profile_cache

logger = logging.getLogger(__name__)


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

