"""
Serializers for IP Asset API endpoints.
"""
from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import IPAsset, RoyaltyPayment
from apps.core.models import LoreUser
from .validators import (
    validate_file_size,
    validate_file_type,
    validate_file_name,
    validate_media_url
)


class CreatorSerializer(serializers.ModelSerializer):
    """Serializer for asset creator information."""

    class Meta:
        model = LoreUser
        fields = ['id', 'wallet_address', 'display_name', 'avatar_url']
        read_only_fields = fields


class IPAssetListSerializer(serializers.ModelSerializer):
    """Serializer for listing IP assets (used in browse/explore pages)."""

    creator = CreatorSerializer(read_only=True)
    derivative_count = serializers.SerializerMethodField()

    class Meta:
        model = IPAsset
        fields = [
            'id',
            'story_ip_id',
            'creator',
            'title',
            'description',
            'media_url',
            'is_derivative',
            'derivative_count',
            'allow_derivatives',
            'commercial_rights',
            'registration_status',
            'created_at',
        ]
        read_only_fields = fields

    def get_derivative_count(self, obj):
        """Get derivative count - use annotated value if available."""
        # Use annotated count if available (from queryset optimization)
        if hasattr(obj, 'derivative_count_annotated'):
            return obj.derivative_count_annotated
        # Fallback to property
        return obj.derivative_count


class ParentAssetSerializer(serializers.ModelSerializer):
    """Serializer for parent asset information (used in derivatives)."""

    creator = CreatorSerializer(read_only=True)

    class Meta:
        model = IPAsset
        fields = ['id', 'story_ip_id', 'title', 'creator', 'media_url']
        read_only_fields = fields


class IPAssetDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual IP asset view."""

    creator = CreatorSerializer(read_only=True)
    parent_asset = ParentAssetSerializer(read_only=True)
    derivative_count = serializers.IntegerField(read_only=True)
    derivatives = serializers.SerializerMethodField()

    class Meta:
        model = IPAsset
        fields = [
            'id',
            'story_ip_id',
            'creator',
            'title',
            'description',
            'media_url',
            'metadata_hash',
            'is_derivative',
            'parent_asset',
            'royalty_percentage',
            'allow_derivatives',
            'commercial_rights',
            'derivative_count',
            'derivatives',
            'registration_status',
            'registration_error',
            'registration_attempts',
            'last_registration_attempt',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_derivatives(self, obj):
        """Get list of derivative assets."""
        # Use prefetched derivatives if available (optimized in view)
        if hasattr(obj, '_prefetched_objects_cache') and 'derivatives' in obj._prefetched_objects_cache:
            derivatives = obj._prefetched_objects_cache['derivatives']
        else:
            # Fallback to query if not prefetched
            derivatives = obj.derivatives.filter(is_deleted=False).select_related('creator')[:10]
        return IPAssetListSerializer(derivatives, many=True).data


class IPAssetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new IP asset."""

    # File upload field (will be handled separately for media upload)
    media_file = serializers.FileField(
        write_only=True,
        required=False,
        validators=[validate_file_size, validate_file_type, validate_file_name]
    )

    class Meta:
        model = IPAsset
        fields = [
            'title',
            'description',
            'media_file',
            'media_url',
            'royalty_percentage',
            'allow_derivatives',
            'commercial_rights',
        ]
        extra_kwargs = {
            'media_url': {'required': False},  # Can be provided or uploaded
        }

    def validate_royalty_percentage(self, value):
        """Validate royalty percentage is between 0 and 100."""
        if not (0 <= value <= 100):
            raise serializers.ValidationError(
                "Royalty percentage must be between 0 and 100"
            )
        return value

    def validate_media_url(self, value):
        """Validate media URL format if provided."""
        if value:
            validate_media_url(value)
        return value

    def validate(self, attrs):
        """Validate that either media_file or media_url is provided."""
        media_file = attrs.get('media_file')
        media_url = attrs.get('media_url')

        if not media_file and not media_url:
            raise serializers.ValidationError(
                "Either media_file or media_url must be provided"
            )

        return attrs

    def create(self, validated_data):
        """
        Create IP asset and register it on Story Protocol.
        This method will be called from the view after blockchain registration.
        """
        # Remove media_file from validated_data (handled in view)
        validated_data.pop('media_file', None)

        # Creator will be set in the view from request.user
        return super().create(validated_data)


class IPAssetUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating an IP asset (limited fields only)."""

    class Meta:
        model = IPAsset
        fields = ['title', 'description']
        
    def validate_title(self, value):
        """Validate title is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Title cannot be empty")
        return value.strip()
    
    def validate_description(self, value):
        """Validate description is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("Description cannot be empty")
        return value.strip()


class DerivativeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a derivative/remix of an existing IP asset."""

    parent_asset_id = serializers.IntegerField(write_only=True)
    media_file = serializers.FileField(
        write_only=True,
        required=False,
        validators=[validate_file_size, validate_file_type, validate_file_name]
    )

    class Meta:
        model = IPAsset
        fields = [
            'parent_asset_id',
            'title',
            'description',
            'media_file',
            'media_url',
            'commercial_rights',
        ]
        extra_kwargs = {
            'media_url': {'required': False},
        }

    def validate_media_url(self, value):
        """Validate media URL format if provided."""
        if value:
            validate_media_url(value)
        return value

    def validate_parent_asset_id(self, value):
        """Validate that parent asset exists and allows derivatives."""
        try:
            parent = IPAsset.objects.get(id=value, is_deleted=False)
        except IPAsset.DoesNotExist:
            raise serializers.ValidationError("Parent asset not found")

        if not parent.allow_derivatives:
            raise serializers.ValidationError(
                "Parent asset does not allow derivatives"
            )

        # Store parent for later use
        self.context['parent_asset'] = parent
        return value

    def validate(self, attrs):
        """Validate that either media_file or media_url is provided."""
        media_file = attrs.get('media_file')
        media_url = attrs.get('media_url')

        if not media_file and not media_url:
            raise serializers.ValidationError(
                "Either media_file or media_url must be provided"
            )

        return attrs

    def create(self, validated_data):
        """
        Create derivative asset and register it on Story Protocol.
        This method will be called from the view after blockchain registration.
        """
        parent_asset_id = validated_data.pop('parent_asset_id')
        validated_data.pop('media_file', None)

        # Set derivative-specific fields
        validated_data['is_derivative'] = True
        validated_data['parent_asset_id'] = parent_asset_id

        # Inherit parent's royalty settings
        parent = self.context.get('parent_asset')
        if parent:
            validated_data['royalty_percentage'] = parent.royalty_percentage

        return super().create(validated_data)


class RoyaltyPaymentSerializer(serializers.ModelSerializer):
    """Serializer for royalty payment records."""

    asset = IPAssetListSerializer(read_only=True)
    recipient = CreatorSerializer(read_only=True)

    class Meta:
        model = RoyaltyPayment
        fields = [
            'id',
            'asset',
            'recipient',
            'amount',
            'transaction_hash',
            'block_number',
            'created_at',
        ]
        read_only_fields = fields
