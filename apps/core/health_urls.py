"""
URL configuration for health check endpoints
"""
from django.urls import path
from apps.core import views

# No app_name here to avoid namespace conflicts

urlpatterns = [
    path('health/', views.health_check, name='health'),
    path('health/detailed/', views.health_detailed, name='health_detailed'),
]

