"""
Serializers for Favorites feature.
"""
from rest_framework import serializers
from .models import Favorite, IPAsset
from apps.core.serializers import CreatorSerializer


class FavoriteSerializer(serializers.ModelSerializer):
    """Serializer for Favorite model."""
    
    asset = serializers.SerializerMethodField()
    user = CreatorSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = [
            'id',
            'user',
            'asset',
            'created_at',
        ]
        read_only_fields = fields

    def get_asset(self, obj):
        """Get asset details."""
        from .serializers import IPAssetListSerializer
        return IPAssetListSerializer(obj.asset).data


class FavoriteCreateSerializer(serializers.Serializer):
    """Serializer for creating a favorite."""
    
    asset_id = serializers.IntegerField(required=True)

    def validate_asset_id(self, value):
        """Validate that asset exists and is not deleted."""
        try:
            asset = IPAsset.objects.get(id=value, is_deleted=False)
            return value
        except IPAsset.DoesNotExist:
            raise serializers.ValidationError("Asset not found")

