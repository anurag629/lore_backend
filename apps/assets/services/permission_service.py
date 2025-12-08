"""
Permission Service - Manage IP Account Permissions

Handles permission management for IP assets on Story Protocol.
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from django.db import transaction
from django.db import models
from django.utils import timezone
from apps.core.utils import normalize_wallet_address

from apps.assets.models import IPAsset, IPAccountPermission
from apps.core.models import LoreUser

logger = logging.getLogger(__name__)


class PermissionService:
    """Service for managing IP Account permissions."""

    # Permission type constants
    EXECUTE = 'execute'
    TRANSFER_ERC20 = 'transfer_erc20'
    SET_METADATA = 'set_metadata'
    ATTACH_LICENSE = 'attach_license'
    REGISTER_DERIVATIVE = 'register_derivative'
    COLLECT_ROYALTY = 'collect_royalty'

    ALL_PERMISSIONS = [
        EXECUTE,
        TRANSFER_ERC20,
        SET_METADATA,
        ATTACH_LICENSE,
        REGISTER_DERIVATIVE,
        COLLECT_ROYALTY,
    ]

    def __init__(self, story_service=None):
        """
        Initialize permission service.

        Args:
            story_service: Optional Story Protocol service for blockchain operations
        """
        self.story_service = story_service

    def set_permission(
        self,
        asset: IPAsset,
        grantee_address: str,
        permission_type: str,
        is_granted: bool = True,
        expires_at: Optional[datetime] = None,
        granted_by_user: Optional[LoreUser] = None,
        notes: str = ''
    ) -> IPAccountPermission:
        """
        Set a single permission for an IP asset.

        Args:
            asset: IP asset to set permission for
            grantee_address: Wallet address to grant/revoke permission
            permission_type: Type of permission
            is_granted: True to grant, False to revoke
            expires_at: Optional expiration time
            granted_by_user: User granting the permission
            notes: Optional notes

        Returns:
            IPAccountPermission: Created or updated permission

        Raises:
            ValueError: If permission type is invalid or address is invalid
        """
        # Validate permission type
        if permission_type not in self.ALL_PERMISSIONS:
            raise ValueError(f"Invalid permission type: {permission_type}")

        # Normalize wallet address
        try:
            grantee_address = normalize_wallet_address(grantee_address)
        except Exception as e:
            raise ValueError(f"Invalid grantee address: {e}")

        # TODO: Call Story Protocol to set permission on-chain
        # For now, we'll just create the permission in the database
        if self.story_service and self.story_service.is_ready():
            try:
                # Placeholder for blockchain call
                logger.info(
                    f"Setting permission {permission_type} for asset {asset.story_ip_id} "
                    f"to {grantee_address}: {is_granted}"
                )
                # result = self.story_service.set_permission(
                #     ip_id=asset.story_ip_id,
                #     grantee=grantee_address,
                #     permission=permission_type,
                #     is_granted=is_granted
                # )
                # transaction_hash = result.get('transaction_hash', '')
                transaction_hash = ''
            except Exception as e:
                logger.error(f"Failed to set permission on-chain: {e}")
                transaction_hash = ''
        else:
            transaction_hash = ''

        # Create or update permission in database
        with transaction.atomic():
            permission, created = IPAccountPermission.objects.update_or_create(
                asset=asset,
                grantee_address=grantee_address,
                permission_type=permission_type,
                defaults={
                    'is_granted': is_granted,
                    'expires_at': expires_at,
                    'granted_by': granted_by_user,
                    'notes': notes,
                    'transaction_hash': transaction_hash,
                }
            )

        action = "granted" if is_granted else "revoked"
        logger.info(f"Permission {permission_type} {action} for {grantee_address} on asset {asset.uuid}")

        return permission

    def set_all_permissions(
        self,
        asset: IPAsset,
        grantee_address: str,
        is_granted: bool = True,
        expires_at: Optional[datetime] = None,
        granted_by_user: Optional[LoreUser] = None,
        notes: str = ''
    ) -> List[IPAccountPermission]:
        """
        Set all permissions for an IP asset to the same state.

        Args:
            asset: IP asset to set permissions for
            grantee_address: Wallet address to grant/revoke permissions
            is_granted: True to grant all, False to revoke all
            expires_at: Optional expiration time for all permissions
            granted_by_user: User granting the permissions
            notes: Optional notes

        Returns:
            List[IPAccountPermission]: List of created/updated permissions
        """
        permissions = []

        for permission_type in self.ALL_PERMISSIONS:
            permission = self.set_permission(
                asset=asset,
                grantee_address=grantee_address,
                permission_type=permission_type,
                is_granted=is_granted,
                expires_at=expires_at,
                granted_by_user=granted_by_user,
                notes=notes
            )
            permissions.append(permission)

        action = "granted" if is_granted else "revoked"
        logger.info(f"All permissions {action} for {grantee_address} on asset {asset.uuid}")

        return permissions

    def revoke_permission(
        self,
        asset: IPAsset,
        grantee_address: str,
        permission_type: str,
        granted_by_user: Optional[LoreUser] = None
    ) -> IPAccountPermission:
        """
        Revoke a specific permission.

        Args:
            asset: IP asset to revoke permission for
            grantee_address: Wallet address to revoke permission from
            permission_type: Type of permission to revoke
            granted_by_user: User revoking the permission

        Returns:
            IPAccountPermission: Updated permission
        """
        return self.set_permission(
            asset=asset,
            grantee_address=grantee_address,
            permission_type=permission_type,
            is_granted=False,
            granted_by_user=granted_by_user
        )

    def revoke_all_permissions(
        self,
        asset: IPAsset,
        grantee_address: str,
        granted_by_user: Optional[LoreUser] = None
    ) -> List[IPAccountPermission]:
        """
        Revoke all permissions for an address.

        Args:
            asset: IP asset to revoke permissions for
            grantee_address: Wallet address to revoke permissions from
            granted_by_user: User revoking the permissions

        Returns:
            List[IPAccountPermission]: List of updated permissions
        """
        return self.set_all_permissions(
            asset=asset,
            grantee_address=grantee_address,
            is_granted=False,
            granted_by_user=granted_by_user
        )

    def get_permissions(
        self,
        asset: IPAsset,
        grantee_address: Optional[str] = None,
        permission_type: Optional[str] = None,
        active_only: bool = False
    ) -> List[IPAccountPermission]:
        """
        Get permissions for an asset.

        Args:
            asset: IP asset to get permissions for
            grantee_address: Optional filter by grantee address
            permission_type: Optional filter by permission type
            active_only: If True, only return active (granted and not expired) permissions

        Returns:
            List[IPAccountPermission]: List of permissions
        """
        queryset = IPAccountPermission.objects.filter(asset=asset)

        if grantee_address:
            grantee_address = normalize_wallet_address(grantee_address)
            queryset = queryset.filter(grantee_address=grantee_address)

        if permission_type:
            queryset = queryset.filter(permission_type=permission_type)

        if active_only:
            # Only granted permissions
            queryset = queryset.filter(is_granted=True)

            # Exclude expired permissions
            now = timezone.now()
            queryset = queryset.filter(
                models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
            )

        return list(queryset.select_related('asset', 'granted_by').order_by('-created_at'))

    def check_permission(
        self,
        asset: IPAsset,
        grantee_address: str,
        permission_type: str
    ) -> bool:
        """
        Check if an address has a specific permission for an asset.

        Args:
            asset: IP asset to check
            grantee_address: Wallet address to check
            permission_type: Type of permission to check

        Returns:
            bool: True if permission is active, False otherwise
        """
        grantee_address = normalize_wallet_address(grantee_address)

        try:
            permission = IPAccountPermission.objects.get(
                asset=asset,
                grantee_address=grantee_address,
                permission_type=permission_type
            )
            return permission.is_active
        except IPAccountPermission.DoesNotExist:
            return False

    def get_permission_summary(
        self,
        asset: IPAsset,
        grantee_address: str
    ) -> Dict[str, bool]:
        """
        Get a summary of all permissions for an address on an asset.

        Args:
            asset: IP asset to check
            grantee_address: Wallet address to check

        Returns:
            Dict[str, bool]: Map of permission types to active status
        """
        grantee_address = normalize_wallet_address(grantee_address)

        permissions = IPAccountPermission.objects.filter(
            asset=asset,
            grantee_address=grantee_address
        )

        summary = {perm_type: False for perm_type in self.ALL_PERMISSIONS}

        for permission in permissions:
            summary[permission.permission_type] = permission.is_active

        return summary

    def cleanup_expired_permissions(self) -> int:
        """
        Clean up expired permissions (mark as revoked).

        Returns:
            int: Number of permissions cleaned up
        """
        now = timezone.now()

        expired_permissions = IPAccountPermission.objects.filter(
            expires_at__lte=now,
            is_granted=True
        )

        count = expired_permissions.count()

        expired_permissions.update(
            is_granted=False,
            updated_at=now
        )

        logger.info(f"Cleaned up {count} expired permissions")

        return count


# Singleton instance
_permission_service = None


def get_permission_service(story_service=None) -> PermissionService:
    """Get or create permission service instance."""
    global _permission_service

    if _permission_service is None:
        _permission_service = PermissionService(story_service=story_service)

    return _permission_service
