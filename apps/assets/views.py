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
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import F, Count, Q, Prefetch
from django.utils import timezone
from asgiref.sync import async_to_sync

from .models import IPAsset, RoyaltyPayment
from .serializers import (
    IPAssetListSerializer,
    IPAssetDetailSerializer,
    IPAssetCreateSerializer,
    IPAssetUpdateSerializer,
    DerivativeCreateSerializer,
    RoyaltyPaymentSerializer,
)
from .story_service import get_story_service
from .pinata_service import get_pinata_service
from .throttles import AIRateThrottle, UploadRateThrottle
from .filters import IPAssetFilter
from .cache import get_cached_asset_list, cache_asset_list, get_cached_asset_detail, cache_asset_detail
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
        """
        queryset = super().get_queryset()
        
        # Filter out deleted assets
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_deleted=False)
        
        # Optimize queryset based on action
        if self.action == 'list':
            # For list view, annotate derivative count to avoid N+1 queries
            queryset = queryset.annotate(
                derivative_count_annotated=Count(
                    'derivatives',
                    filter=Q(derivatives__is_deleted=False)
                )
            )
        elif self.action == 'retrieve':
            # For detail view, prefetch derivatives with creator
            queryset = queryset.prefetch_related(
                Prefetch(
                    'derivatives',
                    queryset=IPAsset.objects.filter(is_deleted=False)
                        .select_related('creator')
                        .order_by('-created_at')[:10]
                )
            )
        
        return queryset

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
        asset_id = kwargs.get('pk')
        
        # Try to get from cache
        cached_response = get_cached_asset_detail(asset_id)
        if cached_response:
            return Response(cached_response)
        
        # Get response from super
        response = super().retrieve(request, *args, **kwargs)
        
        # Cache the response
        if response.status_code == 200:
            cache_asset_detail(asset_id, response.data)
        
        return response

    def update(self, request, *args, **kwargs):
        """Update asset with cache invalidation."""
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            asset_id = kwargs.get('pk')
            invalidate_asset_cache(asset_id)
        return response

    def partial_update(self, request, *args, **kwargs):
        """Partial update asset with cache invalidation."""
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200:
            asset_id = kwargs.get('pk')
            invalidate_asset_cache(asset_id)
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

            # Step 2: Start database transaction
            # All DB operations from here will rollback on failure
            with transaction.atomic():
                # Step 3: Save asset temporarily to get ID for metadata
                asset = serializer.save(
                    creator=request.user,
                    story_ip_id='',  # Will be updated after registration
                    media_url=media_url,
                    metadata_hash=''  # Will be updated after metadata upload
                )

                # Step 4: Upload metadata to IPFS
                try:
                    logger.info("Uploading metadata to IPFS")
                    # Normalize wallet address before passing to metadata
                    from apps.core.utils import normalize_wallet_address
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

                except Exception as e:
                    logger.error(f"Failed to upload metadata to IPFS: {str(e)}")
                    # Transaction will rollback, asset deleted
                    raise

                # Step 5: Register IP asset on Story Protocol
                # Ensure wallet address is normalized
                normalized_creator_address = normalize_wallet_address(request.user.wallet_address)
                logger.info(f"Registering IP asset on Story Protocol for user: {normalized_creator_address}")
                logger.info(f"Metadata hash format: {metadata_hash[:20]}... (length: {len(metadata_hash)})")
                try:
                    registration_result = async_to_sync(story_service.register_ip_asset)(
                        metadata_uri=metadata_uri,
                        metadata_hash=metadata_hash,
                        creator_address=normalized_creator_address
                    )

                    story_ip_id = registration_result['ip_id']
                    logger.info(f"IP Asset registered with ID: {story_ip_id}")

                except Exception as e:
                    logger.error(f"Failed to register IP on Story Protocol: {str(e)}")
                    # Transaction will rollback
                    raise

                # Step 6: Attach license terms
                try:
                    async_to_sync(story_service.attach_license_terms)(
                        ip_id=story_ip_id,
                        allow_derivatives=serializer.validated_data.get('allow_derivatives', True),
                        commercial_use=serializer.validated_data.get('commercial_rights', False),
                        royalty_percentage=serializer.validated_data.get('royalty_percentage', 0)
                    )
                    logger.info(f"License terms attached to IP: {story_ip_id}")

                except Exception as e:
                    logger.error(f"Failed to attach license terms: {str(e)}")
                    # Note: Asset is registered but license not attached
                    # We continue as this is not critical - asset can still function
                    # Consider: Should we rollback or continue?
                    # For now, log and continue

                # Step 7: Update asset with Story Protocol ID and metadata hash
                asset.story_ip_id = story_ip_id
                asset.metadata_hash = metadata_hash
                asset.save()

            # Invalidate cache
            invalidate_asset_cache()

            # Transaction completed successfully
            # Return created asset
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
                try:
                    registration_result = async_to_sync(story_service.register_ip_asset)(
                        metadata_uri=metadata_uri,
                        metadata_hash=metadata_hash,
                        creator_address=request.user.wallet_address
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
    def derivatives(self, request, pk=None):
        """Get all derivatives of an IP asset."""
        asset = self.get_object()
        # Optimize query with select_related for creator
        derivatives = asset.derivatives.filter(is_deleted=False).select_related('creator').order_by('-created_at')
        serializer = IPAssetListSerializer(derivatives, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def claim_royalties(self, request, pk=None):
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
    def royalty_balance(self, request, pk=None):
        """Get current royalty balance for an IP asset."""
        asset = self.get_object()

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
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RoyaltyPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing royalty payment history.
    Read-only - payments are created by blockchain event listeners.
    """

    queryset = RoyaltyPayment.objects.select_related('asset', 'recipient').all()
    serializer_class = RoyaltyPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter royalty payments for current user."""
        return super().get_queryset().filter(recipient=self.request.user)


# ===== AI Feature Endpoints =====

from rest_framework.decorators import api_view, permission_classes
from .ai_service import get_ai_service
from .models import AIGenerationLog, AIAssetMetadata
from .serializers import (
    TitleGenerationSerializer,
    DescriptionEnhancementSerializer,
    ContentAnalysisSerializer,
    LicenseSuggestionSerializer,
    DerivativeAnalysisSerializer,
)
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
import time


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def generate_title(request):
    """Generate title suggestions from description."""
    serializer = TitleGenerationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    start_time = time.time()
    log_entry = None

    try:
        ai_service = get_ai_service()
        if not ai_service.is_ready():
            return Response(
                {'error': 'AI service not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # Call AI service (returns tuple with metadata)
        result = ai_service.generate_title(
            description=serializer.validated_data['description'],
            context={'asset_type': serializer.validated_data.get('asset_type')}
        )

        # Unpack result
        titles, model_used, response_time_ms, tokens_used, cache_hit = result

        # Create log entry
        log_entry = AIGenerationLog.objects.create(
            user=request.user,
            operation_type='title',
            input_data={
                'description': serializer.validated_data['description'],
                'asset_type': serializer.validated_data.get('asset_type')
            },
            output_data={'titles': titles},
            model_used=model_used,
            model_tier='fast',
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            status='success',
            cache_hit=cache_hit
        )

        return Response({
            'titles': titles,
            'model_used': model_used,
            'log_id': log_entry.id
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Title generation failed: {e}")

        # Log failure
        if log_entry is None:
            AIGenerationLog.objects.create(
                user=request.user,
                operation_type='title',
                input_data=serializer.validated_data,
                output_data=None,
                model_used=ai_service.default_model if ai_service else 'unknown',
                model_tier='fast',
                response_time_ms=int((time.time() - start_time) * 1000),
                status='failed',
                error_message=str(e),
                cache_hit=False
            )

        return Response(
            {'error': 'Failed to generate titles', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def enhance_description(request):
    """Enhance brief description into detailed narrative."""
    serializer = DescriptionEnhancementSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    start_time = time.time()

    try:
        ai_service = get_ai_service()
        if not ai_service.is_ready():
            return Response(
                {'error': 'AI service not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        result = ai_service.enhance_description(
            description=serializer.validated_data['description'],
            title=serializer.validated_data.get('title'),
            asset_type=serializer.validated_data.get('asset_type')
        )

        enhanced, model_used, response_time_ms, tokens_used, cache_hit = result

        log_entry = AIGenerationLog.objects.create(
            user=request.user,
            operation_type='description',
            input_data=serializer.validated_data,
            output_data={'enhanced_description': enhanced},
            model_used=model_used,
            model_tier='fast',
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            status='success',
            cache_hit=cache_hit
        )

        return Response({
            'enhanced_description': enhanced,
            'model_used': model_used,
            'log_id': log_entry.id
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Description enhancement failed: {e}")

        AIGenerationLog.objects.create(
            user=request.user,
            operation_type='description',
            input_data=serializer.validated_data,
            output_data=None,
            model_used=ai_service.default_model if ai_service else 'unknown',
            model_tier='fast',
            response_time_ms=int((time.time() - start_time) * 1000),
            status='failed',
            error_message=str(e),
            cache_hit=False
        )

        return Response(
            {'error': 'Failed to enhance description', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def analyze_content(request):
    """Analyze content and extract categories, tags."""
    serializer = ContentAnalysisSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    start_time = time.time()

    try:
        ai_service = get_ai_service()
        if not ai_service.is_ready():
            return Response(
                {'error': 'AI service not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        result = ai_service.analyze_content(
            title=serializer.validated_data['title'],
            description=serializer.validated_data['description'],
            media_url=serializer.validated_data.get('media_url')
        )

        analysis, model_used, response_time_ms, tokens_used, cache_hit = result

        log_entry = AIGenerationLog.objects.create(
            user=request.user,
            operation_type='analysis',
            input_data=serializer.validated_data,
            output_data=analysis,
            model_used=model_used,
            model_tier='quality',
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            status='success',
            cache_hit=cache_hit
        )

        analysis['model_used'] = model_used
        analysis['log_id'] = log_entry.id
        return Response(analysis, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Content analysis failed: {e}")

        AIGenerationLog.objects.create(
            user=request.user,
            operation_type='analysis',
            input_data=serializer.validated_data,
            output_data=None,
            model_used=ai_service.default_model if ai_service else 'unknown',
            model_tier='quality',
            response_time_ms=int((time.time() - start_time) * 1000),
            status='failed',
            error_message=str(e),
            cache_hit=False
        )

        return Response(
            {'error': 'Failed to analyze content', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def suggest_license(request):
    """Suggest optimal license terms."""
    serializer = LicenseSuggestionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    start_time = time.time()

    try:
        ai_service = get_ai_service()
        if not ai_service.is_ready():
            return Response(
                {'error': 'AI service not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        result = ai_service.suggest_license(
            asset_type=serializer.validated_data['asset_type'],
            description=serializer.validated_data['description'],
            intended_use=serializer.validated_data.get('intended_use')
        )

        suggestions, model_used, response_time_ms, tokens_used, cache_hit = result

        log_entry = AIGenerationLog.objects.create(
            user=request.user,
            operation_type='license',
            input_data=serializer.validated_data,
            output_data=suggestions,
            model_used=model_used,
            model_tier='fast',
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            status='success',
            cache_hit=cache_hit
        )

        suggestions['model_used'] = model_used
        suggestions['log_id'] = log_entry.id
        return Response(suggestions, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"License suggestion failed: {e}")

        AIGenerationLog.objects.create(
            user=request.user,
            operation_type='license',
            input_data=serializer.validated_data,
            output_data=None,
            model_used=ai_service.default_model if ai_service else 'unknown',
            model_tier='fast',
            response_time_ms=int((time.time() - start_time) * 1000),
            status='failed',
            error_message=str(e),
            cache_hit=False
        )

        return Response(
            {'error': 'Failed to suggest license', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIRateThrottle])
def analyze_derivative(request):
    """Analyze parent-derivative relationship."""
    serializer = DerivativeAnalysisSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)

    start_time = time.time()

    try:
        ai_service = get_ai_service()
        if not ai_service.is_ready():
            return Response(
                {'error': 'AI service not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        parent_asset = serializer.context.get('parent_asset')

        result = ai_service.analyze_derivative(
            parent_title=parent_asset.title,
            parent_description=parent_asset.description,
            derivative_description=serializer.validated_data['derivative_description'],
            derivative_title=serializer.validated_data.get('derivative_title')
        )

        analysis, model_used, response_time_ms, tokens_used, cache_hit = result

        log_entry = AIGenerationLog.objects.create(
            user=request.user,
            operation_type='derivative',
            input_data={
                'parent_asset_id': parent_asset.id,
                'derivative_description': serializer.validated_data['derivative_description'],
                'derivative_title': serializer.validated_data.get('derivative_title')
            },
            output_data=analysis,
            model_used=model_used,
            model_tier='quality',
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            status='success',
            cache_hit=cache_hit
        )

        analysis['model_used'] = model_used
        analysis['log_id'] = log_entry.id
        return Response(analysis, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Derivative analysis failed: {e}")

        AIGenerationLog.objects.create(
            user=request.user,
            operation_type='derivative',
            input_data=serializer.validated_data,
            output_data=None,
            model_used=ai_service.default_model if ai_service else 'unknown',
            model_tier='quality',
            response_time_ms=int((time.time() - start_time) * 1000),
            status='failed',
            error_message=str(e),
            cache_hit=False
        )

        return Response(
            {'error': 'Failed to analyze derivative', 'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ===== AI Analytics Endpoints =====

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_usage_stats(request):
    """Get AI usage statistics for current user."""
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # User's AI usage
    user_logs = AIGenerationLog.objects.filter(
        user=request.user,
        created_at__gte=start_date
    )

    stats = {
        'total_requests': user_logs.count(),
        'by_operation': list(user_logs.values('operation_type').annotate(
            count=Count('id')
        )),
        'success_rate': (
            user_logs.filter(status='success').count() / user_logs.count() * 100
            if user_logs.count() > 0 else 0
        ),
        'cache_hit_rate': (
            user_logs.filter(cache_hit=True).count() / user_logs.count() * 100
            if user_logs.count() > 0 else 0
        ),
        'avg_response_time': user_logs.filter(
            cache_hit=False
        ).aggregate(Avg('response_time_ms'))['response_time_ms__avg'] or 0,
        'total_tokens': user_logs.aggregate(
            Sum('tokens_used')
        )['tokens_used__sum'] or 0,
    }

    # AI metadata accepted by user
    accepted_content = AIAssetMetadata.objects.filter(
        asset__creator=request.user,
        accepted=True,
        created_at__gte=start_date
    )

    stats['accepted_suggestions'] = accepted_content.count()
    stats['by_content_type'] = list(
        accepted_content.values('content_type').annotate(count=Count('id'))
    )

    return Response(stats, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_platform_stats(request):
    """Get platform-wide AI statistics (admin only)."""
    if not request.user.is_staff:
        return Response(
            {'error': 'Admin access required'},
            status=status.HTTP_403_FORBIDDEN
        )

    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    all_logs = AIGenerationLog.objects.filter(created_at__gte=start_date)

    stats = {
        'total_requests': all_logs.count(),
        'unique_users': all_logs.values('user').distinct().count(),
        'by_operation': list(
            all_logs.values('operation_type').annotate(count=Count('id'))
        ),
        'by_model': list(
            all_logs.values('model_used').annotate(count=Count('id'))
        ),
        'success_rate': (
            all_logs.filter(status='success').count() / all_logs.count() * 100
            if all_logs.count() > 0 else 0
        ),
        'cache_hit_rate': (
            all_logs.filter(cache_hit=True).count() / all_logs.count() * 100
            if all_logs.count() > 0 else 0
        ),
        'avg_response_time': all_logs.filter(
            cache_hit=False
        ).aggregate(Avg('response_time_ms'))['response_time_ms__avg'] or 0,
        'total_tokens': all_logs.aggregate(
            Sum('tokens_used')
        )['tokens_used__sum'] or 0,
        'rate_limited_requests': all_logs.filter(
            status='rate_limited'
        ).count(),
    }

    # Acceptance metrics
    all_metadata = AIAssetMetadata.objects.filter(created_at__gte=start_date)
    total_suggestions = all_metadata.count()
    accepted_suggestions = all_metadata.filter(accepted=True).count()

    stats['acceptance_rate'] = (
        accepted_suggestions / total_suggestions * 100
        if total_suggestions > 0 else 0
    )

    return Response(stats, status=status.HTTP_200_OK)
