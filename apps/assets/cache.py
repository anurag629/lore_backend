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
    # Include cache version in key to enable invalidation
    version = get_asset_list_cache_version()
    cache_key = get_cache_key('asset_list', version=version, **params)
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
    # Include cache version in key to enable invalidation
    version = get_asset_list_cache_version()
    cache_key = get_cache_key('asset_list', version=version, **params)
    return cache.get(cache_key)


def cache_asset_detail(asset_id, data: dict, timeout: int = 600):
    """
    Cache asset detail response.
    
    Args:
        asset_id: Asset ID (can be UUID string or integer)
        data: Response data to cache
        timeout: Cache timeout in seconds (default: 10 minutes)
    """
    cache_key = f"asset_detail:{asset_id}"
    cache.set(cache_key, data, timeout)
    return cache_key


def get_cached_asset_detail(asset_id):
    """
    Get cached asset detail.
    
    Args:
        asset_id: Asset ID (can be UUID string or integer)
        
    Returns:
        Cached data or None
    """
    cache_key = f"asset_detail:{asset_id}"
    return cache.get(cache_key)


def invalidate_asset_list_caches():
    """
    Invalidate all asset list caches.
    This is needed when an asset is created, updated, or deleted.
    """
    # Since we can't easily list all cache keys, we'll use a version-based approach
    # Increment a version number that's included in cache keys
    from django.core.cache import cache
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        current_version = cache.get('asset_list_cache_version', 0)
        new_version = current_version + 1
        # Set with a very long timeout (effectively permanent until next increment)
        cache.set('asset_list_cache_version', new_version, timeout=86400 * 365)  # 1 year
        logger.info(f"Asset list cache invalidated. Version incremented from {current_version} to {new_version}")
        return new_version
    except Exception as e:
        # If versioning fails, we can't invalidate - log and continue
        logger.error(f"Failed to invalidate asset list caches: {e}", exc_info=True)
        return None


def get_asset_list_cache_version():
    """
    Get current asset list cache version.
    This should be included in cache keys to enable invalidation.
    """
    from django.core.cache import cache
    return cache.get('asset_list_cache_version', 0)


def invalidate_asset_cache(asset_id=None, asset_uuid=None, invalidate_lists=True):
    """
    Invalidate asset cache.
    
    Args:
        asset_id: Specific asset ID (integer) to invalidate
        asset_uuid: Specific asset UUID (string) to invalidate
        invalidate_lists: Whether to invalidate list caches (default: True)
    """
    if asset_uuid:
        # Invalidate by UUID (primary method since API uses UUID)
        cache.delete(f"asset_detail:{asset_uuid}")
    elif asset_id:
        # Invalidate by integer ID (fallback)
        cache.delete(f"asset_detail:{asset_id}")
    
    # Invalidate list caches (they might contain this asset)
    if invalidate_lists:
        invalidate_asset_list_caches()


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

