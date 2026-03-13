"""
Configuration management for the sales coach application.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any
from pydantic_settings import BaseSettings
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Azure AI Foundry
    foundry_endpoint: str
    foundry_project_name: str
    
    # Azure Speech Service (unused — kept for backwards compat, not required)
    speech_key: str = ""
    speech_region: str = ""
    
    # Azure AI Language (for emotion analysis)
    language_endpoint: str = ""
    language_key: str = ""
    
    # Azure AI Video Indexer (for facial emotion analysis)
    video_indexer_account_id: str = ""
    video_indexer_location: str = "trial"  # "trial" or Azure region like "eastus"
    video_indexer_resource_id: str = ""  # ARM resource ID for production
    video_indexer_api_key: str = ""  # For trial accounts
    
    # Model Configuration
    gpt_model_name: str = "gpt-4.1"
    gpt_api_version: str = "2024-10-21"
    
    # Application Settings
    environment: str = "development"
    log_level: str = "INFO"
    
    # Voice Live API (Speech-to-Speech)
    # voice_live_endpoint: Foundry resource base URL, e.g. https://myresource.services.ai.azure.com
    # Falls back to foundry_endpoint if not set. Can also be a cognitiveservices.azure.com URL.
    voice_live_endpoint: str = ""
    # voice_live_key: API key for the Foundry / Speech-in-Foundry resource.
    # Leave empty to disable Voice Live interactive mode.
    voice_live_key: str = ""
    # Model: gpt-4.1 recommended — uses Azure STT+TTS for best transcription quality and HD voices.
    # Alternatives: gpt-realtime (native audio, lower latency), gpt-4o, gpt-4.1-mini
    voice_live_model: str = "gpt-4.1"
    # Azure TTS voice for the avatar — HD voice requires region support (eastus, westus2, westeurope, etc.)
    voice_live_voice_name: str = "en-US-Ava:DragonHDLatestNeural"
    # Avatar character and style
    voice_live_avatar_character: str = "lisa"
    voice_live_avatar_style: str = "casual-sitting"

    # Visual analysis — webcam frame sampling during recording
    # FRAME_CAPTURE_INTERVAL_SECONDS: how often a snapshot is taken (default: 30s)
    # FRAME_CAPTURE_MAX_COUNT: max frames sent to GPT vision; evenly sampled across the session (default: 20)
    frame_capture_interval_seconds: int = 30
    frame_capture_max_count: int = 20

    # Optional: Application Insights
    applicationinsights_connection_string: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = False


class AppConfig:
    """Global application configuration manager."""
    
    def __init__(self):
        self.settings = Settings()
        self._rules: Dict[str, Any] = {}
        self._project_client: AIProjectClient | None = None
        self._credential = DefaultAzureCredential()
        
        # Load custom rules
        self._load_rules()
    
    def _load_rules(self):
        """Load custom coaching rules from JSON configuration file."""
        rules_path = Path(__file__).parent.parent / "config" / "rules.json"
        
        if not rules_path.exists():
            raise FileNotFoundError(f"Rules configuration not found at {rules_path}")
        
        with open(rules_path, 'r') as f:
            self._rules = json.load(f)
    
    @property
    def rules(self) -> Dict[str, Any]:
        """Get custom coaching rules."""
        return self._rules
    
    @property
    def project_client(self) -> AIProjectClient:
        """Get or create Azure AI Foundry project client."""
        if self._project_client is None:
            self._project_client = AIProjectClient(
                endpoint=self.settings.foundry_endpoint,
                credential=self._credential
            )
        return self._project_client
    
    def get_openai_client(self):
        """Get OpenAI client configured for Azure AI Foundry."""
        return self.project_client.get_openai_client(
            api_version=self.settings.gpt_api_version
        )

    def get_voice_live_ws_url(self) -> str:
        """Build the Voice Live WebSocket URL from the configured endpoint."""
        base = (self.settings.voice_live_endpoint or self.settings.foundry_endpoint).rstrip("/")
        ws_base = base.replace("https://", "wss://")
        return (
            f"{ws_base}/voice-live/realtime"
            f"?api-version=2025-10-01"
            f"&model={self.settings.voice_live_model}"
        )
    
    def get_rules_prompt_section(self) -> str:
        """Generate prompt section containing custom rules for agent instructions."""
        rules_data = self._rules.get("rules", {})
        
        prompt_sections = []
        
        # Politeness rules
        if "politeness" in rules_data:
            politeness = rules_data["politeness"]
            prompt_sections.append(f"""
## Politeness & Professionalism
- Required phrases to include: {', '.join(politeness.get('required_phrases', []))}
- Forbidden phrases to avoid: {', '.join(politeness.get('forbidden_phrases', []))}
- Weight: {politeness.get('weight', 0.2)}
""")
        
        # Company wording rules
        if "company_wording" in rules_data:
            wording = rules_data["company_wording"]
            terms_text = []
            for avoid, prefer_list in wording.get("preferred_terms", {}).items():
                terms_text.append(f"  - Instead of '{avoid}', use: {', '.join(prefer_list)}")
            
            prompt_sections.append(f"""
## Company Wording Standards
{chr(10).join(terms_text)}
- Weight: {wording.get('weight', 0.25)}
""")
        
        # Sales structure rules
        if "sales_structure" in rules_data:
            structure = rules_data["sales_structure"]
            elements_text = []
            for element in structure.get("required_elements", []):
                elements_text.append(f"  - {element['name']}: {element['description']}")
            
            prompt_sections.append(f"""
## Sales Presentation Structure
Required elements in order:
{chr(10).join(elements_text)}
- Order matters: {structure.get('order_matters', True)}
- Weight: {structure.get('weight', 0.3)}
""")
        
        # Engagement criteria
        if "engagement" in rules_data:
            engagement = rules_data["engagement"]
            criteria = engagement.get("criteria", {})
            
            filler = criteria.get("filler_words", {})
            questions = criteria.get("questions", {})
            
            prompt_sections.append(f"""
## Engagement & Delivery
- Filler words: Maximum {filler.get('max_count_per_minute', 5)} per minute
  Examples: {', '.join(filler.get('examples', []))}
- Questions: Minimum {questions.get('min_count', 2)} engaging questions
- Weight: {engagement.get('weight', 0.25)}
""")
        
        return "\n".join(prompt_sections)


# Global configuration instance
config = AppConfig()
