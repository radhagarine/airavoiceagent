"""Twilio + Daily voice bot implementation with knowledge base integration."""

import argparse
import asyncio
import os
import sys
import logging

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
from pipecat.processors.frame_processor import FrameProcessor

# Import the knowledge base and Supabase helpers
from utils.knowledge_base import KnowledgeBase
from utils.supabase_helper import get_business_by_phone

# Setup logging
load_dotenv()
logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# Initialize Twilio client
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

# Initialize knowledge base
try:
    kb = KnowledgeBase()
    knowledge_base_available = True
    logger.info("Knowledge base initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize knowledge base: {str(e)}")
    logger.warning("Voice agent will run without knowledge base capabilities")
    knowledge_base_available = False


class KnowledgeEnhancerProcessor(FrameProcessor):
    """Processor that enhances user queries with knowledge base context."""
    
    def __init__(self, business_id: str):
        """Initialize the knowledge enhancer processor.
        
        Args:
            business_id: The ID of the business whose knowledge base to query
        """
        super().__init__()
        self.business_id = business_id
        logger.info(f"Initialized KnowledgeEnhancerProcessor for business {business_id}")
    
    async def process_frame(self, frame, direction):
        """Process a frame by adding knowledge base context.
        
        Args:
            frame: The frame to process
            direction: The direction of the frame in the pipeline
        """
        # Call the parent class's process_frame method first
        await super().process_frame(frame, direction)
        
        # Only process text frames with user input
        if isinstance(frame, TextFrame) and hasattr(frame, "text"):
            user_query = frame.text
            logger.info(f"User query: {user_query}")
            
            # Get relevant knowledge base entries
            kb_results = kb.query(self.business_id, user_query)
            
            if kb_results:
                # Format the context
                kb_context = "\n".join(kb_results)
                logger.info(f"Found {len(kb_results)} relevant KB entries")
                
                # Enhance the text with the knowledge base context
                enhanced_text = (
                    f"User query: {user_query}\n\n"
                    f"Context from knowledge base:\n{kb_context}"
                )
                frame.text = enhanced_text
            else:
                logger.info("No relevant knowledge base entries found")
                # No need to modify the frame, just pass it through

async def run_bot(room_url: str, token: str, call_id: str, sip_uri: str, caller_phone: str) -> None:
    """Run the voice bot with the given parameters.

    Args:
        room_url: The Daily room URL
        token: The Daily room token
        call_id: The Twilio call ID
        sip_uri: The Daily SIP URI for forwarding the call
        caller_phone: The phone number of the caller
    """
    logger.info(f"Starting bot with room: {room_url}")
    logger.info(f"SIP endpoint: {sip_uri}")
    logger.info(f"Caller phone: {caller_phone}")

    # Get the Twilio number that received the call
    try:
        # Get call details from Twilio API
        call_details = twilio_client.calls(call_id).fetch()
        twilio_number = call_details.to
        logger.info(f"Call was made to Twilio number: {twilio_number}")
        
        # Look up the business for this Twilio number
        logger.info(f"About to call get_business_by_phone with number: {twilio_number}")
        business = get_business_by_phone(twilio_number)
        business_name = None
        knowledge_integration = False  # Default to no integration
        
        if not business:
            logger.warning(f"No business found for Twilio number {twilio_number}, using generic bot")
            # Try one more time with raw format from Twilio
            logger.info(f"Trying raw Twilio number format: {call_details.to_formatted}")
            business = get_business_by_phone(call_details.to_formatted)
            
            if business:
                business_id = business.get("id")
                business_name = business.get("name")
                logger.info(f"Found business with formatted number: {business_name} (ID: {business_id})")
            else:
                business_id = None
        else:
            business_id = business.get("id")
            business_name = business.get("name")
            logger.info(f"Found business: {business_name} (ID: {business_id})")
            
        if not knowledge_base_available:
            logger.warning("Knowledge base is not available, using generic bot")
            knowledge_integration = False
        elif not business_id:
            logger.warning("No business ID found, using generic bot")
            knowledge_integration = False
        elif kb.business_has_knowledge_base(business_id):
            logger.info(f"Business {business_id} has a knowledge base")
            knowledge_integration = True
        else:
            logger.info(f"Found business ID: {business_id}")
            # Check if business has a knowledge base
            if kb.business_has_knowledge_base(business_id):
                logger.info(f"Business {business_id} has a knowledge base")
                knowledge_integration = True
            else:
                logger.warning(f"Business {business_id} has no knowledge base, using generic bot")
                knowledge_integration = False
    except Exception as e:
        logger.error(f"Error looking up business: {str(e)}")
        # Fallback to generic bot
        business_id = None
        knowledge_integration = False

    call_already_forwarded = False

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

    # Initialize LLM context with system prompt
    system_prompt = (
        "You are a friendly phone assistant for a business. "
        "Your responses will be read aloud, so keep them concise and conversational. "
        "Avoid special characters or formatting. "
    )
    
    # Add business name to greeting if available
    greeting = "Begin by greeting the caller and asking how you can help them today."
    if business_name:
        greeting = f'Begin by greeting the caller with "Welcome to {business_name}!" and asking how you can help them today.'
    
    # If we have knowledge base integration, enhance the system prompt
    if knowledge_integration:
        system_prompt += (
            "\n\nYou have access to a knowledge base with information about the business. "
            "When answering queries, use the provided context information to give accurate "
            "and specific answers. If the context doesn't contain relevant information, "
            "be honest about not having that specific information and offer to help with "
            "something else or take a message."
            "\n\nWhen the user's query is provided, it will include both the original query "
            "and relevant context from the knowledge base. Use this to inform your responses."
        )
    
    system_prompt += "\n\n" + greeting
    
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
    ]

    # Setup the conversational context
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Build the pipeline
    pipeline_processors = [
        transport.input(),
    ]
    
    # Add knowledge base processor if we have a business ID and knowledge base is available
    if knowledge_integration and business_id and knowledge_base_available:
        knowledge_processor = KnowledgeEnhancerProcessor(business_id)
        pipeline_processors.append(knowledge_processor)
    
    # Add the rest of the processors
    pipeline_processors.extend([
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])
    
    # Create the pipeline
    pipeline = Pipeline(pipeline_processors)

    # Create the pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True  # Enable barge-in so callers can interrupt the bot
        ),
    )

    # Handle participant joining
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"First participant joined: {participant['id']}")
        await transport.capture_participant_transcription(participant["id"])
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    # Handle participant leaving
    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant['id']}, reason: {reason}")
        await task.cancel()

    # Handle call ready to forward
    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, cdata):
        nonlocal call_already_forwarded

        # We only want to forward the call once
        # The on_dialin_ready event will be triggered for each sip endpoint provisioned
        if call_already_forwarded:
            logger.warning("Call already forwarded, ignoring this event.")
            return

        logger.info(f"Forwarding call {call_id} to {sip_uri}")

        try:
            # Update the Twilio call with TwiML to forward to the Daily SIP endpoint
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
        logger.debug(f"Dial-in connected: {data}")

    @transport.event_handler("on_dialin_stopped")
    async def on_dialin_stopped(transport, data):
        logger.debug(f"Dial-in stopped: {data}")

    @transport.event_handler("on_dialin_error")
    async def on_dialin_error(transport, data):
        logger.error(f"Dial-in error: {data}")
        # If there is an error, the bot should leave the call
        # This may be also handled in on_participant_left with
        # await task.cancel()

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
    
    # Optional caller phone number
    parser.add_argument("-p", type=str, default="unknown-caller", help="Caller phone number")

    args = parser.parse_args()

    # Validate required arguments
    if not all([args.u, args.t, args.i, args.s]):
        logger.error("All arguments (-u, -t, -i, -s) are required")
        parser.print_help()
        sys.exit(1)

    await run_bot(args.u, args.t, args.i, args.s, args.p)


if __name__ == "__main__":
    asyncio.run(main())