"""
AI generation endpoints for content creation.
"""
import logging
import time
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.ai.services import get_ai_service
from apps.ai.models import AIGenerationLog, AIAssetMetadata
from apps.ai.serializers import (
    TitleGenerationSerializer,
    DescriptionEnhancementSerializer,
    ContentAnalysisSerializer,
    LicenseSuggestionSerializer,
    DerivativeAnalysisSerializer,
)
from apps.ai.throttles import AIRateThrottle

logger = logging.getLogger(__name__)


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

