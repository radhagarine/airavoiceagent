"""Updated server.py with simplified business-driven Twilio integration."""

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

# Import the Twilio handler with simplified interface
from utils.twilio_handler import get_twilio_manager, get_client_for_phone

# Load environment variables
load_dotenv()

# Import monitoring and cache
from monitoring_system import (
    initialize_monitoring,
    initialize_memory_leak_detection,
    monitor_performance,
    logger,
    log_context,
    metrics,
    add_metrics_endpoint,
    update_system_metrics,
    get_memory_report,
    shutdown_monitoring,
    track_object_creation
)
from cache.simplified_cache import (
    initialize_cache,
    shutdown_cache,
    get_cache_health,
    get_cache_stats
)

# Import agent system
from agents import initialize_agent_system, shutdown_agent_system, get_agent_system

# Initialize monitoring
initialize_monitoring()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session
    app.state.session = aiohttp.ClientSession()
    logger.info("Server starting up")
    
    # Initialize Twilio business manager
    app.state.twilio_manager = get_twilio_manager()
    accounts = app.state.twilio_manager.get_all_accounts()
    phone_count = len(app.state.twilio_manager.get_all_phone_mappings())
    logger.info(f"Initialized Twilio Business Manager with {len(accounts)} accounts and {phone_count} phone mappings")

    # Initialize monitoring
    initialize_monitoring()
    initialize_memory_leak_detection(enabled=os.getenv("MEMORY_LEAK_DETECTION", "true").lower() == "true")
    
    # Initialize cache system
    logger.info("Initializing cache system")
    try:
        await initialize_cache()
        logger.info("Cache system initialized successfully")
        
        # Warm cache with common business lookups if available
        common_phones = []  # Add your most common business phones here
        if common_phones:
            await warm_business_lookups(common_phones)
            logger.info(f"Cache warmed with {len(common_phones)} business lookups")
    except Exception as e:
        logger.error(f"Failed to initialize cache: {str(e)}")
        logger.warning("Continuing without cache")
    
    # Initialize agent system
    logger.info("Initializing agent system")
    try:
        await initialize_agent_system()
        logger.info("Agent system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize agent system: {str(e)}")
        logger.warning("Continuing without agent system")
    
    yield
    
    # Cleanup
    await app.state.session.close()
    
    # Shutdown agent system
    logger.info("Shutting down agent system")
    try:
        await shutdown_agent_system()
        logger.info("Agent system shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down agent system: {str(e)}")
    
    # Shutdown cache system
    logger.info("Shutting down cache system")
    try:
        await shutdown_cache()
        logger.info("Cache system shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down cache: {str(e)}")
    
    # Shutdown monitoring
    await shutdown_monitoring()
    await metrics.shutdown()
    logger.info("Server shutdown complete")

app = FastAPI(lifespan=lifespan, title="Voice Bot Webhook Server with Business-Driven Twilio Integration", version="1.0.0")

# Add metrics endpoint
add_metrics_endpoint(app)

@app.get("/call", response_class=PlainTextResponse)
async def handle_call_get(request: Request):
    """Handle GET request to /call endpoint (for testing)."""
    return "This endpoint expects a POST request from Twilio. Please configure your Twilio webhook to send POST requests to this URL."

@monitor_performance("twilio_webhook")
@app.post("/call", response_class=PlainTextResponse)
async def handle_call_post(request: Request):
    """Handle incoming Twilio call webhook with simplified business-driven Twilio integration."""
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
                # Extract phone numbers - extract both caller and called numbers
                caller_phone = str(data.get("From", "unknown-caller"))
                called_phone = str(data.get("To", "unknown-called"))
                
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

                # Start bot process with business phone parameter
                # Escape the phone numbers to ensure command line safety
                escaped_caller = shlex.quote(caller_phone)
                escaped_called = shlex.quote(called_phone)
                
                bot_cmd = f"python bot.py -u {room_url} -t {token} -i {call_sid} -s {sip_endpoint} -p {escaped_caller} -b {escaped_called}"
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

@app.get("/twilio/accounts")
async def list_twilio_accounts(request: Request):
    """List all configured Twilio accounts (masked for security)."""
    twilio_manager = request.app.state.twilio_manager
    return {
        "accounts": twilio_manager.get_all_accounts(),
        "count": len(twilio_manager.accounts)
    }

@app.get("/twilio/phone-mappings")
async def list_phone_mappings(request: Request):
    """List all phone-to-account mappings (masked for security)."""
    twilio_manager = request.app.state.twilio_manager
    return {
        "mappings": twilio_manager.get_all_phone_mappings(),
        "count": len(twilio_manager.phone_map)
    }

@app.get("/health")
async def health_check():
    """Health check endpoint with cache and agent status."""
    # Update system metrics
    await update_system_metrics()
    
    # Get cache health
    cache_health = await get_cache_health()
    
    # Get agent system health
    agent_system = get_agent_system()
    agent_health = await agent_system.health_check() if agent_system else {"status": "not_initialized"}
    
    # Overall health determination
    overall_health = "healthy"
    if cache_health.get("status") != "healthy":
        overall_health = "degraded"
    if agent_health.get("status") not in ["healthy", "not_initialized"]:
        overall_health = "degraded"
    
    return {
        "status": overall_health,
        "timestamp": time.time(),
        "monitoring": {
            "metrics_enabled": metrics.enabled,
            "structured_logging": True
        },
        "cache": cache_health,
        "agents": agent_health,
        "components": {
            "cache": cache_health.get("status", "unknown"),
            "redis_l2": cache_health.get("l2_cache", {}).get("status", "unknown"),
            "agents": agent_health.get("status", "unknown"),
            "monitoring": "healthy"
        }
    }

@app.get("/cache/stats")
async def cache_statistics():
    """Get cache statistics endpoint."""
    return get_cache_stats()

@app.get("/cache/health")
async def cache_health_check():
    """Dedicated cache health check endpoint."""
    return await get_cache_health()

@app.post("/cache/warm")
async def warm_cache_endpoint(phones: list[str]):
    """Manually trigger cache warming for business lookups."""
    try:
        await warm_business_lookups(phones)
        return {
            "status": "success",
            "message": f"Cache warming initiated for {len(phones)} phone numbers",
            "phones": phones
        }
    except Exception as e:
        logger.error("Cache warming failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cache warming failed: {str(e)}")

# Agent system endpoints
@app.get("/agents/health")
async def agent_health_check():
    """Get agent system health status."""
    agent_system = get_agent_system()
    if not agent_system:
        return {
            "status": "not_initialized",
            "error": "Agent system not initialized"
        }
    
    return await agent_system.health_check()

@app.get("/agents/stats")
async def agent_statistics():
    """Get agent system statistics."""
    agent_system = get_agent_system()
    if not agent_system:
        return {
            "error": "Agent system not initialized"
        }
    
    registry_stats = agent_system.registry.get_registry_stats()
    factory_stats = agent_system.factory.get_factory_stats()
    
    return {
        "registry": registry_stats,
        "factory": factory_stats,
        "system": {
            "initialized": agent_system.is_initialized,
            "registered_types": len(agent_system.registry),
            "cached_agents": len(agent_system.factory._agent_cache)
        }
    }

@app.get("/agents/types")
async def list_agent_types():
    """List all registered agent types."""
    agent_system = get_agent_system()
    if not agent_system:
        return {"error": "Agent system not initialized"}
    
    return {
        "registered_types": agent_system.registry.get_registered_types(),
        "default_type": agent_system.registry._default_agent_type
    }

@app.get("/test-call")
async def test_call():
    """Test endpoint."""
    return {"message": "This is a test endpoint. The actual /call endpoint expects POST requests from Twilio."}

# Development endpoint for testing cache
@app.get("/dev/cache-test")
async def test_cache():
    """Development endpoint to test cache functionality."""
    if not os.getenv("ENVIRONMENT") == "development":
        raise HTTPException(status_code=403, detail="This endpoint is only available in development")
    
    try:
        from cache import get_cache_instance
        cache = get_cache_instance()
        
        if not cache:
            return {"error": "Cache not initialized"}
        
        # Test basic cache operations
        test_key = "test_key"
        test_value = {"test": "data", "timestamp": time.time()}
        
        # Set a value
        await cache.set(test_key, test_value)
        
        # Get the value
        retrieved = await cache.get(test_key)
        
        # Get stats
        stats = cache.get_stats()
        
        return {
            "cache_operational": True,
            "test_set_get": retrieved == test_value,
            "stats": stats
        }
    except Exception as e:
        logger.error("Cache test failed", error=str(e))
        return {
            "cache_operational": False,
            "error": str(e)
        }

# Development endpoint for testing agents
@app.get("/dev/agent-test")
async def test_agent():
    """Development endpoint to test agent functionality."""
    if not os.getenv("ENVIRONMENT") == "development":
        raise HTTPException(status_code=403, detail="This endpoint is only available in development")
    
    try:
        agent_system = get_agent_system()
        if not agent_system:
            return {"error": "Agent system not initialized"}
        
        # Test each agent type
        test_results = {}
        for business_type in ["restaurant", "retail", "service", "default"]:
            try:
                agent = agent_system.get_agent_for_business(business_type)
                health = await agent.health_check()
                stats = agent.get_stats()
                
                test_results[business_type] = {
                    "agent_id": agent.agent_id,
                    "health": health,
                    "stats": stats
                }
            except Exception as e:
                test_results[business_type] = {
                    "error": str(e)
                }
        
        return {
            "agent_system_operational": True,
            "test_results": test_results,
            "summary": {
                "total_types_tested": len(test_results),
                "successful_tests": len([r for r in test_results.values() if "error" not in r]),
                "failed_tests": len([r for r in test_results.values() if "error" in r])
            }
        }
    except Exception as e:
        logger.error("Agent test failed", error=str(e))
        return {
            "agent_system_operational": False,
            "error": str(e)
        }

# Add memory endpoints
@app.get("/memory/report")
async def memory_report():
    """Get detailed memory usage report."""
    return get_memory_report()

@app.get("/memory/snapshot")
async def memory_snapshot():
    """Get current memory snapshot with leak detection."""
    if not os.getenv("ENVIRONMENT") == "development":
        raise HTTPException(status_code=403, detail="Memory snapshots only available in development")
    
    import tracemalloc
    import gc
    import psutil
    
    # Force garbage collection
    gc.collect()
    
    # Get tracemalloc snapshot
    if tracemalloc.is_tracing():
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('traceback')
        
        return {
            "memory_usage_mb": psutil.Process().memory_info().rss / 1024 / 1024,
            "top_allocations": [
                {
                    "size_mb": stat.size / 1024 / 1024,
                    "count": stat.count,
                    "traceback": stat.traceback.format()
                }
                for stat in top_stats[:10]
            ],
            "gc_stats": gc.get_stats()
        }
    else:
        return {"error": "tracemalloc not enabled"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting server with cache and agent integration", port=port)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)