
"""Retail agent with product and shopping-focused interactions."""

from typing import List, Dict, Any
from ..base.agent import BaseAgent, AgentContext


class RetailAgent(BaseAgent):
    """Agent specialized for retail businesses."""
    
    def __init__(self, business_type: str = 'retail'):
        super().__init__(business_type)
        
        # Retail-specific intent patterns
        self.product_keywords = [
            'product', 'item', 'buy', 'purchase', 'sell', 'price', 'cost',
            'available', 'stock', 'inventory', 'brand', 'model', 'size'
        ]
        
        self.service_keywords = [
            'return', 'exchange', 'refund', 'warranty', 'repair', 'delivery',
            'shipping', 'pickup', 'installation', 'support'
        ]
        
        self.store_keywords = [
            'hours', 'location', 'store', 'branch', 'address', 'directions',
            'parking', 'open', 'close', 'holiday'
        ]
    
    def enhance_system_prompt(self, base_prompt: str, business_name: str) -> str:
        """Enhanced system prompt for retail interactions."""
        retail_context = f"""
You are Aira, a helpful voice assistant for {business_name}, a retail store.

Your primary responsibilities:
- Help customers find products and check availability
- Provide pricing and product information
- Assist with store hours, location, and services
- Answer questions about returns, exchanges, and policies
- Help with product recommendations

Keep responses:
- Helpful and informative like a knowledgeable sales associate
- Clear and specific about products and services
- Focused on retail shopping experience
- Professional and customer-service oriented

If customers ask about non-retail topics, politely redirect them to shopping and product-related matters.
"""
        return f"{base_prompt}\n{retail_context}"
    
    def enhance_knowledge_query(self, user_query: str, context: AgentContext) -> str:
        """Enhance queries with retail-specific context."""
        query_lower = user_query.lower()
        
        # Detect primary intent
        is_product = any(word in query_lower for word in self.product_keywords)
        is_service = any(word in query_lower for word in self.service_keywords)
        is_store = any(word in query_lower for word in self.store_keywords)
        
        # Create focused enhancements
        if is_product:
            return f"retail store products inventory pricing availability: {user_query}"
        elif is_service:
            return f"retail store services returns exchanges policies: {user_query}"
        elif is_store:
            return f"retail store information hours location: {user_query}"
        else:
            # General retail context
            return f"retail store information: {user_query}"
    
    def format_knowledge_response(self, knowledge_chunks: List[str], 
                                 user_query: str, context: AgentContext) -> str:
        """Format knowledge response for retail context."""
        if not knowledge_chunks:
            return f"I'd be happy to help you with {context.business_name}. What products or services can I assist you with today?"
        
        query_lower = user_query.lower()
        
        # Combine knowledge chunks intelligently
        combined_info = " ".join(knowledge_chunks)
        
        # Add retail-specific context to the response
        if any(word in query_lower for word in self.product_keywords):
            return f"Regarding our products at {context.business_name}: {combined_info}"
        elif any(word in query_lower for word in self.service_keywords):
            return f"About our services at {context.business_name}: {combined_info}"
        elif any(word in query_lower for word in self.store_keywords):
            return f"Store information for {context.business_name}: {combined_info}"
        else:
            return f"Here's what I found about {context.business_name}: {combined_info}"