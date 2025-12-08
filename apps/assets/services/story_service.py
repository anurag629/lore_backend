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
from .blockchain_utils import get_transaction_manager, BlockchainTransactionError
from apps.core.web3_utils import WalletAddressValidator, InvalidAddressError

logger = logging.getLogger(__name__)

# Try to import SDK constants if available
try:
    from story_protocol_python_sdk.constants import (
        SPG_NFT_CONTRACT_ADDRESS,
        ROYALTY_POLICY_LAP_ADDRESS,
        WIP_TOKEN_ADDRESS,
    )
    SDK_CONSTANTS_AVAILABLE = True
except ImportError:
    SDK_CONSTANTS_AVAILABLE = False
    # Logger not yet defined here, will log later if needed

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
        self.tx_manager = None
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

            # Initialize transaction manager for receipt verification
            self.tx_manager = get_transaction_manager(self.web3)

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

    def register_ip_asset(
        self,
        metadata_uri: str,
        metadata_hash: str,
        creator_address: str,
        allow_derivatives: bool = True,
        commercial_use: bool = False,
        royalty_percentage: int = 0
    ) -> Dict[str, Any]:
        """
        Register a new IP asset on Story Protocol.

        Args:
            metadata_uri: URI to the metadata (IPFS URL)
            metadata_hash: Hash of the metadata
            creator_address: Ethereum address of the creator
            allow_derivatives: Whether derivatives are allowed (default: True)
            commercial_use: Whether commercial use is allowed (default: False)
            royalty_percentage: Royalty percentage 0-100 (default: 0)

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

            # Validate required parameters
            if not metadata_uri:
                raise ValueError("metadata_uri is required but was None or empty")
            if not metadata_hash:
                raise ValueError("metadata_hash is required but was None or empty")

            hash_preview = metadata_hash[:20] + '...' if len(metadata_hash) > 20 else metadata_hash
            logger.info(f"Metadata hash: {hash_preview} (length: {len(metadata_hash)})")

            # Ensure metadata_hash is in correct format
            # Story Protocol SDK expects hex string - keep 0x prefix for hash
            if not metadata_hash.startswith('0x'):
                metadata_hash = '0x' + metadata_hash
            
            # Validate and checksum creator_address using WalletAddressValidator
            try:
                creator_address = WalletAddressValidator.checksum(creator_address)
                logger.info(f"Validated and checksummed creator address: {creator_address}")
            except InvalidAddressError as e:
                logger.error(f"Invalid creator address {creator_address}: {e}")
                raise RuntimeError(f"Invalid creator address: {creator_address}. Error: {e}")

            # Register IP Asset using Story Protocol SDK
            # According to SDK docs: register() requires nft_contract and token_id
            # Since we don't have an NFT contract, we use mint_and_register_ip_asset_with_pil_terms
            # which mints a new NFT and registers it as an IP asset
            
            import inspect
            
            # Check available methods
            ip_asset_methods = [m for m in dir(self.client.IPAsset) if not m.startswith('_')]
            logger.info(f"Available IPAsset methods: {ip_asset_methods}")
            
            # Prepare IP metadata dict according to SDK documentation
            # ip_metadata_hash should be a hex string (with 0x prefix)
            ip_metadata = {
                'ip_metadata_uri': metadata_uri,
                'ip_metadata_hash': metadata_hash,
            }
            hash_preview = metadata_hash[:20] + '...' if metadata_hash and len(metadata_hash) > 20 else metadata_hash
            logger.info(f"IP metadata prepared: uri={metadata_uri}, hash={hash_preview}")
            
            # Initialize result variable
            result = None
            
            # Try mint_and_register_ip_asset_with_pil_terms first (recommended for new IP assets)
            if hasattr(self.client.IPAsset, 'mint_and_register_ip_asset_with_pil_terms'):
                logger.info("Using mint_and_register_ip_asset_with_pil_terms method")
                
                # Get SPG NFT contract address
                # Try SDK constants first, then settings, then check client
                spg_nft_contract = None
                royalty_policy = None
                currency = None
                
                # Try to get from SDK constants
                if SDK_CONSTANTS_AVAILABLE:
                    try:
                        spg_nft_contract = SPG_NFT_CONTRACT_ADDRESS
                        royalty_policy = ROYALTY_POLICY_LAP_ADDRESS
                        currency = WIP_TOKEN_ADDRESS
                        logger.info(f"Using SDK constants - SPG: {spg_nft_contract}, Royalty: {royalty_policy}, Currency: {currency}")
                    except Exception as e:
                        logger.warning(f"Could not use SDK constants: {e}")
                
                # Try to get from client config/attributes
                if not spg_nft_contract:
                    try:
                        # Check various possible attributes
                        client_attrs = dir(self.client)
                        logger.info(f"Client attributes: {[a for a in client_attrs if not a.startswith('_')]}")
                        
                        if hasattr(self.client, 'config'):
                            config = self.client.config
                            config_attrs = dir(config)
                            logger.info(f"Client config attributes: {[a for a in config_attrs if not a.startswith('_')]}")
                            
                            # Try common attribute names
                            for attr_name in ['spg_nft_contract', 'spgNftContract', 'spg_contract', 'nft_contract']:
                                if hasattr(config, attr_name):
                                    spg_nft_contract = getattr(config, attr_name)
                                    logger.info(f"Got SPG NFT contract from client.config.{attr_name}: {spg_nft_contract}")
                                    break
                    except Exception as e:
                        logger.warning(f"Could not inspect client config: {e}")
                
                # Fallback to settings
                if not spg_nft_contract:
                    spg_nft_contract = getattr(settings, 'STORY_PROTOCOL_SPG_NFT_CONTRACT', None)
                    logger.info(f"Using SPG NFT contract from settings: {spg_nft_contract}")
                
                if not spg_nft_contract:
                    raise RuntimeError(
                        "SPG NFT contract address not found. Please:\n"
                        "1. Set STORY_PROTOCOL_SPG_NFT_CONTRACT in environment variables, or\n"
                        "2. Ensure SDK constants are available, or\n"
                        "3. Check Story Protocol documentation for the correct Aeneid testnet SPG NFT contract address"
                    )
                
                # Ensure all contract addresses are checksummed BEFORE validation (required by Web3.py)
                try:
                    spg_nft_contract = self.web3.to_checksum_address(spg_nft_contract)
                    if royalty_policy:
                        royalty_policy = self.web3.to_checksum_address(royalty_policy)
                    if currency:
                        currency = self.web3.to_checksum_address(currency)
                    logger.info(f"Checksummed contract addresses - SPG: {spg_nft_contract}, Royalty: {royalty_policy}, Currency: {currency}")
                except Exception as e:
                    logger.error(f"Failed to checksum contract addresses: {e}")
                    raise RuntimeError(f"Invalid contract address format. Error: {e}")
                
                # Validate the contract exists on chain - CRITICAL CHECK
                try:
                    code = self.web3.eth.get_code(spg_nft_contract)
                    if code == b'':
                        error_msg = (
                            f"SPG NFT Contract {spg_nft_contract} has NO CODE on chain {settings.STORY_PROTOCOL_CHAIN_ID}.\n"
                            "This address does not exist on Aeneid testnet.\n"
                            "The transaction will fail with 'execution reverted'.\n\n"
                            "Please:\n"
                            "1. Get the correct SPG NFT contract address from Story Protocol documentation\n"
                            "2. Set STORY_PROTOCOL_SPG_NFT_CONTRACT in your .env file\n"
                            "3. Or check Story Protocol SDK for contract address constants\n\n"
                            "You can find contract addresses at:\n"
                            "- Story Protocol docs: https://docs.story.foundation\n"
                            "- Aeneid explorer: https://aeneid.storyscan.xyz"
                        )
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    else:
                        logger.info(f"[OK] SPG NFT Contract {spg_nft_contract} verified (code length: {len(code)} bytes)")
                except RuntimeError:
                    # Re-raise our custom error
                    raise
                except Exception as code_error:
                    logger.warning(f"Could not verify SPG NFT contract code: {code_error}")
                    # Continue anyway, but log warning
                
                # Prepare PIL (Programmable IP License) terms according to SDK documentation
                # Terms must be an array, and cannot be empty
                # Using commercial_remix_terms structure from SDK docs
                
                # Check account balance before proceeding
                try:
                    account_balance = self.web3.eth.get_balance(self.account.address)
                    balance_eth = self.web3.from_wei(account_balance, 'ether')
                    logger.info(f"Account balance: {balance_eth} ETH ({account_balance} wei)")
                    if account_balance == 0:
                        raise RuntimeError(
                            f"Account {self.account.address} has zero balance. "
                            "Please fund the account with testnet ETH from https://faucet.story.foundation/"
                        )
                    # Check if balance is very low (less than 0.001 ETH)
                    if account_balance < self.web3.to_wei(0.001, 'ether'):
                        logger.warning(
                            f"Account balance is very low ({balance_eth} ETH). "
                            "Transaction may fail due to insufficient gas. "
                            "Consider funding from https://faucet.story.foundation/"
                        )
                except Exception as balance_error:
                    logger.warning(f"Could not check account balance: {balance_error}")
                
                # Validate contract addresses
                logger.info(f"Validating contract addresses...")
                logger.info(f"SPG NFT Contract: {spg_nft_contract}")
                logger.info(f"Royalty Policy: 0xBe54FB168b3c982b7AaE60dB6CF75Bd8447b390E")
                logger.info(f"Currency ($WIP): 0x1514000000000000000000000000000000000000")
                
                # Check if SPG NFT contract exists
                try:
                    code = self.web3.eth.get_code(spg_nft_contract)
                    if code == b'':
                        logger.warning(f"SPG NFT Contract {spg_nft_contract} appears to have no code. It may not exist on this network.")
                    else:
                        logger.info(f"SPG NFT Contract {spg_nft_contract} exists (code length: {len(code)} bytes)")
                except Exception as code_error:
                    logger.warning(f"Could not verify SPG NFT contract code: {code_error}")
                
                # Use contract addresses from SDK constants if available, otherwise use defaults
                if not royalty_policy:
                    royalty_policy = "0xBe54FB168b3c982b7AaE60dB6CF75Bd8447b390E"  # RoyaltyPolicyLAP default
                if not currency:
                    currency = "0x1514000000000000000000000000000000000000"  # $WIP default
                
                # Determine which PIL flavor to use based on settings
                # Use simplified terms structure - let SDK handle defaults
                if commercial_use and allow_derivatives:
                    # Commercial Remix License - use minimal required fields
                    pil_terms_data = {
                        "transferable": True,
                        "royalty_policy": royalty_policy,
                        "default_minting_fee": 0,
                        "expiration": 0,
                        "commercial_use": True,
                        "commercial_attribution": True,
                        "commercializer_checker": "0x0000000000000000000000000000000000000000",
                        "commercializer_checker_data": "0x0000000000000000000000000000000000000000",
                        "commercial_rev_share": min(royalty_percentage, 100),  # Ensure max 100
                        "commercial_rev_ceiling": 0,
                        "derivatives_allowed": True,
                        "derivatives_attribution": True,
                        "derivatives_approval": False,
                        "derivatives_reciprocal": True,
                        "derivative_rev_ceiling": 0,
                        "currency": currency,
                        "uri": "",
                    }
                elif allow_derivatives:
                    # Non-Commercial Remix License
                    # SDK REQUIREMENT: When commercial_use=False, royalty_policy MUST be ZERO_ADDRESS
                    # See: license_terms.py line 243-246 verify_commercial_use()
                    pil_terms_data = {
                        "transferable": True,
                        "royalty_policy": "0x0000000000000000000000000000000000000000",  # MUST be zero for non-commercial
                        "default_minting_fee": 0,
                        "expiration": 0,
                        "commercial_use": False,
                        "commercial_attribution": False,  # Must be False when commercial_use is False
                        "commercializer_checker": "0x0000000000000000000000000000000000000000",
                        "commercializer_checker_data": "0x0000000000000000000000000000000000000000",
                        "commercial_rev_share": 0,
                        "commercial_rev_ceiling": 0,
                        "derivatives_allowed": True,
                        "derivatives_attribution": True,
                        "derivatives_approval": False,
                        "derivatives_reciprocal": True,
                        "derivative_rev_ceiling": 0,
                        "currency": "0x0000000000000000000000000000000000000000",  # Can be zero for non-commercial
                        "uri": "",
                    }
                else:
                    # Commercial Use Only License (no derivatives) OR Non-commercial, no derivatives
                    # SDK REQUIREMENT: royalty_policy must be ZERO_ADDRESS if commercial_use=False
                    pil_terms_data = {
                        "transferable": True,
                        "royalty_policy": royalty_policy if commercial_use else "0x0000000000000000000000000000000000000000",
                        "default_minting_fee": 0,
                        "expiration": 0,
                        "commercial_use": commercial_use,
                        "commercial_attribution": commercial_use,  # Only True if commercial_use is True
                        "commercializer_checker": "0x0000000000000000000000000000000000000000",
                        "commercializer_checker_data": "0x0000000000000000000000000000000000000000",
                        "commercial_rev_share": min(royalty_percentage, 100) if commercial_use else 0,
                        "commercial_rev_ceiling": 0,
                        "derivatives_allowed": False,
                        "derivatives_attribution": False,
                        "derivatives_approval": False,
                        "derivatives_reciprocal": False,
                        "derivative_rev_ceiling": 0,
                        "currency": currency if commercial_use else "0x0000000000000000000000000000000000000000",
                        "uri": "",
                    }
                    
                # Licensing config is REQUIRED by SDK (not optional)
                # SDK's _validate_license_terms_data expects licensing_config to be present
                licensing_config = {
                    "is_set": False,
                    "minting_fee": 0,
                    "licensing_hook": "0x0000000000000000000000000000000000000000",
                    "hook_data": "0x0000000000000000000000000000000000000000",
                    "commercial_rev_share": 0,  # Set to 0 per SDK docs
                    "disabled": False,
                    "expect_minimum_group_reward_share": 0,
                    "expect_group_reward_pool": "0x0000000000000000000000000000000000000000",
                }
                
                # Terms must be an array according to SDK docs
                # Each element MUST have both 'terms' and 'licensing_config'
                terms = [{
                    "terms": pil_terms_data,
                    "licensing_config": licensing_config
                }]
                
                logger.info(f"SPG NFT Contract: {spg_nft_contract}")
                logger.info(f"Terms structure: {len(terms)} term(s) configured")
                logger.info(f"IP Metadata: {ip_metadata}")
                logger.info(f"Creator Address: {creator_address}")
                
                # Try different parameter combinations
                try:
                    # First try with all parameters
                    logger.info("Attempting mint_and_register_ip_asset_with_pil_terms with full parameters")
                    result = self.client.IPAsset.mint_and_register_ip_asset_with_pil_terms(
                        spg_nft_contract=spg_nft_contract,
                        terms=terms,
                        allow_duplicates=True,
                        ip_metadata=ip_metadata,
                        recipient=creator_address,
                        tx_options={'from': creator_address}
                    )
                    logger.info("Successfully used mint_and_register_ip_asset_with_pil_terms with full parameters")
                except TypeError as type_error:
                    logger.warning(f"TypeError with full parameters: {type_error}")
                    # Try without tx_options
                    try:
                        logger.info("Attempting without tx_options")
                        result = self.client.IPAsset.mint_and_register_ip_asset_with_pil_terms(
                            spg_nft_contract=spg_nft_contract,
                            terms=terms,
                            allow_duplicates=True,
                            ip_metadata=ip_metadata,
                            recipient=creator_address
                        )
                        logger.info("Successfully used mint_and_register_ip_asset_with_pil_terms without tx_options")
                    except TypeError as type_error2:
                        logger.warning(f"TypeError without tx_options: {type_error2}")
                        # Try minimal parameters
                        try:
                            logger.info("Attempting with minimal parameters")
                            result = self.client.IPAsset.mint_and_register_ip_asset_with_pil_terms(
                                spg_nft_contract=spg_nft_contract,
                                terms=terms,
                                ip_metadata=ip_metadata
                            )
                            logger.info("Successfully used mint_and_register_ip_asset_with_pil_terms with minimal parameters")
                        except Exception as e3:
                            logger.error(f"All parameter combinations failed. Last error: {e3}")
                            # Log the method signature for debugging
                            try:
                                sig = inspect.signature(self.client.IPAsset.mint_and_register_ip_asset_with_pil_terms)
                                logger.error(f"Method signature: {sig}")
                            except:
                                pass
                            raise Exception(f"Failed to call mint_and_register_ip_asset_with_pil_terms: {e3}")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"mint_and_register_ip_asset_with_pil_terms failed with exception: {error_msg}")
                    logger.error(f"Exception type: {type(e).__name__}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    
                    # Provide helpful error messages for common issues
                    if "execution reverted" in error_msg.lower():
                        helpful_msg = (
                            "Transaction was reverted by the smart contract. Possible causes:\n"
                            "1. Invalid contract addresses (SPG NFT contract, royalty policy, or currency)\n"
                            "2. Account has insufficient balance for gas fees\n"
                            "3. Invalid PIL terms parameters\n"
                            "4. Contract validation failed\n\n"
                            f"Account: {self.account.address}\n"
                            f"SPG NFT Contract: {spg_nft_contract}\n"
                            f"Royalty Policy: {pil_terms_data.get('royalty_policy')}\n"
                            f"Currency: {pil_terms_data.get('currency')}\n"
                            f"Please check:\n"
                            f"- Account balance at https://aeneid.storyscan.xyz/address/{self.account.address}\n"
                            f"- Contract addresses are correct for Aeneid testnet\n"
                            f"- PIL terms are valid"
                        )
                        raise RuntimeError(f"{error_msg}\n\n{helpful_msg}")
                    else:
                        raise
            
            # Fallback: If we have an NFT contract, use register()
            # Note: This requires nft_contract and token_id which we don't have
            elif hasattr(self.client.IPAsset, 'register'):
                logger.warning("mint_and_register_ip_asset_with_pil_terms not available, trying register")
                sig = inspect.signature(self.client.IPAsset.register)
                logger.info(f"IPAsset.register signature: {sig}")
                
                # register() requires nft_contract and token_id which we don't have
                # This will only work if you have an existing NFT contract
                raise RuntimeError(
                    "register() method requires nft_contract and token_id. "
                    "Use mint_and_register_ip_asset_with_pil_terms() instead for new IP assets, "
                    "or configure an NFT contract address."
                )
            else:
                raise AttributeError(
                    "Neither mint_and_register_ip_asset_with_pil_terms nor register method found on IPAsset. "
                    f"Available methods: {ip_asset_methods}"
                )
            
            # Check if registration was successful
            if result is None:
                raise RuntimeError("IP asset registration failed - no result returned")

            tx_hash = result.get('txHash')
            logger.info(f"IP Asset registered successfully. IP ID: {result.get('ipId')}, TX: {tx_hash}")

            # Verify transaction receipt to ensure it actually succeeded on-chain
            if self.tx_manager and tx_hash:
                try:
                    logger.info(f"Verifying transaction receipt for {tx_hash}")
                    receipt = self.tx_manager.wait_for_receipt(tx_hash, timeout=120)

                    logger.info(
                        f"Transaction confirmed in block {receipt.get('blockNumber')}, "
                        f"gas used: {receipt.get('gasUsed')}"
                    )

                    return {
                        'ip_id': result.get('ipId'),
                        'transaction_hash': tx_hash,
                        'block_number': receipt.get('blockNumber'),
                        'gas_used': receipt.get('gasUsed'),
                        'receipt': receipt,
                    }
                except BlockchainTransactionError as e:
                    logger.error(f"Transaction verification failed: {e}")
                    raise RuntimeError(
                        f"IP asset registration transaction failed verification: {str(e)}"
                    )
            else:
                # Fallback if tx_manager not available (shouldn't happen)
                logger.warning("Transaction manager not available, skipping receipt verification")
                return {
                    'ip_id': result.get('ipId'),
                    'transaction_hash': tx_hash,
                    'block_number': result.get('blockNumber'),
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to register IP asset: {error_msg}")
            
            # Log additional debugging info
            if hasattr(self.client, 'IPAsset'):
                try:
                    import inspect
                    if hasattr(self.client.IPAsset, 'register'):
                        sig = inspect.signature(self.client.IPAsset.register)
                        logger.error(f"IPAsset.register signature: {sig}")
                    if hasattr(self.client.IPAsset, 'registerIpAsset'):
                        sig = inspect.signature(self.client.IPAsset.registerIpAsset)
                        logger.error(f"IPAsset.registerIpAsset signature: {sig}")
                except Exception as debug_error:
                    logger.warning(f"Could not inspect method signatures: {debug_error}")
            
            raise Exception(f"Failed to register IP asset: {error_msg}. Please check Story Protocol SDK documentation for correct method signature.")

    def attach_license_terms(
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

    def register_derivative(
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

            tx_hash = result.get('txHash')
            logger.info(f"Derivative registered successfully. TX: {tx_hash}")

            # Verify transaction receipt to ensure it actually succeeded on-chain
            if self.tx_manager and tx_hash:
                try:
                    logger.info(f"Verifying derivative registration transaction receipt for {tx_hash}")
                    receipt = self.tx_manager.wait_for_receipt(tx_hash, timeout=120)

                    logger.info(
                        f"Derivative transaction confirmed in block {receipt.get('blockNumber')}, "
                        f"gas used: {receipt.get('gasUsed')}"
                    )

                    return {
                        'transaction_hash': tx_hash,
                        'block_number': receipt.get('blockNumber'),
                        'gas_used': receipt.get('gasUsed'),
                        'receipt': receipt,
                    }
                except BlockchainTransactionError as e:
                    logger.error(f"Derivative registration transaction verification failed: {e}")
                    raise RuntimeError(
                        f"Derivative registration transaction failed verification: {str(e)}"
                    )
            else:
                # Fallback if tx_manager not available
                logger.warning("Transaction manager not available, skipping receipt verification")
                return {
                    'transaction_hash': tx_hash,
                    'block_number': result.get('blockNumber'),
                }

        except Exception as e:
            logger.error(f"Failed to register derivative: {str(e)}")
            raise

    def claim_royalties(
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

    def get_royalty_balance(
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
