"""
Pre-Mint Validation Workflow

Comprehensive validation workflow that runs before minting an IP asset.
Coordinates Copyright, Quality, and Pricing agents to provide complete analysis.
"""
import logging
from typing import Dict, Any
from datetime import datetime

from django.utils import timezone

from apps.assets.models import IPAsset
from apps.ai.models import ValidationWorkflowResult
from apps.ai.agents import CopyrightAgent, QualityAgent, PricingAgent
from .orchestrator import Workflow, WorkflowStep, AgentOrchestrator, WorkflowResult

logger = logging.getLogger(__name__)


class PreMintValidationWorkflow:
    """
    Pre-mint validation workflow that analyzes assets before minting.

    Runs three agents in sequence:
    1. Copyright Detection - Check for potential infringement
    2. Quality Analysis - Assess asset quality
    3. Smart Pricing - Recommend royalty rates (conditional on quality)
    """

    WORKFLOW_NAME = "pre_mint_validation"

    @staticmethod
    def create_workflow() -> Workflow:
        """
        Create the pre-mint validation workflow.

        Returns:
            Configured Workflow instance
        """
        steps = [
            WorkflowStep(
                agent_name='copyright',
                description='Copyright and plagiarism detection',
                required=True,
                timeout=30
            ),
            WorkflowStep(
                agent_name='quality',
                description='Quality analysis and scoring',
                required=True,
                timeout=30
            ),
            WorkflowStep(
                agent_name='pricing',
                description='Smart pricing recommendations',
                required=False,  # Optional - only if quality is good
                condition=lambda data, results: (
                    'quality' in results and
                    results['quality'].success and
                    results['quality'].data.get('overall_score', 0) > 40
                ),
                timeout=20
            ),
        ]

        return Workflow(
            name=PreMintValidationWorkflow.WORKFLOW_NAME,
            steps=steps,
            description="Comprehensive pre-mint validation including copyright, quality, and pricing analysis"
        )

    @staticmethod
    def create_orchestrator() -> AgentOrchestrator:
        """
        Create and configure the orchestrator with all required agents.

        Returns:
            Configured AgentOrchestrator instance
        """
        orchestrator = AgentOrchestrator()

        # Register agents
        orchestrator.register_agent('copyright', CopyrightAgent())
        orchestrator.register_agent('quality', QualityAgent())
        orchestrator.register_agent('pricing', PricingAgent())

        # Register workflow
        workflow = PreMintValidationWorkflow.create_workflow()
        orchestrator.register_workflow(workflow)

        return orchestrator

    @staticmethod
    def validate_asset(asset_id: int) -> Dict[str, Any]:
        """
        Run complete pre-mint validation on an asset.

        Args:
            asset_id: ID of the IPAsset to validate

        Returns:
            Dictionary with validation results
        """
        logger.info(f"Starting pre-mint validation for asset {asset_id}")

        try:
            # Get the asset
            asset = IPAsset.objects.get(id=asset_id)
        except IPAsset.DoesNotExist:
            return {
                'success': False,
                'error': f"Asset with id {asset_id} not found"
            }

        # Create workflow result entry
        workflow_result, created = ValidationWorkflowResult.objects.get_or_create(
            asset=asset,
            defaults={
                'workflow_status': 'running',
                'started_at': timezone.now(),
            }
        )

        if not created:
            # Update existing record
            workflow_result.workflow_status = 'running'
            workflow_result.started_at = timezone.now()
            workflow_result.save()

        # Create orchestrator and run workflow
        orchestrator = PreMintValidationWorkflow.create_orchestrator()

        try:
            result = orchestrator.run_workflow(
                PreMintValidationWorkflow.WORKFLOW_NAME,
                {'asset_id': asset_id}
            )

            # Process results
            overall_verdict, warnings, blockers = PreMintValidationWorkflow._analyze_results(
                result,
                asset
            )

            # Update workflow result
            workflow_result.workflow_status = 'completed' if result.success else 'failed'
            workflow_result.steps_completed = result.steps_completed
            workflow_result.overall_verdict = overall_verdict
            workflow_result.agent_results = {
                name: agent_result.to_dict()
                for name, agent_result in result.agent_results.items()
            }
            workflow_result.warnings = warnings
            workflow_result.blockers = blockers
            workflow_result.total_processing_time = result.total_time
            workflow_result.completed_at = timezone.now()
            workflow_result.save()

            # Build response
            response = {
                'success': result.success,
                'workflow_status': workflow_result.workflow_status,
                'overall_verdict': overall_verdict,
                'steps_completed': result.steps_completed,
                'warnings': warnings,
                'blockers': blockers,
                'total_time': result.total_time,
                'analysis': PreMintValidationWorkflow._format_analysis(result),
            }

            logger.info(
                f"Pre-mint validation completed for asset {asset_id}: {overall_verdict}"
            )

            return response

        except Exception as e:
            logger.error(f"Error in pre-mint validation: {e}", exc_info=True)

            # Update workflow result with error
            workflow_result.workflow_status = 'failed'
            workflow_result.completed_at = timezone.now()
            workflow_result.save()

            return {
                'success': False,
                'error': str(e),
                'workflow_status': 'failed'
            }

    @staticmethod
    def _analyze_results(
        result: WorkflowResult,
        asset: IPAsset
    ) -> tuple[str, list[str], list[str]]:
        """
        Analyze workflow results and determine overall verdict.

        Args:
            result: WorkflowResult from orchestrator
            asset: The asset being validated

        Returns:
            Tuple of (overall_verdict, warnings, blockers)
        """
        warnings = list(result.warnings)
        blockers = []

        # Analyze copyright results
        if 'copyright' in result.agent_results:
            copyright_result = result.agent_results['copyright']
            if copyright_result.success:
                risk_level = copyright_result.data.get('risk_level', 'low')

                if risk_level == 'high':
                    blockers.append(
                        "⛔ High copyright risk detected. Please review potential matches "
                        "before minting."
                    )
                elif risk_level == 'medium':
                    warnings.append(
                        "⚠️ Medium copyright risk. Review similarity to existing assets."
                    )

        # Analyze quality results
        if 'quality' in result.agent_results:
            quality_result = result.agent_results['quality']
            if quality_result.success:
                overall_score = quality_result.data.get('overall_score', 0)

                if overall_score < 30:
                    warnings.append(
                        f"⚠️ Low quality score ({overall_score:.1f}/100). "
                        "Consider improving asset quality."
                    )
                elif overall_score < 50:
                    warnings.append(
                        f"Quality score is moderate ({overall_score:.1f}/100). "
                        "Review improvement suggestions."
                    )

        # Determine overall verdict
        if blockers:
            overall_verdict = 'rejected'
        elif warnings:
            overall_verdict = 'warning'
        else:
            overall_verdict = 'approved'

        return overall_verdict, warnings, blockers

    @staticmethod
    def _format_analysis(result: WorkflowResult) -> Dict[str, Any]:
        """
        Format analysis results for API response.

        Args:
            result: WorkflowResult from orchestrator

        Returns:
            Formatted analysis dictionary
        """
        analysis = {}

        # Copyright analysis
        if 'copyright' in result.agent_results:
            copyright_result = result.agent_results['copyright']
            if copyright_result.success:
                analysis['copyright'] = {
                    'risk_level': copyright_result.data.get('risk_level'),
                    'similarity_score': copyright_result.data.get('similarity_score'),
                    'is_likely_original': copyright_result.data.get('is_likely_original'),
                    'potential_matches': copyright_result.data.get('potential_matches', [])[:3],
                    'recommendations': copyright_result.data.get('recommendations', []),
                    'confidence': copyright_result.confidence,
                }

        # Quality analysis
        if 'quality' in result.agent_results:
            quality_result = result.agent_results['quality']
            if quality_result.success:
                analysis['quality'] = {
                    'overall_score': quality_result.data.get('overall_score'),
                    'technical_quality': quality_result.data.get('technical_quality', {}).get('overall_score', 0),
                    'description_quality': quality_result.data.get('description_quality', {}).get('overall_score', 0),
                    'metadata_completeness': quality_result.data.get('metadata_completeness'),
                    'market_appeal': quality_result.data.get('market_appeal'),
                    'strengths': quality_result.data.get('strengths', []),
                    'improvements': quality_result.data.get('improvement_suggestions', []),
                    'confidence': quality_result.confidence,
                }

        # Pricing analysis
        if 'pricing' in result.agent_results:
            pricing_result = result.agent_results['pricing']
            if pricing_result.success:
                analysis['pricing'] = {
                    'suggested_tiers': pricing_result.data.get('suggested_tiers', []),
                    'market_average': pricing_result.data.get('market_average'),
                    'similar_assets_count': pricing_result.data.get('similar_assets_count'),
                    'demand_prediction': pricing_result.data.get('demand_prediction'),
                    'reasoning': pricing_result.data.get('reasoning'),
                    'confidence': pricing_result.confidence,
                }

        return analysis
