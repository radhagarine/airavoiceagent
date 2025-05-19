
"""
Simplified cache implementation for the voice bot application.

This module provides a streamlined two-level caching system with:
1. Level 1: In-memory cache using TTLCache
2. Level 2: Redis cache (single instance)

It maintains backward compatibility with the existing cache interface
while removing unnecessary complexity.
"""

import os
import asyncio
import json
import pickle
import time
import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, List, Union
import hashlib

from cachetools import TTLCache
import redis.asyncio as redis_async
from redis.exceptions import RedisError

# Configure logging
logger = logging.getLogger(__name__)

# Singleton cache instance
_cache_instance = None

class SimplifiedCache:
    """
    Simplified two-level cache implementation.
    
    Features:
    - L1 (in-memory) cache with TTL
    - L2 (Redis) cache with configurable TTL
    - Simple statistics tracking
    - Clean API for cache operations
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the cache system.
        
        Args:
            config: Optional configuration dictionary. If not provided, 
                   values are read from environment variables.
        """
        self.config = config or self._read_config_from_env()
        
        # Initialize statistics
        self.stats = {
            "l1_hits": 0,
            "l1_misses": 0,
            "l2_hits": 0,
            "l2_misses": 0,
            "errors": 0,
            "total_requests": 0,
            "start_time": time.time()
        }
        
        # Initialize L1 cache (in-memory)
        self.l1_cache = TTLCache(
            maxsize=self.config["l1_max_size"],
            ttl=self.config["l1_ttl"]
        )
        
        # Initialize L2 cache (Redis)
        self.redis = None
        self._redis_initialized = False
        
        logger.info(f"Cache initialized with L1 size: {self.config['l1_max_size']}, " 
                    f"L1 TTL: {self.config['l1_ttl']}s")
    
    def _read_config_from_env(self) -> Dict:
        """Read configuration from environment variables with sensible defaults."""
        return {
            # L1 Cache config
            "l1_max_size": int(os.getenv("CACHE_L1_SIZE", "500")),
            "l1_ttl": int(os.getenv("CACHE_L1_TTL", "300")),  # 5 minutes
            
            # L2 Cache config
            "redis_host": os.getenv("REDIS_HOST", "localhost"),
            "redis_port": int(os.getenv("REDIS_PORT", "6379")),
            "redis_password": os.getenv("REDIS_PASSWORD"),
            "redis_db": int(os.getenv("REDIS_DB", "0")),
            
            # TTL config for different cache types
            "business_lookup_ttl": int(os.getenv("CACHE_BUSINESS_TTL", "1800")),  # 30 minutes
            "knowledge_base_ttl": int(os.getenv("CACHE_KNOWLEDGE_TTL", "3600")),  # 1 hour
            "default_ttl": int(os.getenv("CACHE_DEFAULT_TTL", "600")),  # 10 minutes
            
            # Other settings
            "compression_enabled": os.getenv("CACHE_COMPRESSION", "true").lower() == "true",
            "compression_threshold": int(os.getenv("CACHE_COMPRESSION_THRESHOLD", "1024")),
            "prefix": os.getenv("CACHE_PREFIX", "voice_bot")
        }

    async def _init_redis(self):
        """Initialize Redis connection lazily."""
        if self._redis_initialized:
            return
            
        try:
            # Create Redis client
            self.redis = redis_async.Redis(
                host=self.config["redis_host"],
                port=self.config["redis_port"],
                password=self.config["redis_password"],
                db=self.config["redis_db"],
                decode_responses=False,  # Keep binary for flexible serialization
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            
            # Test connection
            await self.redis.ping()
            self._redis_initialized = True
            logger.info(f"Connected to Redis at {self.config['redis_host']}:{self.config['redis_port']}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            self.redis = None
            self._redis_initialized = False
            self.stats["errors"] += 1
            raise
    
    def _get_ttl_for_type(self, cache_type: str) -> int:
        """Get TTL value based on cache type."""
        ttl_map = {
            "business_lookup": self.config["business_lookup_ttl"],
            "knowledge_base": self.config["knowledge_base_ttl"],
            "default": self.config["default_ttl"]
        }
        return ttl_map.get(cache_type, self.config["default_ttl"])
    
    def _get_cache_key(self, key: str, cache_type: str = "default") -> str:
        """Generate a properly formatted cache key."""
        return f"{self.config['prefix']}:{cache_type}:{key}"
    
    def _get_l1_key(self, key: str, cache_type: str) -> str:
        """Generate L1 cache key."""
        return f"{cache_type}:{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value with optional compression."""
        try:
            # Use JSON for simple types, pickle for complex objects
            if isinstance(value, (str, int, float, bool, type(None))) or (
                    isinstance(value, (list, dict)) and not any(
                        not isinstance(x, (str, int, float, bool, type(None)))
                        for x in value
                    )
            ):
                data = json.dumps(value).encode('utf-8')
            else:
                data = pickle.dumps(value)
            
            # Compress if enabled and data is large enough
            if (self.config["compression_enabled"] and 
                len(data) > self.config["compression_threshold"]):
                import gzip
                data = b'compressed:' + gzip.compress(data)
            
            return data
        except Exception as e:
            logger.error(f"Serialization error: {str(e)}")
            self.stats["errors"] += 1
            raise
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value with decompression."""
        try:
            # Check if compressed
            if data.startswith(b'compressed:'):
                import gzip
                data = gzip.decompress(data[11:])  # Remove 'compressed:' prefix
            
            # Try JSON first, then pickle
            try:
                return json.loads(data.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return pickle.loads(data)
                
        except Exception as e:
            logger.error(f"Deserialization error: {str(e)}")
            self.stats["errors"] += 1
            raise
    
    async def get(self, key: str, compute_func: Optional[Callable] = None,
                  cache_type: str = "default") -> Any:
        """
        Get a value from the cache, computing it if necessary.
        
        Args:
            key: Cache key
            compute_func: Function to compute the value if not in cache
            cache_type: Type of cache (business_lookup, knowledge_base, default)
            
        Returns:
            Cached value or computed value if not cached
        """
        self.stats["total_requests"] += 1
        ttl = self._get_ttl_for_type(cache_type)
        
        # Try L1 cache first
        l1_key = self._get_l1_key(key, cache_type)
        value = self.l1_cache.get(l1_key)
        
        if value is not None:
            self.stats["l1_hits"] += 1
            logger.debug(f"L1 cache hit: {l1_key}")
            return value
        
        self.stats["l1_misses"] += 1
        
        # Try L2 cache if available
        if self.redis is not None or not self._redis_initialized:
            try:
                if not self._redis_initialized:
                    await self._init_redis()
                
                if self.redis:
                    redis_key = self._get_cache_key(key, cache_type)
                    data = await self.redis.get(redis_key)
                    
                    if data is not None:
                        self.stats["l2_hits"] += 1
                        value = self._deserialize(data)
                        
                        # Update L1 cache
                        self.l1_cache[l1_key] = value
                        
                        logger.debug(f"L2 cache hit: {redis_key}")
                        return value
                    
                    self.stats["l2_misses"] += 1
            except Exception as e:
                logger.warning(f"Redis error during get: {str(e)}")
                self.stats["errors"] += 1
                # Continue to compute function as fallback
        
        # Compute value if not found in cache
        if compute_func is not None:
            try:
                # Execute compute function
                if asyncio.iscoroutinefunction(compute_func):
                    value = await compute_func()
                else:
                    # Run in thread pool for non-async functions
                    loop = asyncio.get_event_loop()
                    value = await loop.run_in_executor(None, compute_func)
                
                # Store in L1 cache
                self.l1_cache[l1_key] = value
                
                # Store in L2 cache if available
                if self.redis is not None and self._redis_initialized:
                    try:
                        redis_key = self._get_cache_key(key, cache_type)
                        data = self._serialize(value)
                        await self.redis.setex(redis_key, ttl, data)
                    except Exception as e:
                        logger.warning(f"Redis error during set: {str(e)}")
                        self.stats["errors"] += 1
                
                return value
            except Exception as e:
                logger.error(f"Error computing value: {str(e)}")
                self.stats["errors"] += 1
                raise
        
        return None
    
    async def set(self, key: str, value: Any, cache_type: str = "default") -> bool:
        """
        Set a value in the cache.
        
        Args:
            key: Cache key
            value: Value to cache
            cache_type: Type of cache (business_lookup, knowledge_base, default)
            
        Returns:
            True if successful, False on error
        """
        ttl = self._get_ttl_for_type(cache_type)
        
        try:
            # Store in L1 cache
            l1_key = self._get_l1_key(key, cache_type)
            self.l1_cache[l1_key] = value
            
            # Store in L2 cache if available
            if self.redis is not None or not self._redis_initialized:
                try:
                    if not self._redis_initialized:
                        await self._init_redis()
                    
                    if self.redis:
                        redis_key = self._get_cache_key(key, cache_type)
                        data = self._serialize(value)
                        await self.redis.setex(redis_key, ttl, data)
                except Exception as e:
                    logger.warning(f"Redis error during set: {str(e)}")
                    self.stats["errors"] += 1
                    # Continue, as we've already cached in L1
            
            return True
        except Exception as e:
            logger.error(f"Error setting cache value: {str(e)}")
            self.stats["errors"] += 1
            return False
    
    async def delete(self, key: str, cache_type: str = "default") -> bool:
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
            cache_type: Type of cache (business_lookup, knowledge_base, default)
            
        Returns:
            True if successful, False on error
        """
        try:
            # Delete from L1 cache
            l1_key = self._get_l1_key(key, cache_type)
            if l1_key in self.l1_cache:
                del self.l1_cache[l1_key]
            
            # Delete from L2 cache if available
            if self.redis is not None or not self._redis_initialized:
                try:
                    if not self._redis_initialized:
                        await self._init_redis()
                    
                    if self.redis:
                        redis_key = self._get_cache_key(key, cache_type)
                        await self.redis.delete(redis_key)
                except Exception as e:
                    logger.warning(f"Redis error during delete: {str(e)}")
                    self.stats["errors"] += 1
                    # Continue as we've already removed from L1
            
            return True
        except Exception as e:
            logger.error(f"Error deleting cache value: {str(e)}")
            self.stats["errors"] += 1
            return False
    
    async def clear_pattern(self, pattern: str, cache_type: str = "default") -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (* for wildcard)
            cache_type: Type of cache (business_lookup, knowledge_base, default)
            
        Returns:
            Number of keys deleted
        """
        count = 0
        
        try:
            # Clear from L1 cache
            import fnmatch
            l1_prefix = f"{cache_type}:"
            keys_to_delete = []
            
            for k in list(self.l1_cache.keys()):
                if k.startswith(l1_prefix):
                    actual_key = k[len(l1_prefix):]
                    if fnmatch.fnmatch(actual_key, pattern):
                        keys_to_delete.append(k)
            
            for k in keys_to_delete:
                del self.l1_cache[k]
                count += 1
            
            # Clear from L2 cache if available
            if self.redis is not None or not self._redis_initialized:
                try:
                    if not self._redis_initialized:
                        await self._init_redis()
                    
                    if self.redis:
                        redis_pattern = self._get_cache_key(pattern, cache_type)
                        # Replace * with Redis pattern
                        redis_pattern = redis_pattern.replace("*", "*")
                        
                        # Get matching keys
                        keys = await self.redis.keys(redis_pattern)
                        if keys:
                            # Delete in batches for performance
                            for i in range(0, len(keys), 100):
                                batch = keys[i:i+100]
                                deleted = await self.redis.delete(*batch)
                                count += deleted
                except Exception as e:
                    logger.warning(f"Redis error during pattern delete: {str(e)}")
                    self.stats["errors"] += 1
            
            return count
        except Exception as e:
            logger.error(f"Error clearing cache pattern: {str(e)}")
            self.stats["errors"] += 1
            return count
    
    async def health_check(self) -> Dict:
        """
        Perform health check on cache system.
        
        Returns:
            Dictionary with health status information
        """
        health = {
            "status": "healthy",
            "l1_cache": {
                "size": len(self.l1_cache),
                "max_size": self.config["l1_max_size"],
                "utilization_percent": round(len(self.l1_cache) / self.config["l1_max_size"] * 100, 2)
            },
            "l2_cache": {
                "status": "unknown",
                "connected": False
            }
        }
        
        # Check Redis connection
        if self._redis_initialized and self.redis:
            try:
                # Test Redis connection with ping
                start_time = time.time()
                await self.redis.ping()
                latency = time.time() - start_time
                
                health["l2_cache"].update({
                    "status": "healthy",
                    "connected": True,
                    "latency_ms": round(latency * 1000, 2),
                    "host": self.config["redis_host"],
                    "port": self.config["redis_port"]
                })
                
                # Get Redis info if available
                try:
                    info = await self.redis.info()
                    health["l2_cache"].update({
                        "redis_version": info.get("redis_version", "unknown"),
                        "used_memory_human": info.get("used_memory_human", "unknown"),
                        "connected_clients": info.get("connected_clients", 0)
                    })
                except:
                    pass  # Skip detailed info if not available
                
            except Exception as e:
                health["l2_cache"].update({
                    "status": "unhealthy",
                    "connected": False,
                    "error": str(e)
                })
                health["status"] = "degraded"
        else:
            health["l2_cache"]["status"] = "disabled"
        
        # Add statistics
        health["statistics"] = self.get_stats()
        
        return health
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        uptime = time.time() - self.stats["start_time"]
        total_operations = self.stats["total_requests"]
        
        # Calculate hit rates
        l1_hit_rate = self.stats["l1_hits"] / max(self.stats["l1_hits"] + self.stats["l1_misses"], 1) * 100
        l2_attempts = max(self.stats["l2_hits"] + self.stats["l2_misses"], 1)
        l2_hit_rate = self.stats["l2_hits"] / l2_attempts * 100
        
        total_hits = self.stats["l1_hits"] + self.stats["l2_hits"]
        overall_hit_rate = total_hits / max(total_operations, 1) * 100
        
        return {
            "uptime_seconds": round(uptime, 2),
            "total_operations": total_operations,
            "hit_rates": {
                "l1_hit_rate": round(l1_hit_rate, 2),
                "l2_hit_rate": round(l2_hit_rate, 2),
                "overall_hit_rate": round(overall_hit_rate, 2)
            },
            "counts": {
                "l1_hits": self.stats["l1_hits"],
                "l1_misses": self.stats["l1_misses"],
                "l2_hits": self.stats["l2_hits"],
                "l2_misses": self.stats["l2_misses"],
                "errors": self.stats["errors"]
            }
        }
    
    async def shutdown(self):
        """Shut down cache connections."""
        if self.redis is not None and self._redis_initialized:
            await self.redis.close()
            self._redis_initialized = False
            logger.info("Redis connection closed")
        
        logger.info("Cache system shut down")


# Decorator for cache_result
def cache_result(ttl: Optional[int] = None, 
                 cache_type: str = "default",
                 key_prefix: str = "", 
                 key_generator: Optional[Callable] = None):
    """
    Decorator to automatically cache function results.
    
    Args:
        ttl: Time to live in seconds (uses cache type default if None)
        cache_type: Type of cache (business_lookup, knowledge_base, default)
        key_prefix: Prefix for cache key
        key_generator: Custom function to generate cache key
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = await get_cache_instance()
            if not cache:
                return await func(*args, **kwargs)
            
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = generate_cache_key(func, key_prefix, *args, **kwargs)
            
            # Define async compute function to wrap the original function
            async def compute_value():
                return await func(*args, **kwargs)
            
            # Get from cache or compute
            result = await cache.get(
                cache_key,
                compute_value,
                cache_type
            )
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            async def get_cached():
                cache = await get_cache_instance()
                if not cache:
                    return func(*args, **kwargs)
                
                # Generate cache key
                if key_generator:
                    cache_key = key_generator(*args, **kwargs)
                else:
                    cache_key = generate_cache_key(func, key_prefix, *args, **kwargs)
                
                # Define regular compute function
                def compute_value():
                    return func(*args, **kwargs)
                
                # Get from cache or compute
                return await cache.get(
                    cache_key,
                    compute_value,
                    cache_type
                )
            
            # Run in event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(get_cached())
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Business-specific cache decorators
def cache_business_lookup(ttl: Optional[int] = None):
    """Cache decorator for business lookups."""
    return cache_result(ttl=ttl, cache_type="business_lookup", key_prefix="business")


def cache_knowledge_base(ttl: Optional[int] = None):
    """Cache decorator for knowledge base queries."""
    return cache_result(ttl=ttl, cache_type="knowledge_base", key_prefix="kb")


# Utility functions
def generate_cache_key(func: Callable, key_prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from function name and arguments."""
    key_parts = [func.__name__]
    
    # Add args to key
    if args:
        key_parts.append("_".join(str(arg) for arg in args))
    
    # Add kwargs to key (sorted by key)
    if kwargs:
        kwarg_parts = sorted(f"{k}={v}" for k, v in kwargs.items())
        key_parts.append("_".join(kwarg_parts))
    
    # Build key
    key = "_".join(key_parts)
    
    # Hash long keys
    if len(key) > 250:
        key = hashlib.md5(key.encode()).hexdigest()
    
    # Add prefix if provided
    if key_prefix:
        key = f"{key_prefix}:{key}"
    
    return key


def generate_business_key(phone: str) -> str:
    """Generate a standardized key for business cache."""
    # Normalize phone number - remove non-digit characters
    normalized = ''.join(filter(str.isdigit, phone))
    return f"phone:{normalized}"


def generate_knowledge_base_key(business_id: str, query: str) -> str:
    """Generate a standardized key for knowledge base cache."""
    # Hash query to handle special characters and length
    query_hash = hashlib.md5(query.encode()).hexdigest()
    return f"kb:{business_id}:{query_hash}"


# Global cache management functions
async def initialize_cache(config: Optional[Dict] = None) -> bool:
    """
    Initialize the global cache system.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        True if successful, False otherwise
    """
    global _cache_instance
    
    try:
        if _cache_instance is None:
            _cache_instance = SimplifiedCache(config)
            # Test Redis connection if available
            await _cache_instance._init_redis()
        logger.info("Cache system initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize cache: {str(e)}")
        return False


async def get_cache_instance() -> Optional[SimplifiedCache]:
    """
    Get the global cache instance.
    
    Returns:
        Initialized cache instance or None if not initialized
    """
    global _cache_instance
    
    if _cache_instance is None:
        # Attempt to initialize
        await initialize_cache()
    
    return _cache_instance


async def shutdown_cache():
    """Shut down the global cache system."""
    global _cache_instance
    
    if _cache_instance:
        await _cache_instance.shutdown()
        _cache_instance = None
        logger.info("Global cache system shut down")


async def get_cache_health() -> Dict:
    """
    Get cache health information.
    
    Returns:
        Health status dictionary
    """
    cache = await get_cache_instance()
    if cache:
        return await cache.health_check()
    return {"status": "not_initialized", "error": "Cache not initialized"}


def get_cache_stats() -> Dict:
    """
    Get cache statistics.
    
    Returns:
        Statistics dictionary
    """
    if _cache_instance:
        return _cache_instance.get_stats()
    return {"error": "Cache not initialized"}


async def invalidate_business_cache(phone: str) -> bool:
    """
    Invalidate cache for a specific business.
    
    Args:
        phone: Business phone number
        
    Returns:
        True if successful, False otherwise
    """
    cache = await get_cache_instance()
    if not cache:
        return False
    
    key = generate_business_key(phone)
    return await cache.delete(key, "business_lookup")


async def invalidate_knowledge_base_cache(business_id: str) -> bool:
    """
    Invalidate knowledge base cache for a specific business.
    
    Args:
        business_id: Business ID
        
    Returns:
        True if successful, False otherwise
    """
    cache = await get_cache_instance()
    if not cache:
        return False
    
    pattern = f"kb:{business_id}:*"
    count = await cache.clear_pattern(pattern, "knowledge_base")
    return count > 0


async def warm_business_lookups(phones: List[str]) -> int:
    """
    Warm cache with business lookups.
    
    Args:
        phones: List of phone numbers to warm
        
    Returns:
        Number of successfully warmed entries
    """
    from utils.supabase_helper import get_business_by_phone
    
    cache = await get_cache_instance()
    if not cache:
        return 0
    
    success_count = 0
    for phone in phones:
        key = generate_business_key(phone)
        
        # Define compute function that gets business info
        def get_business():
            return get_business_by_phone(phone)
        
        # Cache the result
        result = await cache.get(key, get_business, "business_lookup")
        if result:
            success_count += 1
    
    logger.info(f"Warmed cache with {success_count} business lookups")
    return success_count