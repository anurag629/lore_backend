"""
Web3 Utilities for Ethereum Address Handling

Provides consistent wallet address validation and normalization
to prevent comparison failures and ensure proper formatting.
"""
from typing import Optional
from web3 import Web3
import re
import logging
import hashlib
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class InvalidAddressError(ValueError):
    """Raised when an Ethereum address is invalid"""
    pass


class WalletAddressValidator:
    """
    Validator and normalizer for Ethereum wallet addresses.

    Ensures consistent address handling throughout the application:
    - Lowercase storage for database consistency
    - Checksummed format for Web3 interactions
    - Validation before use
    """

    # Ethereum address pattern: 0x followed by 40 hex characters
    ADDRESS_PATTERN = re.compile(r'^0x[a-fA-F0-9]{40}$')

    @staticmethod
    def is_valid(address: str) -> bool:
        """
        Check if an address is a valid Ethereum address.

        Args:
            address: Address string to validate

        Returns:
            True if valid, False otherwise
        """
        if not address:
            return False

        # Check format
        if not isinstance(address, str):
            return False

        # Check pattern
        if not WalletAddressValidator.ADDRESS_PATTERN.match(address):
            return False

        # Additional check with Web3
        try:
            return Web3.is_address(address)
        except Exception as e:
            logger.warning(f"Web3 address validation failed: {e}")
            return False

    @staticmethod
    def normalize(address: str) -> str:
        """
        Normalize address to lowercase format for storage.

        Use this for:
        - Database storage
        - Comparison operations
        - Dictionary keys

        Args:
            address: Ethereum address to normalize

        Returns:
            Lowercase address with 0x prefix

        Raises:
            InvalidAddressError: If address is invalid
        """
        if not address:
            raise InvalidAddressError("Address cannot be empty")

        # Add 0x prefix if missing
        if not address.startswith('0x'):
            address = '0x' + address

        # Validate
        if not WalletAddressValidator.is_valid(address):
            raise InvalidAddressError(f"Invalid Ethereum address: {address}")

        # Return lowercase
        return address.lower()

    @staticmethod
    def checksum(address: str) -> str:
        """
        Convert address to checksummed format.

        Use this for:
        - Web3 interactions
        - Smart contract calls
        - Transaction signing

        Args:
            address: Ethereum address to checksum

        Returns:
            Checksummed address

        Raises:
            InvalidAddressError: If address is invalid
        """
        if not address:
            raise InvalidAddressError("Address cannot be empty")

        # Add 0x prefix if missing
        if not address.startswith('0x'):
            address = '0x' + address

        # Validate
        if not WalletAddressValidator.is_valid(address):
            raise InvalidAddressError(f"Invalid Ethereum address: {address}")

        try:
            # Use Web3's toChecksumAddress
            return Web3.to_checksum_address(address)
        except Exception as e:
            raise InvalidAddressError(f"Failed to checksum address {address}: {e}")

    @staticmethod
    def validate_and_normalize(address: str, for_storage: bool = True) -> str:
        """
        Validate and normalize an address.

        Args:
            address: Ethereum address to validate and normalize
            for_storage: If True, return lowercase (for DB storage).
                        If False, return checksummed (for Web3 use).

        Returns:
            Normalized address (lowercase or checksummed based on for_storage)

        Raises:
            InvalidAddressError: If address is invalid
        """
        if for_storage:
            return WalletAddressValidator.normalize(address)
        else:
            return WalletAddressValidator.checksum(address)

    @staticmethod
    def are_equal(address1: str, address2: str) -> bool:
        """
        Compare two addresses for equality (case-insensitive).

        Args:
            address1: First address
            address2: Second address

        Returns:
            True if addresses are equal, False otherwise
        """
        try:
            normalized1 = WalletAddressValidator.normalize(address1)
            normalized2 = WalletAddressValidator.normalize(address2)
            return normalized1 == normalized2
        except InvalidAddressError:
            return False

    @staticmethod
    def strip_0x(address: str) -> str:
        """
        Remove 0x prefix from address.

        Args:
            address: Address with or without 0x prefix

        Returns:
            Address without 0x prefix
        """
        if address.startswith('0x'):
            return address[2:]
        return address

    @staticmethod
    def add_0x(address: str) -> str:
        """
        Add 0x prefix to address if missing.

        Args:
            address: Address with or without 0x prefix

        Returns:
            Address with 0x prefix
        """
        if not address.startswith('0x'):
            return '0x' + address
        return address

    @staticmethod
    def truncate(address: str, start_chars: int = 6, end_chars: int = 4) -> str:
        """
        Truncate address for display (e.g., "0x1234...5678").

        Args:
            address: Address to truncate
            start_chars: Number of characters to show at start (default: 6)
            end_chars: Number of characters to show at end (default: 4)

        Returns:
            Truncated address string

        Raises:
            InvalidAddressError: If address is invalid
        """
        if not WalletAddressValidator.is_valid(address):
            raise InvalidAddressError(f"Invalid address: {address}")

        if len(address) <= start_chars + end_chars:
            return address

        return f"{address[:start_chars]}...{address[-end_chars:]}"


# Convenience functions for common operations

def normalize_address(address: str) -> str:
    """
    Normalize address to lowercase.

    Convenience function for WalletAddressValidator.normalize()
    """
    return WalletAddressValidator.normalize(address)


def checksum_address(address: str) -> str:
    """
    Convert address to checksummed format.

    Convenience function for WalletAddressValidator.checksum()
    """
    return WalletAddressValidator.checksum(address)


def validate_address(address: str) -> bool:
    """
    Check if address is valid.

    Convenience function for WalletAddressValidator.is_valid()
    """
    return WalletAddressValidator.is_valid(address)


def compare_addresses(address1: str, address2: str) -> bool:
    """
    Compare two addresses (case-insensitive).

    Convenience function for WalletAddressValidator.are_equal()
    """
    return WalletAddressValidator.are_equal(address1, address2)


# Zero address constant
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def is_zero_address(address: str) -> bool:
    """
    Check if address is the zero address.

    Args:
        address: Address to check

    Returns:
        True if address is zero address, False otherwise
    """
    try:
        normalized = normalize_address(address)
        return normalized == ZERO_ADDRESS.lower()
    except InvalidAddressError:
        return False


# Idempotency key generation for blockchain transactions

def generate_idempotency_key(
    operation: str,
    user_id: int,
    additional_data: Optional[str] = None
) -> str:
    """
    Generate a deterministic idempotency key for blockchain operations.

    This key ensures that retrying an operation with the same parameters
    won't result in duplicate blockchain transactions.

    Args:
        operation: Operation type (e.g., 'register_asset', 'create_derivative')
        user_id: User ID performing the operation
        additional_data: Optional additional data to include in key

    Returns:
        Hex string idempotency key (64 characters)

    Example:
        key = generate_idempotency_key('register_asset', user.id, f'{asset.uuid}')
    """
    # Create a string with all components
    timestamp_str = datetime.utcnow().isoformat()
    random_component = str(uuid.uuid4())

    components = [
        operation,
        str(user_id),
        timestamp_str,
        random_component,
    ]

    if additional_data:
        components.append(str(additional_data))

    # Combine and hash
    data_string = '|'.join(components)
    hash_obj = hashlib.sha256(data_string.encode('utf-8'))

    return hash_obj.hexdigest()


def generate_deterministic_idempotency_key(
    operation: str,
    user_id: int,
    resource_id: str
) -> str:
    """
    Generate a deterministic idempotency key based on operation and resource.

    Unlike generate_idempotency_key(), this produces the same key for the
    same inputs, making it useful for idempotent retries of the exact same operation.

    Args:
        operation: Operation type (e.g., 'register_asset')
        user_id: User ID performing the operation
        resource_id: Unique resource identifier (e.g., asset UUID)

    Returns:
        Hex string idempotency key (64 characters)

    Example:
        key = generate_deterministic_idempotency_key(
            'register_asset',
            user.id,
            str(asset.uuid)
        )
    """
    components = [
        operation,
        str(user_id),
        str(resource_id),
    ]

    data_string = '|'.join(components)
    hash_obj = hashlib.sha256(data_string.encode('utf-8'))

    return hash_obj.hexdigest()
