"""
Custom throttle classes for API rate limiting.
"""
from rest_framework.throttling import UserRateThrottle


class TokenRefreshThrottle(UserRateThrottle):
    """
    Rate limit for token refresh endpoint.
    Allows 10 requests per minute per user to prevent abuse.
    """
    rate = '10/minute'
    scope = 'token_refresh'
