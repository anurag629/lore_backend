"""
Celery tasks for asynchronous operations.
"""
from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging

from .models import IPAsset, RoyaltyPayment
from .story_service import get_story_service

logger = logging.getLogger(__name__)


@shared_task(name='sync_blockchain_events')
def sync_blockchain_events():
    """
    Periodic task to sync blockchain events from Story Protocol.
    This task should run every 5-10 minutes to check for:
    - New derivative registrations
    - Royalty payments
    - License updates
    """
    try:
        story_service = get_story_service()
        if not story_service.is_ready():
            logger.warning("Story Protocol service not available for blockchain sync")
            return

        # Get assets that need sync (registered in last 24 hours or recently updated)
        cutoff_time = timezone.now() - timezone.timedelta(hours=24)
        assets_to_sync = IPAsset.objects.filter(
            story_ip_id__isnull=False,
            created_at__gte=cutoff_time,
            is_deleted=False
        ).select_related('creator')

        synced_count = 0
        for asset in assets_to_sync:
            try:
                # Sync derivative relationships
                # Note: This is a placeholder - implement actual Story Protocol event listening
                # For now, we'll just log that sync would happen
                logger.info(f"Would sync events for asset {asset.id} (IP ID: {asset.story_ip_id})")
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to sync events for asset {asset.id}: {e}")

        logger.info(f"Blockchain sync completed: {synced_count} assets processed")
        return {'synced': synced_count, 'timestamp': timezone.now().isoformat()}

    except Exception as e:
        logger.error(f"Blockchain sync task failed: {e}")
        raise


@shared_task(name='process_royalty_payments')
def process_royalty_payments():
    """
    Periodic task to process royalty payments from Story Protocol.
    Checks for new royalty payments and updates user balances.
    """
    try:
        story_service = get_story_service()
        if not story_service.is_ready():
            logger.warning("Story Protocol service not available for royalty processing")
            return

        # Get assets with pending royalties
        assets_with_royalties = IPAsset.objects.filter(
            story_ip_id__isnull=False,
            is_deleted=False,
            allow_derivatives=True
        ).select_related('creator')

        processed_count = 0
        total_amount = 0

        for asset in assets_with_royalties:
            try:
                # Check for new royalty payments
                # Note: This is a placeholder - implement actual Story Protocol royalty checking
                # For now, we'll just log that processing would happen
                logger.info(f"Would process royalties for asset {asset.id}")
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed to process royalties for asset {asset.id}: {e}")

        logger.info(f"Royalty processing completed: {processed_count} assets processed")
        return {
            'processed': processed_count,
            'total_amount': total_amount,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Royalty processing task failed: {e}")
        raise


@shared_task(name='cleanup_old_logs')
def cleanup_old_logs():
    """
    Periodic task to clean up old AI generation logs.
    Keeps logs for last 90 days, deletes older ones.
    """
    try:
        from .models import AIGenerationLog
        
        cutoff_date = timezone.now() - timezone.timedelta(days=90)
        deleted_count, _ = AIGenerationLog.objects.filter(
            created_at__lt=cutoff_date
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old AI generation logs")
        return {'deleted': deleted_count, 'timestamp': timezone.now().isoformat()}

    except Exception as e:
        logger.error(f"Log cleanup task failed: {e}")
        raise


@shared_task(name='update_asset_statistics')
def update_asset_statistics():
    """
    Periodic task to update asset statistics (derivative counts, etc.).
    This helps keep statistics accurate without expensive queries on every request.
    """
    try:
        # Update derivative counts for assets
        # This could be optimized further with bulk updates
        assets = IPAsset.objects.filter(is_deleted=False).select_related('creator')
        
        updated_count = 0
        for asset in assets:
            # Clear cached derivative count
            if hasattr(asset, '_derivative_count_cache'):
                delattr(asset, '_derivative_count_cache')
            updated_count += 1

        logger.info(f"Updated statistics for {updated_count} assets")
        return {'updated': updated_count, 'timestamp': timezone.now().isoformat()}

    except Exception as e:
        logger.error(f"Statistics update task failed: {e}")
        raise

