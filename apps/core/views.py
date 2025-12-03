"""
Authentication views for SIWE (Sign-In with Ethereum)
"""
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.serializers import (
    NonceRequestSerializer,
    NonceResponseSerializer,
    SIWELoginSerializer,
    LoginResponseSerializer,
    LoreUserSerializer
)
from apps.core.utils import generate_nonce, create_siwe_message


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
        chain_id=1,  # Mainnet - change based on your needs
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


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update current user's profile.

    Allows updating: username, bio, avatar_url
    Cannot update: wallet_address, total_earnings
    """
    serializer = LoreUserSerializer(
        request.user,
        data=request.data,
        partial=True
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

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
