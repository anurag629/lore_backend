"""
Serializers for Collections and Favorites features.
"""
from rest_framework import serializers
from .models import Collection, Favorite
from apps.assets.serializers import IPAssetListSerializer
from apps.core.serializers import CreatorSerializer


class CollectionListSerializer(serializers.ModelSerializer):
    """Serializer for listing collections."""
    
    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    asset_count = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    def get_asset_count(self, obj):
        """Get asset count from annotation or property."""
        # Use annotated value if available (from optimized queryset)
        if hasattr(obj, 'asset_count_annotated'):
            return obj.asset_count_annotated
        # Fallback to model property
        return obj.asset_count

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
    
    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    assets = serializers.SerializerMethodField()
    asset_count = serializers.SerializerMethodField()

    def get_asset_count(self, obj):
        """Get asset count from annotation or property."""
        # Use annotated value if available (from optimized queryset)
        if hasattr(obj, 'asset_count_annotated'):
            return obj.asset_count_annotated
        # Fallback to model property
        return obj.asset_count

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
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        help_text="List of asset UUIDs to add to collection"
    )
    cover_image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Cover image file to upload to IPFS"
    )

    class Meta:
        model = Collection
        fields = [
            'title',
            'description',
            'cover_image_url',
            'cover_image',
            'is_public',
            'asset_ids',
        ]

    def create(self, validated_data):
        """Create collection and add assets."""
        asset_ids = validated_data.pop('asset_ids', [])
        cover_image = validated_data.pop('cover_image', None)
        
        # Handle cover image upload to IPFS
        if cover_image:
            from apps.assets.services.pinata_service import get_pinata_service
            pinata = get_pinata_service()
            result = pinata.upload_file(cover_image, f"collection-cover-{cover_image.name}")
            validated_data['cover_image_url'] = result['url']
        
        # creator is passed via serializer.save(creator=user) in the view
        collection = Collection.objects.create(**validated_data)
        
        # Add assets to collection by UUID
        if asset_ids:
            from apps.assets.models import IPAsset
            assets = IPAsset.objects.filter(
                uuid__in=asset_ids,
                is_deleted=False
            )
            collection.assets.set(assets)
        
        return collection


class CollectionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a collection."""
    
    asset_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        help_text="List of asset UUIDs to replace collection assets"
    )
    cover_image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Cover image file to upload to IPFS"
    )

    class Meta:
        model = Collection
        fields = [
            'title',
            'description',
            'cover_image_url',
            'cover_image',
            'is_public',
            'asset_ids',
        ]

    def update(self, instance, validated_data):
        """Update collection and optionally update assets."""
        asset_ids = validated_data.pop('asset_ids', None)
        cover_image = validated_data.pop('cover_image', None)
        
        # Handle cover image upload to IPFS
        if cover_image:
            from apps.assets.services.pinata_service import get_pinata_service
            pinata = get_pinata_service()
            result = pinata.upload_file(cover_image, f"collection-cover-{cover_image.name}")
            validated_data['cover_image_url'] = result['url']
        
        # Update collection fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update assets if provided (by UUID)
        if asset_ids is not None:
            from apps.assets.models import IPAsset
            assets = IPAsset.objects.filter(
                uuid__in=asset_ids,
                is_deleted=False
            )
            instance.assets.set(assets)
        
        return instance


class FavoriteSerializer(serializers.ModelSerializer):
    """Serializer for Favorite model."""
    
    id = serializers.UUIDField(source='uuid', read_only=True)
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
        return IPAssetListSerializer(obj.asset).data


class FavoriteCreateSerializer(serializers.Serializer):
    """Serializer for creating a favorite."""
    
    asset_id = serializers.UUIDField(required=True)

    def validate_asset_id(self, value):
        """Validate that asset exists and is not deleted."""
        from apps.assets.models import IPAsset
        try:
            asset = IPAsset.objects.get(uuid=value, is_deleted=False)
            return value
        except IPAsset.DoesNotExist:
            raise serializers.ValidationError("Asset not found")
