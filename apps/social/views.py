"""
API views for social features (comments, interactions).
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Count, Q
from django.utils import timezone

from .models import Comment, Interaction
from .serializers import (
    CommentSerializer,
    CommentCreateSerializer,
    CommentUpdateSerializer,
    InteractionSerializer,
)
from apps.assets.models import IPAsset

logger = logging.getLogger(__name__)


class CommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for comment CRUD operations.
    Supports nested replies (threaded comments).
    """
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        """Get comments for an asset, excluding deleted ones."""
        queryset = Comment.objects.select_related(
            'user', 'asset', 'parent'
        ).prefetch_related(
            'replies'
        ).filter(
            is_deleted=False
        )
        
        # Filter by asset if provided
        asset_id = self.request.query_params.get('asset')
        if asset_id:
            queryset = queryset.filter(asset_id=asset_id)
        
        # Filter by parent (for replies)
        parent_id = self.request.query_params.get('parent')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        else:
            # Only top-level comments by default
            queryset = queryset.filter(parent__isnull=True)
        
        # Annotate reply counts
        queryset = queryset.annotate(
            reply_count=Count('replies', filter=Q(replies__is_deleted=False))
        )
        
        return queryset.order_by('created_at')
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return CommentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CommentUpdateSerializer
        return CommentSerializer
    
    def perform_create(self, serializer):
        """Create comment with current user."""
        serializer.save(user=self.request.user)
    
    def perform_destroy(self, instance):
        """Soft delete comment instead of hard delete."""
        instance.soft_delete()
    
    @action(detail=True, methods=['get'])
    def replies(self, request, pk=None):
        """Get replies to a specific comment."""
        comment = self.get_object()
        replies = Comment.objects.select_related(
            'user', 'asset', 'parent'
        ).filter(
            parent=comment,
            is_deleted=False
        ).order_by('created_at')
        
        serializer = self.get_serializer(replies, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def like(self, request, pk=None):
        """Like/unlike a comment (using Interaction model)."""
        comment = self.get_object()
        user = request.user
        
        # Check if user already liked this comment
        interaction, created = Interaction.objects.get_or_create(
            user=user,
            asset=comment.asset,
            type='like',
            defaults={}
        )
        
        if not created:
            # Unlike: delete the interaction
            interaction.delete()
            return Response({'liked': False}, status=status.HTTP_200_OK)
        
        return Response({'liked': True}, status=status.HTTP_201_CREATED)


class InteractionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing interactions.
    """
    
    queryset = Interaction.objects.select_related('user', 'asset').all()
    serializer_class = InteractionSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        """Filter interactions by asset if provided."""
        queryset = super().get_queryset()
        
        asset_id = self.request.query_params.get('asset')
        if asset_id:
            queryset = queryset.filter(asset_id=asset_id)
        
        interaction_type = self.request.query_params.get('type')
        if interaction_type:
            queryset = queryset.filter(type=interaction_type)
        
        return queryset.order_by('-created_at')

