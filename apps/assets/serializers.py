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


# ===== AI Feature Serializers =====

class TitleGenerationSerializer(serializers.Serializer):
    """Serializer for title generation request."""
    description = serializers.CharField(required=True, max_length=1000)
    asset_type = serializers.CharField(required=False, max_length=50)


class TitleGenerationResponseSerializer(serializers.Serializer):
    """Serializer for title generation response."""
    titles = serializers.ListField(child=serializers.CharField())
    model_used = serializers.CharField()
    log_id = serializers.IntegerField()


class DescriptionEnhancementSerializer(serializers.Serializer):
    """Serializer for description enhancement request."""
    description = serializers.CharField(required=True, max_length=500)
    title = serializers.CharField(required=False, max_length=255)
    asset_type = serializers.CharField(required=False, max_length=50)


class DescriptionEnhancementResponseSerializer(serializers.Serializer):
    """Serializer for description enhancement response."""
    enhanced_description = serializers.CharField()
    model_used = serializers.CharField()
    log_id = serializers.IntegerField()


class ContentAnalysisSerializer(serializers.Serializer):
    """Serializer for content analysis request."""
    title = serializers.CharField(required=True, max_length=255)
    description = serializers.CharField(required=True)
    media_url = serializers.URLField(required=False)


class ContentAnalysisResponseSerializer(serializers.Serializer):
    """Serializer for content analysis response."""
    category = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField())
    art_style = serializers.CharField(required=False, allow_null=True)
    theme = serializers.CharField(required=False, allow_null=True)
    genre = serializers.CharField(required=False, allow_null=True)
    model_used = serializers.CharField()
    log_id = serializers.IntegerField()


class LicenseSuggestionSerializer(serializers.Serializer):
    """Serializer for license suggestion request."""
    asset_type = serializers.CharField(required=True, max_length=50)
    description = serializers.CharField(required=True)
    intended_use = serializers.CharField(required=False)


class LicenseSuggestionResponseSerializer(serializers.Serializer):
    """Serializer for license suggestion response."""
    royalty_percentage = serializers.IntegerField(min_value=0, max_value=100)
    allow_derivatives = serializers.BooleanField()
    commercial_rights = serializers.BooleanField()
    reasoning = serializers.CharField()
    model_used = serializers.CharField()
    log_id = serializers.IntegerField()


class DerivativeAnalysisSerializer(serializers.Serializer):
    """Serializer for derivative analysis request."""
    parent_asset_id = serializers.IntegerField(required=True)
    derivative_description = serializers.CharField(required=True)
    derivative_title = serializers.CharField(required=False, max_length=255)

    def validate_parent_asset_id(self, value):
        """Validate that parent asset exists."""
        from .models import IPAsset
        try:
            parent = IPAsset.objects.get(id=value, is_deleted=False)
            self.context['parent_asset'] = parent
            return value
        except IPAsset.DoesNotExist:
            raise serializers.ValidationError("Parent asset not found")


class DerivativeAnalysisResponseSerializer(serializers.Serializer):
    """Serializer for derivative analysis response."""
    similarity_score = serializers.FloatField(min_value=0.0, max_value=1.0)
    transformation_type = serializers.CharField()
    suggested_attribution = serializers.CharField()
    key_differences = serializers.ListField(child=serializers.CharField())
    model_used = serializers.CharField()
    log_id = serializers.IntegerField()
