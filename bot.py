"""Twilio + Daily voice bot implementation with business lookup - hybrid approach."""

import argparse
import asyncio
import os
import sys

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

# Import only the Supabase helper for business lookup
from utils.supabase_helper import get_business_by_phone

# Setup logging
load_dotenv()
logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# Initialize Twilio client
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

async def run_bot(room_url: str, token: str, call_id: str, sip_uri: str, caller_phone: str) -> None:
    """Run the voice bot with the given parameters."""
    logger.info(f"Starting bot with room: {room_url}")
    logger.info(f"SIP endpoint: {sip_uri}")
    logger.info(f"Caller phone: {caller_phone}")

    # Default business information
    business_name = "Our Business"  # Default name
    
    # PHASE 1: Business Lookup
    # This is separated from the bot setup to isolate any issues
    try:
        # Get call details from Twilio API
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
            logger.info(f"Found business: {business_name}")
        else:
            logger.warning(f"No business found for number {twilio_number}, using default")
    except Exception as e:
        logger.error(f"Error in business lookup: {str(e)}")
        logger.warning("Using default business name due to error")
    
    # Track if call has been forwarded
    call_already_forwarded = False

    # PHASE 2: Bot Setup
    # This follows the minimal working structure
    
    # Setup the Daily transport
    transport = DailyTransport(
        room_url,
        token,
        "Phone Bot",
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

    # Construct the greeting message with the business name
    greeting_message = f"Hello! Welcome to {business_name}. How can I help you today?"
    
    # Create system prompt with business name
    system_prompt = (
        f"You are a friendly phone assistant for {business_name}. "
        "Your responses will be read aloud, so keep them concise and conversational. "
        f"Begin by greeting the caller with 'Welcome to {business_name}!' and asking how you can help them today."
    )
    
    # Set up the conversation context
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        # Explicitly add the greeting as the first assistant message
        {
            "role": "assistant",
            "content": greeting_message,
        },
    ]

    # Setup the context and aggregator
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Build the minimal pipeline
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

    # PHASE 3: Event Handlers
    # Only use the standard event handlers that worked in the minimal version
    
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"First participant joined: {participant['id']}")
        await transport.capture_participant_transcription(participant["id"])
        
        # Queue the context frame to start the conversation
        logger.info(f"Queueing context with greeting: {greeting_message}")
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant['id']}, reason: {reason}")
        await task.cancel()

    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, cdata):
        nonlocal call_already_forwarded

        if call_already_forwarded:
            logger.warning("Call already forwarded, ignoring this event.")
            return

        logger.info(f"Forwarding call {call_id} to {sip_uri}")

        try:
            # Forward the call to the Daily SIP endpoint
            twilio_client.calls(call_id).update(
                twiml=f"<Response><Dial><Sip>{sip_uri}</Sip></Dial></Response>"
            )
            logger.info("Call forwarded successfully")
            call_already_forwarded = True
        except Exception as e:
            logger.error(f"Failed to forward call: {str(e)}")
            raise

    @transport.event_handler("on_dialin_connected")
    async def on_dialin_connected(transport, data):
        logger.info(f"Dial-in connected: {data}")

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