"""Updated bot.py with simplified business info retrieval flow.
This version has a cleaner flow from business phone to info.
"""

import argparse
import asyncio
import os
import sys
import time
from enum import Enum
from typing import Optional
from dataclasses import dataclass

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.frames.frames import TextFrame

# Import the Twilio handler with simplified interface
from utils.twilio_handler import forward_call, get_client_for_phone, get_business_name

# Import the Supabase helper for business lookup
from utils.supabase_helper import get_business_by_phone

# Import cache utilities
from cache import (
    initialize_cache,
    get_cache_instance,
    cache_business_lookup,
    generate_business_key
)

# Import agent system
from agents import (
    BaseAgent,
    AgentFactory,
    AgentLifecycle,
    initialize_agent_system,
    get_agent_for_business_type
)
from agents.base.agent import AgentContext
from agents.integration.context import create_agent_enhanced_context

# Try to import knowledge base - it's optional
try:
    from utils.knowledge_base import KnowledgeBase
    HAS_KNOWLEDGE_BASE = True
except ImportError:
    logger.warning("Knowledge base module not available")
    HAS_KNOWLEDGE_BASE = False

# Setup logging
load_dotenv()
logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class ConversationState(Enum):
    """Represents the current state of the conversation."""
    INITIALIZING = "initializing"
    GREETING = "greeting" 
    CHATTING = "chatting"
    ENDING = "ending"


@dataclass
class BusinessInfo:
    """Enhanced business information data class."""
    id: Optional[str]
    name: str
    phone: str
    type: str  # business type (restaurant, retail, service)
    cache_key: str


class VoiceAssistant:
    """Enhanced voice assistant with optional knowledge base integration."""
    
    def __init__(self, business_name: str = "Our Business", business_id: Optional[str] = None):
        self.business_name = business_name
        self.business_id = business_id
        self.state = ConversationState.INITIALIZING
        self.has_greeted = False
        self.call_forwarded = False
        self.conversation_started = False
        
        # Initialize knowledge base if available
        self.knowledge_base = None
        self.has_knowledge = False
        
        if HAS_KNOWLEDGE_BASE and business_id:
            try:
                self.knowledge_base = KnowledgeBase()
                if self.knowledge_base.business_has_knowledge_base(business_id):
                    self.has_knowledge = True
                    logger.info(f"Knowledge base available for business {business_id}")
                else:
                    logger.info(f"No knowledge base found for business {business_id}")
            except Exception as e:
                logger.error(f"Error initializing knowledge base: {str(e)}")
        
        # Build context with initial greeting
        self.context = [
            {
                "role": "system",
                "content": self._build_system_prompt()
            },
            {
                "role": "assistant", 
                "content": f"Hello! I am Aira. Thank you for calling {self.business_name}. How can I help you today?"
            }
        ]
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM."""
        base_prompt = (
            f"You are a friendly and helpful phone assistant for {self.business_name}. "
            "You are speaking with a customer who called our phone number. "
            "Your responses will be read aloud, so keep them concise, conversational, and natural. "
            
            "You should greet customers when they first call with a warm welcome message. "
            "Listen to what the customer needs and help them accordingly. "
            "If they ask questions, answer them clearly and helpfully. "
        )
        
        if self.has_knowledge:
            base_prompt += (
                "\n\nYou have access to specific information about our business through context provided with user questions. "
                "Use this context when available to give accurate, specific answers. "
                "If the context doesn't contain relevant information, answer based on your general knowledge but acknowledge if you're unsure about specific details. "
            )
        else:
            base_prompt += (
                "\n\nFocus on helping the customer with their questions or needs. "
                "If you don't know specific information, politely let them know and offer to help in other ways. "
            )
        
        return base_prompt
    
    async def handle_first_participant_joined(self, transport, participant_id: str):
        """Handle when the first participant joins the call."""
        logger.info(f"First participant joined: {participant_id}")
        await transport.capture_participant_transcription(participant_id)
        self.state = ConversationState.GREETING
    
    async def handle_dial_in_ready(self, call_id: str, sip_uri: str, business_phone: Optional[str] = None):
        """
        Handle when dial-in is ready - forward the call using the appropriate Twilio account.
        
        Args:
            call_id: Twilio call SID
            sip_uri: Daily SIP URI to forward to
            business_phone: The business phone number that was called
        """
        if self.call_forwarded:
            logger.warning("Call already forwarded, ignoring")
            return
        
        logger.info(f"Forwarding call {call_id} to {sip_uri}")
        logger.info(f"Business phone: {business_phone if business_phone else 'Not specified'}")
        
        try:
            # Forward call using appropriate client based on business phone
            success = forward_call(call_id, sip_uri, business_phone)
            
            if success:
                logger.info("Call forwarded successfully")
                self.call_forwarded = True
            else:
                logger.error("Failed to forward call - no suitable Twilio account found")
                raise RuntimeError("Failed to forward call - no suitable Twilio account found")
                
        except Exception as e:
            logger.error(f"Failed to forward call: {str(e)}")
            raise


@cache_business_lookup()
async def get_business_info_cached(call_id: str, business_phone: str) -> Optional[BusinessInfo]:
    """
    Get business information with caching.
    
    Args:
        call_id: Twilio call SID
        business_phone: Phone number of the business
        
    Returns:
        BusinessInfo object or None if not found
    """
    if not business_phone:
        logger.warning("Empty business phone provided to get_business_info_cached")
        return None
        
    try:
        # Lookup the business in Supabase database
        business = get_business_by_phone(business_phone, call_id=call_id)
        
        if business:
            business_info = BusinessInfo(
                id=business.get("id"),
                name=business.get("name", "Our Business"),
                phone=business.get("phone"),
                type=business.get("type", "default"),
                cache_key=generate_business_key(business_phone)
            )
            logger.info(f"Found business in database: {business_info.name} (ID: {business_info.id}, Type: {business_info.type})")
            return business_info
        else:
            logger.info(f"No business found in database for phone {business_phone}")
            return None
            
    except Exception as e:
        logger.error(f"Error in cached business lookup: {str(e)}")
        return None


async def get_business_info(business_phone: str, call_id: str) -> tuple[str, str, Optional[str]]:
    """
    Get business information using a simple flow:
    1. Try to get from database via cache
    2. Fall back to configuration if not in database
    3. Default to "Our Business" if all else fails
    
    Args:
        business_phone: Phone number of the business
        call_id: Twilio call SID (for logging)
        
    Returns:
        (business_name, business_type, business_id) tuple
    """
    if not business_phone:
        logger.warning(f"No business phone provided for call {call_id}")
        return "Our Business", "default", None
        
    try:
        # First try to get from database
        business_info = await get_business_info_cached(call_id, business_phone)
        
        if business_info:
            # Found in database - use this info
            return business_info.name, business_info.type, business_info.id
        
        # Not in database - try to get name from Twilio config
        business_name = get_business_name(business_phone)
        logger.info(f"Using business name from config: {business_name}")
        
        # Return with default type
        return business_name, "default", None
            
    except Exception as e:
        logger.error(f"Error in business lookup: {str(e)}")
        return "Our Business", "default", None


async def run_bot(room_url: str, token: str, call_id: str, sip_uri: str, 
                 caller_phone: str, business_phone: str) -> None:
    """
    Run the voice bot with business-driven Twilio integration.
    
    Args:
        room_url: Daily room URL
        token: Daily room token
        call_id: Twilio call SID
        sip_uri: Daily SIP URI
        caller_phone: Phone number of the caller
        business_phone: Phone number of the business that was called
    """
    start_time = time.time()
    logger.info(f"Starting bot with room: {room_url}")
    logger.info(f"SIP endpoint: {sip_uri}")
    logger.info(f"Caller phone: {caller_phone}")
    logger.info(f"Business phone: {business_phone}")
    
    # Initialize cache if not already done
    cache = get_cache_instance()
    if not cache:
        logger.info("Initializing cache system")
        await initialize_cache()
        cache = get_cache_instance()
    
    # Initialize agent system if not already done
    await initialize_agent_system()
    
    # Get business information using simplified flow
    business_name, business_type, business_id = await get_business_info(business_phone, call_id)
    
    # Get appropriate agent for business type
    business_agent = get_agent_for_business_type(business_type)
    logger.info(f"Selected agent for business type '{business_type}': {business_agent.agent_id}")
    
    # Create agent context
    agent_context = AgentContext(
        business_id=business_id or "unknown",
        business_name=business_name,
        business_type=business_type,
        call_id=call_id,
        conversation_state={}
    )
    
    # Create the voice assistant
    assistant = VoiceAssistant(business_name, business_id)
    
    # Setup Daily transport
    transport = DailyTransport(
        room_url,
        token,
        "Voice Assistant",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            transcription_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )
    
    # Setup TTS service
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )
    
    # Setup LLM service
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Create agent-enhanced context
    if HAS_KNOWLEDGE_BASE and business_id:
        try:
            knowledge_base = KnowledgeBase()
            logger.info("Using agent-enhanced context with knowledge base")
        except Exception as e:
            logger.error(f"Error initializing knowledge base: {str(e)}")
            knowledge_base = None
    else:
        knowledge_base = None
    
    # Create context aggregator with agent-enhanced context
    context = create_agent_enhanced_context(
        assistant.context,
        business_agent,
        agent_context,
        knowledge_base
    )
    context_aggregator = llm.create_context_aggregator(context)
    
    # Build the pipeline
    pipeline = Pipeline([
        transport.input(),
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])
    
    # Create the pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True
        ),
    )
    
    setup_time = time.time()
    logger.info(f"Bot setup completed after {setup_time - start_time:.2f} seconds")
    
    # Event handlers
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        await assistant.handle_first_participant_joined(transport, participant["id"])
    
    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant['id']}, reason: {reason}")
        assistant.state = ConversationState.ENDING
        await task.cancel()
    
    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, cdata):
        # Pass the business_phone to the handler
        await assistant.handle_dial_in_ready(call_id, sip_uri, business_phone)
    
    @transport.event_handler("on_dialin_connected")
    async def on_dialin_connected(transport, data):
        logger.info(f"Dial-in connected: {data}")
        
        # Start the conversation after dial-in is connected
        if assistant.state == ConversationState.GREETING and not assistant.has_greeted:
            # Queue the initial context to trigger greeting
            logger.info("Queueing context frame to start conversation")
            await task.queue_frames([context_aggregator.user().get_context_frame()])
            assistant.has_greeted = True
            assistant.state = ConversationState.CHATTING
    
    @transport.event_handler("on_dialin_stopped")
    async def on_dialin_stopped(transport, data):
        logger.info(f"Dial-in stopped: {data}")
    
    @transport.event_handler("on_dialin_error")
    async def on_dialin_error(transport, data):
        logger.error(f"Dial-in error: {data}")
    
    @transport.event_handler("on_dialin_warning")
    async def on_dialin_warning(transport, data):
        logger.warning(f"Dial-in warning: {data}")
    
    try:
        # Run the pipeline
        runner = PipelineRunner()
        await runner.run(task)
    except Exception as e:
        logger.error(f"Error running bot pipeline: {str(e)}")
    finally:
        # Log final statistics
        total_time = time.time() - start_time
        logger.info(f"Bot session completed after {total_time:.2f} seconds")


async def main():
    """Parse command line arguments and run the bot."""
    parser = argparse.ArgumentParser(description="Daily + Twilio Voice Bot")
    parser.add_argument("-u", type=str, required=True, help="Daily room URL")
    parser.add_argument("-t", type=str, required=True, help="Daily room token")
    parser.add_argument("-i", type=str, required=True, help="Twilio call ID")
    parser.add_argument("-s", type=str, required=True, help="Daily SIP URI")
    parser.add_argument("-p", type=str, default="unknown-caller", help="Caller phone number")
    parser.add_argument("-b", type=str, default=None, help="Business phone number that was called")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not all([args.u, args.t, args.i, args.s]):
        logger.error("All arguments (-u, -t, -i, -s) are required")
        parser.print_help()
        sys.exit(1)
    
    await run_bot(args.u, args.t, args.i, args.s, args.p, args.b)


if __name__ == "__main__":
    asyncio.run(main())