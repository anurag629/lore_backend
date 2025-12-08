"""
Unit tests for AI Agents.

Tests copyright detection, quality analysis, and pricing agents.
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import Mock, patch, MagicMock
from PIL import Image
import io

from apps.assets.models import IPAsset
from apps.ai.agents import CopyrightAgent, QualityAgent, PricingAgent
from apps.ai.models import (
    CopyrightAnalysisResult,
    QualityAnalysisResult,
    PricingAnalysisResult
)

User = get_user_model()


class CopyrightAgentTestCase(TestCase):
    """Test cases for CopyrightAgent."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            wallet_address='0x1234567890123456789012345678901234567890',
            username='Test User',
        )

        self.asset = IPAsset.objects.create(
            title='Test Asset',
            description='This is a test asset description for copyright analysis.',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
        )

        self.agent = CopyrightAgent()

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        self.assertEqual(self.agent.get_name(), 'CopyrightAgent')
        self.assertIsNotNone(self.agent.config)

    def test_analyze_missing_asset(self):
        """Test analysis with non-existent asset."""
        result = self.agent.analyze(asset_id=99999)

        self.assertFalse(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('not found', result.errors[0])

    def test_analyze_text_similarity(self):
        """Test text similarity analysis."""
        # Create a similar asset
        similar_asset = IPAsset.objects.create(
            title='Test Asset',
            description='This is a test asset description for copyright analysis.',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
            status='minted'
        )

        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('similarity_score', result.data)
        self.assertIn('risk_level', result.data)
        self.assertIn('is_likely_original', result.data)

    @patch('apps.ai.agents.copyright_agent.CopyrightAgent._get_image_hash')
    def test_analyze_with_image(self, mock_get_hash):
        """Test analysis with image file."""
        import imagehash

        # Mock image hash
        mock_hash = MagicMock()
        mock_hash.__sub__ = Mock(return_value=5)  # Hamming distance
        mock_get_hash.return_value = mock_hash

        self.asset.file_url = 'https://example.com/image.jpg'
        self.asset.save()

        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertGreater(result.confidence, 0)

    def test_analyze_saves_result(self):
        """Test that analysis result is saved to database."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)

        # Check database
        db_result = CopyrightAnalysisResult.objects.get(asset=self.asset)
        self.assertIsNotNone(db_result)
        self.assertEqual(db_result.risk_level, result.data['risk_level'])

    def test_risk_level_calculation(self):
        """Test risk level calculation logic."""
        # Test with no matches
        result = self.agent.analyze(asset_id=self.asset.id)
        self.assertEqual(result.data['risk_level'], 'low')


class QualityAgentTestCase(TestCase):
    """Test cases for QualityAgent."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            wallet_address='0x1234567890123456789012345678901234567890',
            username='Test User',
        )

        self.asset = IPAsset.objects.create(
            title='High Quality Test Asset',
            description='This is a comprehensive description that provides detailed information about the asset. '
                       'It includes relevant keywords and is well-structured for SEO optimization.',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
        )

        self.agent = QualityAgent()

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        self.assertEqual(self.agent.get_name(), 'QualityAgent')

    def test_analyze_description_quality(self):
        """Test description quality analysis."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('description_quality', result.data)

        desc_quality = result.data['description_quality']
        self.assertIn('overall_score', desc_quality)
        self.assertIn('length_score', desc_quality)
        self.assertIn('word_count', desc_quality)

    def test_analyze_metadata_completeness(self):
        """Test metadata completeness scoring."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('metadata_completeness', result.data)
        self.assertGreater(result.data['metadata_completeness'], 0)

    def test_analyze_overall_score(self):
        """Test overall quality score calculation."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('overall_score', result.data)
        overall_score = result.data['overall_score']
        self.assertGreaterEqual(overall_score, 0)
        self.assertLessEqual(overall_score, 100)

    def test_improvement_suggestions(self):
        """Test that improvement suggestions are generated."""
        # Create asset with minimal data
        minimal_asset = IPAsset.objects.create(
            title='Test',
            description='Short',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
        )

        result = self.agent.analyze(asset_id=minimal_asset.id)

        self.assertTrue(result.success)
        self.assertIn('improvement_suggestions', result.data)
        self.assertGreater(len(result.data['improvement_suggestions']), 0)

    def test_strengths_identification(self):
        """Test that strengths are identified."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('strengths', result.data)

    @patch('apps.ai.agents.quality_agent.QualityAgent._load_image')
    def test_technical_quality_with_image(self, mock_load_image):
        """Test technical quality analysis with image."""
        # Create a mock image
        mock_image = Image.new('RGB', (1920, 1080))
        mock_load_image.return_value = mock_image

        self.asset.file_url = 'https://example.com/image.jpg'
        self.asset.save()

        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('technical_quality', result.data)
        tech_quality = result.data['technical_quality']
        self.assertTrue(tech_quality['has_image'])
        self.assertTrue(tech_quality['analysis_performed'])

    def test_analyze_saves_result(self):
        """Test that analysis result is saved to database."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)

        # Check database
        db_result = QualityAnalysisResult.objects.get(asset=self.asset)
        self.assertIsNotNone(db_result)
        self.assertEqual(db_result.overall_score, result.data['overall_score'])


class PricingAgentTestCase(TestCase):
    """Test cases for PricingAgent."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            wallet_address='0x1234567890123456789012345678901234567890',
            username='Test User',
        )

        self.asset = IPAsset.objects.create(
            title='Test Asset for Pricing',
            description='This asset needs pricing recommendations.',
            creator=self.user,
            media_url='https://example.com/test-image.jpg',
        )

        # Create some similar assets with royalties
        for i in range(5):
            IPAsset.objects.create(
                title=f'Similar Asset {i}',
                description='Similar asset description.',
                creator=self.user,
                media_url='https://example.com/test-image.jpg',
                status='minted',
                royalty_percentage=10 + i
            )

        self.agent = PricingAgent()

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        self.assertEqual(self.agent.get_name(), 'PricingAgent')

    def test_analyze_returns_pricing_tiers(self):
        """Test that analysis returns three pricing tiers."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('suggested_tiers', result.data)

        tiers = result.data['suggested_tiers']
        self.assertEqual(len(tiers), 3)

        # Check tier names
        tier_names = [tier['tier'] for tier in tiers]
        self.assertIn('conservative', tier_names)
        self.assertIn('balanced', tier_names)
        self.assertIn('aggressive', tier_names)

    def test_market_analysis(self):
        """Test market analysis calculation."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('market_average', result.data)
        self.assertIn('similar_assets_count', result.data)
        self.assertGreater(result.data['similar_assets_count'], 0)

    def test_demand_prediction(self):
        """Test demand prediction scoring."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('demand_prediction', result.data)

        demand = result.data['demand_prediction']
        self.assertGreaterEqual(demand, 0)
        self.assertLessEqual(demand, 100)

    def test_reasoning_generation(self):
        """Test that reasoning is provided."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('reasoning', result.data)
        self.assertIsInstance(result.data['reasoning'], str)
        self.assertGreater(len(result.data['reasoning']), 0)

    def test_tier_royalties_ordered(self):
        """Test that tier royalties are ordered correctly."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)

        tiers = {tier['tier']: tier['royalty_percentage']
                for tier in result.data['suggested_tiers']}

        # Conservative < Balanced < Aggressive
        self.assertLess(tiers['conservative'], tiers['balanced'])
        self.assertLess(tiers['balanced'], tiers['aggressive'])

    def test_with_quality_score(self):
        """Test pricing with existing quality analysis."""
        # Create quality result first
        QualityAnalysisResult.objects.create(
            asset=self.asset,
            overall_score=85.0,
            technical_quality={'overall_score': 80},
            description_quality={'overall_score': 90},
            metadata_completeness=85.0,
            market_appeal=80.0,
            improvement_suggestions=[],
            strengths=['High quality'],
            confidence=0.9
        )

        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)
        self.assertIn('quality_score_used', result.data)
        self.assertEqual(result.data['quality_score_used'], 85.0)

    def test_analyze_saves_result(self):
        """Test that analysis result is saved to database."""
        result = self.agent.analyze(asset_id=self.asset.id)

        self.assertTrue(result.success)

        # Check database
        db_result = PricingAnalysisResult.objects.get(asset=self.asset)
        self.assertIsNotNone(db_result)
        self.assertEqual(db_result.market_average, result.data['market_average'])


# Run tests with: python manage.py test apps.ai.tests.test_agents
