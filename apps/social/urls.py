"""
URL routing for social API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CommentViewSet, InteractionViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'interactions', InteractionViewSet, basename='interaction')

urlpatterns = [
    path('', include(router.urls)),
]

# Available endpoints:
# GET    /api/social/comments/                    - List comments (filter by ?asset=id&parent=id)
# POST   /api/social/comments/                    - Create comment
# GET    /api/social/comments/{id}/               - Get comment details
# PUT    /api/social/comments/{id}/               - Update comment
# DELETE /api/social/comments/{id}/               - Delete comment (soft delete)
# GET    /api/social/comments/{id}/replies/       - Get replies to a comment
# POST   /api/social/comments/{id}/like/          - Like/unlike a comment
#
# GET    /api/social/interactions/                 - List interactions (filter by ?asset=id&type=like)
# GET    /api/social/interactions/{id}/            - Get interaction details
