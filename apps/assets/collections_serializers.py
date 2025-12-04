"""
Serializers for Collections feature.
"""
from rest_framework import serializers
from .models import Collection
from .serializers import IPAssetListSerializer
from apps.core.serializers import CreatorSerializer


class CollectionListSerializer(serializers.ModelSerializer):
    """Serializer for listing collections."""
    
    creator = CreatorSerializer(read_only=True)
    asset_count = serializers.IntegerField(read_only=True)
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = [
            'id',
            'title',
            'description',
            'creator',
            'cover_image_url',
            'is_public',
            'asset_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_cover_image_url(self, obj):
        """Get cover image URL or use first asset's media URL."""
        if obj.cover_image_url:
            return obj.cover_image_url
        
        # Use first asset's media URL as cover
        first_asset = obj.assets.filter(is_deleted=False).first()
        if first_asset:
            return first_asset.media_url
        
        return None


class CollectionDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for collection view."""
    
    creator = CreatorSerializer(read_only=True)
    assets = serializers.SerializerMethodField()
    asset_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Collection
        fields = [
            'id',
            'title',
            'description',
            'creator',
            'cover_image_url',
            'is_public',
            'assets',
            'asset_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'creator', 'created_at', 'updated_at']

    def get_assets(self, obj):
        """Get list of assets in collection."""
        assets = obj.assets.filter(is_deleted=False).select_related('creator').order_by('-created_at')
        return IPAssetListSerializer(assets, many=True).data


class CollectionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new collection."""
    
    asset_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="List of asset IDs to add to collection"
    )

    class Meta:
        model = Collection
        fields = [
            'title',
            'description',
            'cover_image_url',
            'is_public',
            'asset_ids',
        ]

    def create(self, validated_data):
        """Create collection and add assets."""
        asset_ids = validated_data.pop('asset_ids', [])
        creator = self.context['request'].user
        
        collection = Collection.objects.create(
            creator=creator,
            **validated_data
        )
        
        # Add assets to collection
        if asset_ids:
            from .models import IPAsset
            assets = IPAsset.objects.filter(
                id__in=asset_ids,
                is_deleted=False
            )
            collection.assets.set(assets)
        
        return collection


class CollectionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a collection."""
    
    asset_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="List of asset IDs to replace collection assets"
    )

    class Meta:
        model = Collection
        fields = [
            'title',
            'description',
            'cover_image_url',
            'is_public',
            'asset_ids',
        ]

    def update(self, instance, validated_data):
        """Update collection and optionally update assets."""
        asset_ids = validated_data.pop('asset_ids', None)
        
        # Update collection fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update assets if provided
        if asset_ids is not None:
            from .models import IPAsset
            assets = IPAsset.objects.filter(
                id__in=asset_ids,
                is_deleted=False
            )
            instance.assets.set(assets)
        
        return instance

