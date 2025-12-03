"""
Story Protocol Service Layer

Handles all interactions with Story Protocol blockchain including:
- IP Asset registration
- License management
- Derivative creation
- Royalty distribution
"""
from typing import Dict, Optional, Any
from django.conf import settings
from web3 import Web3
from story_protocol_python_sdk import StoryClient
import logging

logger = logging.getLogger(__name__)


class StoryProtocolService:
    """
    Service class for interacting with Story Protocol.
    Manages IP asset registration, licensing, and royalties.
    """

    def __init__(self):
        """Initialize Story Protocol client with Web3 provider."""
        self.web3 = None
        self.client = None
        self.account = None
        self._initialize_client()

    def _initialize_client(self):
        """
        Initialize Web3 and Story Protocol client.
        Uses settings from Django configuration.
        """
        try:
            # Initialize Web3 provider
            rpc_url = settings.WEB3_PROVIDER_URI
            self.web3 = Web3(Web3.HTTPProvider(rpc_url))

            # Check Web3 connection
            if not self.web3.is_connected():
                logger.error(f"Failed to connect to Web3 provider at {rpc_url}")
                raise ConnectionError(f"Cannot connect to {rpc_url}")

            logger.info(f"Connected to Story Protocol RPC: {rpc_url}")

            # Initialize account from private key if provided
            private_key = settings.STORY_PROTOCOL_PRIVATE_KEY
            if private_key:
                self.account = self.web3.eth.account.from_key(private_key)
                logger.info(f"Initialized account: {self.account.address}")
            else:
                logger.warning("No private key configured. Some operations will not be available.")
                return

            # Initialize Story Protocol client
            chain_id = settings.STORY_PROTOCOL_CHAIN_ID
            self.client = StoryClient(
                web3=self.web3,
                account=self.account,
                chain_id=chain_id
            )

            logger.info(f"Story Protocol client initialized for chain ID: {chain_id}")

        except Exception as e:
            logger.error(f"Failed to initialize Story Protocol client: {str(e)}")
            raise

    def is_ready(self) -> bool:
        """Check if the service is properly initialized and ready to use."""
        return (
            self.web3 is not None
            and self.web3.is_connected()
            and self.client is not None
            and self.account is not None
        )

    async def register_ip_asset(
        self,
        metadata_uri: str,
        metadata_hash: str,
        creator_address: str
    ) -> Dict[str, Any]:
        """
        Register a new IP asset on Story Protocol.

        Args:
            metadata_uri: URI to the metadata (IPFS URL)
            metadata_hash: Hash of the metadata
            creator_address: Ethereum address of the creator

        Returns:
            Dict containing:
                - ip_id: The Story Protocol IP Asset ID
                - transaction_hash: Transaction hash of the registration
                - block_number: Block number where registered

        Raises:
            Exception: If registration fails
        """
        if not self.is_ready():
            raise RuntimeError("Story Protocol service not properly initialized")

        try:
            logger.info(f"Registering IP asset for creator: {creator_address}")
            logger.info(f"Metadata URI: {metadata_uri}")

            # Register IP Asset using Story Protocol SDK
            # Note: Actual method names may vary based on SDK version
            result = self.client.IPAsset.register(
                metadata_uri=metadata_uri,
                metadata_hash=metadata_hash,
                owner=creator_address
            )

            logger.info(f"IP Asset registered successfully. IP ID: {result.get('ipId')}")

            return {
                'ip_id': result.get('ipId'),
                'transaction_hash': result.get('txHash'),
                'block_number': result.get('blockNumber'),
            }

        except Exception as e:
            logger.error(f"Failed to register IP asset: {str(e)}")
            raise

    async def attach_license_terms(
        self,
        ip_id: str,
        allow_derivatives: bool = True,
        commercial_use: bool = False,
        royalty_percentage: int = 0
    ) -> Dict[str, Any]:
        """
        Attach license terms to an IP asset.
        Uses Story Protocol's PIL (Programmable IP License).

        Args:
            ip_id: Story Protocol IP Asset ID
            allow_derivatives: Whether derivatives are allowed
            commercial_use: Whether commercial use is allowed
            royalty_percentage: Royalty percentage (0-100)

        Returns:
            Dict containing transaction details

        Raises:
            Exception: If license attachment fails
        """
        if not self.is_ready():
            raise RuntimeError("Story Protocol service not properly initialized")

        try:
            logger.info(f"Attaching license terms to IP: {ip_id}")

            # Prepare license terms
            license_terms = {
                'allowDerivatives': allow_derivatives,
                'commercialUse': commercial_use,
                'royaltyPercentage': royalty_percentage,
            }

            logger.info(f"License terms: {license_terms}")

            # Attach license using Story Protocol SDK
            result = self.client.License.attach(
                ipId=ip_id,
                terms=license_terms
            )

            logger.info(f"License terms attached successfully")

            return {
                'transaction_hash': result.get('txHash'),
                'block_number': result.get('blockNumber'),
                'license_id': result.get('licenseId'),
            }

        except Exception as e:
            logger.error(f"Failed to attach license terms: {str(e)}")
            raise

    async def register_derivative(
        self,
        child_ip_id: str,
        parent_ip_ids: list,
        license_terms: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Register an IP asset as a derivative of parent IP(s).

        Args:
            child_ip_id: Story Protocol ID of the derivative asset
            parent_ip_ids: List of parent IP IDs
            license_terms: Optional license terms for the derivative

        Returns:
            Dict containing transaction details

        Raises:
            Exception: If derivative registration fails
        """
        if not self.is_ready():
            raise RuntimeError("Story Protocol service not properly initialized")

        try:
            logger.info(f"Registering derivative IP: {child_ip_id}")
            logger.info(f"Parent IPs: {parent_ip_ids}")

            # Register derivative relationship
            result = self.client.IPAsset.registerDerivative(
                childIpId=child_ip_id,
                parentIpIds=parent_ip_ids,
                licenseTerms=license_terms or {}
            )

            logger.info(f"Derivative registered successfully")

            return {
                'transaction_hash': result.get('txHash'),
                'block_number': result.get('blockNumber'),
            }

        except Exception as e:
            logger.error(f"Failed to register derivative: {str(e)}")
            raise

    async def claim_royalties(
        self,
        ip_id: str,
        claimer_address: str
    ) -> Dict[str, Any]:
        """
        Claim accumulated royalties for an IP asset.

        Args:
            ip_id: Story Protocol IP Asset ID
            claimer_address: Address claiming the royalties

        Returns:
            Dict containing:
                - amount: Amount of royalties claimed (in wei)
                - transaction_hash: Transaction hash

        Raises:
            Exception: If claiming fails
        """
        if not self.is_ready():
            raise RuntimeError("Story Protocol service not properly initialized")

        try:
            logger.info(f"Claiming royalties for IP: {ip_id}")
            logger.info(f"Claimer: {claimer_address}")

            # Claim royalties using Story Protocol SDK
            result = self.client.Royalty.claim(
                ipId=ip_id,
                claimer=claimer_address
            )

            amount_wei = result.get('amount', 0)
            amount_eth = self.web3.from_wei(amount_wei, 'ether')

            logger.info(f"Royalties claimed: {amount_eth} ETH")

            return {
                'amount': str(amount_eth),
                'amount_wei': amount_wei,
                'transaction_hash': result.get('txHash'),
                'block_number': result.get('blockNumber'),
            }

        except Exception as e:
            logger.error(f"Failed to claim royalties: {str(e)}")
            raise

    async def get_royalty_balance(
        self,
        ip_id: str,
        address: str
    ) -> str:
        """
        Get the current royalty balance for an IP asset.

        Args:
            ip_id: Story Protocol IP Asset ID
            address: Address to check balance for

        Returns:
            Balance as string in ETH

        Raises:
            Exception: If query fails
        """
        if not self.is_ready():
            raise RuntimeError("Story Protocol service not properly initialized")

        try:
            # Query royalty balance
            balance_wei = self.client.Royalty.balanceOf(
                ipId=ip_id,
                account=address
            )

            balance_eth = self.web3.from_wei(balance_wei, 'ether')

            return str(balance_eth)

        except Exception as e:
            logger.error(f"Failed to get royalty balance: {str(e)}")
            raise

    def get_ip_asset_details(self, ip_id: str) -> Dict[str, Any]:
        """
        Retrieve details of an IP asset from the blockchain.

        Args:
            ip_id: Story Protocol IP Asset ID

        Returns:
            Dict containing IP asset details

        Raises:
            Exception: If query fails
        """
        if not self.is_ready():
            raise RuntimeError("Story Protocol service not properly initialized")

        try:
            # Get IP asset details from blockchain
            details = self.client.IPAsset.get(ip_id)

            return {
                'ip_id': details.get('ipId'),
                'owner': details.get('owner'),
                'metadata_uri': details.get('metadataURI'),
                'metadata_hash': details.get('metadataHash'),
                'block_number': details.get('blockNumber'),
            }

        except Exception as e:
            logger.error(f"Failed to get IP asset details: {str(e)}")
            raise


# Singleton instance
_story_service_instance = None


def get_story_service() -> StoryProtocolService:
    """
    Get the singleton instance of StoryProtocolService.

    Returns:
        StoryProtocolService instance
    """
    global _story_service_instance

    if _story_service_instance is None:
        _story_service_instance = StoryProtocolService()

    return _story_service_instance
