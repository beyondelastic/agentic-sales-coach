# 🎯 AI Sales Coach - Interactive Avatar Edition

Real-time AI-powered sales coaching application with an interactive avatar that acts as your customer during presentations. Built with Azure AI Foundry, Azure Speech Service, and GPT-4o.

## ✨ Features

### 🎭 Interactive AI Avatar
- **Real-time conversation**: Avatar acts as a customer, asking questions and responding naturally
- **WebRTC video streaming**: Low-latency, high-quality avatar display (1920x1080, 25 FPS)
- **Natural interactions**: Detects pauses, responds to questions, engages in dialogue
- **Speech synthesis**: Avatar speaks with natural voice and lip-sync

### 🎤 Speech Recognition
- **Real-time transcription**: Continuous speech-to-text during presentations
- **Conversation bubbles**: Separate message bubbles for you and the avatar
- **Smart pause detection**: Avatar responds after natural pauses (4 seconds)
- **Feedback prevention**: Microphone stops during avatar speech

### 🤖 AI-Powered Analysis
- **GPT-4o evaluation**: Analyzes sales techniques and presentation skills
- **Custom rule validation**: Checks politeness, company wording, sales structure
- **6-dimension scoring**: Value proposition, objection handling, active listening, questions, CTA, engagement
- **Actionable feedback**: Specific recommendations for improvement

## 🏗️ Architecture

```
┌─────────────────┐
│   Frontend      │
│  (HTML/JS)      │
│  - Web Speech   │
│  - Azure SDK    │
│  - WebRTC       │
└────────┬────────┘
         │
    WebSocket
         │
┌────────▼────────┐
│   Backend       │
│  (FastAPI)      │
│  - Speech STT   │
│  - GPT-4o       │
│  - Avatar TTS   │
└────────┬────────┘
         │
    ┌────▼────────────────┐
    │  Azure Services     │
    │  - AI Foundry       │
    │  - Speech Service   │
    │  - OpenAI (GPT-4o)  │
    └─────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Azure AI Foundry project with GPT-4o deployment
- Azure Speech Service (eastus, S0 tier for avatar support)
- Modern web browser with microphone access

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd agentic-sales-coach
```

2. **Set up environment**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure Azure credentials**
```bash
cp .env.example .env
# Edit .env with your Azure credentials
```

Required environment variables:
```env
# Azure AI Foundry
AZURE_OPENAI_ENDPOINT=https://your-foundry-resource.services.ai.azure.com
AZURE_OPENAI_KEY=your-key-here
GPT_MODEL_NAME=gpt-4o
GPT_API_VERSION=2024-10-21

# Azure Speech Service (must be eastus for avatar)
SPEECH_REGION=eastus
SPEECH_KEY=your-speech-key-here
```

4. **Run the application**
```bash
./start.sh
```

5. **Open browser**
```
http://localhost:8000
```

## 📖 Usage Guide

### Step 1: Connect Avatar
1. Click **"🎭 Connect Avatar"** button
2. Wait 10-20 seconds for WebRTC connection (connection phases shown in status)
3. Avatar video appears and status shows "✅ Avatar connected - Ready for interactive presentation"

### Step 2: Start Presentation
1. Click **"▶️ Start Presentation"** button
2. Allow microphone access when prompted
3. Avatar greets you: "Hi! I'm interested in learning about your product. Go ahead."
4. Deliver your sales presentation

### Step 3: Interactive Conversation
- **Speak naturally**: Present your product/service
- **Avatar responds**: Asks questions, requests clarification, shows interest
- **Answer questions**: Avatar reacts to your responses
- **Conversation bubbles**: See dialogue in real-time (separate bubbles for you and avatar)

### Step 4: End & Get Coaching
1. Click **"⏹️ Stop & Get Coaching"** button
2. Wait for GPT-4o analysis (10-15 seconds)
3. Review detailed coaching report with scores and recommendations

## 🔧 Configuration

### Custom Sales Rules
Edit `config/sales_rules.json` to customize validation rules:
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

### Avatar Settings
Avatar configuration in `src/services/avatar_service.py`:
- **Character**: `lisa` (professional female avatar)
- **Style**: `casual-sitting` (sitting posture)
- **Voice**: `en-US-JennyMultilingualNeural`
- **Region**: Must be `eastus` for avatar support

## 🏭 Azure Resources Setup

### 1. Create Azure AI Foundry Project
```bash
az login
az account set --subscription <subscription-id>

# Create via portal: ai.azure.com
# 1. Create new project
# 2. Deploy GPT-4o model
# 3. Copy endpoint and key
```

### 2. Create Speech Service (Critical: eastus)
```bash
az cognitiveservices account create \
  --name sales-coach-speech-eastus \
  --resource-group <your-rg> \
  --location eastus \
  --kind SpeechServices \
  --sku S0

az cognitiveservices account keys list \
  --name sales-coach-speech-eastus \
  --resource-group <your-rg> \
  --query "key1" -o tsv
```

**Important**: Avatar feature requires:
- Region: `eastus`, `westus2`, `westeurope`, or `southeastasia`
- Tier: `S0` (Standard)

## 📊 Coaching Report

The AI generates a comprehensive report including:

### Scores (1-10)
1. **Value Proposition Clarity**: Clear, compelling, differentiated value
2. **Objection Handling**: Confidence and evidence in addressing concerns
3. **Active Listening**: Understanding and engaging with customer needs
4. **Question Quality**: Open-ended, discovery-focused questions
5. **Call-to-Action**: Clear, specific next steps
6. **Engagement & Delivery**: Energy, tone, articulation

### Recommendations
- **Strengths**: What you did well
- **Areas for Improvement**: Specific gaps identified
- **Specific Recommendations**: Actionable steps
- **Next Steps**: How to prepare for the next meeting

## 🛠️ Development

### Project Structure
```
agentic-sales-coach/
├── src/
│   ├── agents/
│   │   └── sales_coach_agent.py    # GPT-4o sales coach
│   ├── services/
│   │   ├── speech_service.py       # Azure Speech STT
│   │   └── avatar_service.py       # Avatar configuration
│   ├── models/
│   │   └── report.py               # Pydantic models
│   ├── config.py                   # Configuration loader
│   └── main.py                     # FastAPI application
├── static/
│   ├── index.html                  # UI
│   └── app_with_avatar.js          # Frontend logic
├── config/
│   └── sales_rules.json            # Custom rules
├── .env                            # Environment variables
├── requirements.txt                # Python dependencies
└── start.sh                        # Launch script
```

### Key Endpoints

**REST API**
- `GET /` - Serve frontend
- `GET /api/avatar/config` - Get avatar configuration
- `POST /api/session/start` - Start new session

**WebSocket**
- `WS /ws/interactive` - Real-time conversation
  - `start_session` - Initialize greeting
  - `transcript_update` - Send speech text
  - `pause_detected` - Trigger avatar response
  - `avatar_speak` - Avatar response
  - `end_presentation` - Get coaching report

## 🐛 Troubleshooting

### Avatar won't connect
- Verify Speech Service is in `eastus` region
- Check SKU is `S0` (Standard tier)
- Confirm Speech Key is correct
- Check browser console for WebRTC errors

### Avatar hears itself
- Ensure `shouldRestartRecognition` flag is working
- Check `avatarIsSpeaking` blocks speech recognition
- Verify 1-second buffer after avatar speech

### Avatar interrupts incorrectly
- Question detection only triggers on `?` or sentence-starting question phrases
- Review `is_question` logic in `sales_coach_agent.py`
- Adjust pause detection timeout (currently 4 seconds)

### WebRTC connection slow
- Normal: 10-20 seconds for initial connection
- Azure Speech SDK backend processing time
- Cannot be optimized further (server-side)

## 📝 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Support

For issues or questions:
- Open a GitHub issue
- Check Azure AI Foundry documentation
- Review Azure Speech Service avatar docs

---

**Built with ❤️ using Azure AI Services**
