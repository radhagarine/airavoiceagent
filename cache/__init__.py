"""Cache package for voice bot application."""

from .config import CacheConfig
from .multi_level_cache import MultiLevelCache
from .manager import (
    initialize_cache,
    shutdown_cache,
    get_cache_instance,
    is_cache_initialized,
    get_cache_health,
    get_cache_stats,
    CacheLifecycle,
    warm_business_lookups,
    warm_knowledge_base_queries
)
from .decorators import (
    cache_result,
    cache_business_lookup,
    cache_knowledge_base,
    invalidate_cache_pattern,
    invalidate_business_cache,
    invalidate_knowledge_base_cache,
    CacheContext,
    cache_performance_monitor,
    generate_business_key,
    generate_knowledge_base_key,
    generate_daily_room_key,
    bulk_invalidate,
    bulk_warm_cache,
    get_cache_statistics
)

__all__ = [
    # Core classes
    'CacheConfig',
    'MultiLevelCache',
    'CacheLifecycle',
    
    # Manager functions
    'initialize_cache',
    'shutdown_cache',
    'get_cache_instance',
    'is_cache_initialized',
    'get_cache_health',
    'get_cache_stats',
    
    # Decorators and utilities
    'cache_result',
    'cache_business_lookup',
    'cache_knowledge_base',
    'invalidate_cache_pattern',
    'invalidate_business_cache',
    'invalidate_knowledge_base_cache',
    'CacheContext',
    'cache_performance_monitor',
    
    # Key generators
    'generate_business_key',
    'generate_knowledge_base_key',
    'generate_daily_room_key',
    
    # Bulk operations
    'bulk_invalidate',
    'bulk_warm_cache',
    
    # Warming functions
    'warm_business_lookups',
    'warm_knowledge_base_queries',
    
    # Statistics
    'get_cache_statistics'
]

# Version information
__version__ = "1.0.0"
__author__ = "Voice Bot Team"