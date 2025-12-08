"""
Group IP Service Layer

Handles all interactions with Story Protocol Group IPs including:
- Group registration
- Member management
- Royalty distribution
"""
from typing import Dict, Optional, Any, List
from django.conf import settings
from django.db import transaction
from decimal import Decimal
import logging

from apps.assets.models import GroupIP, GroupIPMembership, IPAsset, GroupRoyaltyDistribution
from apps.core.web3_utils import WalletAddressValidator, InvalidAddressError, generate_idempotency_key

logger = logging.getLogger(__name__)


class GroupIPService:
    """
    Service class for managing Story Protocol Group IPs.
    """

    def __init__(self, story_service=None):
        """
        Initialize Group IP service.

        Args:
            story_service: Optional StoryProtocolService instance for blockchain operations
        """
        self.story_service = story_service

    def create_group(
        self,
        name: str,
        description: str,
        creator_user,
        royalty_percentage: int = 10
    ) -> GroupIP:
        """
        Create a new Group IP (database only, registration happens separately).

        Args:
            name: Group name
            description: Group description
            creator_user: User creating the group
            royalty_percentage: Total royalty percentage for the group (0-100)

        Returns:
            Created GroupIP instance

        Raises:
            ValueError: If parameters are invalid
        """
        # Validate royalty percentage
        if not 0 <= royalty_percentage <= 100:
            raise ValueError("Royalty percentage must be between 0 and 100")

        # Create group in database
        group = GroupIP.objects.create(
            name=name,
            description=description,
            creator=creator_user,
            total_royalty_percentage=royalty_percentage,
            registration_status='pending'
        )

        logger.info(f"Created Group IP: {group.name} (UUID: {group.uuid})")

        return group

    def register_group_on_chain(
        self,
        group: GroupIP,
        creator_address: str
    ) -> Dict[str, Any]:
        """
        Register a Group IP on Story Protocol blockchain.

        Args:
            group: GroupIP instance to register
            creator_address: Ethereum address of creator

        Returns:
            Dict containing registration result with story_group_id and transaction_hash

        Raises:
            RuntimeError: If registration fails
        """
        if not self.story_service:
            raise RuntimeError("Story Protocol service not initialized")

        # Validate and checksum address
        try:
            creator_address = WalletAddressValidator.checksum(creator_address)
        except InvalidAddressError as e:
            raise ValueError(f"Invalid creator address: {e}")

        # Check if already registered
        if group.registration_status == 'registered' and group.story_group_id:
            logger.warning(f"Group {group.uuid} already registered with ID {group.story_group_id}")
            return {
                'story_group_id': group.story_group_id,
                'transaction_hash': group.registration_transaction_hash,
                'already_registered': True
            }

        try:
            # Note: Actual Story Protocol Group IP registration would happen here
            # For now, we'll create a placeholder implementation
            # The Story Protocol SDK would need to support group registration

            logger.info(f"Registering Group IP on-chain: {group.name}")

            # Placeholder - In reality, this would call Story Protocol SDK
            # result = self.story_service.register_group_ip(
            #     name=group.name,
            #     description=group.description,
            #     creator_address=creator_address,
            #     royalty_percentage=group.total_royalty_percentage
            # )

            # For now, generate a mock group ID
            # In production, this would come from the blockchain
            mock_group_id = f"0xgroup{group.uuid.hex[:40]}"
            mock_tx_hash = f"0x{generate_idempotency_key('register_group', group.creator.id, str(group.uuid))[:64]}"

            # Update group with registration info
            group.story_group_id = mock_group_id
            group.registration_transaction_hash = mock_tx_hash
            group.registration_status = 'registered'
            group.save(update_fields=['story_group_id', 'registration_transaction_hash', 'registration_status'])

            logger.info(f"Group IP registered: {mock_group_id}")

            return {
                'story_group_id': mock_group_id,
                'transaction_hash': mock_tx_hash,
                'group': group
            }

        except Exception as e:
            logger.error(f"Failed to register Group IP {group.uuid}: {e}")
            group.registration_status = 'failed'
            group.save(update_fields=['registration_status'])
            raise RuntimeError(f"Group IP registration failed: {str(e)}")

    def add_member_to_group(
        self,
        group: GroupIP,
        asset: IPAsset,
        revenue_share_percentage: Decimal,
        added_by_user
    ) -> GroupIPMembership:
        """
        Add an IP asset as a member of a Group IP.

        Args:
            group: GroupIP to add member to
            asset: IPAsset to add as member
            revenue_share_percentage: Percentage of group revenue for this member
            added_by_user: User adding the member

        Returns:
            Created GroupIPMembership instance

        Raises:
            ValueError: If validation fails
        """
        # Validate revenue share
        if not 0 <= revenue_share_percentage <= 100:
            raise ValueError("Revenue share percentage must be between 0 and 100")

        # Check if total revenue share would exceed 100%
        current_total = group.total_revenue_share
        if current_total + revenue_share_percentage > 100:
            raise ValueError(
                f"Adding {revenue_share_percentage}% would exceed 100% "
                f"(current total: {current_total}%)"
            )

        # Check if asset is already a member
        existing = GroupIPMembership.objects.filter(
            group=group,
            asset=asset,
            is_active=True
        ).first()

        if existing:
            raise ValueError(f"Asset {asset.title} is already a member of {group.name}")

        # Create membership
        with transaction.atomic():
            membership = GroupIPMembership.objects.create(
                group=group,
                asset=asset,
                revenue_share_percentage=revenue_share_percentage,
                added_by=added_by_user,
                is_active=True
            )

            logger.info(
                f"Added {asset.title} to {group.name} "
                f"with {revenue_share_percentage}% revenue share"
            )

        # Note: In production, this would also register the membership on-chain
        # self.story_service.add_group_member(group.story_group_id, asset.story_ip_id)

        return membership

    def remove_member_from_group(
        self,
        membership: GroupIPMembership
    ) -> None:
        """
        Remove a member from a Group IP.

        Args:
            membership: GroupIPMembership to remove

        Raises:
            ValueError: If membership is already inactive
        """
        if not membership.is_active:
            raise ValueError("Membership is already inactive")

        from django.utils import timezone

        with transaction.atomic():
            membership.is_active = False
            membership.removed_at = timezone.now()
            membership.save(update_fields=['is_active', 'removed_at'])

            logger.info(
                f"Removed {membership.asset.title} from {membership.group.name}"
            )

        # Note: In production, this would also update on-chain
        # self.story_service.remove_group_member(...)

    def distribute_royalties(
        self,
        group: GroupIP,
        total_amount: Decimal,
        transaction_hash: str,
        block_number: int
    ) -> List[GroupRoyaltyDistribution]:
        """
        Distribute royalties from a Group IP to its members based on revenue share.

        Args:
            group: GroupIP distributing royalties
            total_amount: Total amount to distribute
            transaction_hash: Blockchain transaction hash
            block_number: Block number of distribution

        Returns:
            List of created GroupRoyaltyDistribution instances

        Raises:
            ValueError: If validation fails
        """
        if total_amount <= 0:
            raise ValueError("Distribution amount must be positive")

        # Get active members
        memberships = group.members.filter(is_active=True)

        if not memberships.exists():
            raise ValueError(f"Group {group.name} has no active members")

        distributions = []

        with transaction.atomic():
            for membership in memberships:
                # Calculate member's share
                member_amount = total_amount * (membership.revenue_share_percentage / 100)

                # Create distribution record
                distribution = GroupRoyaltyDistribution.objects.create(
                    group=group,
                    membership=membership,
                    amount=member_amount,
                    transaction_hash=f"{transaction_hash}_{membership.uuid.hex[:8]}",
                    block_number=block_number
                )

                distributions.append(distribution)

                logger.info(
                    f"Distributed {member_amount} to {membership.asset.title} "
                    f"from {group.name}"
                )

        return distributions

    def get_group_statistics(self, group: GroupIP) -> Dict[str, Any]:
        """
        Get statistics for a Group IP.

        Args:
            group: GroupIP to get statistics for

        Returns:
            Dict containing group statistics
        """
        from django.db.models import Sum, Count

        member_stats = group.members.filter(is_active=True).aggregate(
            total_members=Count('id'),
            total_revenue_share=Sum('revenue_share_percentage')
        )

        distribution_stats = group.distributions.aggregate(
            total_distributed=Sum('amount'),
            distribution_count=Count('id')
        )

        return {
            'group_id': str(group.uuid),
            'name': group.name,
            'member_count': member_stats['total_members'] or 0,
            'total_revenue_share': float(member_stats['total_revenue_share'] or 0),
            'available_revenue_share': 100 - float(member_stats['total_revenue_share'] or 0),
            'total_distributed': float(distribution_stats['total_distributed'] or 0),
            'distribution_count': distribution_stats['distribution_count'] or 0,
            'registration_status': group.registration_status,
            'is_active': group.is_active,
        }


def get_group_ip_service(story_service=None):
    """
    Get a GroupIPService instance.

    Args:
        story_service: Optional StoryProtocolService instance

    Returns:
        GroupIPService instance
    """
    return GroupIPService(story_service=story_service)
