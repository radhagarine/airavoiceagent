
"""Redis cache implementation using redis-py for Python 3.12 compatibility."""

import json
import pickle
import gzip
import asyncio
import random
from typing import Any, Optional, Dict, Callable
import logging

# Redis imports - using redis-py which is more stable
import redis
import redis.asyncio as redis_async

from monitoring_system import logger, monitor_performance
from .config import CacheConfig
from .stats import CacheStats
from .circuit_breaker import CircuitBreaker


class RedisClusterCache:
    """Redis cache implementation using redis-py with monitoring and resilience."""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.redis: Optional[redis_async.Redis] = None
        self._connected = False
        self.circuit_breaker = CircuitBreaker(
            threshold=config.circuit_breaker_threshold,
            timeout=config.circuit_breaker_timeout,
            name="redis_cache"
        )
        self._stats: Optional[CacheStats] = None
        self._is_cluster = False
    
    def set_stats(self, stats: CacheStats):
        """Set stats reference for recording metrics."""
        self._stats = stats
    
    async def connect(self):
        """Connect to Redis using redis-py async client."""
        try:
            # Get the first Redis node configuration
            node = self.config.redis_nodes[0]
            host = node['host']
            port = node['port']
            
            # Create connection parameters
            connection_kwargs = {
                'host': host,
                'port': port,
                'decode_responses': False,
                'socket_timeout': 5,
                'socket_connect_timeout': 5,
                'retry_on_timeout': True,
                'health_check_interval': 30,
            }
            
            # Add password if configured
            if self.config.redis_password:
                connection_kwargs['password'] = self.config.redis_password
            
            # Create async Redis connection
            self.redis = redis_async.Redis(**connection_kwargs)
            
            # Test connection
            await self.redis.ping()
            self._connected = True
            
            logger.info("Connected to Redis", 
                       host=host, 
                       port=port, 
                       password_protected=bool(self.config.redis_password))
                       
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            self._connected = False
            if self._stats:
                self._stats.record_error("connection_error")
            raise
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Disconnected from Redis")
    
    def _get_cache_key(self, key: str, cache_type: str = "default") -> str:
        """Generate prefixed cache key."""
        return f"voice_bot:{cache_type}:{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value with optional compression."""
        # Use JSON for simple types, pickle for complex objects
        if isinstance(value, (str, int, float, bool, type(None))):
            data = json.dumps(value).encode('utf-8')
        else:
            data = pickle.dumps(value)
        
        # Compress if enabled and data is large enough
        if (self.config.compression_enabled and 
            len(data) > self.config.compression_threshold):
            data = b'compressed:' + gzip.compress(data)
            if self._stats:
                self._stats.record_compression_save()
        
        return data
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value with decompression."""
        try:
            # Check if compressed
            if data.startswith(b'compressed:'):
                data = gzip.decompress(data[11:])  # Remove 'compressed:' prefix
            
            # Try JSON first, then pickle
            try:
                return json.loads(data.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return pickle.loads(data)
                
        except Exception as e:
            logger.error("Failed to deserialize cache data", error=str(e))
            if self._stats:
                self._stats.record_error("deserialization_error")
            raise
    
    async def _with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with retry logic and exponential backoff."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self.circuit_breaker.protect():
                    return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if self._stats:
                    self._stats.record_error(f"retry_attempt_{attempt}")
                
                if attempt < self.config.max_retries:
                    # Exponential backoff with jitter
                    delay = self.config.retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                    await asyncio.sleep(delay)
                    logger.debug("Retrying cache operation", 
                               attempt=attempt + 1, 
                               delay=delay,
                               error=str(e))
        
        # All retries failed
        if self._stats:
            self._stats.record_circuit_breaker_trip()
        logger.error("Cache operation failed after retries", 
                    error=str(last_exception),
                    max_retries=self.config.max_retries)
        raise last_exception
    
    @monitor_performance("redis_get")
    async def get(self, key: str, cache_type: str = "default") -> Optional[Any]:
        """Get value from Redis cache."""
        if not self._connected:
            logger.debug("Redis not connected, skipping get operation")
            return None
        
        full_key = self._get_cache_key(key, cache_type)
        
        try:
            async def _get_operation():
                return await self.redis.get(full_key)
            
            data = await self._with_retry(_get_operation)
            
            if data is None:
                return None
            
            value = self._deserialize(data)
            logger.debug("Redis cache hit", key=key, cache_type=cache_type)
            return value
            
        except Exception as e:
            logger.error("Error getting from Redis cache", 
                        key=key, 
                        cache_type=cache_type, 
                        error=str(e))
            if self._stats:
                self._stats.record_error("redis_get_error")
            return None
    
    @monitor_performance("redis_set")
    async def set(self, key: str, value: Any, ttl: Optional[int] = None, 
                  cache_type: str = "default") -> bool:
        """Set value in Redis cache."""
        if not self._connected:
            logger.debug("Redis not connected, skipping set operation")
            return False
        
        full_key = self._get_cache_key(key, cache_type)
        ttl = ttl or self.config.l2_default_ttl
        
        try:
            data = self._serialize(value)
            
            async def _set_operation():
                await self.redis.setex(full_key, ttl, data)
            
            await self._with_retry(_set_operation)
            logger.debug("Redis cache set", key=key, cache_type=cache_type, ttl=ttl)
            return True
            
        except Exception as e:
            logger.error("Error setting in Redis cache", 
                        key=key, 
                        cache_type=cache_type, 
                        error=str(e))
            if self._stats:
                self._stats.record_error("redis_set_error")
            return False
    
    async def delete(self, key: str, cache_type: str = "default") -> bool:
        """Delete key from Redis cache."""
        if not self._connected:
            return False
        
        full_key = self._get_cache_key(key, cache_type)
        
        try:
            async def _delete_operation():
                return await self.redis.delete(full_key)
            
            result = await self._with_retry(_delete_operation)
            logger.debug("Redis cache delete", key=key, cache_type=cache_type)
            return result > 0
            
        except Exception as e:
            logger.error("Error deleting from Redis cache", 
                        key=key, 
                        cache_type=cache_type, 
                        error=str(e))
            return False
    
    async def exists(self, key: str, cache_type: str = "default") -> bool:
        """Check if key exists in Redis cache."""
        if not self._connected:
            return False
        
        full_key = self._get_cache_key(key, cache_type)
        
        try:
            async def _exists_operation():
                return await self.redis.exists(full_key)
            
            result = await self._with_retry(_exists_operation)
            return result > 0
            
        except Exception as e:
            logger.error("Error checking existence in Redis cache", 
                        key=key, 
                        cache_type=cache_type, 
                        error=str(e))
            return False
    
    async def clear_pattern(self, pattern: str, cache_type: str = "default") -> int:
        """Clear all keys matching pattern."""
        if not self._connected:
            return 0
        
        full_pattern = self._get_cache_key(pattern, cache_type)
        
        try:
            keys = []
            
            async def _scan_operation():
                # Use scan_iter to get all matching keys
                cursor = 0
                while True:
                    cursor, partial_keys = await self.redis.scan(cursor, match=full_pattern, count=100)
                    keys.extend(partial_keys)
                    if cursor == 0:
                        break
            
            await self._with_retry(_scan_operation)
            
            if keys:
                async def _delete_operation():
                    return await self.redis.delete(*keys)
                
                deleted = await self._with_retry(_delete_operation)
                logger.info("Cleared cache pattern", 
                          pattern=pattern, 
                          cache_type=cache_type,
                          deleted=deleted)
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error("Error clearing pattern from Redis cache", 
                        pattern=pattern, 
                        cache_type=cache_type,
                        error=str(e))
            return 0
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Redis connection."""
        if not self._connected:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": "Not connected"
            }
        
        try:
            # Simple ping test
            start_time = asyncio.get_event_loop().time()
            await self.redis.ping()
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Get some basic info
            info = await self.redis.info()
            
            return {
                "status": "healthy",
                "connected": True,
                "latency_ms": round(latency, 2),
                "circuit_breaker": self.circuit_breaker.get_status(),
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "is_cluster": self._is_cluster
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": self._connected,
                "error": str(e),
                "circuit_breaker": self.circuit_breaker.get_status()
            }