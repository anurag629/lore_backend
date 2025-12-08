"""
Dispute Views - API endpoints for Story Protocol Disputes
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging

from apps.assets.models import Dispute, DisputeEvidence, IPAsset
from apps.assets.serializers import (
    DisputeListSerializer,
    DisputeDetailSerializer,
    RaiseDisputeSerializer,
    SubmitEvidenceSerializer,
    ResolveDisputeSerializer,
    DisputeEvidenceSerializer
)
from apps.assets.services.dispute_service import get_dispute_service
from apps.assets.services.story_service import get_story_service

logger = logging.getLogger(__name__)


class DisputeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Disputes.

    Endpoints:
    - GET /api/disputes/ - List all disputes
    - POST /api/disputes/raise_dispute/ - Raise a new dispute
    - GET /api/disputes/{uuid}/ - Get dispute details
    - POST /api/disputes/{uuid}/submit_evidence/ - Submit evidence
    - POST /api/disputes/{uuid}/resolve/ - Resolve dispute (admin)
    - POST /api/disputes/{uuid}/cancel/ - Cancel dispute (disputer)
    - GET /api/disputes/{uuid}/evidence/ - Get dispute evidence
    - GET /api/disputes/statistics/ - Get dispute statistics
    """

    queryset = Dispute.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'uuid'

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return DisputeListSerializer
        elif self.action == 'raise_dispute':
            return RaiseDisputeSerializer
        elif self.action == 'submit_evidence':
            return SubmitEvidenceSerializer
        elif self.action == 'resolve':
            return ResolveDisputeSerializer
        else:
            return DisputeDetailSerializer

    def get_queryset(self):
        """Filter queryset based on query params."""
        queryset = super().get_queryset()

        # Filter by asset
        asset_id = self.request.query_params.get('asset')
        if asset_id:
            queryset = queryset.filter(target_asset__uuid=asset_id)

        # Filter by disputer
        disputer = self.request.query_params.get('disputer')
        if disputer:
            queryset = queryset.filter(disputer__wallet_address=disputer)

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by result
        result_filter = self.request.query_params.get('result')
        if result_filter:
            queryset = queryset.filter(result=result_filter)

        # Filter for current user's disputes
        my_disputes = self.request.query_params.get('my_disputes')
        if my_disputes and self.request.user.is_authenticated:
            queryset = queryset.filter(
                Q(disputer=self.request.user) | Q(target_asset__creator=self.request.user)
            )

        return queryset.select_related(
            'target_asset__creator',
            'disputer',
            'resolved_by'
        ).prefetch_related('evidence__submitted_by')

    def list(self, request, *args, **kwargs):
        """List disputes with pagination."""
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def raise_dispute(self, request):
        """
        Raise a new dispute against an IP asset.

        POST /api/disputes/raise_dispute/
        {
            "asset_id": "...",
            "reason": "This asset infringes on my copyright...",
            "evidence_hash": "0x...",  // optional
            "disputer_address": "0x..."  // optional, defaults to user's wallet
        }
        """
        serializer = RaiseDisputeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get asset
        asset = get_object_or_404(IPAsset, uuid=serializer.validated_data['asset_id'])

        # Get disputer address
        disputer_address = serializer.validated_data.get('disputer_address')
        if not disputer_address:
            disputer_address = request.user.wallet_address

        # Get services
        story_service = get_story_service()
        dispute_service = get_dispute_service(story_service=story_service)

        try:
            dispute = dispute_service.raise_dispute(
                target_asset=asset,
                disputer_user=request.user,
                disputer_address=disputer_address,
                reason=serializer.validated_data['reason'],
                evidence_hash=serializer.validated_data.get('evidence_hash')
            )

            output_serializer = DisputeDetailSerializer(dispute)
            return Response({
                'message': f'Dispute raised against "{asset.title}"',
                'dispute': output_serializer.data
            }, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to raise dispute: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit_evidence(self, request, uuid=None):
        """
        Submit evidence for a dispute.

        POST /api/disputes/{uuid}/submit_evidence/
        {
            "description": "Evidence description...",
            "evidence_url": "https://...",  // optional
            "evidence_hash": "0x..."  // optional
        }
        """
        dispute = self.get_object()

        serializer = SubmitEvidenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get service
        dispute_service = get_dispute_service()

        try:
            evidence = dispute_service.submit_evidence(
                dispute=dispute,
                submitter_user=request.user,
                description=serializer.validated_data['description'],
                evidence_url=serializer.validated_data.get('evidence_url'),
                evidence_hash=serializer.validated_data.get('evidence_hash')
            )

            output_serializer = DisputeEvidenceSerializer(evidence)
            return Response({
                'message': 'Evidence submitted successfully',
                'evidence': output_serializer.data
            }, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to submit evidence: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def resolve(self, request, uuid=None):
        """
        Resolve a dispute (admin only).

        POST /api/disputes/{uuid}/resolve/
        {
            "result": "upheld|rejected|settled",
            "resolution_notes": "Resolution explanation..."  // optional
        }
        """
        dispute = self.get_object()

        serializer = ResolveDisputeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get service
        dispute_service = get_dispute_service()

        try:
            dispute = dispute_service.resolve_dispute(
                dispute=dispute,
                resolver_user=request.user,
                result=serializer.validated_data['result'],
                resolution_notes=serializer.validated_data.get('resolution_notes')
            )

            output_serializer = DisputeDetailSerializer(dispute)
            return Response({
                'message': f'Dispute resolved: {dispute.result}',
                'dispute': output_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to resolve dispute: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel(self, request, uuid=None):
        """
        Cancel a dispute (disputer only).

        POST /api/disputes/{uuid}/cancel/
        """
        dispute = self.get_object()

        # Get service
        dispute_service = get_dispute_service()

        try:
            dispute = dispute_service.cancel_dispute(
                dispute=dispute,
                canceller_user=request.user
            )

            output_serializer = DisputeDetailSerializer(dispute)
            return Response({
                'message': 'Dispute cancelled successfully',
                'dispute': output_serializer.data
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Failed to cancel dispute: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def evidence(self, request, uuid=None):
        """
        Get all evidence for a dispute.

        GET /api/disputes/{uuid}/evidence/
        """
        dispute = self.get_object()

        evidence = DisputeEvidence.objects.filter(
            dispute=dispute
        ).select_related('submitted_by').order_by('-submitted_at')

        serializer = DisputeEvidenceSerializer(evidence, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get dispute statistics.

        GET /api/disputes/statistics/
        GET /api/disputes/statistics/?asset={uuid}
        """
        # Get asset if specified
        asset = None
        asset_id = request.query_params.get('asset')
        if asset_id:
            asset = get_object_or_404(IPAsset, uuid=asset_id)

        # Get service
        dispute_service = get_dispute_service()

        try:
            stats = dispute_service.get_dispute_statistics(asset=asset)
            return Response(stats, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Failed to get dispute statistics: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def create(self, request, *args, **kwargs):
        """Disable direct create - use raise_dispute action instead."""
        return Response(
            {'error': 'Use /api/disputes/raise_dispute/ endpoint instead'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def update(self, request, *args, **kwargs):
        """Disable update - disputes cannot be directly updated."""
        return Response(
            {'error': 'Disputes cannot be directly updated. Use specific actions instead.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def partial_update(self, request, *args, **kwargs):
        """Disable partial update."""
        return Response(
            {'error': 'Disputes cannot be directly updated. Use specific actions instead.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def destroy(self, request, *args, **kwargs):
        """Disable delete - use cancel action instead."""
        return Response(
            {'error': 'Use /api/disputes/{uuid}/cancel/ endpoint instead'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
