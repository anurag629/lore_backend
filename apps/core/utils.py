"""
Authentication utilities for SIWE (Sign-In with Ethereum)
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from siwe import SiweMessage, VerificationError
from eth_account.messages import encode_defunct
from web3 import Web3


def generate_nonce() -> str:
    """
    Generate a cryptographically secure random nonce for SIWE

    Returns:
        str: 32-character hex string
    """
    return secrets.token_hex(16)


def to_checksum_address(address: str) -> str:
    """
    Convert address to EIP-55 checksummed format.
    Required for SIWE messages.
    
    Args:
        address: Ethereum wallet address (any case)
        
    Returns:
        str: Checksummed address (mixed case like 0x8BC3DD5d...)
    """
    try:
        w3 = Web3()
        return w3.to_checksum_address(address)
    except Exception:
        return address


def create_siwe_message(
    domain: str,
    wallet_address: str,
    nonce: str,
    chain_id: int = 1,
    uri: str = "http://localhost:3000"
) -> str:
    """
    Create a SIWE message for the user to sign

    Args:
        domain: The domain requesting the signature (e.g., 'localhost')
        wallet_address: User's Ethereum wallet address
        nonce: Random nonce string
        chain_id: Ethereum chain ID (1 for mainnet, 11155111 for Sepolia)
        uri: URI of the application

    Returns:
        str: SIWE message string to be signed
    """
    # SIWE requires EIP-55 checksummed address format
    checksummed_address = to_checksum_address(wallet_address)
    
    # Create SIWE message
    message = SiweMessage(
        domain=domain,
        address=checksummed_address,
        statement="Sign in to Lore",
        uri=uri,
        version="1",
        chain_id=chain_id,
        nonce=nonce,
        issued_at=datetime.now(timezone.utc).isoformat(),
        expiration_time=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )

    return message.prepare_message()


def verify_siwe_signature(
    message: str,
    signature: str,
    expected_domain: str
) -> Optional[Dict[str, any]]:
    """
    Verify a SIWE signature and return wallet address if valid

    Args:
        message: The SIWE message that was signed
        signature: The signature from the wallet
        expected_domain: The expected domain (security check)

    Returns:
        Dict with wallet_address and chain_id if valid, None if invalid

    Example:
        result = verify_siwe_signature(message, signature, "localhost")
        if result:
            wallet_address = result['wallet_address']
            chain_id = result['chain_id']
    """
    try:
        # Parse the SIWE message
        siwe_message = SiweMessage.from_message(message=message)

        # Security check: verify the domain matches
        if siwe_message.domain != expected_domain:
            print(f"Domain mismatch: {siwe_message.domain} != {expected_domain}")
            return None

        # Verify the signature
        siwe_message.verify(signature=signature)

        # If we get here, signature is valid
        return {
            'wallet_address': siwe_message.address,
            'chain_id': siwe_message.chain_id,
            'nonce': siwe_message.nonce,
        }

    except VerificationError as e:
        print(f"SIWE verification error: {str(e)}")
        return None
    except Exception as e:
        print(f"Unexpected error during SIWE verification: {str(e)}")
        return None


def verify_eth_signature_legacy(
    wallet_address: str,
    message: str,
    signature: str
) -> bool:
    """
    Legacy method: Verify Ethereum signature using web3.py
    (Kept for backward compatibility, prefer verify_siwe_signature)

    Args:
        wallet_address: Expected wallet address
        message: Message that was signed
        signature: Signature from wallet

    Returns:
        bool: True if signature is valid
    """
    try:
        w3 = Web3()

        # Encode the message
        encoded_message = encode_defunct(text=message)

        # Recover the address from the signature
        recovered_address = w3.eth.account.recover_message(
            encoded_message,
            signature=signature
        )

        # Check if recovered address matches expected address (case-insensitive)
        return recovered_address.lower() == wallet_address.lower()

    except Exception as e:
        print(f"Error verifying signature: {str(e)}")
        return False


def normalize_wallet_address(address: str) -> str:
    """
    Normalize wallet address to lowercase for consistent storage and lookup.
    
    Note: We store addresses in lowercase to avoid case-sensitivity issues
    with database unique constraints and lookups.

    Args:
        address: Ethereum wallet address

    Returns:
        str: Lowercase address
    """
    if not address:
        return address
    
    # Always return lowercase for consistency
    return address.lower()
