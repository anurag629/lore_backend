"""
Blockchain Transaction Management Utilities

Provides robust transaction handling including:
- Receipt verification with configurable timeout
- Transaction status checking
- Receipt data persistence
"""
from typing import Dict, Optional, Any
from django.conf import settings
from web3 import Web3
from web3.exceptions import TransactionNotFound, TimeExhausted, Web3Exception
import time
import logging
from apps.core.retry_utils import retry_with_backoff, RetryConfig

logger = logging.getLogger(__name__)


class BlockchainTransactionError(Exception):
    """Custom exception for blockchain transaction failures."""
    pass


class BlockchainTransactionManager:
    """
    Manager for blockchain transaction verification and tracking.

    Ensures transactions are properly confirmed on-chain before
    marking operations as complete.
    """

    def __init__(self, web3: Web3, default_timeout: int = 120):
        """
        Initialize the transaction manager.

        Args:
            web3: Web3 instance connected to blockchain
            default_timeout: Default timeout in seconds for receipt waiting (default: 120)
        """
        self.web3 = web3
        self.default_timeout = default_timeout

    def wait_for_receipt(
        self,
        tx_hash: str,
        timeout: Optional[int] = None,
        poll_interval: float = 2.0
    ) -> Dict[str, Any]:
        """
        Wait for a transaction receipt with configurable timeout.

        Args:
            tx_hash: Transaction hash to wait for
            timeout: Timeout in seconds (uses default if not specified)
            poll_interval: How often to poll for receipt in seconds (default: 2.0)

        Returns:
            Transaction receipt as dictionary

        Raises:
            BlockchainTransactionError: If transaction fails or times out
            ValueError: If tx_hash is invalid
        """
        if not tx_hash:
            raise ValueError("Transaction hash cannot be empty")

        # Ensure tx_hash has 0x prefix
        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash

        timeout = timeout or self.default_timeout
        start_time = time.time()

        logger.info(f"Waiting for transaction receipt: {tx_hash} (timeout: {timeout}s)")

        try:
            # Try using Web3's built-in wait_for_transaction_receipt first
            try:
                receipt = self.web3.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=timeout,
                    poll_latency=poll_interval
                )

                # Convert AttributeDict to regular dict
                receipt_dict = dict(receipt)

                # Verify transaction succeeded
                if receipt_dict.get('status') != 1:
                    raise BlockchainTransactionError(
                        f"Transaction {tx_hash} failed with status: {receipt_dict.get('status')}"
                    )

                elapsed = time.time() - start_time
                logger.info(
                    f"Transaction {tx_hash} confirmed in block {receipt_dict.get('blockNumber')} "
                    f"after {elapsed:.2f}s"
                )

                return receipt_dict

            except TimeExhausted:
                # If built-in method times out, fall back to manual polling
                logger.warning(
                    f"Built-in wait_for_transaction_receipt timed out for {tx_hash}, "
                    "falling back to manual polling"
                )
                raise  # Re-raise to be caught by outer try-except

        except TimeExhausted:
            elapsed = time.time() - start_time
            raise BlockchainTransactionError(
                f"Transaction {tx_hash} not confirmed after {elapsed:.2f}s (timeout: {timeout}s). "
                "The transaction may still be pending or may have been dropped from the mempool."
            )
        except TransactionNotFound:
            raise BlockchainTransactionError(
                f"Transaction {tx_hash} not found. It may not have been broadcast to the network."
            )
        except Exception as e:
            logger.error(f"Error waiting for transaction receipt {tx_hash}: {e}")
            raise BlockchainTransactionError(
                f"Failed to retrieve transaction receipt for {tx_hash}: {str(e)}"
            )

    def verify_and_store_receipt(
        self,
        tx_hash: str,
        asset_instance,
        step_name: str,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Verify transaction and store receipt in asset's step_data.

        Args:
            tx_hash: Transaction hash to verify
            asset_instance: IPAsset model instance to update
            step_name: Name of the step (e.g., 'registration', 'derivative_linking')
            timeout: Optional timeout in seconds

        Returns:
            Transaction receipt dictionary

        Raises:
            BlockchainTransactionError: If verification fails
        """
        logger.info(f"Verifying and storing receipt for {step_name}: {tx_hash}")

        # Wait for and get receipt
        receipt = self.wait_for_receipt(tx_hash, timeout)

        # Prepare receipt data for storage (convert non-serializable types)
        receipt_data = {
            'blockHash': receipt.get('blockHash').hex() if receipt.get('blockHash') else None,
            'blockNumber': receipt.get('blockNumber'),
            'transactionHash': receipt.get('transactionHash').hex() if receipt.get('transactionHash') else tx_hash,
            'transactionIndex': receipt.get('transactionIndex'),
            'from': receipt.get('from'),
            'to': receipt.get('to'),
            'gasUsed': receipt.get('gasUsed'),
            'cumulativeGasUsed': receipt.get('cumulativeGasUsed'),
            'effectiveGasPrice': receipt.get('effectiveGasPrice'),
            'status': receipt.get('status'),
            'logs': [
                {
                    'address': log.get('address'),
                    'topics': [topic.hex() for topic in log.get('topics', [])],
                    'data': log.get('data').hex() if log.get('data') else None,
                    'logIndex': log.get('logIndex'),
                }
                for log in receipt.get('logs', [])
            ] if receipt.get('logs') else [],
        }

        # Initialize step_data if it doesn't exist
        if asset_instance.step_data is None:
            asset_instance.step_data = {}

        # Store receipt under step name
        if 'receipts' not in asset_instance.step_data:
            asset_instance.step_data['receipts'] = {}

        asset_instance.step_data['receipts'][step_name] = receipt_data
        asset_instance.save(update_fields=['step_data'])

        logger.info(
            f"Stored receipt for {step_name} in asset {asset_instance.id}. "
            f"Block: {receipt_data['blockNumber']}, Gas used: {receipt_data['gasUsed']}"
        )

        return receipt

    @retry_with_backoff(
        exceptions=(Web3Exception, ConnectionError, TimeoutError),
        config=RetryConfig(max_attempts=3, base_delay=1.0, exponential_base=2.0, max_delay=10.0)
    )
    def get_transaction_status(self, tx_hash: str) -> Optional[str]:
        """
        Get the current status of a transaction without waiting.

        Args:
            tx_hash: Transaction hash to check

        Returns:
            Status string: 'success', 'failed', 'pending', or None if not found
        """
        if not tx_hash:
            return None

        if not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash

        try:
            receipt = self.web3.eth.get_transaction_receipt(tx_hash)

            if receipt.get('status') == 1:
                return 'success'
            elif receipt.get('status') == 0:
                return 'failed'
            else:
                return 'unknown'

        except TransactionNotFound:
            # Check if transaction exists in mempool
            try:
                tx = self.web3.eth.get_transaction(tx_hash)
                if tx:
                    return 'pending'
            except TransactionNotFound:
                pass

            return None
        except Exception as e:
            logger.warning(f"Error checking transaction status for {tx_hash}: {e}")
            return None

    @retry_with_backoff(
        exceptions=(Web3Exception, ConnectionError, TimeoutError),
        config=RetryConfig(max_attempts=3, base_delay=1.0, exponential_base=2.0, max_delay=10.0)
    )
    def estimate_gas(
        self,
        transaction: Dict[str, Any]
    ) -> int:
        """
        Estimate gas required for a transaction.

        Args:
            transaction: Transaction dictionary with 'from', 'to', 'data', etc.

        Returns:
            Estimated gas units required

        Raises:
            BlockchainTransactionError: If estimation fails
        """
        try:
            gas_estimate = self.web3.eth.estimate_gas(transaction)

            # Add 20% buffer to be safe
            gas_with_buffer = int(gas_estimate * 1.2)

            logger.info(
                f"Gas estimate: {gas_estimate} units "
                f"(with 20% buffer: {gas_with_buffer} units)"
            )

            return gas_with_buffer

        except Exception as e:
            logger.error(f"Failed to estimate gas: {e}")
            raise BlockchainTransactionError(
                f"Gas estimation failed: {str(e)}. "
                "The transaction may fail or parameters may be invalid."
            )


def get_transaction_manager(web3: Optional[Web3] = None) -> BlockchainTransactionManager:
    """
    Get a BlockchainTransactionManager instance.

    Args:
        web3: Optional Web3 instance. If not provided, creates a new one from settings.

    Returns:
        BlockchainTransactionManager instance
    """
    if web3 is None:
        # Use module-level settings import (line 10)
        web3 = Web3(Web3.HTTPProvider(settings.WEB3_PROVIDER_URI))

        if not web3.is_connected():
            logger.warning(
                f"Failed to connect to Web3 provider at {settings.WEB3_PROVIDER_URI}"
            )

    # Get timeout from settings or use default
    timeout = getattr(settings, 'BLOCKCHAIN_RECEIPT_TIMEOUT', 120)

    return BlockchainTransactionManager(web3, default_timeout=timeout)
