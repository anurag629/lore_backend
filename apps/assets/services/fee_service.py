"""
Fee Calculation Service - Model F Hybrid Implementation

Calculates derivative minting fees based on:
- Creator-set base minting fee
- Popularity multiplier (based on derivative count)
- Attribution percentage (for multi-parent derivatives)

Fee Distribution:
- 95% goes to parent creator(s)
- 5% goes to platform
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class FeeCalculationService:
    """
    Model F Hybrid Fee Calculation Service.

    Calculates fees based on parent's creator-set minting_fee with
    a popularity multiplier applied dynamically.
    """

    # Configuration
    MAX_POPULARITY_MULTIPLIER = Decimal('2.0')  # Max 2x based on popularity
    PLATFORM_FEE_PERCENTAGE = Decimal('0.05')   # 5% to platform
    MAX_FEE = Decimal('0.5')                    # Cap at 0.5 ETH

    def calculate_derivative_fee(
        self,
        parents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate total fee and breakdown for derivative creation.

        Args:
            parents: List of dicts with:
                - parent_asset: IPAsset instance (must have minting_fee field)
                - attribution_percentage: Decimal or float (0-100)

        Returns:
            {
                'total_fee': float (ETH),
                'total_fee_wei': str,
                'platform_fee': float (ETH),
                'creator_fee': float (ETH),
                'breakdown': [
                    {
                        'parent_asset_id': str,
                        'parent_asset_title': str,
                        'parent_creator': str,
                        'parent_creator_id': int,
                        'attribution_percentage': float,
                        'base_minting_fee': float,
                        'derivative_count': int,
                        'popularity_factor': float,
                        'fee_before_split': float,
                        'fee_share': float,
                        'fee_share_wei': str,
                    }
                ],
                'is_free': bool,
            }

        Raises:
            ValueError: If parents list is empty or invalid
        """
        if not parents:
            raise ValueError("At least one parent required")

        # Validate attribution percentages sum to 100
        total_attribution = sum(
            Decimal(str(p.get('attribution_percentage', 100)))
            for p in parents
        )
        if abs(total_attribution - Decimal('100')) > Decimal('0.01'):
            raise ValueError(
                f"Attribution percentages must sum to 100%, got {total_attribution}%"
            )

        total_fee = Decimal('0')
        breakdown = []

        for p in parents:
            parent_asset = p['parent_asset']
            attribution = Decimal(str(p.get('attribution_percentage', 100)))

            # Get creator-set minting fee (can be 0 for free derivatives)
            base_fee = Decimal(str(parent_asset.minting_fee or 0))

            # Calculate popularity factor based on derivative count
            # More popular assets = higher fee (rewards successful creators)
            derivative_count = parent_asset.derivatives.filter(is_deleted=False).count()
            popularity_factor = min(
                Decimal('1') + (Decimal(str(derivative_count)) / Decimal('100')),
                self.MAX_POPULARITY_MULTIPLIER
            )

            # Fee for this parent = base_fee × popularity × attribution%
            parent_fee = base_fee * popularity_factor * (attribution / Decimal('100'))
            total_fee += parent_fee

            breakdown.append({
                'parent_asset_id': str(parent_asset.uuid),
                'parent_asset_title': parent_asset.title,
                'parent_creator': parent_asset.creator.display_name,
                'parent_creator_id': parent_asset.creator.id,
                'attribution_percentage': float(attribution),
                'base_minting_fee': float(base_fee),
                'derivative_count': derivative_count,
                'popularity_factor': float(popularity_factor),
                'fee_before_split': float(parent_fee),
            })

        # Cap total fee at maximum
        total_fee = min(total_fee, self.MAX_FEE)

        # Platform takes 5%, creators get 95%
        platform_fee = total_fee * self.PLATFORM_FEE_PERCENTAGE
        creator_fee = total_fee - platform_fee

        # Calculate final per-parent share (from creator_fee portion)
        for item in breakdown:
            attribution = Decimal(str(item['attribution_percentage']))
            parent_share = creator_fee * (attribution / Decimal('100'))
            item['fee_share'] = float(parent_share)
            item['fee_share_wei'] = str(int(parent_share * Decimal('1e18')))

        is_free = total_fee == Decimal('0')

        logger.info(
            f"Calculated derivative fee: {float(total_fee)} ETH "
            f"({'free' if is_free else f'{len(parents)} parent(s)'})"
        )

        return {
            'total_fee': float(total_fee),
            'total_fee_wei': str(int(total_fee * Decimal('1e18'))),
            'platform_fee': float(platform_fee),
            'creator_fee': float(creator_fee),
            'breakdown': breakdown,
            'is_free': is_free,
        }

    def calculate_single_parent_fee(
        self,
        parent_asset: Any
    ) -> Dict[str, Any]:
        """
        Convenience method for single-parent derivative fee calculation.

        Args:
            parent_asset: IPAsset instance

        Returns:
            Fee calculation result (same as calculate_derivative_fee)
        """
        return self.calculate_derivative_fee([{
            'parent_asset': parent_asset,
            'attribution_percentage': Decimal('100')
        }])

    def estimate_earnings(
        self,
        minting_fee: Decimal,
        derivative_count: int = 0
    ) -> Dict[str, Any]:
        """
        Estimate potential earnings for a creator based on their minting fee.

        Args:
            minting_fee: Creator's set minting fee
            derivative_count: Current number of derivatives

        Returns:
            {
                'per_derivative_min': float,
                'per_derivative_max': float,
                'with_current_popularity': float,
            }
        """
        base_fee = Decimal(str(minting_fee))

        # Calculate current popularity factor
        current_popularity = min(
            Decimal('1') + (Decimal(str(derivative_count)) / Decimal('100')),
            self.MAX_POPULARITY_MULTIPLIER
        )

        # Creator gets 95% of fee
        creator_share = Decimal('1') - self.PLATFORM_FEE_PERCENTAGE

        per_derivative_min = float(base_fee * creator_share)
        per_derivative_max = float(base_fee * self.MAX_POPULARITY_MULTIPLIER * creator_share)
        with_current = float(base_fee * current_popularity * creator_share)

        return {
            'per_derivative_min': per_derivative_min,
            'per_derivative_max': per_derivative_max,
            'with_current_popularity': with_current,
            'current_popularity_factor': float(current_popularity),
        }


# Singleton instance for easy import
fee_service = FeeCalculationService()
