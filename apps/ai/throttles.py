"""
Custom throttle classes for AI endpoints.
"""
from rest_framework.throttling import UserRateThrottle


class AIRateThrottle(UserRateThrottle):
    """
    Custom throttle for AI endpoints.
    More restrictive than general user throttle.
    """
    scope = 'ai'

