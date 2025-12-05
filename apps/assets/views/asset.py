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
from asgiref.sync import async_to_sync
from apps.core.utils import normalize_wallet_address

from ..models import IPAsset, RoyaltyPayment
from ..serializers import (
    IPAssetListSerializer,
    IPAssetDetailSerializer,
    IPAssetCreateSerializer,
    IPAssetUpdateSerializer,
    DerivativeCreateSerializer,
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
        """
        queryset = super().get_queryset()
        
        # Filter out deleted assets
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_deleted=False)
        
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
        # Build cache key from query params
        cache_params = {
            'search': request.query_params.get('search', ''),
            'is_derivative': request.query_params.get('is_derivative', ''),
            'page': request.query_params.get('page', '1'),
            'ordering': request.query_params.get('ordering', '-created_at'),
        }
        
        # Try to get from cache
        cached_response = get_cached_asset_list(cache_params)
        if cached_response:
            return Response(cached_response)
        
        # Get response from super
        response = super().list(request, *args, **kwargs)
        
        # Cache the response
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
        """Update asset with cache invalidation."""
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            asset_uuid = kwargs.get('uuid')
            invalidate_asset_cache(asset_uuid)
        return response

    def partial_update(self, request, *args, **kwargs):
        """Partial update asset with cache invalidation."""
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200:
            asset_uuid = kwargs.get('uuid')
            invalidate_asset_cache(asset_uuid)
        return response

    def destroy(self, request, *args, **kwargs):
        """Soft delete asset with cache invalidation."""
        asset = self.get_object()
        asset_id = asset.id
        
        # Perform soft delete
        asset.is_deleted = True
        asset.deleted_at = timezone.now()
        asset.save()
        
        # Invalidate cache
        invalidate_asset_cache(asset_id)
        
        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a new IP asset with full transaction rollback on failure.
        Steps:
        1. Upload media file to IPFS (outside transaction)
        2. Start database transaction
        3. Save asset temporarily to get ID
        4. Upload metadata to IPFS
        5. Register IP on Story Protocol
        6. Attach license terms
        7. Update asset with blockchain data
        If any step fails, transaction rolls back automatically.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Get Story Protocol service
            story_service = get_story_service()

            if not story_service.is_ready():
                return Response(
                    {
                        'error': 'Story Protocol service not available',
                        'detail': 'Please configure STORY_PROTOCOL_PRIVATE_KEY in settings'
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # Step 1: Upload media file to IPFS (outside transaction)
            # This happens before DB transaction to avoid rollback of IPFS uploads
            pinata_service = get_pinata_service()
            media_url = serializer.validated_data.get('media_url', '')
            media_file = serializer.validated_data.get('media_file')

            if media_file:
                try:
                    logger.info(f"Uploading media file to IPFS: {media_file.name}")
                    media_result = pinata_service.upload_file(
                        file=media_file,
                        filename=media_file.name
                    )
                    media_url = media_result['url']  # Gateway URL
                    logger.info(f"Media uploaded to IPFS: {media_result['ipfs_hash']}")
                except Exception as e:
                    logger.error(f"Failed to upload media to IPFS: {str(e)}")
                    return Response(
                        {
                            'error': 'Failed to upload media to IPFS',
                            'detail': str(e)
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

            # Step 2: Save asset to Django database FIRST (so it persists even if Story Protocol fails)
            # This ensures we have a record of all assets, even if blockchain registration fails
            from django.utils import timezone
            asset = serializer.save(
                creator=request.user,
                story_ip_id='',  # Will be updated after registration
                media_url=media_url,
                metadata_hash='',  # Will be updated after metadata upload
                registration_status='pending',  # Initial status
                registration_attempts=0
            )
            logger.info(f"Asset saved to database with ID: {asset.id}, status: pending")

            # Step 3: Upload metadata to IPFS
            try:
                logger.info("Uploading metadata to IPFS")
                # Normalize wallet address before passing to metadata
                normalized_address = normalize_wallet_address(request.user.wallet_address)
                
                metadata_result = pinata_service.upload_ip_metadata(
                    title=serializer.validated_data['title'],
                    description=serializer.validated_data['description'],
                    media_url=media_url,
                    creator_address=normalized_address,
                    asset_id=asset.id,
                    license_terms={
                        'allow_derivatives': serializer.validated_data.get('allow_derivatives', True),
                        'commercial_rights': serializer.validated_data.get('commercial_rights', False),
                        'royalty_percentage': serializer.validated_data.get('royalty_percentage', 0),
                    }
                )

                metadata_uri = metadata_result['url']  # ipfs:// URI
                metadata_hash = metadata_result['hash']  # Hex string without 0x prefix
                logger.info(f"Metadata uploaded to IPFS: {metadata_result['ipfs_hash']}")
                logger.info(f"Metadata hash: {metadata_result.get('hash_with_prefix', metadata_hash)}")

                # Update asset with metadata hash
                asset.metadata_hash = metadata_hash
                asset.save()

            except Exception as e:
                logger.error(f"Failed to upload metadata to IPFS: {str(e)}")
                # Update asset status to failed
                asset.registration_status = 'failed'
                asset.registration_error = f"Failed to upload metadata to IPFS: {str(e)}"
                asset.registration_attempts = 1
                asset.last_registration_attempt = timezone.now()
                asset.save()
                raise

            # Step 4: Register IP asset on Story Protocol (OUTSIDE transaction so asset persists on failure)
            # Ensure wallet address is normalized and checksummed (required by Web3.py)
            from web3 import Web3
            normalized_creator_address = normalize_wallet_address(request.user.wallet_address)
            # Double-check checksumming (normalize_wallet_address may fail silently)
            try:
                normalized_creator_address = Web3.to_checksum_address(normalized_creator_address)
            except Exception as e:
                logger.error(f"Failed to checksum address {normalized_creator_address}: {e}")
                asset.registration_status = 'failed'
                asset.registration_error = f"Invalid wallet address format: {normalized_creator_address}"
                asset.registration_attempts = 1
                asset.last_registration_attempt = timezone.now()
                asset.save()
                raise ValueError(f"Invalid wallet address format: {normalized_creator_address}")
            
            logger.info(f"Registering IP asset on Story Protocol for user: {normalized_creator_address}")
            logger.info(f"Metadata hash format: {metadata_hash[:20]}... (length: {len(metadata_hash)})")
            
            # Update asset status to retrying
            asset.registration_status = 'retrying'
            asset.registration_attempts += 1
            asset.last_registration_attempt = timezone.now()
            asset.save()
            
            try:
                registration_result = async_to_sync(story_service.register_ip_asset)(
                    metadata_uri=metadata_uri,
                    metadata_hash=metadata_hash,
                    creator_address=normalized_creator_address,
                    allow_derivatives=serializer.validated_data.get('allow_derivatives', True),
                    commercial_use=serializer.validated_data.get('commercial_rights', False),
                    royalty_percentage=serializer.validated_data.get('royalty_percentage', 0)
                )

                story_ip_id = registration_result['ip_id']
                logger.info(f"IP Asset registered with ID: {story_ip_id}")

                # Step 5: Attach license terms
                try:
                    async_to_sync(story_service.attach_license_terms)(
                        ip_id=story_ip_id,
                        allow_derivatives=serializer.validated_data.get('allow_derivatives', True),
                        commercial_use=serializer.validated_data.get('commercial_rights', False),
                        royalty_percentage=serializer.validated_data.get('royalty_percentage', 0)
                    )
                    logger.info(f"License terms attached to IP: {story_ip_id}")

                except Exception as e:
                    logger.warning(f"Failed to attach license terms: {str(e)}")
                    # Note: Asset is registered but license not attached
                    # We continue as this is not critical - asset can still function

                # Step 6: Update asset with Story Protocol ID and success status
                asset.story_ip_id = story_ip_id
                asset.registration_status = 'registered'
                asset.registration_error = ''  # Clear any previous errors
                asset.save()
                logger.info(f"Asset {asset.id} successfully registered on Story Protocol with IP ID: {story_ip_id}")

            except Exception as e:
                error_message = str(e)
                logger.error(f"Failed to register IP on Story Protocol: {error_message}")
                # Update asset status to failed (but keep asset in database)
                asset.registration_status = 'failed'
                asset.registration_error = error_message
                asset.save()
                logger.warning(f"Asset {asset.id} saved to database but Story Protocol registration failed. Error: {error_message}")
                # Don't raise - return the asset with failed status so user can retry

            # Invalidate cache
            invalidate_asset_cache()

            # Return created asset (even if Story Protocol registration failed)
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
            registration_result = async_to_sync(story_service.register_ip_asset)(
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
                async_to_sync(story_service.attach_license_terms)(
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

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    @transaction.atomic
    def create_derivative(self, request):
        """
        Create a derivative/remix of an existing IP asset with transaction rollback.
        Requires parent asset to allow derivatives.
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

            # Step 1: Handle file upload to IPFS (outside transaction)
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

            # Step 2: Start database transaction
            with transaction.atomic():
                # Step 3: Save derivative temporarily to get ID
                derivative = serializer.save(
                    creator=request.user,
                    story_ip_id='',
                    media_url=media_url,
                    metadata_hash=''
                )

                # Step 4: Upload metadata to IPFS
                try:
                    logger.info("Uploading derivative metadata to IPFS")
                    metadata_result = pinata_service.upload_ip_metadata(
                        title=serializer.validated_data['title'],
                        description=serializer.validated_data['description'],
                        media_url=media_url,
                        creator_address=request.user.wallet_address,
                        asset_id=derivative.id,
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
                    # Transaction will rollback
                    raise

                # Step 5: Register derivative IP on Story Protocol
                # Ensure wallet address is normalized and checksummed (required by Web3.py)
                from web3 import Web3
                normalized_creator_address = normalize_wallet_address(request.user.wallet_address)
                # Double-check checksumming (normalize_wallet_address may fail silently)
                try:
                    checksummed_address = Web3.to_checksum_address(normalized_creator_address)
                except Exception as e:
                    logger.error(f"Failed to checksum address {normalized_creator_address}: {e}")
                    raise ValueError(f"Invalid wallet address format: {normalized_creator_address}")
                
                try:
                    registration_result = async_to_sync(story_service.register_ip_asset)(
                        metadata_uri=metadata_uri,
                        metadata_hash=metadata_hash,
                        creator_address=checksummed_address
                    )

                    child_ip_id = registration_result['ip_id']
                    logger.info(f"Derivative IP registered with ID: {child_ip_id}")

                except Exception as e:
                    logger.error(f"Failed to register derivative IP: {str(e)}")
                    # Transaction will rollback
                    raise

                # Step 6: Register derivative relationship
                try:
                    async_to_sync(story_service.register_derivative)(
                        child_ip_id=child_ip_id,
                        parent_ip_ids=[parent_asset.story_ip_id],
                        license_terms=None
                    )
                    logger.info(f"Derivative relationship registered")
                except Exception as e:
                    logger.error(f"Failed to register derivative relationship: {str(e)}")
                    # Continue - relationship can be registered later
                    # Asset is already registered

                # Step 7: Update derivative with Story Protocol data
                derivative.story_ip_id = child_ip_id
                derivative.metadata_hash = metadata_hash
                derivative.save()

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
            result = async_to_sync(story_service.claim_royalties)(
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

            balance = async_to_sync(story_service.get_royalty_balance)(
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

