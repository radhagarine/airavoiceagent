"""Knowledge-Enhanced Voice Bot - Fixed Version with Proper Greeting Flow."""

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
from twilio.rest import Client

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.frames.frames import TextFrame

# Import helpers
from utils.supabase_helper import get_business_by_phone

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

# Initialize Twilio client
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))


class ConversationState(Enum):
    """Represents the current state of the conversation."""
    INITIALIZING = "initializing"
    GREETING = "greeting" 
    CHATTING = "chatting"
    ENDING = "ending"


@dataclass
class QueryResponse:
    """Holds the response from LLM along with the original query for context."""
    response: str
    was_enhanced: bool = False


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
    
    async def enhance_query_with_knowledge(self, user_query: str) -> str:
        """Enhance user query with knowledge base context if available."""
        if not self.has_knowledge:
            return user_query
        
        try:
            # Query the knowledge base
            relevant_chunks = self.knowledge_base.query(self.business_id, user_query, top_k=3)
            
            if relevant_chunks:
                # Create enhanced context
                context_text = "\n".join(relevant_chunks)
                enhanced_query = f"""
Context from our knowledge base:
{context_text}

User question: {user_query}

Please answer the user's question using the provided context when relevant. If the context doesn't contain relevant information, answer based on your general knowledge about restaurants/businesses.
"""
                logger.info(f"Enhanced query with {len(relevant_chunks)} knowledge chunks")
                return enhanced_query
        except Exception as e:
            logger.error(f"Error enhancing query with knowledge: {str(e)}")
        
        return user_query
    
    async def handle_dial_in_ready(self, call_id: str, sip_uri: str):
        """Handle when dial-in is ready - forward the call."""
        if self.call_forwarded:
            logger.warning("Call already forwarded, ignoring")
            return
        
        logger.info(f"Forwarding call {call_id} to {sip_uri}")
        
        try:
            twilio_client.calls(call_id).update(
                twiml=f"<Response><Dial><Sip>{sip_uri}</Sip></Dial></Response>"
            )
            logger.info("Call forwarded successfully")
            self.call_forwarded = True
        except Exception as e:
            logger.error(f"Failed to forward call: {str(e)}")
            raise


# Custom context aggregator that intercepts messages for knowledge enhancement
class KnowledgeEnhancedContext(OpenAILLMContext):
    """Extends OpenAILLMContext to enhance user messages with knowledge base."""
    
    def __init__(self, messages, assistant: VoiceAssistant):
        super().__init__(messages)
        self.assistant = assistant
    
    async def get_messages_for_llm(self):
        """Override to enhance the last user message if needed."""
        messages = await super().get_messages_for_llm()
        
        # Enhance the last user message if knowledge base is available
        if self.assistant.has_knowledge and messages and messages[-1].get("role") == "user":
            user_query = messages[-1]["content"]
            enhanced_query = await self.assistant.enhance_query_with_knowledge(user_query)
            
            # Replace the last message with enhanced version
            enhanced_messages = messages[:-1] + [{"role": "user", "content": enhanced_query}]
            return enhanced_messages
        
        return messages


async def get_business_info(call_id: str, caller_phone: str) -> tuple[str, Optional[str]]:
    """Get business information from Twilio number with caching."""
    try:
        # Get call details from Twilio
        call_details = twilio_client.calls(call_id).fetch()
        twilio_number = call_details.to
        logger.info(f"Call was made to Twilio number: {twilio_number}")
        
        # Use cached business lookup
        business_info = await get_business_info_cached(call_id, twilio_number)
        
        if business_info:
            return business_info.name, business_info.id
        else:
            logger.warning(f"No business found for number {twilio_number}")
            return "Our Business", None
            
    except Exception as e:
        logger.error(f"Error in business lookup: {str(e)}")
        return "Our Business", None

@cache_business_lookup()
async def get_business_info_cached(call_id: str, twilio_number: str) -> Optional[BusinessInfo]:
    """Get business information with caching."""
    try:
        # Get call details from Twilio
        call_details = twilio_client.calls(call_id).fetch()
        
        # Look up the business for this Twilio number
        business = get_business_by_phone(twilio_number, call_id=call_id)
        
        if not business and call_details.to_formatted:
            # Try with formatted number
            business = get_business_by_phone(call_details.to_formatted, call_id=call_id)
        
        if business:
            business_info = BusinessInfo(
                id=business.get("id"),
                name=business.get("name", "Our Business"),
                phone=business.get("phone"),
                cache_key=generate_business_key(twilio_number)
            )
            logger.info(f"Found business: {business_info.name} (ID: {business_info.id})")
            return business_info
        else:
            logger.warning(f"No business found for number {twilio_number}")
            return BusinessInfo(
                id=None,
                name="Our Business",
                phone=twilio_number,
                cache_key=generate_business_key(twilio_number)
            )
            
    except Exception as e:
        logger.error(f"Error in cached business lookup: {str(e)}")
        return BusinessInfo(
            id=None,
            name="Our Business",
            phone=twilio_number,
            cache_key=generate_business_key(twilio_number)
        )

async def run_bot(room_url: str, token: str, call_id: str, sip_uri: str, caller_phone: str) -> None:
    """Run the voice bot with cache integration."""
    start_time = time.time()
    logger.info(f"Starting bot with room: {room_url}")
    logger.info(f"SIP endpoint: {sip_uri}")
    logger.info(f"Caller phone: {caller_phone}")
    
    # Initialize cache if not already done
    cache = get_cache_instance()
    if not cache:
        logger.info("Initializing cache system")
        await initialize_cache()
        cache = get_cache_instance()
    
    # Get business information with caching
    business_name, business_id = await get_business_info(call_id, caller_phone)
    
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
    
    # Use knowledge-enhanced context if available
    if assistant.has_knowledge:
        context = KnowledgeEnhancedContext(assistant.context, assistant)
        logger.info("Using knowledge-enhanced context with cache")
    else:
        context = OpenAILLMContext(assistant.context)
        logger.info("Using standard context")
    
    # Setup context aggregator
    context_aggregator = llm.create_context_aggregator(context)
    
    # Build the simple pipeline
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
        await assistant.handle_dial_in_ready(call_id, sip_uri)
    
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
        
        # Log cache statistics if available
        if cache:
            stats = cache.get_stats()
            logger.info("Cache statistics for this session", **stats.get("performance", {}))


async def main():
    """Parse command line arguments and run the bot."""
    parser = argparse.ArgumentParser(description="Daily + Twilio Voice Bot")
    parser.add_argument("-u", type=str, required=True, help="Daily room URL")
    parser.add_argument("-t", type=str, required=True, help="Daily room token")
    parser.add_argument("-i", type=str, required=True, help="Twilio call ID")
    parser.add_argument("-s", type=str, required=True, help="Daily SIP URI")
    parser.add_argument("-p", type=str, default="unknown-caller", help="Caller phone number")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not all([args.u, args.t, args.i, args.s]):
        logger.error("All arguments (-u, -t, -i, -s) are required")
        parser.print_help()
        sys.exit(1)
    
    await run_bot(args.u, args.t, args.i, args.s, args.p)


if __name__ == "__main__":
    asyncio.run(main())