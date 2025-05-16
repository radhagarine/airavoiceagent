"""Agent-enhanced context aggregator for seamless pipeline integration."""

import asyncio
from typing import List, Dict, Any, Optional

from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.frames.frames import LLMMessagesFrame

from monitoring_system import logger, monitor_performance
from agents.base.agent import BaseAgent, AgentContext


class AgentEnhancedContext(OpenAILLMContext):
    """
    Extends OpenAILLMContext to seamlessly integrate agent enhancements.
    
    This class provides zero-latency agent integration by enhancing queries
    only when they're sent to the LLM, not during conversation flow.
    """
    
    def __init__(self, messages: List[Dict], business_agent: BaseAgent,
                 agent_context: AgentContext, knowledge_base=None):
        # Initialize the enhanced context with agent-modified messages
        enhanced_messages = business_agent.enhance_context(messages, agent_context)
        super().__init__(enhanced_messages)
        
        self.agent = business_agent
        self.agent_context = agent_context
        self.knowledge_base = knowledge_base
        
        logger.debug("Agent-enhanced context initialized",
                    agent_type=business_agent.business_type,
                    business_id=agent_context.business_id)
    
    @monitor_performance("agent_context_process")
    async def get_messages_for_llm(self) -> List[Dict]:
        """
        Override to enhance user messages with agent processing.
        
        This is called by the LLM processor when it needs the conversation context.
        Agent enhancement happens here to avoid adding latency to the conversation flow.
        """
        # Get base messages from parent class
        messages = await super().get_messages_for_llm()
        
        # Find the last user message for enhancement
        if not messages:
            return messages
        
        last_message_idx = None
        for i in reversed(range(len(messages))):
            if messages[i].get("role") == "user":
                last_message_idx = i
                break
        
        if last_message_idx is None:
            return messages
        
        # Get the user query
        user_query = messages[last_message_idx]["content"]
        
        try:
            # Process query through agent
            enhanced_query = await self.agent.process_query(
                user_query, 
                self.agent_context,
                self.knowledge_base
            )
            
            # Create enhanced messages list
            enhanced_messages = messages.copy()
            enhanced_messages[last_message_idx] = {
                "role": "user",
                "content": enhanced_query
            }
            
            logger.debug("Agent enhanced user query for LLM",
                        agent_type=self.agent.business_type,
                        original_length=len(user_query),
                        enhanced_length=len(enhanced_query))
            
            return enhanced_messages
            
        except Exception as e:
            logger.error("Error in agent enhancement, using original query",
                        error=str(e),
                        agent_type=self.agent.business_type)
            # Return original messages on error
            return messages


def create_agent_enhanced_context(base_messages: List[Dict], 
                                 business_agent: BaseAgent,
                                 agent_context: AgentContext,
                                 knowledge_base=None) -> AgentEnhancedContext:
    """
    Factory function to create agent-enhanced context.
    
    Args:
        base_messages: Base conversation messages
        business_agent: Agent instance for the business
        agent_context: Context information for the agent
        knowledge_base: Optional knowledge base instance
        
    Returns:
        AgentEnhancedContext instance ready for use in pipeline
    """
    return AgentEnhancedContext(base_messages, business_agent, agent_context, knowledge_base)