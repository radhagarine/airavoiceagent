"""Restaurant agent with menu and reservation-focused interactions."""

from typing import List, Dict, Any
from ..base.agent import BaseAgent, AgentContext


class RestaurantAgent(BaseAgent):
    """Agent specialized for restaurant businesses."""
    
    def __init__(self, business_type: str = 'restaurant'):
        super().__init__(business_type)
        
        # Restaurant-specific intent patterns
        self.reservation_keywords = [
            'book', 'reserve', 'table', 'reservation', 'available', 'tonight',
            'tomorrow', 'weekend', 'party of', 'people', 'guests'
        ]
        
        self.menu_keywords = [
            'menu', 'food', 'dish', 'meal', 'special', 'today', 'recommend',
            'vegetarian', 'vegan', 'gluten free', 'allergen', 'price', 'cost'
        ]
        
        self.hours_keywords = [
            'hours', 'open', 'close', 'time', 'when', 'schedule', 'holiday'
        ]
    
    def enhance_system_prompt(self, base_prompt: str, business_name: str) -> str:
        """Enhanced system prompt for restaurant interactions."""
        restaurant_context = f"""
You are Aira, a helpful voice assistant for {business_name}, a restaurant.

Your primary responsibilities:
- Help customers with menu inquiries and recommendations
- Assist with table reservations and availability
- Provide information about hours, location, and dining options
- Answer questions about special dietary needs (vegetarian, vegan, gluten-free)

Keep responses:
- Warm and welcoming like restaurant hospitality
- Concise but informative
- Focused on food, dining, and reservations
- Professional yet friendly

If customers ask about non-restaurant topics, politely redirect them to restaurant-related matters.
"""
        return f"{base_prompt}\n{restaurant_context}"
    
    def enhance_knowledge_query(self, user_query: str, context: AgentContext) -> str:
        """Enhance queries with restaurant-specific context."""
        query_lower = user_query.lower()
        
        # Detect primary intent
        is_reservation = any(word in query_lower for word in self.reservation_keywords)
        is_menu = any(word in query_lower for word in self.menu_keywords)
        is_hours = any(word in query_lower for word in self.hours_keywords)
        
        # Create focused enhancements
        if is_reservation:
            return f"restaurant table reservation booking availability: {user_query}"
        elif is_menu:
            return f"restaurant menu dishes food specials: {user_query}"
        elif is_hours:
            return f"restaurant hours operation schedule: {user_query}"
        else:
            # General restaurant context
            return f"restaurant information: {user_query}"
    
    def format_knowledge_response(self, knowledge_chunks: List[str], 
                                 user_query: str, context: AgentContext) -> str:
        """Format knowledge response for restaurant context."""
        if not knowledge_chunks:
            return f"I'd be happy to help you with {context.business_name}. Could you please be more specific about what you'd like to know?"
        
        query_lower = user_query.lower()
        
        # Combine knowledge chunks intelligently
        combined_info = " ".join(knowledge_chunks)
        
        # Add restaurant-specific context to the response
        if any(word in query_lower for word in self.reservation_keywords):
            return f"For reservations at {context.business_name}: {combined_info}"
        elif any(word in query_lower for word in self.menu_keywords):
            return f"Regarding our menu at {context.business_name}: {combined_info}"
        elif any(word in query_lower for word in self.hours_keywords):
            return f"Our hours at {context.business_name}: {combined_info}"
        else:
            return f"Here's information about {context.business_name}: {combined_info}"