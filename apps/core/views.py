"""
Authentication views for SIWE (Sign-In with Ethereum)
"""
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
import logging

logger = logging.getLogger(__name__)

from apps.core.serializers import (
    NonceRequestSerializer,
    NonceResponseSerializer,
    SIWELoginSerializer,
    LoginResponseSerializer,
    LoreUserSerializer
)
from apps.core.utils import generate_nonce, create_siwe_message
from apps.core.models import LoreUser
from apps.assets.cache import get_cached_user_profile, cache_user_profile
from apps.assets.validators import validate_file_name, validate_file_size, validate_file_type, validate_image_content


@api_view(['POST'])
@permission_classes([AllowAny])
def get_nonce(request):
    """
    Generate a nonce for SIWE authentication.

    This endpoint generates a random nonce and creates a SIWE message
    for the user to sign with their wallet.

    The nonce is cached for 5 minutes to prevent replay attacks.
    """
    serializer = NonceRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    wallet_address = serializer.validated_data['wallet_address']

    # Generate nonce
    nonce = generate_nonce()

    # Cache the nonce for 5 minutes (prevents replay attacks)
    cache_key = f"siwe_nonce_{wallet_address.lower()}"
    cache.set(cache_key, nonce, timeout=300)  # 5 minutes

    # Get domain from request
    domain = request.get_host().split(':')[0]

    # Create SIWE message
    message = create_siwe_message(
        domain=domain,
        wallet_address=wallet_address,
        nonce=nonce,
        chain_id=settings.STORY_PROTOCOL_CHAIN_ID,  # Configured chain ID
        uri=f"{request.scheme}://{request.get_host()}"
    )

    response_data = {
        'nonce': nonce,
        'message': message,
        'wallet_address': wallet_address,
    }

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def siwe_login(request):
    """
    Login with SIWE (Sign-In with Ethereum).

    Verifies the SIWE signature and returns JWT tokens if valid.
    Creates a new user if the wallet address doesn't exist.

    Returns:
        - access: JWT access token (expires in 15 minutes)
        - refresh: JWT refresh token (expires in 7 days)
        - user: User profile data
        - created: Boolean indicating if user was newly created
    """
    serializer = SIWELoginSerializer(
        data=request.data,
        context={'request': request}
    )
    serializer.is_valid(raise_exception=True)

    # Create user and generate tokens
    result = serializer.save()

    response_data = {
        'access': result['access'],
        'refresh': result['refresh'],
        'user': LoreUserSerializer(result['user']).data,
        'created': result['created'],
    }

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """
    Get current authenticated user's profile.

    Requires valid JWT access token in Authorization header.
    """
    serializer = LoreUserSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_user_by_address(request, wallet_address):
    """
    Get user profile by wallet address.
    Public endpoint - anyone can view user profiles.
    """
    # Try to get from cache
    cached_response = get_cached_user_profile(wallet_address)
    if cached_response:
        return Response(cached_response, status=status.HTTP_200_OK)
    
    # Use filter().first() instead of get() to handle potential duplicates
    # (can occur due to case sensitivity issues with wallet addresses)
    user = LoreUser.objects.prefetch_related(
        'assets'
    ).filter(wallet_address__iexact=wallet_address).first()
    
    if not user:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = LoreUserSerializer(user)
    response_data = serializer.data
    
    # Cache the response
    cache_user_profile(wallet_address, response_data)
    
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_avatar(request):
    """
    Upload avatar image to IPFS and update user profile.
    
    Accepts multipart/form-data with 'avatar' file field.
    """
    if 'avatar' not in request.FILES:
        return Response(
            {'error': 'No avatar file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    avatar_file = request.FILES['avatar']
    
    
    # Comprehensive validation using validator functions
    try:
        validate_file_name(avatar_file)
        validate_file_size(avatar_file)
        validate_file_type(avatar_file)
        validate_image_content(avatar_file)  # Pillow-based content validation
    except ValidationError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        from apps.assets.services import get_pinata_service
        
        pinata_service = get_pinata_service()
        result = pinata_service.upload_file(
            file=avatar_file,
            filename=f"avatar_{request.user.id}_{avatar_file.name}"
        )
        
        # Update user profile
        request.user.avatar_url = result['url']
        request.user.save()
        
        from apps.core.serializers import LoreUserSerializer
        serializer = LoreUserSerializer(request.user)
        
        return Response({
            'url': result['url'],
            'ipfs_hash': result['ipfs_hash'],
            'user': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Failed to upload avatar: {str(e)}")
        return Response(
            {'error': 'Failed to upload avatar', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_banner(request):
    """
    Upload banner image to IPFS and update user profile.
    
    Accepts multipart/form-data with 'banner' file field.
    """
    if 'banner' not in request.FILES:
        return Response(
            {'error': 'No banner file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    banner_file = request.FILES['banner']
    
    
    # Comprehensive validation using validator functions
    try:
        validate_file_name(banner_file)
        validate_file_size(banner_file)
        validate_file_type(banner_file)
        validate_image_content(banner_file)  # Pillow-based content validation
    except ValidationError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        from apps.assets.services import get_pinata_service
        
        pinata_service = get_pinata_service()
        result = pinata_service.upload_file(
            file=banner_file,
            filename=f"banner_{request.user.id}_{banner_file.name}"
        )
        
        # Update user profile
        request.user.banner_url = result['url']
        request.user.save()
        
        from apps.core.serializers import LoreUserSerializer
        serializer = LoreUserSerializer(request.user)
        
        return Response({
            'url': result['url'],
            'ipfs_hash': result['ipfs_hash'],
            'user': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Failed to upload banner: {str(e)}")
        return Response(
            {'error': 'Failed to upload banner', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update current user's profile.

    Allows updating: username, bio, avatar_url, banner_url
    Cannot update: wallet_address, total_earnings
    """
    serializer = LoreUserSerializer(
        request.user,
        data=request.data,
        partial=True
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    # Invalidate user-related caches
    user_wallet = request.user.wallet_address.lower()
    cache_keys = [
        f'user_profile_{user_wallet}',
        f'user_assets_{user_wallet}',
        f'user_stats_{user_wallet}',
    ]
    for key in cache_keys:
        cache.delete(key)
    
    logger.info(f"Invalidated cache for user {user_wallet} after profile update")

    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout and blacklist the refresh token.

    The refresh token passed in the request body will be blacklisted
    and cannot be used again.
    """
    try:
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return Response(
                {'detail': 'Refresh token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Blacklist the token
        token = RefreshToken(refresh_token)
        token.blacklist()

        return Response(
            {'detail': 'Successfully logged out'},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'detail': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view that includes user data
    """
    pass


# ===== Health Check Endpoints =====

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Basic health check endpoint."""
    return Response({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_detailed(request):
    """Detailed health check with service status."""
    checks = {
        'database': _check_database(),
        'cache': _check_cache(),
        'story_protocol': _check_story_protocol(),
        'pinata': _check_pinata(),
        'ai_service': _check_ai_service(),
    }
    
    all_healthy = all(check['status'] == 'healthy' for check in checks.values())
    
    return Response({
        'status': 'healthy' if all_healthy else 'degraded',
        'checks': checks,
        'timestamp': timezone.now().isoformat(),
    }, status=200 if all_healthy else 503)


def _check_database():
    """Check database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {'status': 'healthy'}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}


def _check_cache():
    """Check cache connectivity."""
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            return {'status': 'healthy'}
        return {'status': 'unhealthy', 'error': 'Cache not working'}
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}


def _check_story_protocol():
    """Check Story Protocol service."""
    try:
        from apps.assets.services import get_story_service
        service = get_story_service()
        if service.is_ready():
            return {'status': 'healthy'}
        return {'status': 'unhealthy', 'error': 'Service not ready'}
    except Exception as e:
        logger.error(f"Story Protocol health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}


def _check_pinata():
    """Check Pinata IPFS service."""
    try:
        from apps.assets.services import get_pinata_service
        service = get_pinata_service()
        if service.test_connection():
            return {'status': 'healthy'}
        return {'status': 'unhealthy', 'error': 'Connection failed'}
    except Exception as e:
        logger.error(f"Pinata health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}


def _check_ai_service():
    """Check AI service."""
    try:
        from apps.ai.services import get_ai_service
        service = get_ai_service()
        if service.is_ready():
            return {'status': 'healthy'}
        return {'status': 'unhealthy', 'error': 'Service not ready'}
    except Exception as e:
        logger.error(f"AI service health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}
