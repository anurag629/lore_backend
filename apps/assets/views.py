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
from asgiref.sync import async_to_sync

from .models import IPAsset, RoyaltyPayment
from .serializers import (
    IPAssetListSerializer,
    IPAssetDetailSerializer,
    IPAssetCreateSerializer,
    DerivativeCreateSerializer,
    RoyaltyPaymentSerializer,
)
from .story_service import get_story_service
from .pinata_service import get_pinata_service

logger = logging.getLogger(__name__)


class IPAssetViewSet(viewsets.ModelViewSet):
    """
    ViewSet for IP Asset CRUD operations.
    Handles asset creation, listing, retrieval, and Story Protocol integration.
    """

    queryset = IPAsset.objects.select_related('creator', 'parent_asset').all()
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return IPAssetCreateSerializer
        elif self.action in ['retrieve']:
            return IPAssetDetailSerializer
        else:
            return IPAssetListSerializer

    def get_queryset(self):
        """
        Optionally filter assets by query parameters.
        Supports filtering by creator, is_derivative, etc.
        """
        queryset = super().get_queryset()

        # Filter by creator
        creator_id = self.request.query_params.get('creator', None)
        if creator_id:
            queryset = queryset.filter(creator_id=creator_id)

        # Filter by derivative status
        is_derivative = self.request.query_params.get('is_derivative', None)
        if is_derivative is not None:
            queryset = queryset.filter(
                is_derivative=is_derivative.lower() == 'true'
            )

        # Search by title
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(title__icontains=search)

        return queryset

    def create(self, request, *args, **kwargs):
        """
        Create a new IP asset.
        Steps:
        1. Upload media file (if provided)
        2. Upload metadata to IPFS
        3. Register IP on Story Protocol
        4. Attach license terms
        5. Save to database
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

            # Upload media file to IPFS via Pinata
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
                    # Fall back to placeholder if Pinata fails
                    media_url = "https://placeholder.example.com/media"

            # Save asset temporarily to get ID for metadata
            asset = serializer.save(
                creator=request.user,
                story_ip_id='',  # Will be updated after registration
                media_url=media_url,
                metadata_hash=''  # Will be updated after metadata upload
            )

            # Upload metadata to IPFS
            try:
                logger.info("Uploading metadata to IPFS")
                metadata_result = pinata_service.upload_ip_metadata(
                    title=serializer.validated_data['title'],
                    description=serializer.validated_data['description'],
                    media_url=media_url,
                    creator_address=request.user.wallet_address,
                    asset_id=asset.id,
                    license_terms={
                        'allow_derivatives': serializer.validated_data.get('allow_derivatives', True),
                        'commercial_rights': serializer.validated_data.get('commercial_rights', False),
                        'royalty_percentage': serializer.validated_data.get('royalty_percentage', 0),
                    }
                )

                metadata_uri = metadata_result['url']  # ipfs:// URI
                metadata_hash = metadata_result['hash']
                logger.info(f"Metadata uploaded to IPFS: {metadata_result['ipfs_hash']}")

            except Exception as e:
                logger.error(f"Failed to upload metadata to IPFS: {str(e)}")
                # Use fallback if Pinata fails
                metadata_uri = "ipfs://placeholder-hash"
                metadata_hash = "0x" + "0" * 64

            logger.info(f"Registering IP asset on Story Protocol for user: {request.user.wallet_address}")

            # Register IP asset on Story Protocol
            try:
                registration_result = async_to_sync(story_service.register_ip_asset)(
                    metadata_uri=metadata_uri,
                    metadata_hash=metadata_hash,
                    creator_address=request.user.wallet_address
                )

                story_ip_id = registration_result['ip_id']
                logger.info(f"IP Asset registered with ID: {story_ip_id}")

            except Exception as e:
                logger.error(f"Failed to register IP on Story Protocol: {str(e)}")
                return Response(
                    {
                        'error': 'Failed to register IP on blockchain',
                        'detail': str(e)
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Attach license terms
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
                # Continue anyway - asset is registered

            # Update asset with Story Protocol ID and metadata hash
            asset.story_ip_id = story_ip_id
            asset.metadata_hash = metadata_hash
            asset.save()

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
    def create_derivative(self, request):
        """
        Create a derivative/remix of an existing IP asset.
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

            # Handle file upload to IPFS
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
                    media_url = "https://placeholder.example.com/media"

            # Save derivative temporarily to get ID
            derivative = serializer.save(
                creator=request.user,
                story_ip_id='',
                media_url=media_url,
                metadata_hash=''
            )

            # Upload metadata to IPFS
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
                metadata_uri = "ipfs://placeholder-derivative-hash"
                metadata_hash = "0x" + "0" * 64

            # Register derivative IP on Story Protocol
            registration_result = async_to_sync(story_service.register_ip_asset)(
                metadata_uri=metadata_uri,
                metadata_hash=metadata_hash,
                creator_address=request.user.wallet_address
            )

            child_ip_id = registration_result['ip_id']

            # Register derivative relationship
            async_to_sync(story_service.register_derivative)(
                child_ip_id=child_ip_id,
                parent_ip_ids=[parent_asset.story_ip_id],
                license_terms=None
            )

            # Update derivative with Story Protocol data
            derivative.story_ip_id = child_ip_id
            derivative.metadata_hash = metadata_hash
            derivative.save()

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
        derivatives = asset.derivatives.all()
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

            # TODO: Save royalty payment record to database
            # RoyaltyPayment.objects.create(...)

            return Response({
                'message': 'Royalties claimed successfully',
                'amount': result['amount'],
                'transaction_hash': result['transaction_hash'],
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
