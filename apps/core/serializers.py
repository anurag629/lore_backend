"""
Serializers for user authentication and user data
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Q

from apps.core.models import LoreUser
from apps.core.utils import verify_siwe_signature, normalize_wallet_address


class CreatorSerializer(serializers.ModelSerializer):
    """Lightweight serializer for creator information (used in assets, collections, etc.)."""
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = LoreUser
        fields = ['id', 'wallet_address', 'display_name', 'avatar_url']
        read_only_fields = fields
    
    def get_display_name(self, obj):
        """Get display name property."""
        return obj.display_name


class LoreUserSerializer(serializers.ModelSerializer):
    """
    Serializer for LoreUser model
    """
    assets_count = serializers.SerializerMethodField()
    total_spinoffs = serializers.SerializerMethodField()

    class Meta:
        model = LoreUser
        fields = [
            'id',
            'wallet_address',
            'username',
            'email',
            'bio',
            'avatar_url',
            'banner_url',
            'total_earnings',
            'assets_count',
            'total_spinoffs',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'wallet_address', 'total_earnings', 'created_at', 'updated_at']

    def get_assets_count(self, obj):
        """Get number of assets created by user"""
        # Use prefetched count if available
        if hasattr(obj, '_prefetched_objects_cache') and 'assets' in obj._prefetched_objects_cache:
            return len([a for a in obj._prefetched_objects_cache['assets'] if not a.is_deleted])
        # Fallback to query
        return obj.assets.filter(is_deleted=False).count()

    def get_total_spinoffs(self, obj):
        """Get total spinoffs across all user's assets"""
        # Optimize with aggregation if possible
        if hasattr(obj, '_prefetched_objects_cache') and 'assets' in obj._prefetched_objects_cache:
            return sum(
                asset.derivative_count 
                for asset in obj._prefetched_objects_cache['assets'] 
                if not asset.is_deleted
            )
        # Fallback to query with aggregation
        from django.db.models import Count
        from apps.assets.models import IPAsset
        return IPAsset.objects.filter(
            parent_asset__creator=obj,
            parent_asset__is_deleted=False,
            is_deleted=False
        ).count()


class NonceRequestSerializer(serializers.Serializer):
    """
    Serializer for nonce generation request
    """
    wallet_address = serializers.CharField(
        max_length=42,
        required=True,
        help_text="Ethereum wallet address (0x...)"
    )

    def validate_wallet_address(self, value):
        """
        Validate and normalize wallet address
        """
        if not value.startswith('0x') or len(value) != 42:
            raise serializers.ValidationError("Invalid Ethereum wallet address format")

        return normalize_wallet_address(value)


class NonceResponseSerializer(serializers.Serializer):
    """
    Serializer for nonce generation response
    """
    nonce = serializers.CharField()
    message = serializers.CharField()
    wallet_address = serializers.CharField()


class SIWELoginSerializer(serializers.Serializer):
    """
    Serializer for SIWE (Sign-In with Ethereum) login
    """
    message = serializers.CharField(
        required=True,
        help_text="SIWE message that was signed"
    )
    signature = serializers.CharField(
        required=True,
        help_text="Signature from wallet"
    )

    def validate(self, attrs):
        """
        Verify the SIWE signature and return user data
        """
        message = attrs.get('message')
        signature = attrs.get('signature')

        # Get expected domain from request context
        request = self.context.get('request')
        domain = request.get_host().split(':')[0] if request else 'localhost'

        # Verify the signature
        verification_result = verify_siwe_signature(
            message=message,
            signature=signature,
            expected_domain=domain
        )

        if not verification_result:
            raise serializers.ValidationError({
                'signature': 'Invalid signature or message'
            })

        wallet_address = verification_result['wallet_address']

        # Normalize wallet address
        wallet_address = normalize_wallet_address(wallet_address)

        # Get or create user
        user, created = LoreUser.objects.get_or_create(
            wallet_address=wallet_address,
            defaults={
                'username': f"user_{wallet_address[:8]}",
                'email': f"{wallet_address}@lore.local",  # Dummy email
            }
        )

        attrs['user'] = user
        attrs['created'] = created

        return attrs

    def create(self, validated_data):
        """
        Generate JWT tokens for authenticated user
        """
        user = validated_data['user']

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        return {
            'user': user,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'created': validated_data['created'],
        }


class LoginResponseSerializer(serializers.Serializer):
    """
    Serializer for login response
    """
    access = serializers.CharField(help_text="JWT access token")
    refresh = serializers.CharField(help_text="JWT refresh token")
    user = LoreUserSerializer()
    created = serializers.BooleanField(help_text="Whether user was newly created")


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer that includes user data
    """
    def validate(self, attrs):
        data = super().validate(attrs)

        # Add user data to response
        data['user'] = LoreUserSerializer(self.user).data

        return data
