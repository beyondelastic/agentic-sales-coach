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
    
    # Azure Speech Service
    speech_key: str
    speech_region: str
    
    # Model Configuration
    gpt_model_name: str = "gpt-4o"
    gpt_api_version: str = "2024-10-21"
    
    # Application Settings
    environment: str = "development"
    log_level: str = "INFO"
    
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
