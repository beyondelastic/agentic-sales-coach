"""
FastAPI backend server for AI Sales Coach application.
"""
import logging
import asyncio
import uuid
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict

from src.config import config
from src.agents.sales_coach_agent import SalesCoachAgent
from src.services.speech_service import SpeechService
from src.services.avatar_service import AvatarService
from src.models.report import PresentationSession, SalesCoachingReport

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global services
sales_coach: SalesCoachAgent = None
avatar_service: AvatarService = None

# Active sessions
active_sessions: Dict[str, PresentationSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting AI Sales Coach application")
    global sales_coach, avatar_service
    
    try:
        sales_coach = SalesCoachAgent()
        avatar_service = AvatarService()
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Sales Coach application")


# Create FastAPI app
app = FastAPI(
    title="AI Sales Coach",
    description="Real-time sales presentation analysis with AI-powered coaching",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Serve the main application page."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "sales_coach": sales_coach is not None,
            "avatar_service": avatar_service is not None
        }
    }


@app.get("/api/config")
async def get_config():
    """Get client configuration."""
    return {
        "speech_region": config.settings.speech_region,
        "model_name": config.settings.gpt_model_name,
        "rules": config.rules
    }


@app.get("/api/avatar/config")
async def get_avatar_config():
    """
    Get avatar configuration for WebRTC connection.
    
    Returns:
        dict: Avatar configuration including credentials and settings
    """
    logger.info("Avatar config requested")
    
    # IMPORTANT: Avatar feature is only available in specific regions
    # Supported regions: westus2, westeurope, southeastasia, eastus, westus
    # If your Speech Service is in swedencentral, you need to create a new one
    # in a supported region for avatar to work
    
    # For now, we'll try to use the configured region, but if it fails,
    # you'll need to create a Speech Service in westus2, westeurope, or eastus
    
    avatar_region = config.settings.speech_region
    
    # Avatar feature requires specific regions - check if current region is supported
    supported_avatar_regions = ['westus2', 'westeurope', 'southeastasia', 'eastus', 'westus']
    
    if avatar_region not in supported_avatar_regions:
        logger.warning(f"Region '{avatar_region}' may not support Avatar feature. Supported regions: {supported_avatar_regions}")
        # You could override to a supported region if you have a Speech Service there
        # avatar_region = "westeurope"  # Uncomment and set if you have a service in this region
    
    return {
        "subscription_key": config.settings.speech_key,
        "region": avatar_region,
        "supported_regions": supported_avatar_regions,
        "current_region_supported": avatar_region in supported_avatar_regions,
        "avatar_character": "Lisa",  # Try with capital L - some SDK versions are case-sensitive
        "avatar_style": "casual-sitting",
        "voice_name": "en-US-JennyNeural",
        "video_format": "webm",
        "video_codec": "vp9"
    }


@app.post("/api/session/start")
async def start_session():
    """
    Start a new presentation session.
    
    Returns:
        dict: Session information including session_id
    """
    session_id = str(uuid.uuid4())
    
    session = PresentationSession(
        session_id=session_id,
        transcript="",
        duration_seconds=0.0,
        segments=[]
    )
    
    active_sessions[session_id] = session
    
    logger.info(f"Started new session: {session_id}")
    
    return {
        "session_id": session_id,
        "status": "started",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/session/{session_id}/analyze")
async def analyze_presentation(session_id: str, transcript_data: dict):
    """
    Analyze a completed presentation.
    
    Args:
        session_id: Session identifier
        transcript_data: Contains transcript, duration, and segments
        
    Returns:
        dict: Analysis report and coaching script
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    # Update session with transcript data
    session.transcript = transcript_data.get("transcript", "")
    session.duration_seconds = transcript_data.get("duration", 0.0)
    
    if not session.transcript.strip():
        raise HTTPException(status_code=400, detail="Empty transcript")
    
    logger.info(f"Analyzing session {session_id}: {len(session.transcript)} characters")
    
    try:
        # Analyze presentation
        report = await sales_coach.analyze_presentation(session.transcript)
        session.report = report
        
        # Generate coaching script for avatar
        coaching_script = sales_coach.generate_coaching_script(report)
        
        logger.info(f"Analysis complete for session {session_id}")
        
        return {
            "session_id": session_id,
            "report": report.model_dump(),
            "coaching_script": coaching_script,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error analyzing session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/api/avatar/synthesize")
async def synthesize_avatar(request_data: dict):
    """
    Synthesize avatar video from coaching script.
    
    Args:
        request_data: Contains coaching_script text
        
    Returns:
        dict: Avatar video URL or audio playback confirmation
    """
    coaching_script = request_data.get("coaching_script", "")
    
    if not coaching_script.strip():
        raise HTTPException(status_code=400, detail="Empty coaching script")
    
    logger.info(f"Synthesizing avatar for {len(coaching_script)} characters")
    
    try:
        # For simplicity, synthesize to speaker
        # In production, could synthesize to video file and return URL
        avatar_service.synthesize_to_speaker(coaching_script)
        
        return {
            "status": "success",
            "message": "Coaching feedback delivered via audio",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error synthesizing avatar: {e}")
        raise HTTPException(status_code=500, detail=f"Avatar synthesis failed: {str(e)}")


@app.get("/api/session/{session_id}/report")
async def get_session_report(session_id: str):
    """
    Get the coaching report for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        dict: Session data including report
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    if not session.report:
        raise HTTPException(status_code=404, detail="Report not yet generated")
    
    return {
        "session_id": session_id,
        "transcript": session.transcript,
        "duration_seconds": session.duration_seconds,
        "report": session.report.model_dump(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete a session.
    
    Args:
        session_id: Session identifier
    """
    if session_id in active_sessions:
        del active_sessions[session_id]
        logger.info(f"Deleted session: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    
    raise HTTPException(status_code=404, detail="Session not found")


@app.websocket("/ws/interactive")
async def websocket_interactive_presentation(websocket: WebSocket):
    """
    WebSocket endpoint for interactive presentation with avatar.
    The avatar listens and responds naturally like a real customer.
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    logger.info(f"Interactive session started: {session_id}")
    
    # Track conversation
    conversation_history = []
    greeting_sent = False
    
    try:
        while True:
            # Receive events from client
            message = await websocket.receive_json()
            
            if message["type"] == "start_session":
                # Send welcome message only when user is ready
                await websocket.send_json({
                    "type": "avatar_speak",
                    "text": "Hi! I'm interested in learning about your product. Go ahead."
                })
                greeting_sent = True
                logger.info("Greeting sent")
                
            elif message["type"] == "transcript_update":
                # Just receive, don't respond yet - wait for pause
                presenter_text = message["text"]
                logger.info(f"Received: {presenter_text}")
                
            elif message["type"] == "pause_detected":
                # User paused - decide if avatar should speak
                recent_text = message.get("recent_text", "").strip()
                
                if not recent_text or len(recent_text.split()) < 5:
                    logger.info("Too short to respond")
                    continue
                
                # Don't respond if we just sent greeting
                if not greeting_sent:
                    logger.info("Waiting for greeting first")
                    continue
                
                logger.info(f"Considering response to: {recent_text[:100]}...")
                
                # Use AI to decide how to respond
                try:
                    response = await sales_coach.generate_natural_response(
                        recent_text,
                        conversation_history
                    )
                    
                    # Only speak if there's actually something to say
                    if response and response.strip() and len(response) > 2:
                        # Send response to avatar
                        await websocket.send_json({
                            "type": "avatar_speak",
                            "text": response
                        })
                        
                        # Add to conversation history
                        conversation_history.append({
                            "speaker": "presenter",
                            "text": recent_text
                        })
                        conversation_history.append({
                            "speaker": "customer",
                            "text": response
                        })
                        
                        logger.info(f"Avatar: {response}")
                    else:
                        logger.info("Avatar chose to stay silent")
                        # Still add presenter's text to history even if no response
                        conversation_history.append({
                            "speaker": "presenter",
                            "text": recent_text
                        })
                    
                except Exception as e:
                    logger.error(f"Error generating response: {e}")
            
            elif message["type"] == "end_presentation":
                # Generate final coaching report
                full_transcript = "\n".join([
                    f"{h['speaker'].upper()}: {h['text']}" 
                    for h in conversation_history
                ])
                
                logger.info("Generating final coaching report")
                
                # Pass transcript string directly to analyze_presentation
                if full_transcript:
                    report = await sales_coach.analyze_presentation(full_transcript)
                else:
                    # If no conversation, create a minimal report
                    report = SalesCoachingReport(
                        overall_score=0.0,
                        scores={},
                        strengths=[],
                        areas_for_improvement=[],
                        specific_recommendations=[],
                        next_steps=[]
                    )
                
                await websocket.send_json({
                    "type": "coaching_report",
                    "report": report.model_dump()
                })
                
                logger.info("Interactive session completed")
                break
                
    except WebSocketDisconnect:
        logger.info(f"Interactive session disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Interactive session error: {e}")
        await websocket.close()


@app.websocket("/ws/speech")
async def websocket_speech_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time speech recognition.
    
    Note: This is a placeholder for browser-based audio streaming.
    Current implementation uses Speech SDK with microphone directly.
    """
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    try:
        while True:
            # Receive audio data from client
            data = await websocket.receive_bytes()
            
            # Process audio chunk
            # In production, this would feed audio to Speech SDK streaming recognizer
            logger.debug(f"Received audio chunk: {len(data)} bytes")
            
            # Send back recognition result
            await websocket.send_json({
                "type": "partial",
                "text": "Processing audio..."
            })
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting uvicorn server")
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.settings.log_level.lower()
    )
