"""Agent lifecycle management for initialization and cleanup."""

import asyncio
import atexit
from typing import Dict, Optional, Any
from contextlib import asynccontextmanager

from monitoring_system import logger, metrics
from .registry import AgentRegistry
from .factory import AgentFactory
from ..types.restaurant import RestaurantAgent
from ..types.retail import RetailAgent
from ..types.service import ServiceAgent
from ..types.default import DefaultAgent


class AgentLifecycle:
    """Manages the lifecycle of the agent system."""
    
    def __init__(self):
        self.registry = AgentRegistry()
        self.factory = AgentFactory()
        self._initialized = False
        self._shutdown_handlers = []
        
        # Register cleanup on process exit
        atexit.register(self._cleanup_on_exit)
    
    async def initialize(self) -> bool:
        """
        Initialize the agent system with default agent types.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            logger.warning("Agent system already initialized")
            return True
        
        try:
            logger.info("Initializing agent system")
            
            # Register default agent types
            self._register_default_agents()
            
            # Set default fallback agent
            self.registry.set_default('default')
            
            # Initialize factory with registry
            self.factory._agent_classes = {
                reg.business_type: reg.agent_class 
                for reg in self.registry._registry.values()
            }
            
            self._initialized = True
            
            # Record initialization metrics
            metrics.increment_counter('agent_system_initialized_total')
            
            logger.info("Agent system initialized successfully",
                       registered_types=self.registry.get_registered_types())
            
            return True
            
        except Exception as e:
            logger.error("Failed to initialize agent system", error=str(e))
            return False
    
    def _register_default_agents(self):
        """Register the default agent types."""
        default_agents = [
            ('default', DefaultAgent, 'Default agent for unknown business types'),
            ('restaurant', RestaurantAgent, 'Agent for restaurant businesses'),
            ('retail', RetailAgent, 'Agent for retail businesses'),
            ('service', ServiceAgent, 'Agent for service businesses')
        ]
        
        for business_type, agent_class, description in default_agents:
            success = self.registry.register(business_type, agent_class, description)
            if success:
                logger.debug("Registered default agent",
                           business_type=business_type,
                           agent_class=agent_class.__name__)
            else:
                logger.error("Failed to register default agent",
                           business_type=business_type,
                           agent_class=agent_class.__name__)
    
    async def shutdown(self):
        """Shutdown the agent system gracefully."""
        if not self._initialized:
            logger.warning("Agent system not initialized, nothing to shutdown")
            return
        
        logger.info("Shutting down agent system")
        
        try:
            # Execute shutdown handlers
            for handler in self._shutdown_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as e:
                    logger.error("Error in shutdown handler", error=str(e))
            
            # Clear agent cache
            self.factory.clear_cache()
            
            # Reset registry
            self.registry._registry.clear()
            
            self._initialized = False
            
            logger.info("Agent system shutdown complete")
            
        except Exception as e:
            logger.error("Error during agent system shutdown", error=str(e))
    
    def _cleanup_on_exit(self):
        """Cleanup handler for process exit."""
        if self._initialized:
            logger.info("Process exit detected, cleaning up agent system")
            # Run shutdown in asyncio context if available
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(self.shutdown())
            except Exception:
                # If no event loop available, do basic cleanup
                self.factory.clear_cache()
                self.registry._registry.clear()
                self._initialized = False
    
    def add_shutdown_handler(self, handler):
        """
        Add a handler to be called during shutdown.
        
        Args:
            handler: Function or coroutine to call during shutdown
        """
        self._shutdown_handlers.append(handler)
        logger.debug("Added shutdown handler", handler=handler.__name__)
    
    def get_agent_for_business(self, business_type: str):
        """
        Get agent for business type (delegates to factory).
        
        Args:
            business_type: Type of business
            
        Returns:
            Agent instance for the business type
        """
        if not self._initialized:
            logger.error("Agent system not initialized")
            raise RuntimeError("Agent system not initialized. Call initialize() first.")
        
        return self.factory.get_agent_for_business(business_type)
    
    def register_custom_agent(self, business_type: str, agent_class, description: str = ''):
        """
        Register a custom agent type.
        
        Args:
            business_type: Business type name
            agent_class: Agent class to register
            description: Optional description
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            logger.error("Cannot register agent before initialization")
            return False
        
        # Register in registry
        success = self.registry.register(business_type, agent_class, description)
        
        if success:
            # Update factory classes
            self.factory._agent_classes[business_type] = agent_class
            logger.info("Custom agent registered",
                       business_type=business_type,
                       agent_class=agent_class.__name__)
        
        return success
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of agent system."""
        if not self._initialized:
            return {
                'status': 'unhealthy',
                'error': 'Agent system not initialized'
            }
        
        try:
            # Get registry health
            registry_health = await self.registry.health_check_registry()
            
            # Get factory health
            factory_health = await self.factory.health_check_all_agents()
            
            # Determine overall health
            overall_status = 'healthy'
            if (registry_health.get('status') != 'healthy' or 
                factory_health.get('overall_status') != 'healthy'):
                overall_status = 'degraded'
            
            return {
                'status': overall_status,
                'initialized': self._initialized,
                'registry': registry_health,
                'factory': factory_health,
                'system_stats': {
                    'registered_types': len(self.registry),
                    'cached_agents': len(self.factory._agent_cache),
                    'shutdown_handlers': len(self._shutdown_handlers)
                }
            }
            
        except Exception as e:
            logger.error("Agent system health check failed", error=str(e))
            return {
                'status': 'unhealthy',
                'error': str(e),
                'initialized': self._initialized
            }
    
    @property
    def is_initialized(self) -> bool:
        """Check if agent system is initialized."""
        return self._initialized
    
    @asynccontextmanager
    async def lifecycle_context(self):
        """Context manager for agent system lifecycle."""
        await self.initialize()
        try:
            yield self
        finally:
            await self.shutdown()


# Global agent lifecycle instance
_agent_lifecycle: Optional[AgentLifecycle] = None


async def initialize_agent_system() -> bool:
    """Initialize the global agent system."""
    global _agent_lifecycle
    
    if _agent_lifecycle is None:
        _agent_lifecycle = AgentLifecycle()
    
    return await _agent_lifecycle.initialize()


async def shutdown_agent_system():
    """Shutdown the global agent system."""
    global _agent_lifecycle
    
    if _agent_lifecycle:
        await _agent_lifecycle.shutdown()
        _agent_lifecycle = None


def get_agent_system() -> Optional[AgentLifecycle]:
    """Get the global agent system instance."""
    return _agent_lifecycle


def get_agent_for_business_type(business_type: str):
    """Get agent for business type from global system."""
    if _agent_lifecycle is None:
        raise RuntimeError("Agent system not initialized")
    
    return _agent_lifecycle.get_agent_for_business(business_type)