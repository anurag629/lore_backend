"""
Pinata IPFS service for uploading files and metadata
"""
import requests
import hashlib
import json
from typing import Dict, Any, Optional, BinaryIO
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from apps.core.retry_utils import retry_with_backoff, RetryConfig


class PinataService:
    """Service for interacting with Pinata IPFS API"""

    def __init__(self):
        self.api_key = settings.PINATA_API_KEY
        self.api_secret = settings.PINATA_SECRET_KEY
        self.base_url = 'https://api.pinata.cloud'
        self.gateway_url = 'https://gateway.pinata.cloud/ipfs'

        # Headers for authentication
        self.headers = {
            'pinata_api_key': self.api_key,
            'pinata_secret_api_key': self.api_secret,
        }

    @retry_with_backoff(
        exceptions=(requests.exceptions.RequestException, requests.exceptions.Timeout),
        config=RetryConfig(max_attempts=4, base_delay=2.0, exponential_base=2.0, max_delay=30.0)
    )
    def upload_file(self, file: InMemoryUploadedFile, filename: Optional[str] = None) -> Dict[str, str]:
        """
        Upload a file to Pinata IPFS

        Args:
            file: Django uploaded file object
            filename: Optional custom filename

        Returns:
            Dict with 'ipfs_hash' and 'url'
        """
        url = f"{self.base_url}/pinning/pinFileToIPFS"

        # Use provided filename or original filename
        file_name = filename or file.name

        # Prepare file for upload
        files = {
            'file': (file_name, file.read(), file.content_type)
        }

        # Optional metadata
        data = {
            'pinataMetadata': json.dumps({
                'name': file_name,
            }),
            'pinataOptions': json.dumps({
                'cidVersion': 1,
            })
        }

        try:
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=self.headers,
                timeout=60
            )
            response.raise_for_status()

            result = response.json()
            ipfs_hash = result['IpfsHash']

            return {
                'ipfs_hash': ipfs_hash,
                'url': f"{self.gateway_url}/{ipfs_hash}",
                'pinata_url': f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}",
            }
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to upload file to Pinata: {str(e)}")

    @retry_with_backoff(
        exceptions=(requests.exceptions.RequestException, requests.exceptions.Timeout),
        config=RetryConfig(max_attempts=4, base_delay=2.0, exponential_base=2.0, max_delay=30.0)
    )
    def upload_json(self, data: Dict[str, Any], name: Optional[str] = None) -> Dict[str, str]:
        """
        Upload JSON metadata to Pinata IPFS

        Args:
            data: Dictionary to upload as JSON
            name: Optional name for the metadata

        Returns:
            Dict with 'ipfs_hash' and 'url'
        """
        url = f"{self.base_url}/pinning/pinJSONToIPFS"

        payload = {
            'pinataContent': data,
            'pinataMetadata': {
                'name': name or 'metadata.json',
            },
            'pinataOptions': {
                'cidVersion': 1,
            }
        }

        headers = {
            **self.headers,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            ipfs_hash = result['IpfsHash']

            return {
                'ipfs_hash': ipfs_hash,
                'url': f"ipfs://{ipfs_hash}",
                'gateway_url': f"{self.gateway_url}/{ipfs_hash}",
            }
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to upload JSON to Pinata: {str(e)}")

    def upload_ip_metadata(
        self,
        title: str,
        description: str,
        media_url: str,
        creator_address: str,
        asset_id: int,
        license_terms: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Upload IP Asset metadata to IPFS following Story Protocol standards

        Args:
            title: Asset title
            description: Asset description
            media_url: IPFS URL of the media file
            creator_address: Wallet address of creator
            asset_id: Database asset ID
            license_terms: Optional license terms dictionary

        Returns:
            Dict with 'ipfs_hash', 'url', and 'hash'
        """
        # Create metadata following Story Protocol format
        metadata = {
            "name": title,
            "description": description,
            "image": media_url,
            "external_url": f"https://lore.app/explore/{asset_id}",
            "attributes": [
                {
                    "trait_type": "Creator",
                    "value": creator_address
                },
                {
                    "trait_type": "Asset ID",
                    "value": str(asset_id)
                }
            ]
        }

        # Add license terms if provided
        if license_terms:
            metadata["license"] = license_terms

        # Upload to IPFS
        result = self.upload_json(
            data=metadata,
            name=f"asset-{asset_id}-metadata.json"
        )

        # Calculate metadata hash (for Story Protocol)
        # Story Protocol expects a hex string without '0x' prefix, or bytes
        metadata_json = json.dumps(metadata, sort_keys=True)
        hash_digest = hashlib.sha256(metadata_json.encode()).hexdigest()
        # Return both formats: with 0x prefix (for display) and without (for Story Protocol)
        metadata_hash = hash_digest  # Story Protocol SDK handles hex conversion internally

        return {
            **result,
            'hash': metadata_hash,
            'hash_with_prefix': '0x' + hash_digest,  # For display/logging
            'metadata': metadata
        }

    def test_connection(self) -> bool:
        """
        Test connection to Pinata API

        Returns:
            True if connection is successful
        """
        url = f"{self.base_url}/data/testAuthentication"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException:
            return False


def get_pinata_service() -> PinataService:
    """Get singleton Pinata service instance"""
    return PinataService()
