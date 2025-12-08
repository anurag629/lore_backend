"""
Unit tests for AI Workflows and Orchestration.

Tests the orchestrator and pre-mint validation workflow.
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import Mock, patch, MagicMock

from apps.assets.models import IPAsset
from apps.ai.models import ValidationWorkflowResult
from apps.ai.agents import CopyrightAgent, QualityAgent, PricingAgent
from apps.ai.agents.base_agent import AgentResult
from apps.ai.workflows.orchestrator import (
    AgentOrchestrator,
    Workflow,
    WorkflowStep,
    WorkflowResult
)
from apps.ai.workflows.validation import PreMintValidationWorkflow

User = get_user_model()


class AgentOrchestratorTestCase(TestCase):
    """Test cases for AgentOrchestrator."""

    def setUp(self):
        """Set up test data."""
        self.orchestrator = AgentOrchestrator()

    def test_register_agent(self):
        """Test agent registration."""
        agent = CopyrightAgent()
        self.orchestrator.register_agent('test_agent', agent)

        self.assertIn('test_agent', self.orchestrator.agents)
        self.assertEqual(self.orchestrator.agents['test_agent'], agent)

    def test_register_workflow(self):
        """Test workflow registration."""
        workflow = Workflow(
            name='test_workflow',
            steps=[],
            description='Test workflow'
        )
        self.orchestrator.register_workflow(workflow)

        self.assertIn('test_workflow', self.orchestrator.workflows)

    def test_run_agent_not_found(self):
        """Test running non-existent agent raises error."""
        with self.assertRaises(ValueError):
            self.orchestrator.run_agent('nonexistent', asset_id=1)

    def test_run_workflow_not_found(self):
        """Test running non-existent workflow raises error."""
        with self.assertRaises(ValueError):
            self.orchestrator.run_workflow('nonexistent', {})

    def test_get_available_agents(self):
        """Test getting list of available agents."""
        agent1 = CopyrightAgent()
        agent2 = QualityAgent()

        self.orchestrator.register_agent('agent1', agent1)
        self.orchestrator.register_agent('agent2', agent2)

        available = self.orchestrator.get_available_agents()
        self.assertEqual(len(available), 2)
        self.assertIn('agent1', available)
        self.assertIn('agent2', available)

    def test_get_available_workflows(self):
        """Test getting list of available workflows."""
        workflow1 = Workflow(name='wf1', steps=[])
        workflow2 = Workflow(name='wf2', steps=[])

        self.orchestrator.register_workflow(workflow1)
        self.orchestrator.register_workflow(workflow2)

        available = self.orchestrator.get_available_workflows()
        self.assertEqual(len(available), 2)
        self.assertIn('wf1', available)
        self.assertIn('wf2', available)


class WorkflowTestCase(TestCase):
    """Test cases for Workflow execution."""

    def setUp(self):
        """Set up test data."""
        self.orchestrator = AgentOrchestrator()

        # Register mock agents
        self.mock_agent1 = Mock()
        self.mock_agent2 = Mock()

        self.orchestrator.register_agent('agent1', self.mock_agent1)
        self.orchestrator.register_agent('agent2', self.mock_agent2)

    def test_workflow_execution_success(self):
        """Test successful workflow execution."""
        # Mock successful agent results
        self.mock_agent1.run.return_value = AgentResult(
            success=True,
            data={'result': 'data1'},
            confidence=0.9
        )
        self.mock_agent2.run.return_value = AgentResult(
            success=True,
            data={'result': 'data2'},
            confidence=0.8
        )

        workflow = Workflow(
            name='test_workflow',
            steps=[
                WorkflowStep(agent_name='agent1', description='Step 1'),
                WorkflowStep(agent_name='agent2', description='Step 2'),
            ]
        )

        result = workflow.execute(self.orchestrator, {'test_input': 'value'})

        self.assertTrue(result.success)
        self.assertEqual(len(result.steps_completed), 2)
        self.assertIn('agent1', result.agent_results)
        self.assertIn('agent2', result.agent_results)

    def test_workflow_with_required_step_failure(self):
        """Test workflow stops on required step failure."""
        # First agent fails
        self.mock_agent1.run.return_value = AgentResult(
            success=False,
            data={},
            errors=['Agent 1 failed']
        )

        workflow = Workflow(
            name='test_workflow',
            steps=[
                WorkflowStep(agent_name='agent1', description='Step 1', required=True),
                WorkflowStep(agent_name='agent2', description='Step 2'),
            ]
        )

        result = workflow.execute(self.orchestrator, {})

        self.assertFalse(result.success)
        self.assertEqual(len(result.steps_completed), 1)
        # Agent 2 should not have been called
        self.mock_agent2.run.assert_not_called()

    def test_workflow_with_optional_step_failure(self):
        """Test workflow continues on optional step failure."""
        # First agent fails but is optional
        self.mock_agent1.run.return_value = AgentResult(
            success=False,
            data={},
            errors=['Agent 1 failed']
        )
        self.mock_agent2.run.return_value = AgentResult(
            success=True,
            data={'result': 'data2'},
            confidence=0.8
        )

        workflow = Workflow(
            name='test_workflow',
            steps=[
                WorkflowStep(agent_name='agent1', description='Step 1', required=False),
                WorkflowStep(agent_name='agent2', description='Step 2', required=True),
            ]
        )

        result = workflow.execute(self.orchestrator, {})

        self.assertTrue(result.success)
        self.assertEqual(len(result.steps_completed), 2)
        self.assertGreater(len(result.errors), 0)

    def test_workflow_conditional_step(self):
        """Test conditional step execution."""
        self.mock_agent1.run.return_value = AgentResult(
            success=True,
            data={'score': 30},
            confidence=0.9
        )

        workflow = Workflow(
            name='test_workflow',
            steps=[
                WorkflowStep(agent_name='agent1', description='Step 1'),
                WorkflowStep(
                    agent_name='agent2',
                    description='Step 2',
                    condition=lambda data, results: results['agent1'].data.get('score', 0) > 50
                ),
            ]
        )

        result = workflow.execute(self.orchestrator, {})

        # Agent 2 should be skipped due to condition
        self.assertTrue(result.success)
        self.assertEqual(len(result.steps_completed), 1)
        self.mock_agent2.run.assert_not_called()
        self.assertGreater(len(result.warnings), 0)


class PreMintValidationWorkflowTestCase(TestCase):
    """Test cases for PreMintValidationWorkflow."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            wallet_address='0x1234567890123456789012345678901234567890',
            username='Test User',
        )

        self.asset = IPAsset.objects.create(
            title='Test Asset for Validation',
            description='This is a comprehensive test asset with detailed description.',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
        )

    def test_create_workflow(self):
        """Test workflow creation."""
        workflow = PreMintValidationWorkflow.create_workflow()

        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.name, 'pre_mint_validation')
        self.assertGreater(len(workflow.steps), 0)

    def test_create_orchestrator(self):
        """Test orchestrator creation."""
        orchestrator = PreMintValidationWorkflow.create_orchestrator()

        self.assertIsNotNone(orchestrator)
        self.assertIn('copyright', orchestrator.agents)
        self.assertIn('quality', orchestrator.agents)
        self.assertIn('pricing', orchestrator.agents)
        self.assertIn('pre_mint_validation', orchestrator.workflows)

    @patch('apps.ai.workflows.validation.PreMintValidationWorkflow.create_orchestrator')
    @patch('apps.ai.agents.copyright_agent.CopyrightAgent.analyze')
    @patch('apps.ai.agents.quality_agent.QualityAgent.analyze')
    @patch('apps.ai.agents.pricing_agent.PricingAgent.analyze')
    def test_validate_asset_success(self, mock_pricing, mock_quality, mock_copyright, mock_orchestrator):
        """Test successful asset validation."""
        # Mock agent results
        mock_copyright.return_value = AgentResult(
            success=True,
            data={
                'risk_level': 'low',
                'similarity_score': 0.1,
                'is_likely_original': True,
                'potential_matches': [],
                'recommendations': ['All clear']
            },
            confidence=0.9
        )

        mock_quality.return_value = AgentResult(
            success=True,
            data={
                'overall_score': 75,
                'technical_quality': {'overall_score': 80},
                'description_quality': {'overall_score': 70},
                'metadata_completeness': 80,
                'market_appeal': 70,
                'strengths': ['Good quality'],
                'improvement_suggestions': []
            },
            confidence=0.85
        )

        mock_pricing.return_value = AgentResult(
            success=True,
            data={
                'suggested_tiers': [
                    {'tier': 'conservative', 'royalty_percentage': 7.0},
                    {'tier': 'balanced', 'royalty_percentage': 10.0},
                    {'tier': 'aggressive', 'royalty_percentage': 13.0}
                ],
                'market_average': 10.0,
                'similar_assets_count': 10,
                'demand_prediction': 65,
                'reasoning': 'Test reasoning'
            },
            confidence=0.8
        )

        # Mock orchestrator to use actual workflow but mocked agents
        real_orchestrator = PreMintValidationWorkflow.create_orchestrator()
        mock_orchestrator.return_value = real_orchestrator

        # Replace agents with mocked versions
        real_orchestrator.agents['copyright'].analyze = mock_copyright
        real_orchestrator.agents['quality'].analyze = mock_quality
        real_orchestrator.agents['pricing'].analyze = mock_pricing

        result = PreMintValidationWorkflow.validate_asset(self.asset.id)

        self.assertTrue(result['success'])
        self.assertEqual(result['overall_verdict'], 'approved')
        self.assertIn('analysis', result)
        self.assertIn('copyright', result['analysis'])
        self.assertIn('quality', result['analysis'])
        self.assertIn('pricing', result['analysis'])

    def test_validate_asset_not_found(self):
        """Test validation with non-existent asset."""
        result = PreMintValidationWorkflow.validate_asset(99999)

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    @patch('apps.ai.workflows.validation.PreMintValidationWorkflow.create_orchestrator')
    @patch('apps.ai.agents.copyright_agent.CopyrightAgent.analyze')
    @patch('apps.ai.agents.quality_agent.QualityAgent.analyze')
    def test_validate_asset_with_warnings(self, mock_quality, mock_copyright, mock_orchestrator):
        """Test validation that produces warnings."""
        # Copyright shows medium risk
        mock_copyright.return_value = AgentResult(
            success=True,
            data={
                'risk_level': 'medium',
                'similarity_score': 0.8,
                'is_likely_original': False,
                'potential_matches': [{'asset_id': 1, 'similarity': 0.8}],
                'recommendations': ['Review similarity']
            },
            confidence=0.9
        )

        # Quality is low
        mock_quality.return_value = AgentResult(
            success=True,
            data={
                'overall_score': 35,
                'technical_quality': {'overall_score': 30},
                'description_quality': {'overall_score': 40},
                'metadata_completeness': 30,
                'market_appeal': 35,
                'strengths': [],
                'improvement_suggestions': ['Improve quality']
            },
            confidence=0.7
        )

        real_orchestrator = PreMintValidationWorkflow.create_orchestrator()
        mock_orchestrator.return_value = real_orchestrator
        real_orchestrator.agents['copyright'].analyze = mock_copyright
        real_orchestrator.agents['quality'].analyze = mock_quality

        result = PreMintValidationWorkflow.validate_asset(self.asset.id)

        self.assertTrue(result['success'])
        self.assertEqual(result['overall_verdict'], 'warning')
        self.assertGreater(len(result['warnings']), 0)

    def test_validation_creates_database_record(self):
        """Test that validation creates ValidationWorkflowResult."""
        # Use a simple mock to avoid complexity
        with patch('apps.ai.workflows.validation.PreMintValidationWorkflow.create_orchestrator'):
            PreMintValidationWorkflow.validate_asset(self.asset.id)

        # Check database record was created
        result = ValidationWorkflowResult.objects.filter(asset=self.asset).first()
        self.assertIsNotNone(result)


# Run tests with: python manage.py test apps.ai.tests.test_workflows
