"""Base agent framework with monitoring and caching integration."""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from monitoring_system import logger, monitor_performance, metrics, log_context
from cache.simplified_cache import cache_result, generate_knowledge_base_key, cache_knowledge_base



@dataclass
class AgentContext:
    """Context for agent operations."""
    business_id: str
    business_name: str
    business_type: str
    call_id: str
    conversation_state: Dict[str, Any]


class BaseAgent(ABC):
    """Base class for all business agents with full infrastructure integration."""
    
    def __init__(self, business_type: str):
        self.business_type = business_type
        self.agent_id = f"{business_type}_agent"
        self.creation_time = time.time()
        self._stats = {
            'queries_processed': 0,
            'knowledge_queries': 0,
            'context_enhancements': 0,
            'errors': 0
        }
        
        logger.info("Agent initialized", 
                   agent_type=business_type,
                   agent_id=self.agent_id)
    
    # Core Interface Methods
    
    @abstractmethod
    def enhance_system_prompt(self, base_prompt: str, business_name: str) -> str:
        """Enhance system prompt with business type-specific context."""
        pass
    
    @abstractmethod
    def enhance_knowledge_query(self, user_query: str, context: AgentContext) -> str:
        """Enhance user query for better knowledge base retrieval."""
        pass
    
    @abstractmethod 
    def format_knowledge_response(self, knowledge_chunks: List[str], 
                                 user_query: str, context: AgentContext) -> str:
        """Format knowledge base results for business-appropriate response."""
        pass
    
    # Core Processing Methods
    
    @monitor_performance("agent_process_query")
    async def process_query(self, user_query: str, context: AgentContext,
                          knowledge_base=None) -> str:
        """
        Process user query with agent-specific enhancements.
        
        This is the main entry point for agent processing, handling both
        query enhancement and response formatting.
        """
        start_time = time.time()
        
        with log_context(agent_type=self.business_type, 
                        business_id=context.business_id,
                        call_id=context.call_id):
            
            try:
                # Step 1: Enhance query for knowledge base
                enhanced_query = self.enhance_knowledge_query(user_query, context)
                self._stats['knowledge_queries'] += 1
                
                # Step 2: Query knowledge base if available
                if knowledge_base and knowledge_base.business_has_knowledge_base(context.business_id):
                    knowledge_chunks = await self._query_knowledge_base_cached(
                        knowledge_base, context.business_id, enhanced_query
                    )
                    
                    # Step 3: Format knowledge response
                    if knowledge_chunks:
                        response = self.format_knowledge_response(
                            knowledge_chunks, user_query, context
                        )
                        logger.debug("Agent processed query with knowledge",
                                   query_length=len(user_query),
                                   response_length=len(response),
                                   knowledge_chunks=len(knowledge_chunks))
                        return response
                
                # Step 4: Fallback to enhanced query for LLM
                self._stats['queries_processed'] += 1
                return enhanced_query
                
            except Exception as e:
                self._stats['errors'] += 1
                logger.error("Agent query processing error",
                           error=str(e),
                           user_query=user_query[:100])
                # Return original query on error to avoid breaking conversation
                return user_query
            finally:
                # Record processing metrics
                duration = time.time() - start_time
                metrics.observe_histogram(
                    'agent_query_duration_seconds',
                    duration,
                    labels={'agent_type': self.business_type, 'business_id': context.business_id}
                )
    
    @cache_result(cache_type="knowledge_base", ttl=3600)
    async def _query_knowledge_base_cached(self, knowledge_base, business_id: str, 
                                         enhanced_query: str) -> List[str]:
        """Query knowledge base with caching."""
        return knowledge_base.query(business_id, enhanced_query, top_k=3)
    
    def enhance_context(self, base_messages: List[Dict], context: AgentContext) -> List[Dict]:
        """
        Enhance conversation context with business-specific system prompt.
        
        This method is called once during agent initialization to set up
        the business-specific context.
        """
        enhanced_messages = base_messages.copy()
        
        # Update system prompt
        if enhanced_messages and enhanced_messages[0].get("role") == "system":
            original_prompt = enhanced_messages[0]["content"]
            enhanced_prompt = self.enhance_system_prompt(original_prompt, context.business_name)
            enhanced_messages[0]["content"] = enhanced_prompt
            
            self._stats['context_enhancements'] += 1
            logger.debug("Agent enhanced system prompt",
                        agent_type=self.business_type,
                        business_name=context.business_name)
        
        return enhanced_messages
    
    # Utility Methods
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent performance statistics."""
        return {
            'agent_type': self.business_type,
            'agent_id': self.agent_id,
            'uptime_seconds': time.time() - self.creation_time,
            'statistics': self._stats.copy(),
            'health_status': 'healthy'
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform agent health check."""
        return {
            'status': 'healthy',
            'agent_type': self.business_type,
            'agent_id': self.agent_id,
            'uptime_seconds': time.time() - self.creation_time,
            'error_rate': (
                self._stats['errors'] / max(self._stats['queries_processed'], 1) * 100
                if self._stats['queries_processed'] > 0 else 0
            )
        }
    
    # Helper Methods for Subclasses
    
    def _extract_intent_keywords(self, query: str) -> List[str]:
        """Extract intent keywords from user query."""
        query_lower = query.lower()
        
        # Common intent patterns
        booking_keywords = ['book', 'reserve', 'appointment', 'table', 'schedule']
        menu_keywords = ['menu', 'food', 'drink', 'special', 'dish']
        hours_keywords = ['hours', 'open', 'close', 'time']
        location_keywords = ['address', 'location', 'where', 'directions']
        
        intents = []
        if any(word in query_lower for word in booking_keywords):
            intents.append('booking')
        if any(word in query_lower for word in menu_keywords):
            intents.append('menu')
        if any(word in query_lower for word in hours_keywords):
            intents.append('hours')
        if any(word in query_lower for word in location_keywords):
            intents.append('location')
            
        return intents
    
    def _create_business_focused_enhancement(self, query: str, business_focus: str) -> str:
        """Create business-focused query enhancement."""
        intents = self._extract_intent_keywords(query)
        
        if not intents:
            # No specific intent, add general business context
            return f"{business_focus} related: {query}"
        
        # Add specific business context based on detected intents
        context_parts = [business_focus]
        for intent in intents:
            if intent == 'booking':
                context_parts.append(f"{business_focus} reservations booking")
            elif intent == 'menu':
                context_parts.append(f"{business_focus} menu offerings")
            elif intent == 'hours':
                context_parts.append(f"{business_focus} hours operation schedule")
            elif intent == 'location':
                context_parts.append(f"{business_focus} location address")
        
        enhanced_context = " ".join(context_parts)
        return f"{enhanced_context}: {query}"