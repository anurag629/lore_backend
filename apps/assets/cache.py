"""
Caching utilities for IP assets.
"""
from django.core.cache import cache
from django.conf import settings
import hashlib
import json


def get_cache_key(prefix: str, **kwargs) -> str:
    """
    Generate a cache key from prefix and kwargs.
    
    Args:
        prefix: Cache key prefix
        **kwargs: Key-value pairs to include in cache key
        
    Returns:
        Cache key string
    """
    # Sort kwargs for consistent key generation
    sorted_kwargs = sorted(kwargs.items())
    key_data = json.dumps(sorted_kwargs, sort_keys=True)
    key_hash = hashlib.md5(key_data.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def cache_asset_list(params: dict, data: dict, timeout: int = 300):
    """
    Cache asset list response.
    
    Args:
        params: Query parameters used for the request
        data: Response data to cache
        timeout: Cache timeout in seconds (default: 5 minutes)
    """
    cache_key = get_cache_key('asset_list', **params)
    cache.set(cache_key, data, timeout)
    return cache_key


def get_cached_asset_list(params: dict):
    """
    Get cached asset list.
    
    Args:
        params: Query parameters used for the request
        
    Returns:
        Cached data or None
    """
    cache_key = get_cache_key('asset_list', **params)
    return cache.get(cache_key)


def cache_asset_detail(asset_id: int, data: dict, timeout: int = 600):
    """
    Cache asset detail response.
    
    Args:
        asset_id: Asset ID
        data: Response data to cache
        timeout: Cache timeout in seconds (default: 10 minutes)
    """
    cache_key = f"asset_detail:{asset_id}"
    cache.set(cache_key, data, timeout)
    return cache_key


def get_cached_asset_detail(asset_id: int):
    """
    Get cached asset detail.
    
    Args:
        asset_id: Asset ID
        
    Returns:
        Cached data or None
    """
    cache_key = f"asset_detail:{asset_id}"
    return cache.get(cache_key)


def invalidate_asset_cache(asset_id: int = None):
    """
    Invalidate asset cache.
    
    Args:
        asset_id: Specific asset ID to invalidate, or None to invalidate all
    """
    if asset_id:
        # Invalidate specific asset
        cache.delete(f"asset_detail:{asset_id}")
        # Also invalidate list caches (they might contain this asset)
        # Note: In production, consider using cache versioning or tags
    else:
        # Invalidate all asset caches
        # Note: This is a simple approach. For production, consider cache versioning
        pass


def cache_user_profile(wallet_address: str, data: dict, timeout: int = 300):
    """
    Cache user profile response.
    
    Args:
        wallet_address: User wallet address
        data: Response data to cache
        timeout: Cache timeout in seconds (default: 5 minutes)
    """
    cache_key = f"user_profile:{wallet_address.lower()}"
    cache.set(cache_key, data, timeout)
    return cache_key


def get_cached_user_profile(wallet_address: str):
    """
    Get cached user profile.
    
    Args:
        wallet_address: User wallet address
        
    Returns:
        Cached data or None
    """
    cache_key = f"user_profile:{wallet_address.lower()}"
    return cache.get(cache_key)


def invalidate_user_profile_cache(wallet_address: str):
    """
    Invalidate user profile cache.
    
    Args:
        wallet_address: User wallet address
    """
    cache_key = f"user_profile:{wallet_address.lower()}"
    cache.delete(cache_key)

