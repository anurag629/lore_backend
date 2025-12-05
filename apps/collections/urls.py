"""
URL routing for Collections and Favorites API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CollectionViewSet, FavoriteViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'collections', CollectionViewSet, basename='collection')
router.register(r'favorites', FavoriteViewSet, basename='favorite')

app_name = 'collections'

urlpatterns = [
    path('', include(router.urls)),
]

