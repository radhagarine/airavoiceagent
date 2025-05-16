"""Service agent for service businesses (salons, spas, repair shops, etc.)."""

from typing import List, Dict, Any
from ..base.agent import BaseAgent, AgentContext


class ServiceAgent(BaseAgent):
    """Agent specialized for service businesses (salons, spas, repair, etc.)."""
    
    def __init__(self, business_type: str = 'service'):
        super().__init__(business_type)
        
        # Service-specific intent patterns
        self.appointment_keywords = [
            'appointment', 'book', 'schedule', 'available', 'time', 'slot',
            'tomorrow', 'next week', 'today', 'cancel', 'reschedule'
        ]
        
        self.service_keywords = [
            'service', 'treatment', 'package', 'price', 'cost', 'offer',
            'special', 'promotion', 'discount', 'membership'
        ]
        
        self.business_keywords = [
            'hours', 'location', 'staff', 'stylist', 'technician', 'specialist',
            'experience', 'qualification', 'open', 'close'
        ]
    
    def enhance_system_prompt(self, base_prompt: str, business_name: str) -> str:
        """Enhanced system prompt for service business interactions."""
        service_context = f"""
You are Aira, a helpful voice assistant for {business_name}, a service business.

Your primary responsibilities:
- Help customers schedule appointments and check availability
- Provide information about services, treatments, and pricing
- Answer questions about business hours and location
- Assist with service recommendations and packages
- Help with staff and specialist information

Keep responses:
- Professional and service-oriented
- Clear about appointment availability and procedures
- Focused on services and scheduling
- Helpful with service recommendations

If customers ask about non-service topics, politely redirect them to appointments and services.
"""
        return f"{base_prompt}\n{service_context}"
    
    def enhance_knowledge_query(self, user_query: str, context: AgentContext) -> str:
        """Enhance queries with service business-specific context."""
        query_lower = user_query.lower()
        
        # Detect primary intent
        is_appointment = any(word in query_lower for word in self.appointment_keywords)
        is_service = any(word in query_lower for word in self.service_keywords)
        is_business = any(word in query_lower for word in self.business_keywords)
        
        # Create focused enhancements
        if is_appointment:
            return f"service business appointment booking scheduling availability: {user_query}"
        elif is_service:
            return f"service business treatments services pricing packages: {user_query}"
        elif is_business:
            return f"service business information hours staff location: {user_query}"
        else:
            # General service context
            return f"service business information: {user_query}"
    
    def format_knowledge_response(self, knowledge_chunks: List[str], 
                                 user_query: str, context: AgentContext) -> str:
        """Format knowledge response for service business context."""
        if not knowledge_chunks:
            return f"I'd be happy to help you with {context.business_name}. What service or appointment can I assist you with today?"
        
        query_lower = user_query.lower()
        
        # Combine knowledge chunks intelligently
        combined_info = " ".join(knowledge_chunks)
        
        # Add service-specific context to the response
        if any(word in query_lower for word in self.appointment_keywords):
            return f"For appointments at {context.business_name}: {combined_info}"
        elif any(word in query_lower for word in self.service_keywords):
            return f"Our services at {context.business_name}: {combined_info}"
        elif any(word in query_lower for word in self.business_keywords):
            return f"About {context.business_name}: {combined_info}"
        else:
            return f"Here's information about {context.business_name}: {combined_info}"