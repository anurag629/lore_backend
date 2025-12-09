"""
Serializers for IP Asset API endpoints.
"""
from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import (
    IPAsset, RoyaltyPayment, GroupIP, GroupIPMembership, GroupRoyaltyDistribution,
    Dispute, DisputeEvidence, DerivativeRelationship, IPAccountPermission, MintingFeePayment
)
from apps.core.models import LoreUser
from .validators import (
    validate_file_size,
    validate_file_type,
    validate_file_name,
    validate_media_url
)


class CreatorSerializer(serializers.ModelSerializer):
    """Serializer for asset creator information."""
    # User uses wallet_address as public ID, not UUID
    id = serializers.IntegerField(read_only=True)  # Keep internal ID for user

    class Meta:
        model = LoreUser
        fields = ['id', 'wallet_address', 'display_name', 'avatar_url']
        read_only_fields = fields


class IPAssetListSerializer(serializers.ModelSerializer):
    """Serializer for listing IP assets (used in browse/explore pages)."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    derivative_count = serializers.SerializerMethodField()
    parent_asset_id = serializers.SerializerMethodField()
    is_deleted = serializers.BooleanField(read_only=True)
    deleted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    minting_fee = serializers.DecimalField(max_digits=10, decimal_places=6, read_only=True)

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
            'parent_asset_id',
            'derivative_count',
            'allow_derivatives',
            'commercial_rights',
            'minting_fee',
            'registration_status',
            'is_deleted',
            'deleted_at',
            'created_at',
        ]
        read_only_fields = fields

    def get_derivative_count(self, obj):
        """Get derivative count - use annotated value if available."""
        # Use annotated count if available (from queryset optimization)
        if hasattr(obj, 'derivative_count_annotated'):
            return obj.derivative_count_annotated
        # Fallback to property (which now includes both legacy and M2M)
        return obj.derivative_count

    def get_parent_asset_id(self, obj):
        """Get parent asset UUID (supports both legacy FK and M2M relationships)."""
        # Check legacy FK first (primary parent for old single-parent derivatives)
        if obj.parent_asset_id:
            return str(obj.parent_asset.uuid)

        # Fallback to M2M - get first parent from relationships
        # Use prefetched data if available
        if hasattr(obj, '_prefetched_objects_cache') and 'parent_relationships' in obj._prefetched_objects_cache:
            relationships = obj._prefetched_objects_cache['parent_relationships']
            if relationships:
                return str(relationships[0].parent_asset.uuid)
        else:
            first_rel = obj.parent_relationships.select_related('parent_asset').first()
            if first_rel:
                return str(first_rel.parent_asset.uuid)

        return None


class ParentAssetSerializer(serializers.ModelSerializer):
    """Serializer for parent asset information (used in derivatives)."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    minting_fee = serializers.DecimalField(max_digits=10, decimal_places=6, read_only=True)

    class Meta:
        model = IPAsset
        fields = ['id', 'story_ip_id', 'title', 'creator', 'media_url', 'minting_fee']
        read_only_fields = fields


class IPAssetDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual IP asset view."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    parent_asset = ParentAssetSerializer(read_only=True)
    parent_asset_id = serializers.SerializerMethodField()
    parent_relationships = serializers.SerializerMethodField()
    derivative_count = serializers.IntegerField(read_only=True)
    derivatives = serializers.SerializerMethodField()
    minting_fee = serializers.DecimalField(max_digits=10, decimal_places=6, read_only=True)

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
            'parent_asset_id',
            'parent_relationships',
            'royalty_percentage',
            'allow_derivatives',
            'commercial_rights',
            'minting_fee',
            'derivative_count',
            'derivatives',
            'registration_status',
            'registration_error',
            'registration_attempts',
            'last_registration_attempt',
            'creation_step',
            'failed_at_step',
            'step_data',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_parent_asset_id(self, obj):
        """Get parent asset UUID (supports both legacy FK and M2M relationships)."""
        # Check legacy FK first
        if obj.parent_asset_id:
            return str(obj.parent_asset.uuid)

        # Check M2M relationship - use prefetched data if available
        if hasattr(obj, '_prefetched_objects_cache') and 'parent_relationships' in obj._prefetched_objects_cache:
            relationships = obj._prefetched_objects_cache['parent_relationships']
            if relationships:
                return str(relationships[0].parent_asset.uuid)
        else:
            first_rel = obj.parent_relationships.select_related('parent_asset').first()
            if first_rel:
                return str(first_rel.parent_asset.uuid)

        return None

    def get_parent_relationships(self, obj):
        """Get all parent relationships with attribution percentages."""
        if not obj.is_derivative:
            return []

        # Use prefetched relationships if available
        if hasattr(obj, '_prefetched_objects_cache') and 'parent_relationships' in obj._prefetched_objects_cache:
            relationships = obj._prefetched_objects_cache['parent_relationships']
        else:
            # Fallback to query if not prefetched
            relationships = obj.parent_relationships.select_related(
                'parent_asset__creator'
            ).all()

        # Import here to avoid circular dependency
        return DerivativeRelationshipSerializer(relationships, many=True).data

    def get_derivatives(self, obj):
        """Get list of derivative assets (includes both legacy FK and M2M relationships)."""
        # Use the new method that combines both relationship types
        derivatives = list(obj.get_all_derivatives())

        # Sort by created_at descending and limit to 20
        derivatives = sorted(derivatives, key=lambda x: x.created_at, reverse=True)[:20]

        return IPAssetListSerializer(derivatives, many=True).data


class IPAssetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new IP asset."""

    # File upload field (will be handled separately for media upload)
    media_file = serializers.FileField(
        write_only=True,
        required=False,
        validators=[validate_file_size, validate_file_type, validate_file_name]
    )
    minting_fee = serializers.DecimalField(
        max_digits=10,
        decimal_places=6,
        required=False,
        help_text="Minting fee in ETH for derivative creation (set by creator)"
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
            'minting_fee',
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

    def validate_minting_fee(self, value):
        """Validate minting fee is non-negative and within reasonable bounds."""
        from decimal import Decimal
        if value is None:
            return Decimal('0.005')  # Default minting fee
        if value < 0:
            raise serializers.ValidationError(
                "Minting fee cannot be negative"
            )
        if value > Decimal('0.5'):
            raise serializers.ValidationError(
                "Minting fee cannot exceed 0.5 ETH"
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

    parent_asset_id = serializers.UUIDField(write_only=True)
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
            parent = IPAsset.objects.get(uuid=value, is_deleted=False)
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
        validated_data.pop('parent_asset_id')  # Remove UUID, we'll use parent object
        validated_data.pop('media_file', None)

        # Set derivative-specific fields
        validated_data['is_derivative'] = True

        # Use parent object from context (set during validation)
        # This sets the ForeignKey correctly using the model instance
        parent = self.context.get('parent_asset')
        if parent:
            validated_data['parent_asset'] = parent  # Set FK to parent object, not UUID
            validated_data['royalty_percentage'] = parent.royalty_percentage

        return super().create(validated_data)


class DerivativeRelationshipSerializer(serializers.ModelSerializer):
    """Serializer for derivative-parent relationships."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    parent_asset = ParentAssetSerializer(read_only=True)
    parent_asset_id = serializers.UUIDField(write_only=True, required=False)
    fee_paid = serializers.DecimalField(max_digits=10, decimal_places=6, read_only=True)

    class Meta:
        model = DerivativeRelationship
        fields = [
            'id',
            'parent_asset',
            'parent_asset_id',
            'attribution_percentage',
            'license_terms_id',
            'fee_paid',
            'transaction_hash',
            'created_at',
        ]
        read_only_fields = ['id', 'parent_asset', 'fee_paid', 'transaction_hash', 'created_at']

    def validate_attribution_percentage(self, value):
        """Validate attribution percentage is between 0 and 100."""
        if not (0 < value <= 100):
            raise serializers.ValidationError(
                "Attribution percentage must be between 0 and 100"
            )
        return value


class MintingFeePaymentSerializer(serializers.ModelSerializer):
    """Serializer for minting fee payment records."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    payer_username = serializers.CharField(source='payer.display_name', read_only=True)
    payer_id = serializers.IntegerField(source='payer.id', read_only=True)
    derivative_title = serializers.CharField(source='derivative_asset.title', read_only=True)
    derivative_id = serializers.UUIDField(source='derivative_asset.uuid', read_only=True)
    parent_title = serializers.CharField(source='parent_asset.title', read_only=True)
    parent_id = serializers.UUIDField(source='parent_asset.uuid', read_only=True)
    parent_creator = serializers.CharField(source='parent_asset.creator.display_name', read_only=True)
    parent_creator_id = serializers.IntegerField(source='parent_asset.creator.id', read_only=True)

    class Meta:
        model = MintingFeePayment
        fields = [
            'id',
            'payer_username',
            'payer_id',
            'derivative_title',
            'derivative_id',
            'parent_title',
            'parent_id',
            'parent_creator',
            'parent_creator_id',
            'fee_amount',
            'fee_amount_wei',
            'platform_fee',
            'creator_fee',
            'attribution_percentage',
            'transaction_hash',
            'block_number',
            'status',
            'created_at',
            'paid_at',
            'claimed_at',
        ]
        read_only_fields = fields


class MultiParentDerivativeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a derivative with multiple parent assets."""

    parent_assets = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        min_length=1,
        max_length=10,
        help_text="List of parent assets with attribution percentages"
    )
    media_file = serializers.FileField(
        write_only=True,
        required=False,
        validators=[validate_file_size, validate_file_type, validate_file_name]
    )

    class Meta:
        model = IPAsset
        fields = [
            'parent_assets',
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

    def validate_parent_assets(self, value):
        """
        Validate parent assets list.
        Each parent must have:
        - parent_asset_id: UUID of the parent asset
        - attribution_percentage: float between 0 and 100

        Total attribution percentages must sum to 100.
        """
        if not value:
            raise serializers.ValidationError("At least one parent asset is required")

        if len(value) > 10:
            raise serializers.ValidationError("Maximum 10 parent assets allowed")

        total_attribution = 0
        validated_parents = []
        parent_ids_seen = set()

        for idx, parent_data in enumerate(value):
            # Validate required fields
            if 'parent_asset_id' not in parent_data:
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: 'parent_asset_id' is required"
                )

            if 'attribution_percentage' not in parent_data:
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: 'attribution_percentage' is required"
                )

            # Parse and validate parent_asset_id
            try:
                parent_id = str(parent_data['parent_asset_id'])
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: Invalid parent_asset_id format"
                )

            # Check for duplicate parents
            if parent_id in parent_ids_seen:
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: Duplicate parent asset ID"
                )
            parent_ids_seen.add(parent_id)

            # Validate parent exists and allows derivatives
            try:
                parent = IPAsset.objects.get(uuid=parent_id, is_deleted=False)
            except IPAsset.DoesNotExist:
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: Asset not found"
                )

            if not parent.allow_derivatives:
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: '{parent.title}' does not allow derivatives"
                )

            # Validate attribution percentage
            try:
                attribution = float(parent_data['attribution_percentage'])
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: Invalid attribution_percentage"
                )

            if not (0 < attribution <= 100):
                raise serializers.ValidationError(
                    f"Parent {idx + 1}: Attribution percentage must be between 0 and 100"
                )

            total_attribution += attribution

            validated_parents.append({
                'parent_asset': parent,
                'parent_asset_id': parent_id,
                'attribution_percentage': attribution,
                'license_terms_id': parent_data.get('license_terms_id', '')
            })

        # Validate total attribution sums to 100 (with small tolerance for floating point)
        if abs(total_attribution - 100.0) > 0.01:
            raise serializers.ValidationError(
                f"Total attribution percentages must sum to 100 (current: {total_attribution})"
            )

        # Store validated parents in context for later use
        self.context['validated_parents'] = validated_parents

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
        Create derivative asset with multiple parents.
        The parent relationships will be created after the asset is saved.
        """
        validated_data.pop('parent_assets')  # Will be handled separately
        validated_data.pop('media_file', None)  # Handled in view

        # Set derivative-specific fields
        validated_data['is_derivative'] = True

        # Calculate weighted average royalty percentage from parents
        validated_parents = self.context.get('validated_parents', [])
        if validated_parents:
            weighted_royalty = sum(
                parent['parent_asset'].royalty_percentage * parent['attribution_percentage'] / 100
                for parent in validated_parents
            )
            validated_data['royalty_percentage'] = round(weighted_royalty, 2)

        return super().create(validated_data)


class RoyaltyPaymentSerializer(serializers.ModelSerializer):
    """Serializer for royalty payment records."""

    id = serializers.UUIDField(source='uuid', read_only=True)
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


# ===== Group IP Serializers =====

class GroupIPMembershipSerializer(serializers.ModelSerializer):
    """Serializer for Group IP membership."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    asset = IPAssetListSerializer(read_only=True)
    asset_id = serializers.UUIDField(write_only=True, required=False)
    added_by = CreatorSerializer(read_only=True)

    class Meta:
        model = GroupIPMembership
        fields = [
            'id',
            'asset',
            'asset_id',
            'revenue_share_percentage',
            'added_by',
            'is_active',
            'added_at',
            'removed_at',
            'transaction_hash',
        ]
        read_only_fields = ['id', 'asset', 'added_by', 'added_at', 'removed_at', 'transaction_hash']


class GroupIPListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Group IP list views."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    total_revenue_share = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = GroupIP
        fields = [
            'id',
            'story_group_id',
            'name',
            'description',
            'creator',
            'total_royalty_percentage',
            'registration_status',
            'is_active',
            'member_count',
            'total_revenue_share',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'story_group_id', 'registration_status', 'created_at', 'updated_at']


class GroupIPDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Group IP with members."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    creator = CreatorSerializer(read_only=True)
    members = GroupIPMembershipSerializer(many=True, read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    total_revenue_share = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = GroupIP
        fields = [
            'id',
            'story_group_id',
            'name',
            'description',
            'creator',
            'royalty_pool_address',
            'total_royalty_percentage',
            'registration_status',
            'registration_transaction_hash',
            'is_active',
            'members',
            'member_count',
            'total_revenue_share',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'story_group_id',
            'registration_status',
            'registration_transaction_hash',
            'royalty_pool_address',
            'created_at',
            'updated_at'
        ]


class GroupIPCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new Group IP."""

    class Meta:
        model = GroupIP
        fields = [
            'name',
            'description',
            'total_royalty_percentage',
        ]

    def validate_total_royalty_percentage(self, value):
        """Validate royalty percentage is within bounds."""
        if not 0 <= value <= 100:
            raise serializers.ValidationError("Royalty percentage must be between 0 and 100")
        return value


class AddMemberToGroupSerializer(serializers.Serializer):
    """Serializer for adding a member to a Group IP."""

    asset_id = serializers.UUIDField(required=True)
    revenue_share_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=True
    )

    def validate_revenue_share_percentage(self, value):
        """Validate revenue share percentage."""
        if not 0 <= value <= 100:
            raise serializers.ValidationError("Revenue share percentage must be between 0 and 100")
        return value

    def validate_asset_id(self, value):
        """Validate asset exists."""
        try:
            IPAsset.objects.get(uuid=value)
        except IPAsset.DoesNotExist:
            raise serializers.ValidationError(f"Asset with ID {value} not found")
        return value


class GroupRoyaltyDistributionSerializer(serializers.ModelSerializer):
    """Serializer for Group IP royalty distributions."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    group = GroupIPListSerializer(read_only=True)
    membership = GroupIPMembershipSerializer(read_only=True)

    class Meta:
        model = GroupRoyaltyDistribution
        fields = [
            'id',
            'group',
            'membership',
            'amount',
            'transaction_hash',
            'block_number',
            'distributed_at',
        ]
        read_only_fields = fields


# ===== Dispute Serializers =====

class DisputeEvidenceSerializer(serializers.ModelSerializer):
    """Serializer for dispute evidence."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    submitted_by = CreatorSerializer(read_only=True)

    class Meta:
        model = DisputeEvidence
        fields = [
            'id',
            'submitted_by',
            'description',
            'evidence_url',
            'evidence_ipfs_hash',
            'transaction_hash',
            'submitted_at',
        ]
        read_only_fields = ['id', 'submitted_by', 'transaction_hash', 'submitted_at']


class DisputeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dispute list views."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    target_asset = IPAssetListSerializer(read_only=True)
    disputer = CreatorSerializer(read_only=True)
    evidence_count = serializers.IntegerField(read_only=True)
    is_resolved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Dispute
        fields = [
            'id',
            'story_dispute_id',
            'target_asset',
            'disputer',
            'reason',
            'status',
            'result',
            'evidence_count',
            'is_resolved',
            'raised_at',
            'resolved_at',
        ]
        read_only_fields = fields


class DisputeDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for disputes with evidence."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    target_asset = IPAssetListSerializer(read_only=True)
    disputer = CreatorSerializer(read_only=True)
    resolved_by = CreatorSerializer(read_only=True)
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    evidence_count = serializers.IntegerField(read_only=True)
    is_resolved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Dispute
        fields = [
            'id',
            'story_dispute_id',
            'target_asset',
            'disputer',
            'reason',
            'evidence_ipfs_hash',
            'status',
            'result',
            'resolution_notes',
            'resolved_by',
            'raise_transaction_hash',
            'resolve_transaction_hash',
            'evidence',
            'evidence_count',
            'is_resolved',
            'raised_at',
            'resolved_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'story_dispute_id',
            'raise_transaction_hash',
            'resolve_transaction_hash',
            'raised_at',
            'resolved_at',
            'updated_at'
        ]


class RaiseDisputeSerializer(serializers.Serializer):
    """Serializer for raising a new dispute."""

    asset_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(min_length=10, required=True)
    evidence_hash = serializers.CharField(max_length=66, required=False, allow_blank=True)
    disputer_address = serializers.CharField(max_length=42, required=False)

    def validate_asset_id(self, value):
        """Validate asset exists."""
        try:
            IPAsset.objects.get(uuid=value)
        except IPAsset.DoesNotExist:
            raise serializers.ValidationError(f"Asset with ID {value} not found")
        return value


class SubmitEvidenceSerializer(serializers.Serializer):
    """Serializer for submitting evidence to a dispute."""

    description = serializers.CharField(min_length=10, required=True)
    evidence_url = serializers.URLField(required=False, allow_blank=True)
    evidence_hash = serializers.CharField(max_length=66, required=False, allow_blank=True)


class ResolveDisputeSerializer(serializers.Serializer):
    """Serializer for resolving a dispute."""

    result = serializers.ChoiceField(choices=Dispute.RESULT_CHOICES, required=True)
    resolution_notes = serializers.CharField(required=False, allow_blank=True)


# ===== IP Account Permission Serializers =====

class IPAccountPermissionSerializer(serializers.ModelSerializer):
    """Serializer for IP Account Permissions."""

    id = serializers.UUIDField(source='uuid', read_only=True)
    asset_id = serializers.UUIDField(source='asset.uuid', read_only=True)
    asset_title = serializers.CharField(source='asset.title', read_only=True)
    granted_by = CreatorSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    permission_type_display = serializers.CharField(source='get_permission_type_display', read_only=True)

    class Meta:
        model = IPAccountPermission
        fields = [
            'id',
            'asset_id',
            'asset_title',
            'grantee_address',
            'permission_type',
            'permission_type_display',
            'is_granted',
            'is_active',
            'is_expired',
            'expires_at',
            'transaction_hash',
            'block_number',
            'notes',
            'granted_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'asset_id', 'asset_title', 'is_active', 'is_expired',
            'permission_type_display', 'transaction_hash', 'block_number',
            'granted_by', 'created_at', 'updated_at'
        ]


class SetPermissionSerializer(serializers.Serializer):
    """Serializer for setting a single permission."""

    grantee_address = serializers.CharField(max_length=42, required=True)
    permission_type = serializers.ChoiceField(
        choices=IPAccountPermission.PERMISSION_TYPES,
        required=True
    )
    is_granted = serializers.BooleanField(default=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate_grantee_address(self, value):
        """Validate grantee address format."""
        from apps.core.utils import normalize_wallet_address
        try:
            return normalize_wallet_address(value)
        except Exception as e:
            raise serializers.ValidationError(f"Invalid wallet address: {e}")

    def validate_expires_at(self, value):
        """Validate expiration is in the future."""
        if value:
            from django.utils import timezone
            if value <= timezone.now():
                raise serializers.ValidationError("Expiration time must be in the future")
        return value


class SetAllPermissionsSerializer(serializers.Serializer):
    """Serializer for setting all permissions at once."""

    grantee_address = serializers.CharField(max_length=42, required=True)
    is_granted = serializers.BooleanField(default=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate_grantee_address(self, value):
        """Validate grantee address format."""
        from apps.core.utils import normalize_wallet_address
        try:
            return normalize_wallet_address(value)
        except Exception as e:
            raise serializers.ValidationError(f"Invalid wallet address: {e}")

    def validate_expires_at(self, value):
        """Validate expiration is in the future."""
        if value:
            from django.utils import timezone
            if value <= timezone.now():
                raise serializers.ValidationError("Expiration time must be in the future")
        return value


class PermissionSummarySerializer(serializers.Serializer):
    """Serializer for permission summary response."""

    grantee_address = serializers.CharField()
    permissions = serializers.DictField(child=serializers.BooleanField())
    active_count = serializers.IntegerField()
    total_count = serializers.IntegerField()
