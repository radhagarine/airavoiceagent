"""Cache configuration module - Universal for single node and cluster."""

import os
from dataclasses import dataclass
from typing import List, Dict, Union, Optional


@dataclass
class CacheConfig:
    """Configuration for cache settings."""
    # L1 Cache (In-Memory)
    l1_max_size: int = 500
    l1_default_ttl: int = 300  # 5 minutes
    
    # L2 Cache (Redis)
    redis_nodes: List[Dict[str, Union[str, int]]] = None
    redis_password: Optional[str] = None
    
    # TTL Configuration
    business_lookup_ttl: int = 1800  # 30 minutes
    knowledge_base_ttl: int = 3600   # 1 hour
    l2_default_ttl: int = 3600
    
    # Performance settings
    compression_enabled: bool = True
    compression_threshold: int = 1024
    
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
        """Create config from environment variables with intelligent defaults."""
        
        # Detect Redis configuration strategy
        redis_host = os.getenv("REDIS_HOST")
        redis_port = os.getenv("REDIS_PORT")
        redis_cluster_nodes = os.getenv("REDIS_CLUSTER_NODES")
        
        # Build Redis nodes configuration
        if redis_cluster_nodes:
            # Explicit cluster nodes: "host1:port1,host2:port2,host3:port3"
            nodes = []
            for node_str in redis_cluster_nodes.split(','):
                host, port = node_str.strip().split(':')
                nodes.append({"host": host, "port": int(port)})
            redis_nodes = nodes
        elif redis_host and redis_port:
            # Single node specified
            redis_nodes = [{"host": redis_host, "port": int(redis_port)}]
        else:
            # Default multi-node setup (tries cluster, falls back to single)
            # Check if we're running in a context where Docker internal names work
            # This is a heuristic - if HOSTNAME contains 'docker' or we're in container
            is_docker_internal = (
                os.getenv('HOSTNAME', '').find('docker') >= 0 or
                os.getenv('DOCKER_CONTAINER') == 'true' or
                os.path.exists('/.dockerenv')
            )
            
            if is_docker_internal:
                # Use Docker internal hostnames
                redis_nodes = [
                    {"host": "redis-1", "port": 7001},
                    {"host": "redis-2", "port": 7002},
                    {"host": "redis-3", "port": 7003}
                ]
            else:
                # Use localhost (port mapping)
                redis_nodes = [
                    {"host": "localhost", "port": 7001},
                    {"host": "localhost", "port": 7002},
                    {"host": "localhost", "port": 7003}
                ]
        
        return cls(
            l1_max_size=int(os.getenv("CACHE_L1_SIZE", "500")),
            l1_default_ttl=int(os.getenv("CACHE_L1_TTL", "300")),
            redis_nodes=redis_nodes,
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