"""
FastAPI backend server for AI Sales Coach application.
"""
import logging
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict

from src.config import config
from src.agents.sales_coach_agent import SalesCoachAgent
from src.models.report import PresentationSession

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global services
sales_coach: SalesCoachAgent = None

# Active sessions
active_sessions: Dict[str, PresentationSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    logger.info("Starting AI Sales Coach application")
    global sales_coach

    try:
        sales_coach = SalesCoachAgent()
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    yield

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
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "sales_coach": sales_coach is not None,
        }
    }


@app.get("/api/voice-live/config")
async def get_voice_live_config():
    """Return Voice Live credentials and session parameters for the browser client."""
    if not config.settings.voice_live_key:
        raise HTTPException(
            status_code=503,
            detail="Voice Live not configured. Set VOICE_LIVE_KEY (and optionally VOICE_LIVE_ENDPOINT) in .env"
        )

    instructions = sales_coach.build_voice_live_instructions()

    return {
        "ws_url": config.get_voice_live_ws_url(),
        "api_key": config.settings.voice_live_key,
        "model": config.settings.voice_live_model,
        "voice_name": config.settings.voice_live_voice_name,
        "avatar_character": config.settings.voice_live_avatar_character,
        "avatar_style": config.settings.voice_live_avatar_style,
        "frame_interval_ms": config.settings.frame_capture_interval_seconds * 1000,
        "frame_max_count": config.settings.frame_capture_max_count,
        "instructions": instructions,
    }


@app.post("/api/session/start")
async def start_session():
    """Start a new presentation session and return its ID."""
    session_id = str(uuid.uuid4())
    active_sessions[session_id] = PresentationSession(
        session_id=session_id,
        transcript="",
        duration_seconds=0.0,
        segments=[]
    )
    logger.info(f"Started new session: {session_id}")
    return {
        "session_id": session_id,
        "status": "started",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/session/{session_id}/analyze")
async def analyze_presentation(session_id: str, transcript_data: dict):
    """Analyze a completed presentation and return the coaching report."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = active_sessions[session_id]
    session.transcript = transcript_data.get("transcript", "")
    session.duration_seconds = transcript_data.get("duration", 0.0)
    frames = transcript_data.get("frames", [])  # optional webcam frames for visual analysis

    if not session.transcript.strip():
        raise HTTPException(status_code=400, detail="Empty transcript")

    logger.info(f"Analyzing session {session_id}: {len(session.transcript)} characters")

    try:
        report = await sales_coach.analyze_presentation(session.transcript, frames=frames or None)
        session.report = report
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


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_id in active_sessions:
        del active_sessions[session_id]
        logger.info(f"Deleted session: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


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
