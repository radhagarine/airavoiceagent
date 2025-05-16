"""Cache warming strategies for preloading frequently accessed data."""

import asyncio
import time
from typing import List, Tuple, Callable, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from monitoring_system import logger
from .config import CacheConfig


class CacheWarmer:
    """Handles cache warming strategies with monitoring."""
    
    def __init__(self, config: CacheConfig, cache_instance):
        self.config = config
        self.cache = cache_instance
        self.warming_executor = ThreadPoolExecutor(
            max_workers=config.warming_concurrency,
            thread_name_prefix="cache_warmer"
        )
        self.warming_tasks: Dict[str, asyncio.Task] = {}
        self._stats = None
    
    def set_stats(self, stats):
        """Set stats reference for recording metrics."""
        self._stats = stats
    
    async def warm_business_lookups(self, business_phones: List[str]):
        """Warm cache with business lookup data."""
        if not self.config.enable_warming:
            logger.info("Cache warming disabled, skipping business lookups")
            return
        
        logger.info("Starting business lookup warming", count=len(business_phones))
        
        # Import here to avoid circular import
        from utils.supabase_helper import get_business_by_phone
        
        async def warm_business(phone: str):
            try:
                cache_key = f"business:{phone}"
                
                # Check if already cached
                existing = await self.cache.get(cache_key, cache_type="business_lookup")
                if existing:
                    logger.debug("Business already cached, skipping", phone=phone)
                    return
                
                # Compute and cache
                def get_business():
                    return get_business_by_phone(phone)
                
                await self.cache.get(cache_key, get_business, cache_type="business_lookup")
                
                if self._stats:
                    self._stats.record_warming_operation()
                
                logger.debug("Business lookup warmed", phone=phone)
                
            except Exception as e:
                logger.error("Business warming failed", phone=phone, error=str(e))
        
        # Execute warming tasks
        tasks = []
        for phone in business_phones:
            if phone not in self.warming_tasks:
                task = asyncio.create_task(warm_business(phone))
                tasks.append(task)
                self.warming_tasks[phone] = task
        
        # Wait for completion
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up completed tasks
        for phone in business_phones:
            self.warming_tasks.pop(phone, None)
        
        logger.info("Business lookup warming complete")
    
    async def warm_knowledge_base_queries(self, common_queries: List[Tuple[str, str]]):
        """
        Warm cache with common knowledge base queries.
        
        Args:
            common_queries: List of (business_id, query) tuples
        """
        if not self.config.enable_warming:
            logger.info("Cache warming disabled, skipping knowledge base queries")
            return
        
        logger.info("Starting knowledge base warming", count=len(common_queries))
        
        async def warm_knowledge_query(business_id: str, query: str):
            try:
                cache_key = f"kb:{business_id}:{hash(query)}"
                
                # Check if already cached
                existing = await self.cache.get(cache_key, cache_type="knowledge_base")
                if existing:
                    logger.debug("Knowledge base query already cached, skipping", 
                               business_id=business_id, query=query[:50])
                    return
                
                # Import here to avoid circular import
                try:
                    from utils.knowledge_base import KnowledgeBase
                    kb = KnowledgeBase()
                    
                    # Check if business has knowledge base
                    if not kb.business_has_knowledge_base(business_id):
                        logger.debug("No knowledge base for business", business_id=business_id)
                        return
                    
                    # Define compute function
                    def query_knowledge_base():
                        return kb.query(business_id, query, top_k=3)
                    
                    # Cache the query result
                    await self.cache.get(cache_key, query_knowledge_base, cache_type="knowledge_base")
                    
                    if self._stats:
                        self._stats.record_warming_operation()
                    
                    logger.debug("Knowledge base query warmed", 
                               business_id=business_id, 
                               query=query[:50])
                
                except ImportError:
                    logger.warning("Knowledge base not available for warming")
                    return
                    
            except Exception as e:
                logger.error("Knowledge base warming failed", 
                           business_id=business_id, 
                           query=query[:50], 
                           error=str(e))
        
        # Execute warming tasks
        tasks = []
        for business_id, query in common_queries:
            task_key = f"{business_id}:{hash(query)}"
            if task_key not in self.warming_tasks:
                task = asyncio.create_task(warm_knowledge_query(business_id, query))
                tasks.append(task)
                self.warming_tasks[task_key] = task
        
        # Wait for completion
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up completed tasks
        for business_id, query in common_queries:
            task_key = f"{business_id}:{hash(query)}"
            self.warming_tasks.pop(task_key, None)
        
        logger.info("Knowledge base warming complete")
    
    async def warm_custom_data(self, warming_specs: List[Dict[str, Any]]):
        """
        Warm cache with custom data specifications.
        
        Args:
            warming_specs: List of dicts with keys:
                - 'key': cache key
                - 'compute_func': function to compute value
                - 'cache_type': type of cache
                - 'ttl': optional TTL override
        """
        if not self.config.enable_warming:
            logger.info("Cache warming disabled, skipping custom data")
            return
        
        logger.info("Starting custom data warming", count=len(warming_specs))
        
        async def warm_custom_item(spec: Dict[str, Any]):
            try:
                key = spec['key']
                compute_func = spec['compute_func']
                cache_type = spec.get('cache_type', 'default')
                ttl = spec.get('ttl')
                
                # Check if already cached
                existing = await self.cache.get(key, cache_type=cache_type)
                if existing:
                    logger.debug("Custom item already cached, skipping", key=key)
                    return
                
                # Cache with custom TTL if provided
                if ttl:
                    # We need to handle TTL override differently
                    # This is a simplified approach - in production you might want
                    # to extend the cache interface to support TTL overrides
                    result = compute_func() if not asyncio.iscoroutinefunction(compute_func) else await compute_func()
                    await self.cache.set(key, result, cache_type=cache_type)
                else:
                    await self.cache.get(key, compute_func, cache_type=cache_type)
                
                if self._stats:
                    self._stats.record_warming_operation()
                
                logger.debug("Custom item warmed", key=key, cache_type=cache_type)
                
            except Exception as e:
                logger.error("Custom warming failed", key=spec.get('key', 'unknown'), error=str(e))
        
        # Execute warming tasks
        tasks = []
        for spec in warming_specs:
            key = spec.get('key', f"custom_{time.time()}")
            if key not in self.warming_tasks:
                task = asyncio.create_task(warm_custom_item(spec))
                tasks.append(task)
                self.warming_tasks[key] = task
        
        # Wait for completion
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up completed tasks
        for spec in warming_specs:
            key = spec.get('key', f"custom_{time.time()}")
            self.warming_tasks.pop(key, None)
        
        logger.info("Custom data warming complete")
    
    async def schedule_periodic_warming(self, interval_hours: int = 6):
        """
        Schedule periodic cache warming for critical data.
        
        Args:
            interval_hours: Hours between warming cycles
        """
        logger.info("Starting periodic cache warming", interval_hours=interval_hours)
        
        while True:
            try:
                # Sleep for the specified interval
                await asyncio.sleep(interval_hours * 3600)
                
                # Perform warming operations
                logger.info("Starting periodic cache warming cycle")
                
                # Example: warm most common business lookups
                # You would customize this based on your analytics
                common_phones = await self._get_common_business_phones()
                if common_phones:
                    await self.warm_business_lookups(common_phones)
                
                # Example: warm common knowledge base queries
                common_kb_queries = await self._get_common_kb_queries()
                if common_kb_queries:
                    await self.warm_knowledge_base_queries(common_kb_queries)
                
                logger.info("Periodic cache warming cycle complete")
                
            except asyncio.CancelledError:
                logger.info("Periodic warming cancelled")
                break
            except Exception as e:
                logger.error("Error in periodic warming", error=str(e))
                # Continue the loop despite errors
    
    async def _get_common_business_phones(self) -> List[str]:
        """Get list of commonly accessed business phone numbers."""
        # This would typically query your analytics or logs
        # For now, return empty list - implement based on your needs
        return []
    
    async def _get_common_kb_queries(self) -> List[Tuple[str, str]]:
        """Get list of commonly accessed knowledge base queries."""
        # This would typically query your analytics or logs
        # For now, return empty list - implement based on your needs
        return []
    
    def cancel_all_warming_tasks(self):
        """Cancel all active warming tasks."""
        logger.info("Cancelling all warming tasks", count=len(self.warming_tasks))
        
        for task in self.warming_tasks.values():
            task.cancel()
        
        self.warming_tasks.clear()
    
    async def shutdown(self):
        """Shutdown the cache warmer."""
        self.cancel_all_warming_tasks()
        self.warming_executor.shutdown(wait=True)
        logger.info("Cache warmer shutdown complete")
    
    def get_warming_status(self) -> Dict[str, Any]:
        """Get current warming status for monitoring."""
        return {
            "enabled": self.config.enable_warming,
            "concurrency": self.config.warming_concurrency,
            "active_tasks": len(self.warming_tasks),
            "active_task_keys": list(self.warming_tasks.keys())[:10],  # Show first 10
            "executor_threads": len(self.warming_executor._threads) if hasattr(self.warming_executor, '_threads') else 0
        }