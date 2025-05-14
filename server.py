"""Webhook server with simple monitoring."""

import os
import shlex
import subprocess
import time
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.voice_response import VoiceResponse
from utils.daily_helpers import create_sip_room

# Load environment variables
load_dotenv()

# Import simple monitoring
from monitoring import (
    initialize_monitoring,
    monitor_performance,
    logger,
    log_context,
    metrics,
    add_metrics_endpoint,
    update_system_metrics
)

# Initialize monitoring
initialize_monitoring()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session
    app.state.session = aiohttp.ClientSession()
    logger.info("Server starting up")
    
    yield
    
    # Cleanup
    await app.state.session.close()
    await metrics.shutdown()
    logger.info("Server shutdown complete")

app = FastAPI(lifespan=lifespan)

# Add metrics endpoint
add_metrics_endpoint(app)

@app.get("/call", response_class=PlainTextResponse)
async def handle_call_get(request: Request):
    """Handle GET request to /call endpoint (for testing)."""
    return "This endpoint expects a POST request from Twilio. Please configure your Twilio webhook to send POST requests to this URL."

@monitor_performance("twilio_webhook")
@app.post("/call", response_class=PlainTextResponse)
async def handle_call_post(request: Request):
    """Handle incoming Twilio call webhook."""
    start_time = time.time()
    correlation_id = f"twilio_{int(time.time() * 1000)}"
    
    with log_context(correlation_id=correlation_id, operation="twilio_webhook"):
        logger.info("Received call webhook from Twilio")

        try:
            # Get form data
            form_data = await request.form()
            data = dict(form_data)

            # Extract call ID
            call_sid = data.get("CallSid")
            if not call_sid:
                raise HTTPException(status_code=400, detail="Missing CallSid in request")

            with log_context(call_id=call_sid):
                # Extract phone numbers
                caller_phone = str(data.get("From", "unknown-caller"))
                called_phone = str(data.get("To", "unknown-caller"))
                
                logger.info("Processing call", 
                          caller_phone=caller_phone, 
                          called_phone=called_phone)

                # Create Daily room
                try:
                    room_details = await create_sip_room(request.app.state.session, caller_phone)
                except Exception as e:
                    logger.error("Failed to create Daily room", error=str(e))
                    raise HTTPException(status_code=500, detail=f"Failed to create Daily room: {str(e)}")

                # Log room creation
                room_creation_duration = time.time() - start_time
                logger.info("Daily room created", duration_seconds=room_creation_duration)

                # Extract room details
                room_url = room_details["room_url"]
                token = room_details["token"]
                sip_endpoint = room_details["sip_endpoint"]

                if not sip_endpoint:
                    raise HTTPException(status_code=500, detail="No SIP endpoint provided by Daily")

                # Start bot process
                bot_cmd = f"python bot.py -u {room_url} -t {token} -i {call_sid} -s {sip_endpoint} -p {caller_phone}"
                try:
                    cmd_parts = shlex.split(bot_cmd)
                    subprocess.Popen(cmd_parts)
                    logger.info("Bot process started", command=bot_cmd)
                except Exception as e:
                    logger.error("Failed to start bot", error=str(e))
                    raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

                # Generate TwiML response
                resp = VoiceResponse()
                resp.pause(length=2)
                resp.say("Please wait while we connect you to our assistant...")
                resp.play(
                    url="https://therapeutic-crayon-2467.twil.io/assets/US_ringback_tone.mp3",
                    loop=50,
                )

                # Log completion
                total_duration = time.time() - start_time
                logger.info("TwiML response generated", total_duration_seconds=total_duration)
                
                return str(resp)

        except HTTPException as e:
            logger.error("HTTP error in webhook", error=str(e), status_code=e.status_code)
            raise
        except Exception as e:
            logger.error("Unexpected error in webhook", error=str(e))
            raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Update system metrics
    await update_system_metrics()
    
    return {
        "status": "healthy",
        "monitoring": {
            "metrics_enabled": metrics.enabled,
            "structured_logging": True
        }
    }

@app.get("/test-call")
async def test_call():
    """Test endpoint."""
    return {"message": "This is a test endpoint. The actual /call endpoint expects POST requests from Twilio."}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting server", port=port)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)