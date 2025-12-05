"""
Custom throttle classes for rate limiting API endpoints.
"""
from rest_framework.throttling import UserRateThrottle


class UploadRateThrottle(UserRateThrottle):
    """
    Custom throttle for file upload endpoints.
    Most restrictive to prevent abuse.
    """
    scope = 'upload'

