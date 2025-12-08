"""
Integration test for AI Agents - Validates end-to-end functionality.

This test creates real database objects and verifies the entire workflow works.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.assets.models import IPAsset
from apps.ai.workflows.validation import PreMintValidationWorkflow

User = get_user_model()


class AIAgentIntegrationTest(TestCase):
    """Integration test for the complete AI validation workflow."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            wallet_address='0x' + '1' * 40,
            username='Integration Test User'
        )

        self.asset = IPAsset.objects.create(
            title='Test Asset for AI Validation',
            description='This is a comprehensive test description for AI analysis. '
                        'It contains enough content to properly test the quality scoring system. '
                        'The description includes details about the asset, its purpose, and usage.',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
            royalty_percentage=10,
            allow_derivatives=True,
            commercial_rights=False
        )

    def test_complete_validation_workflow(self):
        """Test that the complete validation workflow executes without errors."""
        # Run the validation workflow
        result = PreMintValidationWorkflow.validate_asset(self.asset.id)

        # Verify the result structure
        self.assertIsNotNone(result)
        self.assertIn('success', result)
        self.assertIn('overall_verdict', result)
        self.assertIn('analysis', result)

        # If successful, check that we got results
        if result['success']:
            self.assertIn('steps_completed', result)
            self.assertGreater(len(result['steps_completed']), 0)

            # Verify we have at least some analysis data
            analysis = result['analysis']
            self.assertTrue(
                'copyright' in analysis or 'quality' in analysis or 'pricing' in analysis,
                "At least one analysis type should be present"
            )

    def test_workflow_verdict_values(self):
        """Test that verdict is one of the expected values."""
        result = PreMintValidationWorkflow.validate_asset(self.asset.id)

        if 'overall_verdict' in result:
            self.assertIn(
                result['overall_verdict'],
                ['approved', 'warning', 'rejected'],
                "Verdict must be one of: approved, warning, rejected"
            )

    def test_workflow_with_existing_asset(self):
        """Test workflow with a real asset from the database."""
        # This verifies that the workflow can handle actual database objects
        result = PreMintValidationWorkflow.validate_asset(self.asset.id)

        # Should not raise exceptions
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
