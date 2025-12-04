"""
Custom throttle classes for rate limiting API endpoints.
"""
from rest_framework.throttling import UserRateThrottle


class AIRateThrottle(UserRateThrottle):
    """
    Custom throttle for AI endpoints.
    More restrictive than general user throttle.
    """
    scope = 'ai'


class UploadRateThrottle(UserRateThrottle):
    """
    Custom throttle for file upload endpoints.
    Most restrictive to prevent abuse.
    """
    scope = 'upload'

