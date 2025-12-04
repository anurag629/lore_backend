"""
Custom exception handlers for Lore API.
Provides consistent error responses across all endpoints.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class LoreAPIException(Exception):
    """Base exception for Lore API."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'A server error occurred.'

    def __init__(self, detail=None, status_code=None):
        self.detail = detail or self.default_detail
        if status_code is not None:
            self.status_code = status_code


class BlockchainError(LoreAPIException):
    """Blockchain operation failed."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Blockchain service unavailable.'


class IPFSError(LoreAPIException):
    """IPFS operation failed."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'IPFS service unavailable.'


class ValidationError(LoreAPIException):
    """Validation error."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Validation failed.'


def custom_exception_handler(exc, context):
    """
    Custom exception handler for consistent error responses.
    
    Returns standardized error format:
    {
        'error': true,
        'message': 'Human-readable error message',
        'detail': {...},
        'status_code': 400
    }
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Add custom handling
    if response is not None:
        # Handle DRF validation errors
        if isinstance(response.data, dict):
            detail = response.data
        elif isinstance(response.data, list):
            detail = {'non_field_errors': response.data}
        else:
            detail = {'detail': str(response.data)}

        custom_response_data = {
            'error': True,
            'message': str(exc) if hasattr(exc, '__str__') else 'An error occurred',
            'detail': detail,
            'status_code': response.status_code,
        }
        response.data = custom_response_data

    # Handle custom exceptions
    elif isinstance(exc, LoreAPIException):
        response = Response(
            {
                'error': True,
                'message': exc.detail,
                'detail': {'detail': exc.detail},
                'status_code': exc.status_code,
            },
            status=exc.status_code
        )

    # Log unexpected errors
    elif response is None:
        logger.error(
            f"Unhandled exception: {exc}",
            exc_info=True,
            extra={'context': context}
        )
        response = Response(
            {
                'error': True,
                'message': 'An unexpected error occurred',
                'detail': {'detail': str(exc) if settings.DEBUG else 'Internal server error'},
                'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response

