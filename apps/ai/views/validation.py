"""
AI Validation Views

API endpoints for pre-mint validation and quality analysis.
"""
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from apps.assets.models import IPAsset
from apps.ai.workflows.validation import PreMintValidationWorkflow

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_asset_before_mint(request, asset_uuid):
    """
    Run comprehensive pre-mint validation on an asset.

    This endpoint runs multiple AI agents to analyze:
    - Copyright/plagiarism risk
    - Quality metrics
    - Pricing recommendations

    **URL**: POST /api/ai/validate/{asset_uuid}/

    **Response**:
    ```json
    {
        "success": true,
        "workflow_status": "completed",
        "overall_verdict": "approved",  // "approved", "warning", or "rejected"
        "steps_completed": ["copyright", "quality", "pricing"],
        "warnings": [],
        "blockers": [],
        "total_time": 2.5,
        "analysis": {
            "copyright": {
                "risk_level": "low",
                "similarity_score": 0.15,
                "is_likely_original": true,
                "recommendations": [...]
            },
            "quality": {
                "overall_score": 75.5,
                "strengths": [...],
                "improvements": [...]
            },
            "pricing": {
                "suggested_tiers": [...],
                "market_average": 10.0
            }
        }
    }
    ```
    """
    # Get the asset
    asset = get_object_or_404(IPAsset, uuid=asset_uuid)

    # Check permission - user must own the asset
    if asset.creator != request.user:
        return Response(
            {
                'error': 'You do not have permission to validate this asset',
                'detail': 'Only the asset creator can run validation'
            },
            status=status.HTTP_403_FORBIDDEN
        )

    # Check asset status
    if asset.status == 'minted':
        return Response(
            {
                'error': 'Asset already minted',
                'detail': 'Validation can only be run on draft assets'
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Run validation workflow
    try:
        result = PreMintValidationWorkflow.validate_asset(asset.id)

        if not result.get('success', False):
            return Response(
                {
                    'error': 'Validation failed',
                    'detail': result.get('error', 'Unknown error occurred')
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(result, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in validate_asset_before_mint: {e}", exc_info=True)
        return Response(
            {
                'error': 'Validation failed',
                'detail': str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_copyright_check(request, asset_uuid):
    """
    Run only copyright analysis on an asset.

    **URL**: POST /api/ai/copyright/{asset_uuid}/

    **Response**:
    ```json
    {
        "success": true,
        "risk_level": "low",
        "similarity_score": 0.15,
        "is_likely_original": true,
        "potential_matches": [...],
        "recommendations": [...]
    }
    ```
    """
    from apps.ai.agents import CopyrightAgent

    # Get the asset
    asset = get_object_or_404(IPAsset, uuid=asset_uuid)

    # Check permission
    if asset.creator != request.user:
        return Response(
            {'error': 'Permission denied'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Run copyright agent
    try:
        agent = CopyrightAgent()
        result = agent.run(asset_id=asset.id)

        if not result.success:
            return Response(
                {
                    'error': 'Copyright analysis failed',
                    'details': result.errors
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(result.data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in run_copyright_check: {e}", exc_info=True)
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_quality_analysis(request, asset_uuid):
    """
    Run only quality analysis on an asset.

    **URL**: POST /api/ai/quality/{asset_uuid}/

    **Response**:
    ```json
    {
        "success": true,
        "overall_score": 75.5,
        "technical_quality": {...},
        "description_quality": {...},
        "metadata_completeness": 80.0,
        "market_appeal": 70.0,
        "strengths": [...],
        "improvement_suggestions": [...]
    }
    ```
    """
    from apps.ai.agents import QualityAgent

    # Get the asset
    asset = get_object_or_404(IPAsset, uuid=asset_uuid)

    # Check permission
    if asset.creator != request.user:
        return Response(
            {'error': 'Permission denied'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Run quality agent
    try:
        agent = QualityAgent()
        result = agent.run(asset_id=asset.id)

        if not result.success:
            return Response(
                {
                    'error': 'Quality analysis failed',
                    'details': result.errors
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(result.data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in run_quality_analysis: {e}", exc_info=True)
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_pricing_analysis(request, asset_uuid):
    """
    Run only pricing analysis on an asset.

    **URL**: POST /api/ai/pricing/{asset_uuid}/

    **Response**:
    ```json
    {
        "success": true,
        "suggested_tiers": [
            {
                "tier": "conservative",
                "royalty_percentage": 7.0,
                "description": "..."
            },
            ...
        ],
        "market_average": 10.0,
        "similar_assets_count": 45,
        "demand_prediction": 65.0,
        "reasoning": "..."
    }
    ```
    """
    from apps.ai.agents import PricingAgent

    # Get the asset
    asset = get_object_or_404(IPAsset, uuid=asset_uuid)

    # Check permission
    if asset.creator != request.user:
        return Response(
            {'error': 'Permission denied'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Run pricing agent
    try:
        agent = PricingAgent()
        result = agent.run(asset_id=asset.id)

        if not result.success:
            return Response(
                {
                    'error': 'Pricing analysis failed',
                    'details': result.errors
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(result.data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in run_pricing_analysis: {e}", exc_info=True)
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
