"""
AI analytics endpoints for usage statistics.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta

from apps.ai.models import AIGenerationLog, AIAssetMetadata


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

