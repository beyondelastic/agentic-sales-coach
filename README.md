# AI Sales Coach

Real-time AI-powered sales coaching with a live avatar that role-plays as your customer. Powered by Azure AI Foundry Voice Live (speech-to-speech) and GPT-4.1.

## Architecture

```
Browser
  │
  ├─── WebSocket (wss) ──────────────────────► Azure Voice Live
  │         mic PCM audio + events             (gpt-4.1 + lisa avatar)
  │
  │◄── WebRTC ───────────────────────────────── Azure Voice Live
  │         avatar video + audio stream
  │
  └─── REST ─────────────────────────────────► FastAPI Backend
            /api/voice-live/config               │
            /api/session/start                   │
            /api/session/{id}/analyze ───────────► Azure AI Foundry
            (transcript + webcam frames)           (GPT-4.1 report + vision)
```

The browser connects **directly** to Azure Voice Live via WebSocket for real-time bidirectional speech. The FastAPI backend only provisions config and runs the post-session coaching report (transcript analysis + webcam frame visual analysis).

## Features

- **Live avatar conversation**: `lisa/casual-sitting` avatar powered by Voice Live; responds naturally using server-side VAD
- **Real-time transcription**: Streaming transcript bubbles for both presenter and avatar turns
- **Echo cancellation**: Server-side AEC + browser `echoCancellation` prevent feedback loops
- **Coaching report**: GPT-4.1 analyzes the full transcript across 6 dimensions plus emotional tone
- **Visual presence analysis**: Webcam frames are captured every 30s during recording; GPT-4.1 vision analyzes facial expressions, eye contact, posture, professional appearance, and confidence arc
- **Custom rules**: JSON-configurable sales rules validated during analysis

## Quick Start

### Prerequisites

- Python 3.11+
- Azure AI Foundry project with a `gpt-4.1` deployment and Voice Live enabled
- Modern browser with microphone and webcam access

### Install

```bash
git clone <repository-url>
cd agentic-sales-coach
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env with your Azure credentials
```

Required environment variables:

```env
# Azure AI Foundry (used for GPT-4.1 report analysis via AIProjectClient)
FOUNDRY_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
FOUNDRY_PROJECT_NAME=<your-project-name>

# Voice Live (direct browser WebSocket connection)
VOICE_LIVE_KEY=<your-api-key>
VOICE_LIVE_ENDPOINT=https://<resource>.services.ai.azure.com

# Model names
VOICE_LIVE_MODEL=gpt-4.1
GPT_MODEL_NAME=gpt-4.1
```

Optional overrides (these have sensible defaults):

```env
VOICE_LIVE_VOICE_NAME=en-US-Ava:DragonHDLatestNeural
VOICE_LIVE_AVATAR_CHARACTER=lisa
VOICE_LIVE_AVATAR_STYLE=casual-sitting
FRAME_CAPTURE_INTERVAL_SECONDS=30   # seconds between webcam snapshots
FRAME_CAPTURE_MAX_COUNT=20          # max frames sent for visual analysis (evenly sampled)
GPT_API_VERSION=2024-10-21
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### Run

```bash
./start.sh
# or: uvicorn src.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## Usage

1. **Connect Avatar** — click "Connect Avatar"; the browser fetches config from `/api/voice-live/config`, starts a session, and opens the Voice Live WebSocket. WebRTC negotiation takes ~5-10 seconds.
2. **Start Presentation** — click "Start Presentation"; microphone is captured as PCM16 and streamed to Voice Live. The avatar responds naturally when you pause.
3. **Stop & Get Coaching** — click "Stop & Get Coaching"; the full transcript plus up to 20 evenly-sampled webcam frames are sent to `/api/session/{id}/analyze`. GPT-4.1 analyzes the transcript and a second vision call analyzes the frames. The coaching report appears in the browser.

## Coaching Report

GPT-4.1 evaluates the transcript across:

| Dimension | What it measures |
|---|---|
| Value Proposition | Clarity, differentiation, benefit framing |
| Objection Handling | Confidence and evidence when challenged |
| Active Listening | Acknowledging and adapting to customer cues |
| Question Quality | Open-ended discovery questions |
| Call-to-Action | Clear, specific next steps |
| Engagement & Delivery | Energy, tone, pacing |

The report also includes:
- **Emotional Tone**: overall sentiment, confidence level, energy level, key moments, authenticity note
- **Visual Presence** *(webcam)*: facial expressions, eye contact, posture & gestures, professional appearance, confidence arc — analyzed by GPT-4.1 vision from evenly-sampled webcam frames
- **Rule Violations**: any breaches of custom rules in `config/rules.json`
- **Strengths**, **Improvements**, **Next Steps**

## Project Structure

```
agentic-sales-coach/
├── src/
│   ├── agents/
│   │   └── sales_coach_agent.py    # GPT-4.1 report + visual analysis
│   ├── models/
│   │   └── report.py               # Pydantic report models (incl. VisualAnalysis)
│   ├── config.py                   # Settings + Azure clients
│   └── main.py                     # FastAPI app (6 endpoints)
├── static/
│   ├── index.html                  # UI
│   ├── app_with_avatar.js          # Voice Live WS + WebRTC client
│   └── pcm-worklet.js              # AudioWorklet PCM capture
├── config/
│   └── rules.json                  # Custom coaching rules
├── .env                            # Credentials (not committed)
├── requirements.txt
└── start.sh
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve `index.html` |
| `GET` | `/health` | Health check |
| `GET` | `/api/voice-live/config` | WebSocket URL + avatar config for browser |
| `POST` | `/api/session/start` | Create a new session |
| `POST` | `/api/session/{id}/analyze` | Run GPT-4.1 coaching analysis (transcript + visual) |
| `DELETE` | `/api/session/{id}` | Clean up session |

## Custom Sales Rules

Edit `config/rules.json`:

```json
{
  "rules": [
    {
      "id": "rule_1",
      "name": "Professional Greeting",
      "description": "Presentation should start with a professional greeting",
      "type": "structure",
      "validation_criteria": "Check if presentation begins with greeting"
    }
  ]
}
```

## Troubleshooting

**Avatar video doesn't appear**
- Check browser console for ICE/WebRTC errors
- Confirm `VOICE_LIVE_KEY` and `VOICE_LIVE_ENDPOINT` are correct
- Ensure the Foundry resource has Voice Live and avatar enabled

**No audio / avatar is silent**
- Verify the `gpt-4.1` model deployment exists in your Foundry resource
- Check that `VOICE_LIVE_MODEL` matches your deployment name

**Coaching report is empty or truncated**
- Confirm `GPT_MODEL_NAME` deployment exists and has sufficient quota
- GPT-5 is NOT supported (reasoning model — exhausts token budget on chain-of-thought); use `gpt-4.1`
- Minimum transcript length is needed for meaningful analysis

**Visual Presence section missing from report**
- Webcam permission must be granted before starting the session
- Check browser console for `[Visual]` log entries; if 0 frames are logged, check camera access
- Visual analysis is non-critical — if it fails the transcript report is still returned

**Echo / feedback loop**
- Browser AEC is enabled automatically; ensure headphones are used or room is quiet
- Server-side echo cancellation is configured via Voice Live session params
