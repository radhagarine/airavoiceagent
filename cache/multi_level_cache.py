"""Main multi-level cache implementation with L1 and L2 layers."""

import asyncio
import time
import hashlib
from typing import Any, Optional, Callable, Dict
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

from cachetools import TTLCache

from monitoring_system import logger, monitor_performance, log_context
from .config import CacheConfig
from .stats import CacheStats
from .redis_cache import RedisClusterCache
from .warmer import CacheWarmer


class MultiLevelCache:
    """Production multi-level cache with monitoring and warming."""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.stats = CacheStats()
        
        # L1 Cache (In-Memory) - Optimized for minimal memory
        self.l1_cache = TTLCache(
            maxsize=config.l1_max_size,
            ttl=config.l1_default_ttl
        )
        
        # L2 Cache (Redis Cluster)
        self.l2_cache = RedisClusterCache(config)
        self.l2_cache.set_stats(self.stats)
        
        # Cache warming
        self.warmer = CacheWarmer(config, self)
        self.warmer.set_stats(self.stats)
        
        # Background executor for compute functions
        self.compute_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="cache_compute"
        )
        
        # Metrics update task
        self._metrics_task: Optional[asyncio.Task] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the cache system."""
        if self._initialized:
            logger.warning("Cache already initialized")
            return
        
        # Connect to Redis
        await self.l2_cache.connect()
        
        # Start periodic metrics updates
        self._metrics_task = asyncio.create_task(self._update_metrics_periodically())
        
        self._initialized = True
        logger.info("Multi-level cache initialized",
                   l1_size=self.config.l1_max_size,
                   l1_ttl=self.config.l1_default_ttl,
                   business_ttl=self.config.business_lookup_ttl,
                   knowledge_ttl=self.config.knowledge_base_ttl)
    
    async def shutdown(self):
        """Shutdown the cache system gracefully."""
        if not self._initialized:
            return
        
        logger.info("Shutting down cache system")
        
        # Cancel metrics task
        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown warmer
        await self.warmer.shutdown()
        
        # Shutdown compute executor
        self.compute_executor.shutdown(wait=True)
        
        # Disconnect from Redis
        await self.l2_cache.disconnect()
        
        self._initialized = False
        logger.info("Multi-level cache shutdown complete")
    
    async def _update_metrics_periodically(self):
        """Update Prometheus metrics periodically."""
        while True:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                self.stats.update_prometheus_metrics(len(self.l1_cache))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error updating cache metrics", error=str(e))
    
    def _get_ttl_for_type(self, cache_type: str) -> int:
        """Get appropriate TTL based on cache type."""
        ttl_map = {
            'business_lookup': self.config.business_lookup_ttl,
            'knowledge_base': self.config.knowledge_base_ttl,
            'default': self.config.l1_default_ttl
        }
        return ttl_map.get(cache_type, self.config.l1_default_ttl)
    
    def _get_l1_key(self, key: str, cache_type: str) -> str:
        """Get L1 cache key with type prefix."""
        return f"{cache_type}:{key}"
    
    @monitor_performance("cache_get")
    async def get(self, key: str, compute_func: Optional[Callable] = None,
                  cache_type: str = "default") -> Any:
        """
        Get value from cache with fallback to compute function.
        
        Args:
            key: Cache key
            compute_func: Function to compute value if not in cache
            cache_type: Type of cache (business_lookup, knowledge_base, default)
        """
        # Get TTL for this cache type
        ttl = self._get_ttl_for_type(cache_type)
        
        start_time = time.time()
        with log_context(cache_key=key, cache_type=cache_type, operation="cache_get"):
            
            # Try L1 cache first
            l1_key = self._get_l1_key(key, cache_type)
            try:
                value = self.l1_cache.get(l1_key)
                if value is not None:
                    self.stats.record_l1_hit()
                    logger.debug("L1 cache hit", key=key, cache_type=cache_type)
                    return value
                else:
                    self.stats.record_l1_miss()
                    logger.debug("L1 cache miss", key=key, cache_type=cache_type)
            except Exception as e:
                logger.error("L1 cache error", key=key, error=str(e))
                self.stats.record_error("l1_error")
            
            # Try L2 cache
            try:
                value = await self.l2_cache.get(key, cache_type)
                if value is not None:
                    self.stats.record_l2_hit()
                    logger.debug("L2 cache hit", key=key, cache_type=cache_type)
                    
                    # Populate L1 cache
                    try:
                        # Use shorter TTL for L1
                        l1_ttl = min(ttl, self.config.l1_default_ttl)
                        # Since TTLCache doesn't support per-item TTL, we use the global TTL
                        self.l1_cache[l1_key] = value
                    except Exception as e:
                        logger.debug("Failed to populate L1 cache", error=str(e))
                    
                    return value
                else:
                    self.stats.record_l2_miss()
                    logger.debug("L2 cache miss", key=key, cache_type=cache_type)
            except Exception as e:
                logger.error("L2 cache error", key=key, error=str(e))
                self.stats.record_error("l2_error")
            
            # Compute value if function provided
            if compute_func:
                logger.debug("Computing value", key=key, cache_type=cache_type)
                try:
                    if asyncio.iscoroutinefunction(compute_func):
                        value = await compute_func()
                    else:
                        # Run in thread pool to avoid blocking
                        loop = asyncio.get_event_loop()
                        value = await loop.run_in_executor(
                            self.compute_executor, 
                            compute_func
                        )
                    
                    self.stats.record_compute()
                    
                    # Cache the computed value (fire and forget)
                    asyncio.create_task(self._cache_value(key, value, ttl, cache_type))
                    
                    # Record total operation time
                    duration = time.time() - start_time
                    self.stats.record_operation_time("cache_get_with_compute", duration)
                    
                    return value
                    
                except Exception as e:
                    logger.error("Error computing cache value", 
                               key=key, 
                               cache_type=cache_type,
                               error=str(e))
                    self.stats.record_error("compute_error")
                    raise
            
            return None
    
    async def _cache_value(self, key: str, value: Any, ttl: int, cache_type: str):
        """Cache a value in both L1 and L2 (internal method)."""
        # Cache in L1
        try:
            l1_key = self._get_l1_key(key, cache_type)
            self.l1_cache[l1_key] = value
        except Exception as e:
            logger.debug("Failed to cache in L1", key=key, error=str(e))
        
        # Cache in L2
        try:
            await self.l2_cache.set(key, value, ttl, cache_type)
        except Exception as e:
            logger.error("Failed to cache in L2", key=key, error=str(e))
    
    async def set(self, key: str, value: Any, cache_type: str = "default") -> bool:
        """Set value in cache."""
        ttl = self._get_ttl_for_type(cache_type)
        
        with log_context(cache_key=key, cache_type=cache_type, operation="cache_set"):
            # Set in L1 cache
            try:
                l1_key = self._get_l1_key(key, cache_type)
                self.l1_cache[l1_key] = value
                logger.debug("L1 cache set", key=key, cache_type=cache_type)
            except Exception as e:
                logger.error("L1 cache set error", key=key, error=str(e))
                self.stats.record_error("l1_set_error")
            
            # Set in L2 cache
            try:
                success = await self.l2_cache.set(key, value, ttl, cache_type)
                logger.debug("L2 cache set", key=key, cache_type=cache_type, success=success)
                return success
            except Exception as e:
                logger.error("L2 cache set error", key=key, error=str(e))
                self.stats.record_error("l2_set_error")
                return False
    
    async def delete(self, key: str, cache_type: str = "default") -> bool:
        """Delete key from cache."""
        with log_context(cache_key=key, cache_type=cache_type, operation="cache_delete"):
            # Delete from L1
            try:
                l1_key = self._get_l1_key(key, cache_type)
                if l1_key in self.l1_cache:
                    del self.l1_cache[l1_key]
                    logger.debug("L1 cache delete", key=key, cache_type=cache_type)
            except Exception as e:
                logger.error("L1 cache delete error", key=key, error=str(e))
            
            # Delete from L2
            try:
                success = await self.l2_cache.delete(key, cache_type)
                logger.debug("L2 cache delete", key=key, cache_type=cache_type, success=success)
                return success
            except Exception as e:
                logger.error("L2 cache delete error", key=key, error=str(e))
                return False
    
    async def clear_pattern(self, pattern: str, cache_type: str = "default") -> int:
        """Clear all keys matching pattern."""
        with log_context(cache_pattern=pattern, cache_type=cache_type, operation="cache_clear_pattern"):
            # Clear from L1 (iterate through all keys)
            l1_cleared = 0
            keys_to_delete = []
            prefix = f"{cache_type}:"
            
            for key in list(self.l1_cache.keys()):
                if key.startswith(prefix):
                    # Extract the actual key part
                    actual_key = key[len(prefix):]
                    if self._match_pattern(actual_key, pattern):
                        keys_to_delete.append(key)
            
            for key in keys_to_delete:
                try:
                    del self.l1_cache[key]
                    l1_cleared += 1
                except:
                    pass
            
            # Clear from L2
            l2_cleared = await self.l2_cache.clear_pattern(pattern, cache_type)
            
            logger.info("Cache pattern cleared",
                       pattern=pattern,
                       cache_type=cache_type,
                       l1_cleared=l1_cleared,
                       l2_cleared=l2_cleared)
            
            return l1_cleared + l2_cleared
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching (supports * wildcards)."""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = self.stats.get_stats()
        stats["l1_cache_size"] = len(self.l1_cache)
        stats["warming_status"] = self.warmer.get_warming_status()
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        l2_health = await self.l2_cache.health_check()
        
        return {
            "status": "healthy" if l2_health["status"] == "healthy" else "degraded",
            "l1_cache": {
                "size": len(self.l1_cache),
                "max_size": self.config.l1_max_size,
                "utilization_percent": round(len(self.l1_cache) / self.config.l1_max_size * 100, 2)
            },
            "l2_cache": l2_health,
            "statistics": self.get_stats(),
            "configuration": {
                "business_lookup_ttl": self.config.business_lookup_ttl,
                "knowledge_base_ttl": self.config.knowledge_base_ttl,
                "compression_enabled": self.config.compression_enabled,
                "warming_enabled": self.config.enable_warming
            }
        }
    
    # Convenience methods for specific cache types
    async def get_business_lookup(self, phone: str, compute_func: Optional[Callable] = None) -> Any:
        """Get business lookup with proper cache type."""
        return await self.get(f"business:{phone}", compute_func, "business_lookup")
    
    async def get_knowledge_base(self, business_id: str, query: str, 
                                compute_func: Optional[Callable] = None) -> Any:
        """Get knowledge base query with proper cache type."""
        # Use hash of query for key to handle long queries
        query_hash = hashlib.md5(query.encode()).hexdigest()
        key = f"kb:{business_id}:{query_hash}"
        return await self.get(key, compute_func, "knowledge_base")
    
    async def invalidate_business(self, phone: str):
        """Invalidate all cache entries for a business."""
        await self.delete(f"business:{phone}", "business_lookup")
        # Also clear any related knowledge base cache if needed
        logger.info("Invalidated business cache", phone=phone)
    
    async def invalidate_knowledge_base(self, business_id: str):
        """Invalidate all knowledge base cache for a business."""
        await self.clear_pattern(f"kb:{business_id}:*", "knowledge_base")
        logger.info("Invalidated knowledge base cache", business_id=business_id)