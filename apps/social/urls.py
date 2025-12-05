"""
URL routing for social API endpoints.
"""
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import CommentViewSet, InteractionViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'interactions', InteractionViewSet, basename='interaction')

# Create viewset instances for explicit action URLs
comment_replies = CommentViewSet.as_view({'get': 'replies'})
comment_like = CommentViewSet.as_view({'post': 'like'})

urlpatterns = [
    # Explicit URLs for comment actions (must come before router.urls to take precedence)
    # Using UUID pattern for comment lookup
    re_path(
        r'^comments/(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/replies/$',
        comment_replies,
        name='comment-replies'
    ),
    re_path(
        r'^comments/(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/like/$',
        comment_like,
        name='comment-like'
    ),
    # Include router URLs
    path('', include(router.urls)),
]

# Available endpoints:
# GET    /api/social/comments/                    - List comments (filter by ?asset=id&parent=id)
# POST   /api/social/comments/                    - Create comment
# GET    /api/social/comments/{uuid}/             - Get comment details
# PUT    /api/social/comments/{uuid}/             - Update comment
# DELETE /api/social/comments/{uuid}/             - Delete comment (soft delete)
# GET    /api/social/comments/{uuid}/replies/     - Get replies to a comment
# POST   /api/social/comments/{uuid}/like/        - Like/unlike a comment
#
# GET    /api/social/interactions/                 - List interactions (filter by ?asset=id&type=like)
# GET    /api/social/interactions/{uuid}/          - Get interaction details
