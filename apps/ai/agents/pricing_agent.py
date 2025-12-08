"""
Smart Pricing Agent

Provides intelligent pricing recommendations based on:
- Market analysis of similar assets
- Historical royalty rates
- Asset quality metrics
- Demand prediction
- Three-tier pricing strategy (conservative, balanced, aggressive)
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from django.db.models import Avg, Count, Q

from apps.assets.models import IPAsset
from apps.ai.models import PricingAnalysisResult, QualityAnalysisResult
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class PricingAgent(BaseAgent):
    """
    Agent for smart pricing recommendations.

    Analyzes market data and asset characteristics to suggest
    optimal royalty percentages across three pricing tiers.
    """

    # Default market averages by asset type
    DEFAULT_ROYALTIES = {
        'image': 10.0,
        'video': 12.0,
        'audio': 15.0,
        'text': 8.0,
        'code': 10.0,
        'model': 10.0,
        'other': 10.0,
    }

    # Tier multipliers
    TIER_MULTIPLIERS = {
        'conservative': 0.7,
        'balanced': 1.0,
        'aggressive': 1.3,
    }

    def get_name(self) -> str:
        return "PricingAgent"

    def analyze(self, asset_id: int, **kwargs) -> AgentResult:
        """
        Analyze market data and suggest pricing tiers.

        Args:
            asset_id: ID of the IPAsset to analyze

        Returns:
            AgentResult with pricing recommendations
        """
        # Validate input
        error = self.validate_input(['asset_id'], asset_id=asset_id)
        if error:
            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                errors=[error]
            )

        try:
            # Get the asset
            asset = IPAsset.objects.select_related('creator').get(id=asset_id)
        except IPAsset.DoesNotExist:
            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                errors=[f"Asset with id {asset_id} not found"]
            )

        warnings = []

        # 1. Find similar assets and calculate market average
        similar_assets, market_average = self._analyze_market(asset)

        # 2. Get quality score (if available)
        quality_score = self._get_quality_score(asset)

        # 3. Predict demand
        demand_prediction = self._predict_demand(
            asset,
            quality_score,
            len(similar_assets)
        )

        # 4. Calculate base royalty
        base_royalty = self._calculate_base_royalty(
            asset,
            market_average,
            quality_score,
            demand_prediction
        )

        # 5. Generate three pricing tiers
        suggested_tiers = self._generate_pricing_tiers(base_royalty)

        # 6. Generate reasoning
        reasoning = self._generate_reasoning(
            asset,
            market_average,
            quality_score,
            demand_prediction,
            len(similar_assets)
        )

        # 7. Calculate confidence
        confidence = self._calculate_confidence(
            asset,
            len(similar_assets),
            quality_score is not None
        )

        # Build result data
        data = {
            'suggested_tiers': suggested_tiers,
            'market_average': round(market_average, 2),
            'similar_assets_count': len(similar_assets),
            'demand_prediction': round(demand_prediction, 2),
            'confidence': round(confidence, 2),
            'reasoning': reasoning,
            'quality_score_used': quality_score,
        }

        # Save result to database
        PricingAnalysisResult.objects.update_or_create(
            asset=asset,
            defaults={
                'suggested_tiers': suggested_tiers,
                'market_average': market_average,
                'similar_assets_count': len(similar_assets),
                'demand_prediction': demand_prediction,
                'confidence': confidence,
                'reasoning': reasoning,
            }
        )

        return AgentResult(
            success=True,
            data=data,
            confidence=confidence,
            warnings=warnings
        )

    def _analyze_market(self, asset: IPAsset) -> Tuple[List[IPAsset], float]:
        """
        Analyze market for similar assets.

        Args:
            asset: The asset to analyze

        Returns:
            Tuple of (similar_assets, market_average_royalty)
        """
        # Find similar assets by type and tags
        similar_query = IPAsset.objects.filter(
            status='minted'
        ).exclude(
            id=asset.id
        )

        # Filter by asset type
        if getattr(asset, 'asset_type', None):
            similar_query = similar_query.filter(asset_type=asset.asset_type)

        # Filter by creator (to understand their pricing patterns)
        creator_assets = similar_query.filter(creator=asset.creator)

        # Get similar assets
        similar_assets = list(similar_query[:100])  # Limit for performance

        # Calculate average royalty
        royalty_avg = similar_query.filter(
            royalty_percentage__isnull=False
        ).aggregate(Avg('royalty_percentage'))['royalty_percentage__avg']

        # If no market data, use defaults
        if royalty_avg is None:
            asset_type = asset.asset_type or 'other'
            royalty_avg = self.DEFAULT_ROYALTIES.get(asset_type, 10.0)
        else:
            royalty_avg = float(royalty_avg)

        return similar_assets, royalty_avg

    def _get_quality_score(self, asset: IPAsset) -> Optional[float]:
        """
        Get quality score from QualityAnalysisResult if available.

        Args:
            asset: The asset

        Returns:
            Quality score or None
        """
        try:
            quality_result = QualityAnalysisResult.objects.get(asset=asset)
            return quality_result.overall_score
        except QualityAnalysisResult.DoesNotExist:
            return None

    def _predict_demand(
        self,
        asset: IPAsset,
        quality_score: Optional[float],
        similar_count: int
    ) -> float:
        """
        Predict demand for the asset.

        Args:
            asset: The asset
            quality_score: Quality score (if available)
            similar_count: Number of similar assets found

        Returns:
            Demand prediction score (0-100)
        """
        demand = 50  # Base demand

        # Quality affects demand
        if quality_score is not None:
            if quality_score >= 80:
                demand += 20
            elif quality_score >= 60:
                demand += 10
            elif quality_score < 40:
                demand -= 10

        # Scarcity affects demand (fewer similar = higher demand)
        if similar_count < 10:
            demand += 15
        elif similar_count < 50:
            demand += 5
        elif similar_count > 200:
            demand -= 10

        # Popular asset types have higher demand
        high_demand_types = ['video', 'audio', 'model']
        if asset.asset_type in high_demand_types:
            demand += 10

        # Complete metadata suggests professionalism -> higher demand
        metadata_fields = [
            asset.description,
            asset.tags,
            asset.license_type,
        ]
        complete_fields = sum(1 for field in metadata_fields if field)
        demand += complete_fields * 3

        return max(0, min(100, demand))

    def _calculate_base_royalty(
        self,
        asset: IPAsset,
        market_average: float,
        quality_score: Optional[float],
        demand_prediction: float
    ) -> float:
        """
        Calculate base royalty percentage.

        Args:
            asset: The asset
            market_average: Market average royalty
            quality_score: Quality score (if available)
            demand_prediction: Predicted demand

        Returns:
            Base royalty percentage
        """
        # Start with market average
        base = market_average

        # Adjust based on quality
        if quality_score is not None:
            if quality_score >= 80:
                base *= 1.2
            elif quality_score >= 60:
                base *= 1.1
            elif quality_score < 40:
                base *= 0.9

        # Adjust based on demand
        if demand_prediction >= 75:
            base *= 1.15
        elif demand_prediction >= 60:
            base *= 1.05
        elif demand_prediction < 40:
            base *= 0.95

        # Ensure within reasonable bounds (2-30%)
        base = max(2.0, min(30.0, base))

        return base

    def _generate_pricing_tiers(self, base_royalty: float) -> List[Dict[str, Any]]:
        """
        Generate three pricing tiers from base royalty.

        Args:
            base_royalty: Calculated base royalty

        Returns:
            List of tier dictionaries
        """
        tiers = []

        for tier_name, multiplier in self.TIER_MULTIPLIERS.items():
            royalty = base_royalty * multiplier
            royalty = max(2.0, min(30.0, royalty))  # Ensure bounds

            tier_data = {
                'tier': tier_name,
                'royalty_percentage': round(royalty, 1),
                'description': self._get_tier_description(tier_name, royalty),
            }
            tiers.append(tier_data)

        return tiers

    def _get_tier_description(self, tier_name: str, royalty: float) -> str:
        """
        Get description for a pricing tier.

        Args:
            tier_name: Name of the tier
            royalty: Royalty percentage

        Returns:
            Description string
        """
        descriptions = {
            'conservative': (
                f"Conservative pricing at {royalty:.1f}% royalty. "
                "Maximizes adoption and derivative creation. Best for building an audience."
            ),
            'balanced': (
                f"Balanced pricing at {royalty:.1f}% royalty. "
                "Market-aligned rate that balances revenue with accessibility. Recommended for most creators."
            ),
            'aggressive': (
                f"Premium pricing at {royalty:.1f}% royalty. "
                "Maximizes revenue per derivative. Best for high-quality, unique assets."
            ),
        }
        return descriptions.get(tier_name, "")

    def _generate_reasoning(
        self,
        asset: IPAsset,
        market_average: float,
        quality_score: Optional[float],
        demand_prediction: float,
        similar_count: int
    ) -> str:
        """
        Generate explanation for pricing recommendations.

        Args:
            asset: The asset
            market_average: Market average royalty
            quality_score: Quality score (if available)
            demand_prediction: Predicted demand
            similar_count: Number of similar assets

        Returns:
            Reasoning text
        """
        reasons = []

        # Market context
        if similar_count > 0:
            reasons.append(
                f"Based on analysis of {similar_count} similar assets, "
                f"the market average royalty is {market_average:.1f}%."
            )
        else:
            reasons.append(
                f"Using industry standard royalty of {market_average:.1f}% "
                f"for {asset.asset_type or 'this type of'} assets."
            )

        # Quality factor
        if quality_score is not None:
            if quality_score >= 70:
                reasons.append(
                    f"Your asset has a high quality score ({quality_score:.1f}/100), "
                    "supporting premium pricing."
                )
            elif quality_score >= 50:
                reasons.append(
                    f"Your asset has a good quality score ({quality_score:.1f}/100), "
                    "supporting market-rate pricing."
                )
            else:
                reasons.append(
                    f"Quality score ({quality_score:.1f}/100) suggests competitive pricing "
                    "to encourage adoption."
                )

        # Demand factor
        if demand_prediction >= 70:
            reasons.append(
                "High predicted demand suggests you can command premium royalties."
            )
        elif demand_prediction <= 40:
            reasons.append(
                "Lower predicted demand suggests conservative pricing to attract users."
            )

        # Scarcity factor
        if similar_count < 20:
            reasons.append(
                "Limited similar assets in marketplace gives you pricing flexibility."
            )
        elif similar_count > 100:
            reasons.append(
                "Competitive market with many similar assets. Pricing is critical for visibility."
            )

        # Recommendation
        reasons.append(
            "\nWe recommend the 'balanced' tier for most cases, but choose based on your goals: "
            "conservative for maximum reach, aggressive for maximum revenue."
        )

        return " ".join(reasons)

    def _calculate_confidence(
        self,
        asset: IPAsset,
        similar_count: int,
        has_quality_score: bool
    ) -> float:
        """
        Calculate confidence in pricing recommendations.

        Args:
            asset: The asset
            similar_count: Number of similar assets found
            has_quality_score: Whether quality analysis was performed

        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.5  # Base confidence

        # More similar assets = higher confidence
        if similar_count >= 50:
            confidence += 0.25
        elif similar_count >= 20:
            confidence += 0.15
        elif similar_count >= 5:
            confidence += 0.05

        # Quality score increases confidence
        if has_quality_score:
            confidence += 0.15

        # Complete metadata increases confidence
        if asset.description and len(asset.description) >= 50:
            confidence += 0.05

        if asset.tags:
            confidence += 0.05

        return min(confidence, 1.0)
