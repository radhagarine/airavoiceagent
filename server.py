"""Webhook server to handle Twilio calls and start the voice bot."""

import os
import shlex
import subprocess
import time
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import VoiceResponse
from utils.daily_helpers import create_sip_room

# Load environment variables
load_dotenv()


# Initialize FastAPI app with aiohttp session
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session to be used for Daily API calls
    app.state.session = aiohttp.ClientSession()
    yield
    # Close session when shutting down
    await app.state.session.close()


app = FastAPI(lifespan=lifespan)


# Handle both GET and POST for the /call endpoint
@app.get("/call", response_class=PlainTextResponse)
async def handle_call_get(request: Request):
    """Handle GET request to /call endpoint (for testing)."""
    return "This endpoint expects a POST request from Twilio. Please configure your Twilio webhook to send POST requests to this URL."


@app.post("/call", response_class=PlainTextResponse)
async def handle_call_post(request: Request):
    """Handle incoming Twilio call webhook."""
    start_time = time.time()
    print(f"Received call webhook from Twilio at {start_time}")

    try:
        # Get form data from Twilio webhook
        form_data = await request.form()
        data = dict(form_data)

        # Print the complete request form data
        print("--- COMPLETE TWILIO REQUEST DATA ---")
        for key, value in data.items():
            print(f"{key}: {value}")
        print("-----------------------------------")

        # Extract call ID (required to forward the call later)
        call_sid = data.get("CallSid")
        if not call_sid:
            raise HTTPException(status_code=400, detail="Missing CallSid in request")

        # Extract the caller's phone number
        caller_phone = str(data.get("From", "unknown-caller"))
        print(f"Processing call with ID: {call_sid} from {caller_phone}")

        # Extract the called phone number
        called_phone = str(data.get("To", "unknown-caller"))
        print(f"Call to: {called_phone}")

        # Create a Daily room with SIP capabilities
        try:
            room_details = await create_sip_room(request.app.state.session, caller_phone)
        except Exception as e:
            print(f"Error creating Daily room: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {str(e)}")

        # Log timing after creating Daily room
        room_time = time.time()
        print(f"Created Daily room after {room_time - start_time:.2f} seconds")

        # Print the complete room details
        print("--- ROOM DETAILS ---")
        for key, value in room_details.items():
            print(f"{key}: {value}")
        print("-------------------")

        # Extract necessary details
        room_url = room_details["room_url"]
        token = room_details["token"]
        sip_endpoint = room_details["sip_endpoint"]

        # Make sure we have a SIP endpoint
        if not sip_endpoint:
            raise HTTPException(status_code=500, detail="No SIP endpoint provided by Daily")

        # Start the bot process with the caller's phone number
        bot_cmd = f"python bot.py -u {room_url} -t {token} -i {call_sid} -s {sip_endpoint} -p {caller_phone}"
        try:
            # Use shlex to properly split the command for subprocess
            cmd_parts = shlex.split(bot_cmd)

            # CHANGE: Keep stdout/stderr for debugging
            # Start the bot in the background but capture output
            subprocess.Popen(
                cmd_parts,
                # Don't redirect output so we can see logs
                # stdout=subprocess.DEVNULL,
                # stderr=subprocess.DEVNULL
            )
            print(f"Started bot process with command: {bot_cmd}")
        except Exception as e:
            print(f"Error starting bot: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

        # Generate TwiML response to put the caller on hold with music
        resp = VoiceResponse()
        resp.pause(length=2)  # 2 second pause
        resp.say("Please wait while we connect you to our assistant...")
        resp.play(
            url="https://therapeutic-crayon-2467.twil.io/assets/US_ringback_tone.mp3",
            loop=50,
        )

        # Log timing before returning TwiML
        twiml_time = time.time()
        print(f"Returning TwiML after {twiml_time - start_time:.2f} seconds")
        return str(resp)

    except HTTPException as e:
        print(f"HTTP Error after {time.time() - start_time:.2f} seconds: {e}")
        raise
    except Exception as e:
        print(f"Error after {time.time() - start_time:.2f} seconds: {e}")
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy"}


# Add a test endpoint to simulate a call (for development only)
@app.get("/test-call")
async def test_call():
    """Test endpoint to simulate a Twilio call (development only)."""
    return {"message": "This is a test endpoint. The actual /call endpoint expects POST requests from Twilio."}


if __name__ == "__main__":
    # Run the server
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)