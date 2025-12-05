"""
Serializers for AI feature endpoints.
"""
from rest_framework import serializers


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
        from apps.assets.models import IPAsset
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

