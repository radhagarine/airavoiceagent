"""Cache decorators and utilities for easy cache integration."""

import asyncio
import hashlib
from functools import wraps
from typing import Callable, Optional, List, Any, Dict

from monitoring import logger


def cache_result(ttl: Optional[int] = None, 
                 cache_type: str = "default",
                 key_prefix: str = "", 
                 key_generator: Optional[Callable] = None,
                 skip_cache_on_error: bool = True):
    """
    Decorator to automatically cache function results.
    
    Args:
        ttl: Time to live in seconds (uses cache type default if None)
        cache_type: Type of cache (business_lookup, knowledge_base, default)
        key_prefix: Prefix for cache key
        key_generator: Custom function to generate cache key
        skip_cache_on_error: If True, execute function normally on cache errors
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            from .manager import get_cache_instance
            
            cache = get_cache_instance()
            if not cache:
                logger.warning("Cache not available, executing function directly")
                return await func(*args, **kwargs)
            
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = _generate_cache_key(func, key_prefix, *args, **kwargs)
            
            # Try to get from cache or compute
            try:
                async def compute_func():
                    return await func(*args, **kwargs)
                
                return await cache.get(cache_key, compute_func, cache_type)
                
            except Exception as e:
                if skip_cache_on_error:
                    logger.warning("Cache error, executing function directly", 
                                 error=str(e), 
                                 function=func.__name__)
                    return await func(*args, **kwargs)
                else:
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            from .manager import get_cache_instance
            
            # For sync functions, we need to run in async context
            async def async_func():
                return func(*args, **kwargs)
            
            cache = get_cache_instance()
            if not cache:
                logger.warning("Cache not available, executing function directly")
                return func(*args, **kwargs)
            
            # Generate cache key (same logic as above)
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                cache_key = _generate_cache_key(func, key_prefix, *args, **kwargs)
            
            # Run in event loop
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(
                    cache.get(cache_key, async_func, cache_type)
                )
            except Exception as e:
                if skip_cache_on_error:
                    logger.warning("Cache error, executing function directly", 
                                 error=str(e), 
                                 function=func.__name__)
                    return func(*args, **kwargs)
                else:
                    raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


def _generate_cache_key(func: Callable, key_prefix: str, *args, **kwargs) -> str:
    """Generate cache key from function name and arguments."""
    key_parts = [func.__name__]
    
    # Add arguments to key
    if args:
        arg_strs = []
        for arg in args:
            # Handle different argument types
            if isinstance(arg, (str, int, float, bool)):
                arg_strs.append(str(arg))
            else:
                # For complex objects, use their string representation
                arg_strs.append(repr(arg)[:100])  # Limit length
        arg_str = "_".join(arg_strs)
        key_parts.append(arg_str)
    
    # Add keyword arguments to key
    if kwargs:
        kwarg_strs = []
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)):
                kwarg_strs.append(f"{k}={v}")
            else:
                kwarg_strs.append(f"{k}={repr(v)[:50]}")  # Limit length
        kwarg_str = "_".join(kwarg_strs)
        key_parts.append(kwarg_str)
    
    # Combine parts
    key_base = "_".join(key_parts)
    
    # Hash long keys to keep them manageable
    if len(key_base) > 200:
        key_base = hashlib.md5(key_base.encode()).hexdigest()
    
    # Add prefix if provided
    return f"{key_prefix}:{key_base}" if key_prefix else key_base


# Specific decorators for common use cases
def cache_business_lookup(ttl: Optional[int] = None, key_generator: Optional[Callable] = None):
    """Decorator specifically for business lookup caching."""
    return cache_result(
        ttl=ttl,
        cache_type="business_lookup",
        key_prefix="business",
        key_generator=key_generator
    )


def cache_knowledge_base(ttl: Optional[int] = None, key_generator: Optional[Callable] = None):
    """Decorator specifically for knowledge base query caching."""
    return cache_result(
        ttl=ttl,
        cache_type="knowledge_base",
        key_prefix="kb",
        key_generator=key_generator
    )


# Utility functions for cache invalidation
async def invalidate_cache_pattern(pattern: str, cache_type: str = "default"):
    """Invalidate cache entries matching a pattern."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if cache:
        await cache.clear_pattern(pattern, cache_type)
        logger.info("Cache pattern invalidated", pattern=pattern, cache_type=cache_type)
    else:
        logger.warning("Cache not available for invalidation")


async def invalidate_business_cache(phone: str):
    """Invalidate cache for a specific business."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if cache:
        await cache.invalidate_business(phone)
    else:
        logger.warning("Cache not available for business invalidation")


async def invalidate_knowledge_base_cache(business_id: str):
    """Invalidate knowledge base cache for a specific business."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if cache:
        await cache.invalidate_knowledge_base(business_id)
    else:
        logger.warning("Cache not available for knowledge base invalidation")


# Context managers for cache operations
class CacheContext:
    """Context manager for cache operations with automatic cleanup."""
    
    def __init__(self, cache_keys: List[str], cache_type: str = "default"):
        self.cache_keys = cache_keys
        self.cache_type = cache_type
        self.cache = None
    
    async def __aenter__(self):
        from .manager import get_cache_instance
        self.cache = get_cache_instance()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # If an exception occurred, invalidate the cache
        if exc_type is not None and self.cache:
            logger.info("Exception occurred, invalidating cache", 
                       keys=self.cache_keys,
                       exception=str(exc_val))
            for key in self.cache_keys:
                await self.cache.delete(key, self.cache_type)
    
    async def get(self, key: str, compute_func: Optional[Callable] = None):
        """Get value from cache within context."""
        if self.cache and key in self.cache_keys:
            return await self.cache.get(key, compute_func, self.cache_type)
        else:
            logger.warning("Key not in context or cache not available", key=key)
            if compute_func:
                return await compute_func() if asyncio.iscoroutinefunction(compute_func) else compute_func()
            return None
    
    async def set(self, key: str, value: Any):
        """Set value in cache within context."""
        if self.cache and key in self.cache_keys:
            await self.cache.set(key, value, self.cache_type)
        else:
            logger.warning("Key not in context or cache not available", key=key)


# Performance monitoring decorators
def cache_performance_monitor(operation_name: str):
    """Decorator to monitor cache operation performance."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import time
            from monitoring import metrics
            
            start_time = time.time()
            success = False
            
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                logger.error(f"Cache operation {operation_name} failed", error=str(e))
                raise
            finally:
                duration = time.time() - start_time
                status = "success" if success else "error"
                
                # Record metrics
                metrics.observe_histogram(
                    'cache_operation_duration_seconds',
                    duration,
                    labels={'operation': operation_name, 'status': status}
                )
                metrics.increment_counter(
                    'cache_operation_total',
                    labels={'operation': operation_name, 'status': status}
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time
            from monitoring import metrics
            
            start_time = time.time()
            success = False
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                logger.error(f"Cache operation {operation_name} failed", error=str(e))
                raise
            finally:
                duration = time.time() - start_time
                status = "success" if success else "error"
                
                # Record metrics
                metrics.observe_histogram(
                    'cache_operation_duration_seconds',
                    duration,
                    labels={'operation': operation_name, 'status': status}
                )
                metrics.increment_counter(
                    'cache_operation_total',
                    labels={'operation': operation_name, 'status': status}
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Helper functions for cache key generation
def generate_business_key(phone: str) -> str:
    """Generate standardized business cache key."""
    # Normalize phone number for consistent caching
    normalized_phone = ''.join(filter(str.isdigit, phone))
    return f"business:{normalized_phone}"


def generate_knowledge_base_key(business_id: str, query: str) -> str:
    """Generate standardized knowledge base cache key."""
    # Hash the query to handle long queries and special characters
    query_hash = hashlib.md5(query.encode()).hexdigest()
    return f"kb:{business_id}:{query_hash}"


def generate_daily_room_key(caller_phone: str) -> str:
    """Generate standardized Daily room cache key."""
    normalized_phone = ''.join(filter(str.isdigit, caller_phone))
    return f"daily_room:{normalized_phone}"


# Bulk operations utilities
async def bulk_invalidate(keys: List[str], cache_type: str = "default"):
    """Invalidate multiple cache keys efficiently."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if not cache:
        logger.warning("Cache not available for bulk invalidation")
        return
    
    # Invalidate in parallel for better performance
    tasks = [cache.delete(key, cache_type) for key in keys]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if r is True)
    error_count = sum(1 for r in results if isinstance(r, Exception))
    
    logger.info("Bulk invalidation completed",
               total_keys=len(keys),
               successful=success_count,
               errors=error_count,
               cache_type=cache_type)


async def bulk_warm_cache(warm_specs: List[Dict[str, Any]]):
    """Warm multiple cache entries efficiently."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if not cache:
        logger.warning("Cache not available for bulk warming")
        return
    
    await cache.warmer.warm_custom_data(warm_specs)


# Cache statistics utilities
async def get_cache_statistics() -> Dict[str, Any]:
    """Get comprehensive cache statistics."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if cache:
        return cache.get_stats()
    else:
        return {"error": "Cache not available"}


async def get_cache_health() -> Dict[str, Any]:
    """Get cache health status."""
    from .manager import get_cache_instance
    
    cache = get_cache_instance()
    if cache:
        return await cache.health_check()
    else:
        return {"status": "unhealthy", "error": "Cache not available"}