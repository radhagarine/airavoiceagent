"""Agent framework for business-specific voice interactions."""

from .base.agent import BaseAgent
from .base.factory import AgentFactory
from .base.registry import AgentRegistry
from .base.lifecycle import AgentLifecycle

# Agent types
from .types.restaurant import RestaurantAgent
from .types.retail import RetailAgent
from .types.service import ServiceAgent
from .types.default import DefaultAgent

# Lifecycle management functions
from .base.lifecycle import (
    initialize_agent_system,
    shutdown_agent_system,
    get_agent_system,
    get_agent_for_business_type
)

__all__ = [
    # Core framework
    'BaseAgent',
    'AgentFactory', 
    'AgentRegistry',
    'AgentLifecycle',
    
    # Agent types
    'RestaurantAgent',
    'RetailAgent', 
    'ServiceAgent',
    'DefaultAgent',
    
    # Lifecycle functions
    'initialize_agent_system',
    'shutdown_agent_system', 
    'get_agent_system',
    'get_agent_for_business_type'
]

__version__ = "1.0.0"