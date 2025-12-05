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
    # Use UUID for lookups instead of integer pk
    lookup_field = 'uuid'
    lookup_url_kwarg = 'uuid'
    
    def get_queryset(self):
        """Get comments for an asset, excluding deleted ones."""
        queryset = Comment.objects.select_related(
            'user', 'asset', 'parent'
        ).prefetch_related(
            'replies'
        ).filter(
            is_deleted=False
        )
        
        # For detail actions (retrieve, replies, like), don't filter by parent
        # This allows looking up any comment by UUID regardless of whether it's a reply
        if self.action in ['retrieve', 'replies', 'like', 'update', 'partial_update', 'destroy']:
            # No parent filtering for detail actions - just return non-deleted comments
            pass
        else:
            # For list action, apply filters
            # Filter by asset UUID if provided
            asset_id = self.request.query_params.get('asset')
            if asset_id:
                try:
                    queryset = queryset.filter(asset__uuid=asset_id)
                except ValueError:
                    # Invalid UUID, return empty queryset
                    queryset = queryset.none()
            
            # Filter by parent UUID (for replies)
            parent_id = self.request.query_params.get('parent')
            if parent_id:
                try:
                    queryset = queryset.filter(parent__uuid=parent_id)
                except ValueError:
                    queryset = queryset.none()
            else:
                # Only top-level comments by default for list
                queryset = queryset.filter(parent__isnull=True)
        
        # Annotate reply counts and like counts
        queryset = queryset.annotate(
            reply_count_annotated=Count('replies', filter=Q(replies__is_deleted=False)),
            like_count_annotated=Count('likes', distinct=True)
        )
        
        # Annotate is_liked if user is authenticated
        if self.request.user.is_authenticated:
            # We can't easily perform a subquery annotation compatible with all DB backends for boolean
            # So we'll use a Prefetch or handle it in the serializer via 'likes' relation
            # But for performance on list views, Exists() subquery is best
            from django.db.models import Exists, OuterRef
            from .models import CommentLike
            
            is_liked_subquery = CommentLike.objects.filter(
                comment=OuterRef('pk'),
                user=self.request.user
            )
            queryset = queryset.annotate(is_liked_annotated=Exists(is_liked_subquery))
        
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
    
    def create(self, request, *args, **kwargs):
        """Create comment and return full comment object."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Return the created comment using the detail serializer
        instance = serializer.instance
        detail_serializer = CommentSerializer(instance, context={'request': request})
        headers = self.get_success_headers(detail_serializer.data)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def perform_destroy(self, instance):
        """Soft delete comment instead of hard delete."""
        instance.soft_delete()
    
    @action(detail=True, methods=['get'], url_path='replies')
    def replies(self, request, uuid=None):
        """Get replies to a specific comment."""
        comment = self.get_object()
        replies = Comment.objects.select_related(
            'user', 'asset', 'parent'
        ).filter(
            parent=comment,
            is_deleted=False
        ).annotate(
            like_count_annotated=Count('likes', distinct=True)
        ).order_by('created_at')
        
        if request.user.is_authenticated:
            from django.db.models import Exists, OuterRef
            from .models import CommentLike
            is_liked_subquery = CommentLike.objects.filter(
                comment=OuterRef('pk'),
                user=request.user
            )
            replies = replies.annotate(is_liked_annotated=Exists(is_liked_subquery))
        
        serializer = self.get_serializer(replies, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='like')
    def like(self, request, uuid=None):
        """Like/unlike a comment (using CommentLike model)."""
        comment = self.get_object()
        user = request.user
        from .models import CommentLike
        
        # Check if user already liked this comment
        like_obj, created = CommentLike.objects.get_or_create(
            user=user,
            comment=comment
        )
        
        if not created:
            # Unlike: delete the like object
            like_obj.delete()
            return Response({'liked': False}, status=status.HTTP_200_OK)
        
        return Response({'liked': True}, status=status.HTTP_201_CREATED)


class InteractionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing interactions.
    """
    
    queryset = Interaction.objects.select_related('user', 'asset').all()
    serializer_class = InteractionSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    # Use UUID for lookups instead of integer pk
    lookup_field = 'uuid'
    
    def get_queryset(self):
        """Filter interactions by asset if provided."""
        queryset = super().get_queryset()
        
        asset_id = self.request.query_params.get('asset')
        if asset_id:
            try:
                queryset = queryset.filter(asset__uuid=asset_id)
            except ValueError:
                queryset = queryset.none()
        
        interaction_type = self.request.query_params.get('type')
        if interaction_type:
            queryset = queryset.filter(type=interaction_type)
        
        return queryset.order_by('-created_at')
