"""Twilio + Daily voice bot implementation with proper state management - Fixed Version."""

import argparse
import asyncio
import os
import sys
from enum import Enum
from typing import Optional

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

# Import the Supabase helper for business lookup
from utils.supabase_helper import get_business_by_phone

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


class VoiceAssistant:
    """Main voice assistant class that manages conversation state and flow."""
    
    def __init__(self, business_name: str = "Our Business", business_id: Optional[str] = None):
        self.business_name = business_name
        self.business_id = business_id
        self.state = ConversationState.INITIALIZING
        self.has_greeted = False
        self.call_forwarded = False
        self.conversation_started = False
        
        # Clean context - no pre-loaded messages
        self.context = [
            {
                "role": "system",
                "content": self._build_system_prompt()
            }
        ]
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM."""
        return (
            f"You are a friendly and helpful phone assistant for {self.business_name}. "
            "You are speaking with a customer who called our phone number. "
            "Your responses will be read aloud, so keep them concise, conversational, and natural. "
            "Do not repeat greetings - the caller has already been greeted when the call started. "
            "Focus on helping the customer with their questions or needs. "
            "If you don't know specific information, politely let them know and offer to help in other ways."
        )
    
    async def handle_first_participant_joined(self, transport, participant_id: str, task: PipelineTask):
        """Handle when the first participant joins the call."""
        logger.info(f"First participant joined: {participant_id}")
        await transport.capture_participant_transcription(participant_id)
        
        # Send greeting immediately
        await self._send_greeting(task)
        self.state = ConversationState.CHATTING
    
    async def _send_greeting(self, task: PipelineTask):
        """Send the greeting message directly to TTS."""
        if self.has_greeted:
            return
        
        greeting = f"Hello! Thank you for calling {self.business_name}. How can I help you today?"
        logger.info(f"Sending greeting: {greeting}")
        
        # Send directly to TTS (not through LLM)
        greeting_frame = TextFrame(greeting)
        await task.queue_frames([greeting_frame])
        
        # Add to context for conversation history
        self.context.append({"role": "assistant", "content": greeting})
        self.has_greeted = True
    
    async def start_conversation(self, context_aggregator, task: PipelineTask):
        """Start the conversation flow after greeting."""
        if self.conversation_started:
            return
            
        logger.info("Starting conversation flow")
        initial_frame = context_aggregator.user().get_context_frame()
        await task.queue_frames([initial_frame])
        self.conversation_started = True
    
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


async def get_business_info(call_id: str, caller_phone: str) -> tuple[str, Optional[str]]:
    """Get business information from Twilio number and Supabase lookup."""
    try:
        # Get call details from Twilio
        call_details = twilio_client.calls(call_id).fetch()
        twilio_number = call_details.to
        logger.info(f"Call was made to Twilio number: {twilio_number}")
        
        # Look up the business for this Twilio number
        business = get_business_by_phone(twilio_number)
        
        if not business and call_details.to_formatted:
            # Try with formatted number
            business = get_business_by_phone(call_details.to_formatted)
        
        if business:
            business_name = business.get("name", "Our Business")
            business_id = business.get("id")
            logger.info(f"Found business: {business_name} (ID: {business_id})")
            return business_name, business_id
        else:
            logger.warning(f"No business found for number {twilio_number}")
            return "Our Business", None
    except Exception as e:
        logger.error(f"Error in business lookup: {str(e)}")
        return "Our Business", None


async def run_bot(room_url: str, token: str, call_id: str, sip_uri: str, caller_phone: str) -> None:
    """Run the voice bot with proper state management."""
    logger.info(f"Starting bot with room: {room_url}")
    logger.info(f"SIP endpoint: {sip_uri}")
    logger.info(f"Caller phone: {caller_phone}")
    
    # Get business information
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
    
    # Setup context aggregator
    context = OpenAILLMContext(assistant.context)
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
    
    # Event handlers
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        await assistant.handle_first_participant_joined(transport, participant["id"], task)
    
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
        # Start conversation after dial-in is connected
        if assistant.has_greeted and not assistant.conversation_started:
            await assistant.start_conversation(context_aggregator, task)
    
    @transport.event_handler("on_dialin_stopped")
    async def on_dialin_stopped(transport, data):
        logger.info(f"Dial-in stopped: {data}")
    
    @transport.event_handler("on_dialin_error")
    async def on_dialin_error(transport, data):
        logger.error(f"Dial-in error: {data}")
    
    @transport.event_handler("on_dialin_warning")
    async def on_dialin_warning(transport, data):
        logger.warning(f"Dial-in warning: {data}")
    
    # Run the pipeline
    runner = PipelineRunner()
    await runner.run(task)


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