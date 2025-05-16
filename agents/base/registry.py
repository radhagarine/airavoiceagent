"""Agent registry for managing and monitoring agent types."""

import time
from typing import Dict, List, Type, Optional
from dataclasses import dataclass, field
from datetime import datetime

from monitoring_system import logger, metrics
from ..base.agent import BaseAgent


@dataclass
class AgentRegistration:
    """Information about a registered agent type."""
    agent_class: Type[BaseAgent]
    business_type: str
    registered_at: datetime = field(default_factory=datetime.now)
    registration_count: int = 0
    last_used: Optional[datetime] = None
    health_status: str = 'healthy'
    description: str = ''


class AgentRegistry:
    """Registry for managing and monitoring different agent types."""
    
    def __init__(self):
        self._registry: Dict[str, AgentRegistration] = {}
        self._default_agent_type = 'default'
        
        logger.info("Agent registry initialized")
    
    def register(self, business_type: str, agent_class: Type[BaseAgent], 
                 description: str = '') -> bool:
        """
        Register an agent type in the registry.
        
        Args:
            business_type: Type of business (restaurant, retail, service)
            agent_class: Agent class to register
            description: Optional description of the agent
            
        Returns:
            True if registration successful, False otherwise
        """
        try:
            # Validate inputs
            if not business_type or not agent_class:
                logger.error("Invalid registration parameters", 
                           business_type=business_type,
                           agent_class=agent_class)
                return False
            
            # Normalize business type
            business_type = business_type.lower().strip()
            
            # Check if already registered
            if business_type in self._registry:
                logger.warning("Agent type already registered", 
                             business_type=business_type,
                             existing_class=self._registry[business_type].agent_class.__name__,
                             new_class=agent_class.__name__)
                return False
            
            # Create registration
            registration = AgentRegistration(
                agent_class=agent_class,
                business_type=business_type,
                description=description
            )
            
            self._registry[business_type] = registration
            
            # Update metrics
            metrics.increment_counter(
                'agent_type_registered_total',
                labels={'business_type': business_type}
            )
            
            logger.info("Agent type registered successfully",
                       business_type=business_type,
                       agent_class=agent_class.__name__,
                       description=description)
            
            return True
            
        except Exception as e:
            logger.error("Failed to register agent type",
                        business_type=business_type,
                        error=str(e))
            return False
    
    def get_agent_class(self, business_type: str) -> Type[BaseAgent]:
        """
        Get agent class for business type.
        
        Args:
            business_type: Type of business
            
        Returns:
            Agent class for the business type
        """
        # Normalize business type
        business_type = business_type.lower().strip() if business_type else ''
        
        # Check registry
        if business_type in self._registry:
            registration = self._registry[business_type]
            registration.last_used = datetime.now()
            registration.registration_count += 1
            
            logger.debug("Agent class retrieved",
                        business_type=business_type,
                        agent_class=registration.agent_class.__name__)
            
            return registration.agent_class
        
        # Fallback to default if not found
        if self._default_agent_type in self._registry:
            logger.warning("Unknown business type, using default agent",
                          requested_type=business_type,
                          default_type=self._default_agent_type)
            return self._registry[self._default_agent_type].agent_class
        
        # If no default registered, raise error
        logger.error("No agent class found and no default registered",
                    business_type=business_type)
        raise ValueError(f"No agent class registered for business type: {business_type}")
    
    def unregister(self, business_type: str) -> bool:
        """
        Unregister an agent type.
        
        Args:
            business_type: Type of business to unregister
            
        Returns:
            True if unregistration successful, False otherwise
        """
        business_type = business_type.lower().strip()
        
        if business_type not in self._registry:
            logger.warning("Attempted to unregister unknown agent type",
                          business_type=business_type)
            return False
        
        del self._registry[business_type]
        
        logger.info("Agent type unregistered",
                   business_type=business_type)
        
        return True
    
    def set_default(self, business_type: str) -> bool:
        """
        Set the default agent type for fallback scenarios.
        
        Args:
            business_type: Type to use as default
            
        Returns:
            True if successful, False otherwise
        """
        business_type = business_type.lower().strip()
        
        if business_type not in self._registry:
            logger.error("Cannot set default to unregistered type",
                        business_type=business_type)
            return False
        
        old_default = self._default_agent_type
        self._default_agent_type = business_type
        
        logger.info("Default agent type changed",
                   old_default=old_default,
                   new_default=business_type)
        
        return True
    
    def get_registered_types(self) -> List[str]:
        """Get list of all registered business types."""
        return list(self._registry.keys())
    
    def get_registry_stats(self) -> Dict:
        """Get comprehensive registry statistics."""
        total_registrations = len(self._registry)
        
        # Calculate usage statistics
        usage_stats = {}
        for business_type, registration in self._registry.items():
            usage_stats[business_type] = {
                'usage_count': registration.registration_count,
                'last_used': registration.last_used.isoformat() if registration.last_used else None,
                'registered_at': registration.registered_at.isoformat(),
                'agent_class': registration.agent_class.__name__,
                'description': registration.description,
                'health_status': registration.health_status
            }
        
        return {
            'total_registered_types': total_registrations,
            'default_agent_type': self._default_agent_type,
            'registered_types': self.get_registered_types(),
            'usage_statistics': usage_stats
        }
    
    async def health_check_registry(self) -> Dict:
        """Perform health check on registry and registered agent types."""
        try:
            # Basic registry health
            health_info = {
                'status': 'healthy',
                'total_types': len(self._registry),
                'default_type': self._default_agent_type,
                'agent_health': {}
            }
            
            # Check each registered agent type
            for business_type, registration in self._registry.items():
                try:
                    # Try to instantiate agent to check health
                    agent = registration.agent_class(business_type)
                    agent_health = await agent.health_check()
                    health_info['agent_health'][business_type] = agent_health
                except Exception as e:
                    health_info['agent_health'][business_type] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }
                    registration.health_status = 'unhealthy'
            
            # Determine overall health
            unhealthy_agents = [
                bt for bt, health in health_info['agent_health'].items()
                if health.get('status') != 'healthy'
            ]
            
            if unhealthy_agents:
                health_info['status'] = 'degraded'
                health_info['unhealthy_agents'] = unhealthy_agents
            
            return health_info
            
        except Exception as e:
            logger.error("Registry health check failed", error=str(e))
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    def __len__(self) -> int:
        """Get number of registered agent types."""
        return len(self._registry)
    
    def __contains__(self, business_type: str) -> bool:
        """Check if business type is registered."""
        return business_type.lower().strip() in self._registry