"""Default agent for unknown business types or fallback scenarios."""

from typing import List, Dict, Any
from ..base.agent import BaseAgent, AgentContext


class DefaultAgent(BaseAgent):
    """Default agent for unknown business types or fallback scenarios."""
    
    def __init__(self, business_type: str = 'default'):
        super().__init__(business_type)
        
        # General intent patterns
        self.general_keywords = [
            'hours', 'location', 'services', 'information', 'help',
            'contact', 'address', 'phone', 'email', 'website'
        ]
    
    def enhance_system_prompt(self, base_prompt: str, business_name: str) -> str:
        """Enhanced system prompt for general business interactions."""
        default_context = f"""
You are Aira, a helpful voice assistant for {business_name}.

Your primary responsibilities:
- Provide general information about the business
- Help customers with basic inquiries about hours and location
- Offer to connect customers with the right person for specific needs
- Maintain professional and helpful tone

Keep responses:
- Clear and informative
- Professional yet friendly
- Focused on helping customers connect with the business
- Gracefully handle any topic while steering toward business matters

When you don't have specific information, offer to help the customer connect with someone who can assist them better.
"""
        return f"{base_prompt}\n{default_context}"
    
    def enhance_knowledge_query(self, user_query: str, context: AgentContext) -> str:
        """Enhance queries with general business context."""
        query_lower = user_query.lower()
        
        # Add basic business context to improve knowledge base retrieval
        return f"business information general inquiries: {user_query}"
    
    def format_knowledge_response(self, knowledge_chunks: List[str], 
                                 user_query: str, context: AgentContext) -> str:
        """Format knowledge response for general business context."""
        if not knowledge_chunks:
            return f"I'd be happy to help you with {context.business_name}. Let me connect you with someone who can assist you better, or you can ask me about our general information like hours and location."
        
        # Combine knowledge chunks with general business context
        combined_info = " ".join(knowledge_chunks)
        return f"Here's information about {context.business_name}: {combined_info}"