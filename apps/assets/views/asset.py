"""
API views for IP Asset management.
Integrates with Story Protocol for blockchain operations.
"""
import json
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from rest_framework.exceptions import NotFound
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import F, Count, Q, Prefetch
from django.utils import timezone
from apps.core.utils import normalize_wallet_address

from ..models import IPAsset, RoyaltyPayment, DerivativeRelationship
from ..serializers import (
    IPAssetListSerializer,
    IPAssetDetailSerializer,
    IPAssetCreateSerializer,
    IPAssetUpdateSerializer,
    DerivativeCreateSerializer,
    MultiParentDerivativeCreateSerializer,
    RoyaltyPaymentSerializer,
)
from ..services import get_story_service, get_pinata_service
from ..throttles import UploadRateThrottle
from ..filters import IPAssetFilter
from ..cache import (
    get_cached_asset_list,
    cache_asset_list,
    get_cached_asset_detail,
    cache_asset_detail,
    invalidate_asset_cache,
)
from rest_framework.decorators import throttle_classes
from rest_framework.filters import SearchFilter, OrderingFilter
import django_filters.rest_framework

logger = logging.getLogger(__name__)


class IPAssetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for IP Asset CRUD operations.
    Handles asset creation, listing, retrieval, and Story Protocol integration.
    """

    queryset = IPAsset.objects.select_related('creator', 'parent_asset').prefetch_related('derivatives').all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    throttle_classes = [UploadRateThrottle]
    throttle_scope = 'upload'
    filterset_class = IPAssetFilter
    search_fields = ['title', 'description', 'creator__wallet_address']
    ordering_fields = ['created_at', 'title', 'royalty_percentage']
    ordering = ['-created_at']
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    # Use UUID for lookups instead of integer pk
    lookup_field = 'uuid'

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return IPAssetCreateSerializer
        elif self.action == 'update' or self.action == 'partial_update':
            return IPAssetUpdateSerializer
        elif self.action in ['retrieve']:
            return IPAssetDetailSerializer
        else:
            return IPAssetListSerializer

    def get_queryset(self):
        """
        Get queryset with optimizations.
        Filtering is handled by django-filter.
        
        Rules:
        - Explore (list view without creator filter): Only show registered assets
        - Dashboard (list view with creator filter for own assets): Show ALL statuses
        - Detail view: Show asset regardless of status (for viewing failed assets)
        - Archive view: When is_deleted=true query param is provided and user is viewing own assets, show only archived assets
        """
        queryset = super().get_queryset()
        
        # Check if user is viewing their own assets
        # The creator filter can be either user ID or wallet address
        creator_param = self.request.query_params.get('creator')
        is_viewing_own_assets = False
        
        if creator_param and self.request.user.is_authenticated:
            try:
                # Try to parse as integer (user ID)
                creator_id = int(creator_param)
                is_viewing_own_assets = creator_id == self.request.user.id
            except (ValueError, TypeError):
                # Not a number, treat as wallet address
                is_viewing_own_assets = (
                    creator_param.lower() == self.request.user.wallet_address.lower()
                )
        
        # Handle is_deleted query parameter for archive functionality
        # Only allow viewing archived assets when user is viewing their own assets
        is_deleted_param = self.request.query_params.get('is_deleted', '').lower()
        show_archived = is_deleted_param == 'true'
        
        if show_archived and is_viewing_own_assets:
            # Show only archived assets (for Archived tab in dashboard)
            queryset = queryset.filter(is_deleted=True)
        elif not self.request.user.is_staff:
            # Default: filter out deleted assets (for Active tab and explore pages)
            queryset = queryset.filter(is_deleted=False)
        
        # For list view: filter by registration status
        if self.action == 'list':
            # If user is viewing their own assets, show ALL statuses
            # Otherwise, only show registered assets (for explore page)
            if not is_viewing_own_assets:
                queryset = queryset.filter(registration_status='registered')
            
            # Annotate derivative count to avoid N+1 queries
            queryset = queryset.annotate(
                derivative_count_annotated=Count(
                    'derivatives',
                    filter=Q(derivatives__is_deleted=False, derivatives__registration_status='registered')
                )
            )
        elif self.action == 'retrieve':
            # For detail view, allow viewing any asset (registered or not)
            # But filter by registration_status for non-owners viewing other users' assets
            # This allows users to view their own failed assets, but prevents viewing others' failed assets
            pass  # No filtering needed - we'll handle this in get_object()
        
        return queryset
    
    def get_object(self):
        """
        Override get_object to allow users to view their own assets regardless of status,
        but only allow viewing registered assets from other users.
        """
        obj = super().get_object()
        
        # If user is authenticated and owns the asset, allow viewing regardless of status
        if self.request.user.is_authenticated and obj.creator_id == self.request.user.id:
            return obj
        
        # For other users' assets, only allow viewing if registered
        if obj.registration_status != 'registered':
            raise NotFound("Asset not found")
        
        return obj

    def list(self, request, *args, **kwargs):
        """
        List assets with caching.
        """
        # Build cache key from query params (include creator for proper caching)
        cache_params = {
            'search': request.query_params.get('search', ''),
            'is_derivative': request.query_params.get('is_derivative', ''),
            'creator': request.query_params.get('creator', ''),
            'page': request.query_params.get('page', '1'),
            'ordering': request.query_params.get('ordering', '-created_at'),
        }
        
        # Try to get from cache
        cached_response = get_cached_asset_list(cache_params)
        if cached_response:
            # Note: Cache versioning should prevent stale cache, but we return cached response
            # The queryset filtering (is_deleted=False) happens in get_queryset() which is
            # called by super().list(), so cached responses should already be filtered.
            # However, if cache was created before an asset was deleted, it might contain it.
            # Cache versioning should handle this, but we'll return the cached response.
            # The real fix is ensuring cache invalidation works (via version increment).
            return Response(cached_response)
        
        # Get response from super (applies is_deleted=False filter via get_queryset)
        response = super().list(request, *args, **kwargs)
        
        # Cache the response
        # Note: We trust that get_queryset() has already filtered out deleted assets
        # via is_deleted=False filter, so we can safely cache the response
        if response.status_code == 200:
            cache_asset_list(cache_params, response.data)
        
        return response

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve asset with caching.
        """
        asset_uuid = kwargs.get('uuid')
        
        # Try to get from cache
        cached_response = get_cached_asset_detail(asset_uuid)
        if cached_response:
            return Response(cached_response)
        
        # Get response from super
        response = super().retrieve(request, *args, **kwargs)
        
        # Cache the response
        if response.status_code == 200:
            cache_asset_detail(asset_uuid, response.data)
        
        return response

    def update(self, request, *args, **kwargs):
        """
        Update asset with cache invalidation.
        Only the creator can update their own asset.
        """
        asset = self.get_object()

        # Check if user is the creator of the asset
        if asset.creator.id != request.user.id:
            return Response(
                {'error': 'You can only update your own assets'},
                status=status.HTTP_403_FORBIDDEN
            )

        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            asset_uuid = kwargs.get('uuid')
            invalidate_asset_cache(asset_uuid=asset_uuid)
        return response

    def partial_update(self, request, *args, **kwargs):
        """
        Partial update asset with cache invalidation.
        Only the creator can update their own asset.
        """
        asset = self.get_object()

        # Check if user is the creator of the asset
        if asset.creator.id != request.user.id:
            return Response(
                {'error': 'You can only update your own assets'},
                status=status.HTTP_403_FORBIDDEN
            )

        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200:
            asset_uuid = kwargs.get('uuid')
            invalidate_asset_cache(asset_uuid=asset_uuid)
        return response

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete asset with cache invalidation.
        Only the creator can delete their own asset.
        """
        asset = self.get_object()

        # Check if user is the creator of the asset
        if asset.creator.id != request.user.id:
            return Response(
                {'error': 'You can only delete your own assets'},
                status=status.HTTP_403_FORBIDDEN
            )

        asset_id = asset.id
        asset_uuid = str(asset.uuid)

        # Perform soft delete
        asset.is_deleted = True
        asset.deleted_at = timezone.now()
        asset.save(update_fields=['is_deleted', 'deleted_at'])

        # Invalidate cache by UUID (since API uses UUID for lookups)
        invalidate_asset_cache(asset_uuid=asset_uuid)

        # Verify cache version was incremented
        from ..cache import get_asset_list_cache_version
        new_version = get_asset_list_cache_version()
        logger.info(f"Asset {asset_uuid} (ID: {asset_id}) soft deleted by user {request.user.wallet_address}. Cache version: {new_version}")

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def restore(self, request, uuid=None):
        """
        Restore an archived asset.
        Only the creator can restore their own asset.
        """
        asset = self.get_object()
        
        # Check ownership
        if asset.creator.id != request.user.id:
            return Response(
                {'error': 'You can only restore your own assets'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if actually deleted
        if not asset.is_deleted:
            return Response(
                {'error': 'Asset is not archived'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Restore asset
        asset.is_deleted = False
        asset.deleted_at = None
        asset.save(update_fields=['is_deleted', 'deleted_at'])
        
        # Invalidate cache
        asset_uuid = str(asset.uuid)
        invalidate_asset_cache(asset_uuid=asset_uuid)
        
        logger.info(f"Asset {asset_uuid} restored by user {request.user.wallet_address}")
        return Response({
            'success': True,
            'message': 'Asset restored successfully'
        })

    @action(detail=True, methods=['delete'], permission_classes=[IsAuthenticated])
    def permanent_delete(self, request, uuid=None):
        """
        Permanently delete an asset from database.
        Only the creator can permanently delete their own asset.
        Asset must be archived first before permanent deletion.
        
        Note: Blockchain registration cannot be removed (blockchain is immutable).
        This only removes the asset from our database.
        """
        asset = self.get_object()
        
        # Check ownership
        if asset.creator.id != request.user.id:
            return Response(
                {'error': 'You can only delete your own assets'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if actually deleted (must be archived first)
        if not asset.is_deleted:
            return Response(
                {'error': 'Asset must be archived before permanent deletion'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        asset_uuid = str(asset.uuid)
        asset_id = asset.id
        
        # Note: Blockchain registration cannot be removed (immutable)
        # We can only remove from our database
        asset.delete()  # Hard delete from database
        
        # Invalidate cache
        invalidate_asset_cache(asset_uuid=asset_uuid)
        
        logger.warning(f"Asset {asset_uuid} (ID: {asset_id}) permanently deleted by user {request.user.wallet_address}")
        return Response({
            'success': True,
            'message': 'Asset permanently deleted'
        })

    # ==================== CREATION STEP HELPERS ====================
    # These methods are idempotent - they check if a step is already completed
    
    def _step_upload_media(self, asset, media_file=None, media_url=None, pinata_service=None):
        """
        Step 1: Upload media to IPFS (idempotent).
        Returns: (media_url, media_ipfs_hash) or raises exception
        """
        # Check if already uploaded
        if asset.media_ipfs_hash and asset.media_url:
            logger.info(f"Media already uploaded for asset {asset.id}, using existing: {asset.media_ipfs_hash}")
            return asset.media_url, asset.media_ipfs_hash
        
        if not media_file and not media_url:
            raise ValueError("Either media_file or media_url must be provided")
        
        if media_url and not media_file:
            # Media URL provided, no file upload needed
            # Extract IPFS hash from URL if it's an IPFS URL
            if 'ipfs' in media_url.lower():
                # Try to extract hash from URL
                parts = media_url.split('/')
                ipfs_hash = parts[-1] if parts else None
                if ipfs_hash:
                    asset.media_ipfs_hash = ipfs_hash
                    asset.media_url = media_url
                    asset.step_data.setdefault('media_upload', {})['ipfs_hash'] = ipfs_hash
                    asset.step_data.setdefault('media_upload', {})['url'] = media_url
                    asset.save(update_fields=['media_ipfs_hash', 'media_url', 'step_data'])
                    return media_url, ipfs_hash
            return media_url, None
        
        # Upload file to IPFS
        if not pinata_service:
            pinata_service = get_pinata_service()
        
        logger.info(f"Uploading media file to IPFS: {media_file.name}")
        media_result = pinata_service.upload_file(
            file=media_file,
            filename=media_file.name
        )
        
        media_url = media_result['url']
        media_ipfs_hash = media_result['ipfs_hash']
        
        # Store results
        asset.media_ipfs_hash = media_ipfs_hash
        asset.media_url = media_url
        asset.step_data.setdefault('media_upload', {})['ipfs_hash'] = media_ipfs_hash
        asset.step_data.setdefault('media_upload', {})['url'] = media_url
        asset.creation_step = 'db_save'
        asset.save(update_fields=['media_ipfs_hash', 'media_url', 'step_data', 'creation_step'])
        
        logger.info(f"Media uploaded to IPFS: {media_ipfs_hash}")
        return media_url, media_ipfs_hash
    
    def _step_upload_metadata(self, asset, title, description, media_url, creator_address, 
                              license_terms, pinata_service=None):
        """
        Step 3: Upload metadata to IPFS (idempotent).
        Returns: (metadata_uri, metadata_hash) or raises exception
        """
        # Check if already uploaded
        if asset.metadata_hash:
            logger.info(f"Metadata already uploaded for asset {asset.id}, using existing: {asset.metadata_hash}")
            metadata_uri = asset.step_data.get('metadata_upload', {}).get('uri', f"ipfs://{asset.metadata_hash}")
            return metadata_uri, asset.metadata_hash
        
        if not pinata_service:
            pinata_service = get_pinata_service()
        
        logger.info("Uploading metadata to IPFS")
        normalized_address = normalize_wallet_address(creator_address)
        
        metadata_result = pinata_service.upload_ip_metadata(
            title=title,
            description=description,
            media_url=media_url,
            creator_address=normalized_address,
            asset_id=asset.id,
            license_terms=license_terms
        )
        
        metadata_uri = metadata_result['url']  # ipfs:// URI
        metadata_hash = metadata_result['hash']  # Hex string without 0x prefix
        
        # Store results
        asset.metadata_hash = metadata_hash
        asset.step_data.setdefault('metadata_upload', {})['uri'] = metadata_uri
        asset.step_data.setdefault('metadata_upload', {})['hash'] = metadata_hash
        asset.step_data.setdefault('metadata_upload', {})['ipfs_hash'] = metadata_result.get('ipfs_hash', '')
        asset.creation_step = 'story_registration'
        asset.save(update_fields=['metadata_hash', 'step_data', 'creation_step'])
        
        logger.info(f"Metadata uploaded to IPFS: {metadata_result.get('ipfs_hash', metadata_hash)}")
        return metadata_uri, metadata_hash
    
    def _step_register_story_protocol(self, asset, metadata_uri, metadata_hash, creator_address,
                                     allow_derivatives, commercial_use, royalty_percentage,
                                     story_service=None):
        """
        Step 4: Register IP on Story Protocol (idempotent).
        Returns: story_ip_id or raises exception
        """
        # Check if already registered
        if asset.story_ip_id:
            logger.info(f"Asset {asset.id} already registered on Story Protocol: {asset.story_ip_id}")
            return asset.story_ip_id
        
        if not story_service:
            story_service = get_story_service()
        
        if not story_service.is_ready():
            raise RuntimeError('Story Protocol service not available')
        
        # Normalize and checksum wallet address
        from web3 import Web3
        normalized_creator_address = normalize_wallet_address(creator_address)
        try:
            normalized_creator_address = Web3.to_checksum_address(normalized_creator_address)
        except Exception as e:
            raise ValueError(f"Invalid wallet address format: {normalized_creator_address}. Error: {e}")
        
        logger.info(f"Registering IP asset on Story Protocol for user: {normalized_creator_address}")
        
        # Update status
        asset.registration_status = 'retrying'
        asset.registration_attempts += 1
        asset.last_registration_attempt = timezone.now()
        asset.save(update_fields=['registration_status', 'registration_attempts', 'last_registration_attempt'])
        
        try:
            registration_result = story_service.register_ip_asset(
                metadata_uri=metadata_uri,
                metadata_hash=metadata_hash,
                creator_address=normalized_creator_address,
                allow_derivatives=allow_derivatives,
                commercial_use=commercial_use,
                royalty_percentage=royalty_percentage
            )
            
            story_ip_id = registration_result['ip_id']
            
            # Store results
            asset.story_ip_id = story_ip_id
            asset.step_data.setdefault('story_registration', {})['ip_id'] = story_ip_id
            asset.step_data.setdefault('story_registration', {})['transaction_hash'] = registration_result.get('transaction_hash', '')
            asset.step_data.setdefault('story_registration', {})['block_number'] = registration_result.get('block_number', 0)
            asset.creation_step = 'license_attachment'
            asset.save(update_fields=['story_ip_id', 'step_data', 'creation_step'])
            
            logger.info(f"IP Asset registered with ID: {story_ip_id}")
            return story_ip_id
            
        except Exception as e:
            error_message = str(e)
            asset.registration_status = 'failed'
            asset.registration_error = error_message
            asset.failed_at_step = 'story_registration'
            asset.save(update_fields=['registration_status', 'registration_error', 'failed_at_step'])
            raise
    
    def _step_attach_license(self, asset, story_ip_id, allow_derivatives, commercial_use,
                            royalty_percentage, story_service=None):
        """
        Step 5: Attach license terms (idempotent, non-critical).
        Returns: True if successful, False if failed (doesn't raise)
        """
        # Check if already attached (non-critical step, so we don't fail if missing)
        if asset.step_data.get('license_attachment', {}).get('attached', False):
            logger.info(f"License already attached for asset {asset.id}")
            return True
        
        if not story_service:
            story_service = get_story_service()
        
        if not story_service.is_ready():
            logger.warning("Story Protocol service not available for license attachment")
            return False
        
        try:
            story_service.attach_license_terms(
                ip_id=story_ip_id,
                allow_derivatives=allow_derivatives,
                commercial_use=commercial_use,
                royalty_percentage=royalty_percentage
            )
            
            # Store result
            asset.step_data.setdefault('license_attachment', {})['attached'] = True
            asset.creation_step = 'completed'
            asset.registration_status = 'registered'
            asset.registration_error = ''
            asset.failed_at_step = None
            asset.save(update_fields=['step_data', 'creation_step', 'registration_status', 'registration_error', 'failed_at_step'])
            
            logger.info(f"License terms attached to IP: {story_ip_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to attach license terms: {str(e)}")
            # Non-critical, so we mark as completed anyway
            asset.creation_step = 'completed'
            asset.registration_status = 'registered'
            asset.registration_error = ''
            asset.failed_at_step = None
            asset.step_data.setdefault('license_attachment', {})['attached'] = False
            asset.step_data.setdefault('license_attachment', {})['error'] = str(e)
            asset.save(update_fields=['step_data', 'creation_step', 'registration_status', 'registration_error', 'failed_at_step'])
            return False

    def create(self, request, *args, **kwargs):
        """
        Create a new IP asset with step-by-step tracking and retry support.
        Steps are tracked and can be resumed from failure point.

        Note: External service calls (IPFS, blockchain) are done OUTSIDE transaction blocks
        to prevent long-running operations from holding database locks.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            pinata_service = get_pinata_service()
            story_service = get_story_service()

            if not story_service.is_ready():
                return Response(
                    {
                        'error': 'Story Protocol service not available',
                        'detail': 'Please configure STORY_PROTOCOL_PRIVATE_KEY in settings'
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # Step 1: Save asset to database FIRST (in small transaction)
            media_url = serializer.validated_data.get('media_url', '')
            media_file = serializer.validated_data.get('media_file')

            with transaction.atomic():
                asset = serializer.save(
                    creator=request.user,
                    story_ip_id=None,  # NULL until registered on-chain (avoids UNIQUE constraint)
                    media_url=media_url or '',  # Will be updated after media upload
                    metadata_hash='',  # Will be updated after metadata upload
                    registration_status='pending',
                    registration_attempts=0,
                    creation_step='media_upload',
                    step_data={}
                )
            logger.info(f"Asset saved to database with ID: {asset.id}, starting from step: media_upload")

            # Step 2: Upload media to IPFS (idempotent)
            try:
                media_url, media_ipfs_hash = self._step_upload_media(
                    asset=asset,
                    media_file=media_file,
                    media_url=media_url,
                    pinata_service=pinata_service
                )
            except Exception as e:
                logger.error(f"Failed to upload media to IPFS: {str(e)}")
                asset.registration_status = 'failed'
                asset.registration_error = f"Failed to upload media to IPFS: {str(e)}"
                asset.failed_at_step = 'media_upload'
                asset.save(update_fields=['registration_status', 'registration_error', 'failed_at_step'])
                raise

            # Step 3: Upload metadata to IPFS (idempotent)
            try:
                license_terms = {
                    'allow_derivatives': serializer.validated_data.get('allow_derivatives', True),
                    'commercial_rights': serializer.validated_data.get('commercial_rights', False),
                    'royalty_percentage': serializer.validated_data.get('royalty_percentage', 0),
                }
                
                metadata_uri, metadata_hash = self._step_upload_metadata(
                    asset=asset,
                    title=serializer.validated_data['title'],
                    description=serializer.validated_data['description'],
                    media_url=media_url,
                    creator_address=request.user.wallet_address,
                    license_terms=license_terms,
                    pinata_service=pinata_service
                )
            except Exception as e:
                logger.error(f"Failed to upload metadata to IPFS: {str(e)}")
                asset.registration_status = 'failed'
                asset.registration_error = f"Failed to upload metadata to IPFS: {str(e)}"
                asset.failed_at_step = 'metadata_upload'
                asset.save(update_fields=['registration_status', 'registration_error', 'failed_at_step'])
                raise

            # Step 4: Register on Story Protocol (idempotent)
            story_ip_id = None  # Initialize to None in case of exception
            try:
                story_ip_id = self._step_register_story_protocol(
                    asset=asset,
                    metadata_uri=metadata_uri,
                    metadata_hash=metadata_hash,
                    creator_address=request.user.wallet_address,
                    allow_derivatives=serializer.validated_data.get('allow_derivatives', True),
                    commercial_use=serializer.validated_data.get('commercial_rights', False),
                    royalty_percentage=serializer.validated_data.get('royalty_percentage', 0),
                    story_service=story_service
                )
            except Exception as e:
                error_message = str(e)
                logger.error(f"Failed to register IP on Story Protocol: {error_message}")
                # Asset is saved with failed status, user can retry
                asset.registration_status = 'failed'
                asset.registration_error = error_message
                asset.failed_at_step = 'story_registration'
                asset.save(update_fields=['registration_status', 'registration_error', 'failed_at_step'])
                # Don't raise - return asset so user can retry

            # Step 5: Attach license terms (non-critical, idempotent)
            if story_ip_id:
                self._step_attach_license(
                    asset=asset,
                    story_ip_id=story_ip_id,
                    allow_derivatives=serializer.validated_data.get('allow_derivatives', True),
                    commercial_use=serializer.validated_data.get('commercial_rights', False),
                    royalty_percentage=serializer.validated_data.get('royalty_percentage', 0),
                    story_service=story_service
                )

            # Invalidate cache
            invalidate_asset_cache()

            # Return created asset (even if some steps failed)
            response_serializer = IPAssetDetailSerializer(asset)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Unexpected error creating IP asset: {str(e)}")
            return Response(
                {
                    'error': 'Failed to create IP asset',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def retry_registration(self, request, uuid=None):
        """
        Retry Story Protocol registration for a failed asset.
        Only works for assets with registration_status='failed'.
        """
        asset = self.get_object()
        
        # Check if user owns the asset
        if asset.creator != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if asset is in failed state
        if asset.registration_status not in ['failed', 'pending']:
            return Response(
                {
                    'error': 'Asset registration cannot be retried',
                    'detail': f'Current status: {asset.registration_status}. Only failed or pending assets can be retried.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if metadata hash exists
        if not asset.metadata_hash:
            return Response(
                {
                    'error': 'Cannot retry registration',
                    'detail': 'Asset metadata hash is missing. Please recreate the asset.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        story_service = get_story_service()
        if not story_service.is_ready():
            return Response(
                {
                    'error': 'Story Protocol service not available',
                    'detail': 'Please configure STORY_PROTOCOL_PRIVATE_KEY in settings'
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        # Get metadata URI from Pinata (reconstruct from hash)
        pinata_service = get_pinata_service()
        metadata_uri = f"ipfs://{asset.metadata_hash}"
        
        # Normalize and checksum wallet address
        from web3 import Web3
        normalized_creator_address = normalize_wallet_address(request.user.wallet_address)
        try:
            normalized_creator_address = Web3.to_checksum_address(normalized_creator_address)
        except Exception as e:
            return Response(
                {
                    'error': 'Invalid wallet address',
                    'detail': f'Failed to checksum address: {e}'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update asset status to retrying
        from django.utils import timezone
        asset.registration_status = 'retrying'
        asset.registration_attempts += 1
        asset.last_registration_attempt = timezone.now()
        asset.save()
        
        try:
            # Attempt registration
            registration_result = story_service.register_ip_asset(
                metadata_uri=metadata_uri,
                metadata_hash=asset.metadata_hash,
                creator_address=normalized_creator_address,
                allow_derivatives=asset.allow_derivatives,
                commercial_use=asset.commercial_rights,
                royalty_percentage=asset.royalty_percentage
            )
            
            story_ip_id = registration_result['ip_id']
            logger.info(f"Asset {asset.id} successfully registered on retry with IP ID: {story_ip_id}")
            
            # Try to attach license terms
            try:
                story_service.attach_license_terms(
                    ip_id=story_ip_id,
                    allow_derivatives=asset.allow_derivatives,
                    commercial_use=asset.commercial_rights,
                    royalty_percentage=asset.royalty_percentage
                )
                logger.info(f"License terms attached to IP: {story_ip_id}")
            except Exception as e:
                logger.warning(f"Failed to attach license terms: {str(e)}")
            
            # Update asset with success
            asset.story_ip_id = story_ip_id
            asset.registration_status = 'registered'
            asset.registration_error = ''
            asset.save()
            
            # Invalidate cache
            invalidate_asset_cache()
            
            response_serializer = IPAssetDetailSerializer(asset)
            return Response(
                {
                    'message': 'Asset successfully registered on Story Protocol',
                    'asset': response_serializer.data
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Retry registration failed for asset {asset.id}: {error_message}")
            
            # Update asset status to failed
            asset.registration_status = 'failed'
            asset.registration_error = error_message
            asset.save()
            
            return Response(
                {
                    'error': 'Registration retry failed',
                    'detail': error_message
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def retry_creation(self, request, uuid=None):
        """
        Comprehensive retry endpoint that resumes asset creation from the failed step.
        This method is idempotent - it checks what's already done and only executes remaining steps.
        
        Steps:
        1. media_upload - Upload media to IPFS
        2. db_save - Save to database (already done if we're retrying)
        3. metadata_upload - Upload metadata to IPFS
        4. story_registration - Register on Story Protocol
        5. license_attachment - Attach license terms
        6. completed - All done
        """
        asset = self.get_object()
        
        # Check if user owns the asset
        if asset.creator != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if asset can be retried
        if asset.registration_status == 'registered' and asset.creation_step == 'completed':
            return Response(
                {
                    'error': 'Asset creation already completed',
                    'detail': 'This asset has been successfully created and registered.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get services
        pinata_service = get_pinata_service()
        story_service = get_story_service()
        
        if not story_service.is_ready():
            return Response(
                {
                    'error': 'Story Protocol service not available',
                    'detail': 'Please configure STORY_PROTOCOL_PRIVATE_KEY in settings'
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        # Determine starting step from failed_at_step or current creation_step
        start_step = asset.failed_at_step or asset.creation_step
        
        logger.info(f"Retrying asset {asset.id} creation from step: {start_step}")
        
        try:
            # Resume from the appropriate step
            if start_step == 'media_upload':
                # Need media file or URL - check if we have it stored
                if not asset.media_url and not asset.media_ipfs_hash:
                    return Response(
                        {
                            'error': 'Cannot retry media upload',
                            'detail': 'Media file or URL is required. Please recreate the asset with media.'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # If we have media_url but no hash, try to extract or skip
                if asset.media_url and not asset.media_ipfs_hash:
                    # Media URL exists, assume it's valid
                    media_url = asset.media_url
                    media_ipfs_hash = None
                else:
                    # Already uploaded, get from stored data
                    media_url = asset.media_url
                    media_ipfs_hash = asset.media_ipfs_hash
                
                # If we don't have a valid media_url, we can't proceed
                if not media_url:
                    return Response(
                        {
                            'error': 'Cannot retry media upload',
                            'detail': 'Media URL is missing. Please recreate the asset.'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # If we're past media_upload, ensure we have media_url
            if start_step != 'media_upload' and not asset.media_url:
                return Response(
                    {
                        'error': 'Cannot retry',
                        'detail': 'Media URL is missing. Please recreate the asset.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            media_url = asset.media_url

            # Initialize variables for later steps (avoid UnboundLocalError)
            metadata_uri = None
            metadata_hash = None
            story_ip_id = None

            # Step 3: Upload metadata (if not already done)
            if start_step in ['media_upload', 'db_save', 'metadata_upload']:
                if not asset.metadata_hash:
                    try:
                        license_terms = {
                            'allow_derivatives': asset.allow_derivatives,
                            'commercial_rights': asset.commercial_rights,
                            'royalty_percentage': asset.royalty_percentage,
                        }

                        metadata_uri, metadata_hash = self._step_upload_metadata(
                            asset=asset,
                            title=asset.title,
                            description=asset.description,
                            media_url=media_url,
                            creator_address=request.user.wallet_address,
                            license_terms=license_terms,
                            pinata_service=pinata_service
                        )
                    except Exception as e:
                        logger.error(f"Failed to upload metadata on retry: {str(e)}")
                        asset.registration_status = 'failed'
                        asset.registration_error = f"Failed to upload metadata to IPFS: {str(e)}"
                        asset.failed_at_step = 'metadata_upload'
                        asset.save(update_fields=['registration_status', 'registration_error', 'failed_at_step'])
                        raise
                else:
                    # Metadata already uploaded, get from stored data
                    metadata_uri = asset.step_data.get('metadata_upload', {}).get('uri', f"ipfs://{asset.metadata_hash}")
                    metadata_hash = asset.metadata_hash

            # Step 4: Register on Story Protocol (if not already done)
            if start_step in ['media_upload', 'db_save', 'metadata_upload', 'story_registration']:
                # Ensure we have metadata_uri and metadata_hash (for story_registration retry)
                if not metadata_uri and asset.metadata_hash:
                    metadata_uri = asset.step_data.get('metadata_upload', {}).get('uri', f"ipfs://{asset.metadata_hash}")
                    metadata_hash = asset.metadata_hash
                    logger.info(f"Retrieved metadata from asset: uri={metadata_uri}, hash={metadata_hash}")

                if not asset.story_ip_id:
                    try:
                        story_ip_id = self._step_register_story_protocol(
                            asset=asset,
                            metadata_uri=metadata_uri,
                            metadata_hash=metadata_hash,
                            creator_address=request.user.wallet_address,
                            allow_derivatives=asset.allow_derivatives,
                            commercial_use=asset.commercial_rights,
                            royalty_percentage=asset.royalty_percentage,
                            story_service=story_service
                        )
                    except Exception as e:
                        error_message = str(e)
                        logger.error(f"Failed to register on Story Protocol on retry: {error_message}")
                        asset.registration_status = 'failed'
                        asset.registration_error = error_message
                        asset.failed_at_step = 'story_registration'
                        asset.save(update_fields=['registration_status', 'registration_error', 'failed_at_step'])
                        raise
                else:
                    story_ip_id = asset.story_ip_id
            
            # Step 5: Attach license terms (non-critical)
            if story_ip_id:
                self._step_attach_license(
                    asset=asset,
                    story_ip_id=story_ip_id,
                    allow_derivatives=asset.allow_derivatives,
                    commercial_use=asset.commercial_rights,
                    royalty_percentage=asset.royalty_percentage,
                    story_service=story_service
                )
            
            # Invalidate cache
            invalidate_asset_cache()
            
            response_serializer = IPAssetDetailSerializer(asset)
            return Response(
                {
                    'message': 'Asset creation retry completed successfully',
                    'asset': response_serializer.data,
                    'resumed_from_step': start_step,
                    'completed_steps': asset.creation_step
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Retry creation failed for asset {asset.id}: {error_message}")
            
            return Response(
                {
                    'error': 'Creation retry failed',
                    'detail': error_message,
                    'failed_at_step': asset.failed_at_step or asset.creation_step,
                    'asset': IPAssetDetailSerializer(asset).data
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def create_derivative(self, request):
        """
        Create a derivative/remix of an existing IP asset.
        Requires parent asset to allow derivatives.

        Note: External service calls (IPFS, blockchain) are done OUTSIDE transaction blocks
        to prevent orphaned uploads and long-running operations holding database locks.
        """
        serializer = DerivativeCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            story_service = get_story_service()

            if not story_service.is_ready():
                return Response(
                    {'error': 'Story Protocol service not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            parent_asset = serializer.context.get('parent_asset')
            pinata_service = get_pinata_service()

            # Step 1: Upload media to IPFS FIRST (outside transaction)
            media_url = serializer.validated_data.get('media_url', '')
            media_file = serializer.validated_data.get('media_file')

            if media_file:
                try:
                    logger.info(f"Uploading derivative media to IPFS: {media_file.name}")
                    media_result = pinata_service.upload_file(
                        file=media_file,
                        filename=media_file.name
                    )
                    media_url = media_result['url']
                    logger.info(f"Derivative media uploaded: {media_result['ipfs_hash']}")
                except Exception as e:
                    logger.error(f"Failed to upload derivative media: {str(e)}")
                    return Response(
                        {
                            'error': 'Failed to upload media to IPFS',
                            'detail': str(e)
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

            # Step 2: Upload metadata to IPFS (outside transaction)
            # Note: We need a temporary asset ID, so we'll use a placeholder
            try:
                logger.info("Uploading derivative metadata to IPFS")
                metadata_result = pinata_service.upload_ip_metadata(
                    title=serializer.validated_data['title'],
                    description=serializer.validated_data['description'],
                    media_url=media_url,
                    creator_address=request.user.wallet_address,
                    asset_id=0,  # Placeholder, will be updated after DB save
                    license_terms={
                        'commercial_rights': serializer.validated_data.get('commercial_rights', False),
                        'parent_ip_id': parent_asset.story_ip_id,
                        'is_derivative': True,
                    }
                )

                metadata_uri = metadata_result['url']
                metadata_hash = metadata_result['hash']
                logger.info(f"Derivative metadata uploaded: {metadata_result['ipfs_hash']}")

            except Exception as e:
                logger.error(f"Failed to upload derivative metadata: {str(e)}")
                return Response(
                    {
                        'error': 'Failed to upload metadata to IPFS',
                        'detail': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Step 3: Register derivative IP on Story Protocol (outside transaction)
            from web3 import Web3
            normalized_creator_address = normalize_wallet_address(request.user.wallet_address)
            try:
                checksummed_address = Web3.to_checksum_address(normalized_creator_address)
            except Exception as e:
                logger.error(f"Failed to checksum address {normalized_creator_address}: {e}")
                return Response(
                    {
                        'error': 'Invalid wallet address format',
                        'detail': str(e)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                registration_result = story_service.register_ip_asset(
                    metadata_uri=metadata_uri,
                    metadata_hash=metadata_hash,
                    creator_address=checksummed_address
                )

                child_ip_id = registration_result['ip_id']
                logger.info(f"Derivative IP registered with ID: {child_ip_id}")

            except Exception as e:
                logger.error(f"Failed to register derivative IP: {str(e)}")
                return Response(
                    {
                        'error': 'Failed to register IP on Story Protocol',
                        'detail': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Step 4: Register derivative relationship (outside transaction)
            try:
                story_service.register_derivative(
                    child_ip_id=child_ip_id,
                    parent_ip_ids=[parent_asset.story_ip_id],
                    license_terms=None
                )
                logger.info(f"Derivative relationship registered")
            except Exception as e:
                logger.error(f"Failed to register derivative relationship: {str(e)}")
                # Continue - asset is already registered, relationship can be added later

            # Step 5: Save to database LAST (in small transaction)
            with transaction.atomic():
                derivative = serializer.save(
                    creator=request.user,
                    story_ip_id=child_ip_id,
                    media_url=media_url,
                    metadata_hash=metadata_hash
                )

            # Invalidate cache
            invalidate_asset_cache()
            if parent_asset:
                invalidate_asset_cache(parent_asset.id)

            # Transaction completed successfully
            response_serializer = IPAssetDetailSerializer(derivative)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Failed to create derivative: {str(e)}")
            return Response(
                {
                    'error': 'Failed to create derivative',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def create_multi_parent_derivative(self, request):
        """
        Create a derivative with multiple parent assets (1-10 parents).
        Attribution percentages must sum to 100%.

        Request format:
        {
            "parent_assets": [
                {"parent_asset_id": "uuid1", "attribution_percentage": 60.0, "license_terms_id": "..."},
                {"parent_asset_id": "uuid2", "attribution_percentage": 40.0}
            ],
            "title": "My Remix",
            "description": "...",
            "media_file": <file> OR "media_url": "https://...",
            "commercial_rights": false
        }
        """
        serializer = MultiParentDerivativeCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        try:
            story_service = get_story_service()

            if not story_service.is_ready():
                return Response(
                    {'error': 'Story Protocol service not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            validated_parents = serializer.context.get('validated_parents', [])
            pinata_service = get_pinata_service()

            # Step 1: Upload media to IPFS FIRST (outside transaction)
            media_url = serializer.validated_data.get('media_url', '')
            media_file = serializer.validated_data.get('media_file')

            if media_file:
                try:
                    logger.info(f"Uploading multi-parent derivative media to IPFS: {media_file.name}")
                    media_result = pinata_service.upload_file(
                        file=media_file,
                        filename=media_file.name
                    )
                    media_url = media_result['url']
                    logger.info(f"Multi-parent derivative media uploaded: {media_result['ipfs_hash']}")
                except Exception as e:
                    logger.error(f"Failed to upload multi-parent derivative media: {str(e)}")
                    return Response(
                        {
                            'error': 'Failed to upload media to IPFS',
                            'detail': str(e)
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

            # Step 2: Upload metadata to IPFS (outside transaction)
            try:
                logger.info("Uploading multi-parent derivative metadata to IPFS")
                parent_ip_ids = [p['parent_asset'].story_ip_id for p in validated_parents]

                metadata_result = pinata_service.upload_ip_metadata(
                    title=serializer.validated_data['title'],
                    description=serializer.validated_data['description'],
                    media_url=media_url,
                    creator_address=request.user.wallet_address,
                    asset_id=0,  # Placeholder
                    license_terms={
                        'commercial_rights': serializer.validated_data.get('commercial_rights', False),
                        'parent_ip_ids': parent_ip_ids,
                        'is_derivative': True,
                        'multi_parent': True,
                        'attribution_percentages': {
                            p['parent_asset'].story_ip_id: p['attribution_percentage']
                            for p in validated_parents
                        }
                    }
                )

                metadata_uri = metadata_result['url']
                metadata_hash = metadata_result['hash']
                logger.info(f"Multi-parent derivative metadata uploaded: {metadata_result['ipfs_hash']}")

            except Exception as e:
                logger.error(f"Failed to upload multi-parent derivative metadata: {str(e)}")
                return Response(
                    {
                        'error': 'Failed to upload metadata to IPFS',
                        'detail': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Step 3: Register derivative IP on Story Protocol (outside transaction)
            from web3 import Web3
            normalized_creator_address = normalize_wallet_address(request.user.wallet_address)
            try:
                checksummed_address = Web3.to_checksum_address(normalized_creator_address)
            except Exception as e:
                logger.error(f"Failed to checksum address {normalized_creator_address}: {e}")
                return Response(
                    {
                        'error': 'Invalid wallet address format',
                        'detail': str(e)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                registration_result = story_service.register_ip_asset(
                    metadata_uri=metadata_uri,
                    metadata_hash=metadata_hash,
                    creator_address=checksummed_address
                )

                child_ip_id = registration_result['ip_id']
                logger.info(f"Multi-parent derivative IP registered with ID: {child_ip_id}")

            except Exception as e:
                logger.error(f"Failed to register multi-parent derivative IP: {str(e)}")
                return Response(
                    {
                        'error': 'Failed to register IP on Story Protocol',
                        'detail': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Step 4: Register derivative relationships with all parents (outside transaction)
            try:
                parent_ip_ids = [p['parent_asset'].story_ip_id for p in validated_parents]
                story_service.register_derivative(
                    child_ip_id=child_ip_id,
                    parent_ip_ids=parent_ip_ids,
                    license_terms=None
                )
                logger.info(f"Multi-parent derivative relationships registered with {len(parent_ip_ids)} parents")
            except Exception as e:
                logger.error(f"Failed to register multi-parent derivative relationships: {str(e)}")
                # Continue - asset is already registered, relationships can be added later

            # Step 5: Save to database LAST (in transaction)
            with transaction.atomic():
                # Create the derivative asset
                derivative = serializer.save(
                    creator=request.user,
                    story_ip_id=child_ip_id,
                    media_url=media_url,
                    metadata_hash=metadata_hash
                )

                # Create DerivativeRelationship records for each parent
                relationships = []
                for parent_data in validated_parents:
                    relationship = DerivativeRelationship(
                        child_asset=derivative,
                        parent_asset=parent_data['parent_asset'],
                        attribution_percentage=parent_data['attribution_percentage'],
                        license_terms_id=parent_data.get('license_terms_id', ''),
                        transaction_hash=''  # Can be updated later if needed
                    )
                    relationships.append(relationship)

                # Bulk create all relationships
                DerivativeRelationship.objects.bulk_create(relationships)
                logger.info(f"Created {len(relationships)} parent relationships")

                # Also set the legacy parent_asset field to the first parent for backward compatibility
                if validated_parents:
                    derivative.parent_asset = validated_parents[0]['parent_asset']
                    derivative.save(update_fields=['parent_asset'])

            # Invalidate cache
            invalidate_asset_cache()
            for parent_data in validated_parents:
                invalidate_asset_cache(parent_data['parent_asset'].id)

            # Transaction completed successfully
            response_serializer = IPAssetDetailSerializer(derivative)
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Failed to create multi-parent derivative: {str(e)}")
            return Response(
                {
                    'error': 'Failed to create multi-parent derivative',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def derivatives(self, request, uuid=None):
        """Get all derivatives of an IP asset."""
        asset = self.get_object()
        # Optimize query with select_related for creator
        derivatives = asset.derivatives.filter(is_deleted=False).select_related('creator').order_by('-created_at')
        serializer = IPAssetListSerializer(derivatives, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def claim_royalties(self, request, uuid=None):
        """
        Claim accumulated royalties for an IP asset.
        Only the creator can claim royalties.
        """
        asset = self.get_object()

        # Check if user is the creator
        if asset.creator != request.user:
            return Response(
                {'error': 'Only the creator can claim royalties'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            story_service = get_story_service()

            if not story_service.is_ready():
                return Response(
                    {'error': 'Story Protocol service not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # Claim royalties from blockchain
            result = story_service.claim_royalties(
                ip_id=asset.story_ip_id,
                claimer_address=request.user.wallet_address
            )

            # Save royalty payment record to database
            with transaction.atomic():
                royalty_payment = RoyaltyPayment.objects.create(
                    asset=asset,
                    recipient=request.user,
                    amount=result['amount'],
                    transaction_hash=result['transaction_hash'],
                    block_number=result.get('block_number', 0)
                )

                # Update user's total earnings
                request.user.total_earnings = F('total_earnings') + result['amount']
                request.user.save(update_fields=['total_earnings'])

            logger.info(f"Royalty payment recorded: {royalty_payment.id} for asset {asset.id}")

            return Response({
                'message': 'Royalties claimed successfully',
                'amount': result['amount'],
                'transaction_hash': result['transaction_hash'],
                'payment_id': royalty_payment.id,
            })

        except Exception as e:
            logger.error(f"Failed to claim royalties: {str(e)}")
            return Response(
                {
                    'error': 'Failed to claim royalties',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def royalty_balance(self, request, uuid=None):
        """Get current royalty balance for an IP asset."""
        asset = self.get_object()

        # If asset is not registered on Story Protocol, return zero balance
        if not asset.story_ip_id or asset.registration_status in ['failed', 'pending']:
            return Response({
                'balance': '0',
                'asset_id': asset.id,
                'story_ip_id': asset.story_ip_id,
                'status': asset.registration_status,
                'message': 'Asset not registered on Story Protocol' if asset.registration_status == 'failed' else 'Asset registration pending'
            })

        try:
            story_service = get_story_service()

            if not story_service.is_ready():
                return Response(
                    {'error': 'Story Protocol service not available'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            balance = story_service.get_royalty_balance(
                ip_id=asset.story_ip_id,
                address=asset.creator.wallet_address
            )

            return Response({
                'balance': balance,
                'asset_id': asset.id,
                'story_ip_id': asset.story_ip_id,
            })

        except Exception as e:
            logger.error(f"Failed to get royalty balance: {str(e)}")
            return Response(
                {
                    'error': 'Failed to get royalty balance',
                    'detail': str(e),
                    'balance': '0',  # Return zero balance on error
                    'asset_id': asset.id,
                },
                status=status.HTTP_200_OK  # Return 200 with error message instead of 500
            )

