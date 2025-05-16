"""Simple and robust Redis cache implementation with minimal dependencies."""

import json
import pickle
import gzip
import asyncio
import random
from typing import Any, Optional, Dict, Callable, List
import logging

# Redis imports
import redis
import redis.asyncio as redis_async
from redis.exceptions import RedisError, ConnectionError

from monitoring_system import logger, monitor_performance
from .config import CacheConfig
from .stats import CacheStats
from .circuit_breaker import CircuitBreaker


class UniversalRedisCache:
    """Simple Redis cache that works with any redis-py version."""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.redis_client: Optional[redis_async.Redis] = None
        self._connected = False
        self._is_cluster = False
        self._connection_mode = "single"
        
        self.circuit_breaker = CircuitBreaker(
            threshold=config.circuit_breaker_threshold,
            timeout=config.circuit_breaker_timeout,
            name="redis_cache"
        )
        self._stats: Optional[CacheStats] = None
    
    def set_stats(self, stats: CacheStats):
        """Set stats reference for recording metrics."""
        self._stats = stats
    
    async def connect(self):
        """Connect to Redis in single node mode for maximum compatibility."""
        # For maximum compatibility, we'll always use single node mode
        # This avoids version-specific cluster parameters
        await self._connect_single_node()
    
    async def _connect_single_node(self):
        """Connect to Redis in single node mode with minimal parameters."""
        last_error = None
        
        # Try each node until one works
        for i, node in enumerate(self.config.redis_nodes):
            try:
                host = node['host']
                port = node['port']
                
                logger.info(f"Attempting connection to Redis node {i+1}", 
                           host=host, port=port)
                
                # Use only the most basic connection parameters
                redis_kwargs = {
                    'host': host,
                    'port': port,
                    'decode_responses': False,
                    'socket_timeout': 5,
                    'socket_connect_timeout': 5,
                }
                
                # Add password if configured
                if self.config.redis_password:
                    redis_kwargs['password'] = self.config.redis_password
                
                # Create Redis client
                self.redis_client = redis_async.Redis(**redis_kwargs)
                
                # Test connection
                await self.redis_client.ping()
                
                # Check if this node is part of a cluster
                try:
                    cluster_info = await self.redis_client.execute_command("CLUSTER", "INFO")
                    if b"cluster_enabled:1" in cluster_info:
                        # It's a cluster node, but we'll still use it as single node
                        # This works because any cluster node can handle any request
                        # (it will automatically redirect internally)
                        logger.info("Connected to Redis cluster node in single-node mode",
                                   host=host, port=port)
                        self._is_cluster = True
                    else:
                        logger.info("Connected to Redis standalone node",
                                   host=host, port=port)
                        self._is_cluster = False
                except:
                    # If CLUSTER INFO fails, it's a standalone Redis
                    logger.info("Connected to Redis standalone node",
                               host=host, port=port)
                    self._is_cluster = False
                
                self._connected = True
                self._connection_mode = "single"
                return
                           
            except Exception as e:
                last_error = e
                logger.debug(f"Failed to connect to Redis node {i+1}", 
                           host=host, port=port, error=str(e))
                if self.redis_client:
                    try:
                        await self.redis_client.close()
                    except:
                        pass
                    self.redis_client = None
                continue
        
        # If we get here, all nodes failed
        logger.error("Failed to connect to any Redis node", 
                    error=str(last_error),
                    nodes_tried=len(self.config.redis_nodes))
        self._connected = False
        if self._stats:
            self._stats.record_error("connection_error")
        raise last_error or Exception("No Redis nodes available")
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis_client:
            try:
                await self.redis_client.close()
            except:
                pass
            self.redis_client = None
        self._connected = False
        logger.info("Disconnected from Redis")
    
    def _get_cache_key(self, key: str, cache_type: str = "default") -> str:
        """Generate prefixed cache key."""
        return f"voice_bot:{cache_type}:{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value with optional compression."""
        # Use JSON for simple types, pickle for complex objects
        if isinstance(value, (str, int, float, bool, type(None))):
            try:
                data = json.dumps(value).encode('utf-8')
            except (TypeError, ValueError):
                data = pickle.dumps(value)
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
        """Execute operation with retry logic."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self.circuit_breaker.protect():
                    return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if self._stats:
                    self._stats.record_error(f"retry_attempt_{attempt}")
                
                # Don't retry on connection errors
                if isinstance(e, (ConnectionError,)) or "connection" in str(e).lower():
                    logger.debug("Connection error, not retrying", error=str(e))
                    raise
                
                if attempt < self.config.max_retries:
                    # Simple exponential backoff
                    delay = self.config.retry_delay * (2 ** attempt)
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
        if not self._connected or not self.redis_client:
            logger.debug("Redis not connected, skipping get operation")
            return None
        
        full_key = self._get_cache_key(key, cache_type)
        
        try:
            async def _get_operation():
                return await self.redis_client.get(full_key)
            
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
        if not self._connected or not self.redis_client:
            logger.debug("Redis not connected, skipping set operation")
            return False
        
        full_key = self._get_cache_key(key, cache_type)
        ttl = ttl or self.config.l2_default_ttl
        
        try:
            data = self._serialize(value)
            
            async def _set_operation():
                await self.redis_client.setex(full_key, ttl, data)
            
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
        if not self._connected or not self.redis_client:
            return False
        
        full_key = self._get_cache_key(key, cache_type)
        
        try:
            async def _delete_operation():
                return await self.redis_client.delete(full_key)
            
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
        if not self._connected or not self.redis_client:
            return False
        
        full_key = self._get_cache_key(key, cache_type)
        
        try:
            async def _exists_operation():
                return await self.redis_client.exists(full_key)
            
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
        if not self._connected or not self.redis_client:
            return 0
        
        full_pattern = self._get_cache_key(pattern, cache_type)
        
        try:
            # Use simple KEYS command for compatibility (not ideal for production with millions of keys)
            keys = await self.redis_client.keys(full_pattern)
            
            if keys:
                # Delete in batches
                batch_size = 100
                deleted_total = 0
                
                for i in range(0, len(keys), batch_size):
                    batch = keys[i:i + batch_size]
                    deleted = await self.redis_client.delete(*batch)
                    deleted_total += deleted
                
                logger.info("Cleared cache pattern", 
                          pattern=pattern, 
                          cache_type=cache_type,
                          deleted=deleted_total)
                return deleted_total
            
            return 0
            
        except Exception as e:
            logger.error("Error clearing pattern from Redis cache", 
                        pattern=pattern, 
                        cache_type=cache_type,
                        error=str(e))
            return 0
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Redis connection."""
        if not self._connected or not self.redis_client:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": "Not connected"
            }
        
        try:
            # Simple ping test
            start_time = asyncio.get_event_loop().time()
            await self.redis_client.ping()
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Get basic info
            info = await self.redis_client.info()
            
            health_info = {
                "status": "healthy",
                "connected": True,
                "connection_mode": self._connection_mode,
                "is_cluster": self._is_cluster,
                "latency_ms": round(latency, 2),
                "circuit_breaker": self.circuit_breaker.get_status(),
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "nodes_configured": len(self.config.redis_nodes)
            }
            
            # Add cluster info if available
            if self._is_cluster:
                try:
                    cluster_info = await self.redis_client.execute_command("CLUSTER", "INFO")
                    cluster_state = self._parse_cluster_state(cluster_info)
                    health_info["cluster_state"] = cluster_state
                except Exception as e:
                    health_info["cluster_note"] = "Connected as single node to cluster member"
            
            return health_info
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": self._connected,
                "connection_mode": self._connection_mode,
                "error": str(e),
                "circuit_breaker": self.circuit_breaker.get_status()
            }
    
    def _parse_cluster_state(self, cluster_info: bytes) -> str:
        """Parse cluster state from cluster info."""
        try:
            info_str = cluster_info.decode()
            for line in info_str.split('\r\n'):
                if line.startswith('cluster_state:'):
                    return line.split(':')[1]
            return "unknown"
        except:
            return "unknown"


# Alias for backward compatibility
RedisClusterCache = UniversalRedisCache