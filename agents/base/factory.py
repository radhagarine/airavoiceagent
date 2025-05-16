"""Agent factory for creating and managing business-specific agents."""

import time
from typing import Dict, Optional, Type
from concurrent.futures import ThreadPoolExecutor

from monitoring_system import logger, monitor_performance, metrics
from ..base.agent import BaseAgent
from ..types.restaurant import RestaurantAgent
from ..types.retail import RetailAgent
from ..types.service import ServiceAgent
from ..types.default import DefaultAgent


class AgentFactory:
    """Factory for creating and caching business-specific agents."""
    
    # Agent type registry
    _agent_classes: Dict[str, Type[BaseAgent]] = {
        'restaurant': RestaurantAgent,
        'retail': RetailAgent,
        'service': ServiceAgent
    }
    
    # Cache for agent instances (one per business type)
    _agent_cache: Dict[str, BaseAgent] = {}
    
    # Statistics
    _stats = {
        'agents_created': 0,
        'cache_hits': 0,
        'cache_misses': 0,
        'factory_errors': 0
    }
    
    @classmethod
    @monitor_performance("agent_factory_get")
    def get_agent_for_business(cls, business_type: str) -> BaseAgent:
        """
        Get agent for business type with caching.
        
        Args:
            business_type: Type of business (restaurant, retail, service)
            
        Returns:
            Cached or newly created agent instance
        """
        start_time = time.time()
        
        # Normalize business type
        business_type = business_type.lower().strip() if business_type else 'default'
        
        logger.debug("Agent factory request", business_type=business_type)
        
        try:
            # Check cache first
            if business_type in cls._agent_cache:
                cls._stats['cache_hits'] += 1
                agent = cls._agent_cache[business_type]
                logger.debug("Agent cache hit", 
                           business_type=business_type,
                           agent_id=agent.agent_id)
                return agent
            
            # Cache miss - create new agent
            cls._stats['cache_misses'] += 1
            logger.info("Creating new agent", business_type=business_type)
            
            # Get agent class
            agent_class = cls._agent_classes.get(business_type, DefaultAgent)
            
            # Create agent instance
            agent = agent_class(business_type)
            
            # Cache the agent
            cls._agent_cache[business_type] = agent
            cls._stats['agents_created'] += 1
            
            # Record metrics
            metrics.increment_counter(
                'agent_created_total',
                labels={'business_type': business_type}
            )
            
            duration = time.time() - start_time
            metrics.observe_histogram(
                'agent_creation_duration_seconds',
                duration,
                labels={'business_type': business_type}
            )
            
            logger.info("Agent created and cached",
                       business_type=business_type,
                       agent_id=agent.agent_id,
                       creation_time=duration)
            
            return agent
            
        except Exception as e:
            cls._stats['factory_errors'] += 1
            logger.error("Agent factory error",
                        business_type=business_type,
                        error=str(e))
            
            # Fallback to default agent
            if business_type != 'default':
                logger.warning("Falling back to default agent")
                return cls.get_agent_for_business('default')
            
            # If default agent creation fails, create basic fallback
            return DefaultAgent('default')
    
    @classmethod
    def register_agent_type(cls, business_type: str, agent_class: Type[BaseAgent]):
        """
        Register a new agent type.
        
        Args:
            business_type: Name of the business type
            agent_class: Agent class to register
        """
        cls._agent_classes[business_type.lower()] = agent_class
        logger.info("Agent type registered", 
                   business_type=business_type,
                   agent_class=agent_class.__name__)
    
    @classmethod
    def get_cached_agents(cls) -> Dict[str, BaseAgent]:
        """Get all cached agent instances."""
        return cls._agent_cache.copy()
    
    @classmethod
    def clear_cache(cls, business_type: Optional[str] = None):
        """
        Clear agent cache.
        
        Args:
            business_type: Specific type to clear, or None for all
        """
        if business_type:
            if business_type in cls._agent_cache:
                del cls._agent_cache[business_type]
                logger.info("Agent cache cleared", business_type=business_type)
        else:
            cls._agent_cache.clear()
            logger.info("All agent cache cleared")
    
    @classmethod
    def get_factory_stats(cls) -> Dict:
        """Get factory statistics."""
        total_requests = cls._stats['cache_hits'] + cls._stats['cache_misses']
        cache_hit_rate = (
            cls._stats['cache_hits'] / total_requests * 100 
            if total_requests > 0 else 0
        )
        
        return {
            'statistics': cls._stats.copy(),
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'cached_agents': list(cls._agent_cache.keys()),
            'registered_types': list(cls._agent_classes.keys()),
            'total_agents_cached': len(cls._agent_cache)
        }
    
    @classmethod
    async def health_check_all_agents(cls) -> Dict:
        """Perform health check on all cached agents."""
        health_results = {}
        
        for business_type, agent in cls._agent_cache.items():
            try:
                health_results[business_type] = await agent.health_check()
            except Exception as e:
                health_results[business_type] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
        
        overall_status = 'healthy' if all(
            result.get('status') == 'healthy' 
            for result in health_results.values()
        ) else 'degraded'
        
        return {
            'overall_status': overall_status,
            'agents': health_results,
            'factory_stats': cls.get_factory_stats()
        }