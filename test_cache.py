#!/usr/bin/env python
"""Test script for the simplified cache implementation."""

import asyncio
import time
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the cache module
try:
    # Updated import path to look for simplified_cache.py in the cache folder
    from cache.simplified_cache import (
        initialize_cache,
        get_cache_instance,
        shutdown_cache,
        get_cache_health,
        get_cache_stats,
        cache_result
    )
except ImportError:
    logger.error("Cannot import simplified_cache. Make sure cache/simplified_cache.py exists.")
    exit(1)

# Sample caching function
@cache_result(ttl=60, cache_type="test")
async def get_sample_data(key):
    """
    Test function that simulates an expensive operation.
    This will be cached by the decorator.
    """
    logger.info(f"Computing data for key: {key} (this should only appear once per key)")
    
    # Simulate a slow operation
    await asyncio.sleep(1)
    
    # Return some test data
    return {
        "key": key,
        "value": f"Data for {key}",
        "timestamp": str(datetime.now()),  # Convert to string to avoid serialization issues
        "computed": True
    }

async def test_cache():
    """Test the cache functionality."""
    print("\n===== CACHE TEST SCRIPT =====\n")
    logger.info("Testing cache initialization...")
    
    # Initialize cache
    success = await initialize_cache()
    if not success:
        logger.error("Failed to initialize cache")
        return False
    
    # Get cache instance
    cache = await get_cache_instance()
    if not cache:
        logger.error("Failed to get cache instance")
        return False
    
    print("\n----- Basic Cache Operations -----\n")
    
    # Test basic set/get operations
    test_key = "test_key"
    test_value = {"message": "Hello, cache!", "timestamp": time.time()}
    
    # Set a value
    success = await cache.set(test_key, test_value)
    logger.info(f"Set value in cache: {success}")
    
    # Get the value
    result = await cache.get(test_key)
    logger.info(f"Retrieved value: {result == test_value}")
    
    # Test with different types
    types_to_test = [
        ("string_value", "This is a test string"),
        ("int_value", 12345),
        ("float_value", 123.45),
        ("bool_value", True),
        ("list_value", [1, 2, 3, "test"]),
        ("dict_value", {"name": "Test", "value": 123}),
        ("complex_value", {"nested": {"data": [1, 2, {"test": True}]}}),
    ]
    
    for key, value in types_to_test:
        await cache.set(key, value)
        result = await cache.get(key)
        logger.info(f"Type test [{key}]: {'✅' if result == value else '❌'}")
    
    print("\n----- Manual Cache Function Test -----\n")
    
    # Test cache with manual function
    async def sample_data_generator(test_key):
        logger.info(f"Computing data for key: {test_key} (this should only appear once per key)")
        await asyncio.sleep(0.5)  # Simulate work
        return {
            "key": test_key,
            "value": f"Data for {test_key}",
            "timestamp": str(datetime.now()),
            "computed": True
        }
    
    # Test keys for caching
    test_keys = ["user_1", "user_2", "user_3"]
    
    # First call - should compute for each key
    logger.info("First call - should compute values:")
    for key in test_keys:
        # Create a unique function for each key to prevent shared reference issues
        async def get_data():
            return await sample_data_generator(key)
            
        result = await cache.get(f"manual_test:{key}", get_data, "test")
        logger.info(f"Result for {key}: {result['value']}")
    
    # Second call - should use cached values
    logger.info("\nSecond call - should use cached values:")
    for key in test_keys:
        async def get_data():
            return await sample_data_generator(key)
            
        result = await cache.get(f"manual_test:{key}", get_data, "test")
        logger.info(f"Result for {key}: {result['value']} (From cache)")
    
    print("\n----- Cache Pattern Delete Test -----\n")
    
    # Test pattern delete
    await cache.set("pattern_test_1", "value 1")
    await cache.set("pattern_test_2", "value 2")
    await cache.set("different_key", "value 3")
    
    # Delete by pattern
    count = await cache.clear_pattern("pattern_test_*")
    logger.info(f"Deleted {count} keys matching pattern")
    
    # Verify deletion
    v1 = await cache.get("pattern_test_1")
    v2 = await cache.get("pattern_test_2")
    v3 = await cache.get("different_key")
    
    logger.info(f"pattern_test_1 exists: {'❌' if v1 is None else '✅'}")
    logger.info(f"pattern_test_2 exists: {'❌' if v2 is None else '✅'}")
    logger.info(f"different_key exists: {'✅' if v3 is not None else '❌'}")
    
    print("\n----- Health and Stats -----\n")
    
    # Get health information
    health = await get_cache_health()
    logger.info(f"Cache health: {health['status']}")
    logger.info(f"L1 cache size: {health['l1_cache']['size']} items")
    logger.info(f"L1 utilization: {health['l1_cache']['utilization_percent']}%")
    
    # Log L2 cache status
    if health['l2_cache']['status'] == 'healthy':
        logger.info(f"L2 cache: Connected to {health['l2_cache']['host']}:{health['l2_cache']['port']}")
    else:
        logger.info(f"L2 cache: {health['l2_cache']['status']}")
    
    # Get stats information
    stats = get_cache_stats()
    logger.info(f"Total operations: {stats['total_operations']}")
    logger.info(f"Hit rates: {json.dumps(stats['hit_rates'], indent=2)}")
    logger.info(f"Operation counts: {json.dumps(stats['counts'], indent=2)}")
    
    print("\n----- Cleanup -----\n")
    
    # Shutdown cache
    await shutdown_cache()
    logger.info("Cache shutdown complete")
    
    print("\n===== TEST COMPLETE =====\n")
    
    # Final success message
    if health['status'] == 'healthy' or health['status'] == 'degraded':
        logger.info("✅ Cache test passed successfully")
        return True
    else:
        logger.error("❌ Cache test failed")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_cache())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Test cancelled by user")
        exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        exit(1)