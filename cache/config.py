
"""Cache configuration module."""

import os
from dataclasses import dataclass
from typing import List, Dict, Union, Optional


@dataclass
class CacheConfig:
    """Configuration for cache settings."""
    # L1 Cache (In-Memory) - Minimal for your budget
    l1_max_size: int = 500  # Reduced from 1000
    l1_default_ttl: int = 300  # 5 minutes
    
    # L2 Cache (Redis - single node with aioredis 2.0.1)
    redis_nodes: List[Dict[str, Union[str, int]]] = None
    redis_password: Optional[str] = None
    
    # TTL Configuration - Configurable as requested
    business_lookup_ttl: int = 1800  # 30 minutes (business info is stable)
    knowledge_base_ttl: int = 3600   # 1 hour (knowledge base is stable)
    l2_default_ttl: int = 3600
    
    # Performance settings
    compression_enabled: bool = True
    compression_threshold: int = 1024  # Compress if > 1KB
    
    # Retry and circuit breaker settings
    max_retries: int = 2
    retry_delay: float = 0.1
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 30
    
    # Cache warming
    enable_warming: bool = True
    warming_concurrency: int = 4
    
    @classmethod
    def from_env(cls) -> 'CacheConfig':
        """Create config from environment variables."""
        # Default Redis nodes - use single node for aioredis 2.0.1 compatibility
        # The cache will connect to the first node, treating the Redis cluster as a single node
        default_nodes = [
            {"host": "localhost", "port": 7001},  # Primary Redis node
            {"host": "localhost", "port": 7002},  # Backup (not used in single node mode)
            {"host": "localhost", "port": 7003}   # Backup (not used in single node mode)
        ]
        
        # Override with environment if specified
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "7001"))
        
        if redis_host != "localhost" or redis_port != 7001:
            default_nodes = [{"host": redis_host, "port": redis_port}]
        
        return cls(
            l1_max_size=int(os.getenv("CACHE_L1_SIZE", "500")),
            l1_default_ttl=int(os.getenv("CACHE_L1_TTL", "300")),
            redis_nodes=default_nodes,
            redis_password=os.getenv("REDIS_PASSWORD"),
            business_lookup_ttl=int(os.getenv("CACHE_BUSINESS_TTL", "1800")),
            knowledge_base_ttl=int(os.getenv("CACHE_KNOWLEDGE_TTL", "3600")),
            l2_default_ttl=int(os.getenv("CACHE_L2_TTL", "3600")),
            compression_enabled=os.getenv("CACHE_COMPRESSION", "true").lower() == "true",
            max_retries=int(os.getenv("CACHE_MAX_RETRIES", "2")),
            retry_delay=float(os.getenv("CACHE_RETRY_DELAY", "0.1")),
            circuit_breaker_threshold=int(os.getenv("CACHE_CB_THRESHOLD", "5")),
            circuit_breaker_timeout=int(os.getenv("CACHE_CB_TIMEOUT", "30")),
            enable_warming=os.getenv("CACHE_WARMING", "true").lower() == "true"
        )