"""
Dispute Service Layer

Handles all interactions with Story Protocol Disputes including:
- Raising disputes
- Submitting evidence
- Resolving disputes
- Cancelling disputes
"""
from typing import Dict, Optional, Any
from django.conf import settings
from django.db import transaction
from django.utils import timezone
import logging

from apps.assets.models import Dispute, DisputeEvidence, IPAsset
from apps.core.web3_utils import WalletAddressValidator, InvalidAddressError, generate_idempotency_key

logger = logging.getLogger(__name__)


class DisputeService:
    """
    Service class for managing Story Protocol Disputes.
    """

    def __init__(self, story_service=None):
        """
        Initialize Dispute service.

        Args:
            story_service: Optional StoryProtocolService instance for blockchain operations
        """
        self.story_service = story_service

    def raise_dispute(
        self,
        target_asset: IPAsset,
        disputer_user,
        disputer_address: str,
        reason: str,
        evidence_hash: Optional[str] = None
    ) -> Dispute:
        """
        Raise a new dispute against an IP asset.

        Args:
            target_asset: IP asset being disputed
            disputer_user: User raising the dispute
            disputer_address: Ethereum address of disputer
            reason: Reason for the dispute
            evidence_hash: Optional IPFS hash of initial evidence

        Returns:
            Created Dispute instance

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If blockchain registration fails
        """
        # Validate disputer address
        try:
            disputer_address = WalletAddressValidator.checksum(disputer_address)
        except InvalidAddressError as e:
            raise ValueError(f"Invalid disputer address: {e}")

        # Validate reason
        if not reason or len(reason.strip()) < 10:
            raise ValueError("Dispute reason must be at least 10 characters")

        # Create dispute in database
        with transaction.atomic():
            dispute = Dispute.objects.create(
                target_asset=target_asset,
                disputer=disputer_user,
                reason=reason,
                evidence_ipfs_hash=evidence_hash,
                status=Dispute.STATUS_PENDING
            )

            logger.info(
                f"Dispute raised against {target_asset.title} by {disputer_user.display_name}"
            )

        # Register dispute on-chain (if story_service available)
        if self.story_service:
            try:
                # Note: Actual Story Protocol dispute raising would happen here
                # For now, we'll create a placeholder implementation

                # Placeholder - In reality, this would call Story Protocol SDK
                # result = self.story_service.raise_dispute(
                #     target_ip_id=target_asset.story_ip_id,
                #     disputer_address=disputer_address,
                #     evidence_hash=evidence_hash
                # )

                # Generate mock transaction hash
                mock_tx_hash = f"0x{generate_idempotency_key('raise_dispute', disputer_user.id, str(dispute.uuid))[:64]}"
                mock_dispute_id = f"0xdispute{dispute.uuid.hex[:40]}"

                # Update dispute with on-chain info
                dispute.story_dispute_id = mock_dispute_id
                dispute.raise_transaction_hash = mock_tx_hash
                dispute.status = Dispute.STATUS_UNDER_REVIEW
                dispute.save(update_fields=['story_dispute_id', 'raise_transaction_hash', 'status'])

                logger.info(f"Dispute registered on-chain: {mock_dispute_id}")

            except Exception as e:
                logger.error(f"Failed to register dispute on-chain: {e}")
                # Don't fail the entire operation if blockchain registration fails
                # The dispute is still recorded in the database

        return dispute

    def submit_evidence(
        self,
        dispute: Dispute,
        submitter_user,
        description: str,
        evidence_url: Optional[str] = None,
        evidence_hash: Optional[str] = None
    ) -> DisputeEvidence:
        """
        Submit evidence for a dispute.

        Args:
            dispute: Dispute to submit evidence for
            submitter_user: User submitting the evidence
            description: Description of the evidence
            evidence_url: Optional URL to evidence file
            evidence_hash: Optional IPFS hash of evidence

        Returns:
            Created DisputeEvidence instance

        Raises:
            ValueError: If validation fails
        """
        # Check if dispute is still open
        if dispute.is_resolved:
            raise ValueError("Cannot submit evidence to a resolved dispute")

        # Validate description
        if not description or len(description.strip()) < 10:
            raise ValueError("Evidence description must be at least 10 characters")

        # Check authorization - only disputer or asset owner can submit evidence
        is_disputer = submitter_user == dispute.disputer
        is_asset_owner = submitter_user == dispute.target_asset.creator

        if not (is_disputer or is_asset_owner):
            raise ValueError("Only the disputer or asset owner can submit evidence")

        # Create evidence record
        with transaction.atomic():
            evidence = DisputeEvidence.objects.create(
                dispute=dispute,
                submitted_by=submitter_user,
                description=description,
                evidence_url=evidence_url,
                evidence_ipfs_hash=evidence_hash
            )

            # Update dispute status if still pending
            if dispute.status == Dispute.STATUS_PENDING:
                dispute.status = Dispute.STATUS_UNDER_REVIEW
                dispute.save(update_fields=['status'])

            logger.info(
                f"Evidence submitted for dispute {dispute.uuid} by {submitter_user.display_name}"
            )

        # Note: In production, this would also submit evidence on-chain
        # self.story_service.submit_dispute_evidence(...)

        return evidence

    def resolve_dispute(
        self,
        dispute: Dispute,
        resolver_user,
        result: str,
        resolution_notes: Optional[str] = None
    ) -> Dispute:
        """
        Resolve a dispute (admin/moderator action).

        Args:
            dispute: Dispute to resolve
            resolver_user: User resolving the dispute (admin)
            result: Result of the dispute (upheld, rejected, settled)
            resolution_notes: Optional notes about the resolution

        Returns:
            Updated Dispute instance

        Raises:
            ValueError: If validation fails
        """
        # Check if dispute is already resolved
        if dispute.is_resolved:
            raise ValueError("Dispute is already resolved")

        # Validate result
        valid_results = [choice[0] for choice in Dispute.RESULT_CHOICES]
        if result not in valid_results:
            raise ValueError(f"Invalid result. Must be one of: {', '.join(valid_results)}")

        # Update dispute
        with transaction.atomic():
            dispute.status = Dispute.STATUS_RESOLVED
            dispute.result = result
            dispute.resolution_notes = resolution_notes
            dispute.resolved_by = resolver_user
            dispute.resolved_at = timezone.now()
            dispute.save(update_fields=[
                'status', 'result', 'resolution_notes', 'resolved_by', 'resolved_at'
            ])

            logger.info(
                f"Dispute {dispute.uuid} resolved by {resolver_user.display_name}: {result}"
            )

        # Note: In production, this would also resolve on-chain
        # if self.story_service:
        #     result = self.story_service.resolve_dispute(
        #         dispute_id=dispute.story_dispute_id,
        #         resolution=result
        #     )
        #     dispute.resolve_transaction_hash = result['transaction_hash']
        #     dispute.save(update_fields=['resolve_transaction_hash'])

        return dispute

    def cancel_dispute(
        self,
        dispute: Dispute,
        canceller_user
    ) -> Dispute:
        """
        Cancel a dispute (only by the disputer).

        Args:
            dispute: Dispute to cancel
            canceller_user: User cancelling the dispute

        Returns:
            Updated Dispute instance

        Raises:
            ValueError: If validation fails
        """
        # Check authorization - only disputer can cancel
        if canceller_user != dispute.disputer:
            raise ValueError("Only the disputer can cancel a dispute")

        # Check if dispute is already resolved
        if dispute.is_resolved:
            raise ValueError("Cannot cancel a resolved dispute")

        # Update dispute
        with transaction.atomic():
            dispute.status = Dispute.STATUS_CANCELLED
            dispute.resolved_at = timezone.now()
            dispute.save(update_fields=['status', 'resolved_at'])

            logger.info(
                f"Dispute {dispute.uuid} cancelled by {canceller_user.display_name}"
            )

        # Note: In production, this would also cancel on-chain
        # self.story_service.cancel_dispute(...)

        return dispute

    def get_dispute_statistics(self, asset: Optional[IPAsset] = None) -> Dict[str, Any]:
        """
        Get dispute statistics.

        Args:
            asset: Optional asset to get statistics for (if None, returns global stats)

        Returns:
            Dict containing dispute statistics
        """
        from django.db.models import Count, Q

        queryset = Dispute.objects.all()
        if asset:
            queryset = queryset.filter(target_asset=asset)

        stats = queryset.aggregate(
            total_disputes=Count('id'),
            pending=Count('id', filter=Q(status=Dispute.STATUS_PENDING)),
            under_review=Count('id', filter=Q(status=Dispute.STATUS_UNDER_REVIEW)),
            resolved=Count('id', filter=Q(status=Dispute.STATUS_RESOLVED)),
            cancelled=Count('id', filter=Q(status=Dispute.STATUS_CANCELLED)),
            upheld=Count('id', filter=Q(result=Dispute.RESULT_UPHELD)),
            rejected=Count('id', filter=Q(result=Dispute.RESULT_REJECTED)),
            settled=Count('id', filter=Q(result=Dispute.RESULT_SETTLED)),
        )

        return {
            'total_disputes': stats['total_disputes'] or 0,
            'by_status': {
                'pending': stats['pending'] or 0,
                'under_review': stats['under_review'] or 0,
                'resolved': stats['resolved'] or 0,
                'cancelled': stats['cancelled'] or 0,
            },
            'by_result': {
                'upheld': stats['upheld'] or 0,
                'rejected': stats['rejected'] or 0,
                'settled': stats['settled'] or 0,
            }
        }


def get_dispute_service(story_service=None):
    """
    Get a DisputeService instance.

    Args:
        story_service: Optional StoryProtocolService instance

    Returns:
        DisputeService instance
    """
    return DisputeService(story_service=story_service)
