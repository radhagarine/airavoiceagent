"""Cache manager - Singleton pattern for global cache instance."""

import asyncio
from typing import Optional

from monitoring_system import logger
from .config import CacheConfig
from .multi_level_cache import MultiLevelCache


class CacheManager:
    """Singleton manager for the global cache instance."""
    
    _instance: Optional['CacheManager'] = None
    _cache: Optional[MultiLevelCache] = None
    _initialized: bool = False
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self, config: Optional[CacheConfig] = None):
        """Initialize the cache system."""
        async with self._lock:
            if self._initialized:
                logger.warning("Cache already initialized")
                return
            
            if config is None:
                config = CacheConfig.from_env()
            
            self._cache = MultiLevelCache(config)
            await self._cache.initialize()
            self._initialized = True
            
            logger.info("Cache manager initialized successfully")
    
    async def shutdown(self):
        """Shutdown the cache system."""
        async with self._lock:
            if self._cache and self._initialized:
                await self._cache.shutdown()
                self._cache = None
                self._initialized = False
                logger.info("Cache manager shutdown complete")
    
    def get_cache(self) -> Optional[MultiLevelCache]:
        """Get the cache instance if initialized."""
        return self._cache if self._initialized else None
    
    @property
    def is_initialized(self) -> bool:
        """Check if cache is initialized."""
        return self._initialized
    
    async def health_check(self) -> dict:
        """Perform health check on cache system."""
        if not self._initialized or not self._cache:
            return {
                "status": "unhealthy",
                "error": "Cache not initialized"
            }
        
        return await self._cache.health_check()
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        if not self._initialized or not self._cache:
            return {
                "error": "Cache not initialized"
            }
        
        return self._cache.get_stats()


# Global cache manager instance
_cache_manager = CacheManager()


async def initialize_cache(config: Optional[CacheConfig] = None):
    """Initialize the global cache system."""
    await _cache_manager.initialize(config)


async def shutdown_cache():
    """Shutdown the global cache system."""
    await _cache_manager.shutdown()


def get_cache_instance() -> Optional[MultiLevelCache]:
    """Get the global cache instance."""
    return _cache_manager.get_cache()


def is_cache_initialized() -> bool:
    """Check if cache is initialized."""
    return _cache_manager.is_initialized


async def get_cache_health() -> dict:
    """Get cache health status."""
    return await _cache_manager.health_check()


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return _cache_manager.get_stats()


# Context manager for cache lifecycle
class CacheLifecycle:
    """Context manager for cache lifecycle management."""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config
    
    async def __aenter__(self):
        await initialize_cache(self.config)
        return get_cache_instance()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await shutdown_cache()
        if exc_type:
            logger.error("Exception during cache lifecycle", 
                        exception=str(exc_val))


# Convenience functions for common operations
async def warm_business_lookups(phone_numbers: list):
    """Warm cache with business lookups."""
    cache = get_cache_instance()
    if cache:
        await cache.warmer.warm_business_lookups(phone_numbers)
    else:
        logger.warning("Cache not available for warming")


async def warm_knowledge_base_queries(queries: list):
    """Warm cache with knowledge base queries."""
    cache = get_cache_instance()
    if cache:
        await cache.warmer.warm_knowledge_base_queries(queries)
    else:
        logger.warning("Cache not available for warming")