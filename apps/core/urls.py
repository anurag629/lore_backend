"""
URL configuration for authentication endpoints
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core import views


app_name = 'core'

urlpatterns = [
    # SIWE Authentication
    path('nonce/', views.get_nonce, name='get_nonce'),
    path('login/', views.siwe_login, name='siwe_login'),
    path('logout/', views.logout, name='logout'),

    # JWT Token Management
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # User Profile
    path('me/', views.get_current_user, name='current_user'),
    path('profile/', views.update_profile, name='update_profile'),
]
