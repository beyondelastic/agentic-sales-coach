"""
Sales Coach Agent using Azure AI Foundry.
"""
import json
import logging
import asyncio
from typing import Dict, Any
from openai import AzureOpenAI

from src.config import config
from src.models.report import SalesCoachingReport, RuleViolation, ImprovementItem, CriteriaScores

logger = logging.getLogger(__name__)


class SalesCoachAgent:
    """
    AI agent for analyzing sales presentations and generating coaching reports.
    Uses Azure AI Foundry with GPT-4o for comprehensive transcript analysis.
    """
    
    def __init__(self):
        """Initialize the sales coach agent with Foundry client."""
        self.client = config.get_openai_client()
        self.model = config.settings.gpt_model_name
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build comprehensive system prompt with custom rules."""
        rules_section = config.get_rules_prompt_section()
        
        prompt = f"""# Role
You are an expert AI sales coach analyzing sales presentation transcripts to provide 
specific, actionable coaching feedback.

# Task
Analyze the provided sales presentation transcript and generate a structured improvement 
report with detailed scores, strengths, improvement areas, and rule compliance assessment.

# Analysis Criteria

## 1. Value Proposition Clarity (Score 1-10)
- Is the value proposition clear, compelling, and differentiated?
- Does it address specific customer needs?
- Is ROI or business impact quantified?

## 2. Objection Handling (Score 1-10)
- How well are concerns or objections addressed?
- Are responses confident and evidence-based?
- Does the presenter acknowledge and validate concerns?

## 3. Active Listening (Score 1-10)
- Does the presenter demonstrate understanding of customer needs?
- Are customer statements acknowledged and referenced?
- Is there genuine engagement with customer input?

## 4. Question Quality (Score 1-10)
- Are questions open-ended and discovery-focused?
- Do questions uncover deeper needs and pain points?
- Is there a good balance of asking vs. telling?

## 5. Call-to-Action (Score 1-10)
- Are next steps clear, specific, and actionable?
- Is there appropriate urgency without pressure?
- Does the CTA align with the customer's buying journey?

## 6. Engagement & Delivery (Score 1-10)
- Energy level and enthusiasm
- Minimal use of filler words (um, uh, like, you know)
- Confident and professional tone
- Clear and articulate speech

## 7. Rule Compliance (Score 1-10)
Evaluate adherence to the following custom rules:

{rules_section}

# Output Format

You MUST respond with valid JSON matching this exact structure:

{{
  "overall_score": <number 1-10>,
  "performance_level": "<excellent|good|fair|needs_improvement>",
  "criteria_scores": {{
    "value_proposition": <number 1-10>,
    "objection_handling": <number 1-10>,
    "active_listening": <number 1-10>,
    "question_quality": <number 1-10>,
    "call_to_action": <number 1-10>,
    "engagement": <number 1-10>,
    "rule_compliance": <number 1-10>
  }},
  "strengths": [
    "<specific strength with brief example>"
  ],
  "improvements": [
    {{
      "area": "<improvement category>",
      "current_state": "<what was observed>",
      "recommendation": "<specific action to take>",
      "example": "<direct quote from transcript or null>"
    }}
  ],
  "rule_violations": [
    {{
      "rule_category": "<politeness|company_wording|sales_structure|engagement>",
      "rule_name": "<specific rule>",
      "severity": "<low|medium|high>",
      "description": "<what was violated>",
      "example": "<quote showing violation or null>",
      "suggestion": "<how to fix>"
    }}
  ],
  "summary": "<2-3 sentence overall assessment>",
  "next_steps": [
    "<actionable recommendation>"
  ]
}}

# Guidelines

1. Base ALL feedback on evidence from the transcript
2. Be specific and constructive - avoid generic advice
3. Include direct quotes as examples wherever possible
4. Provide 3-5 strengths and 3-5 improvement areas
5. Focus on behaviors and techniques, not personality
6. Ensure recommendations are actionable and measurable
7. Calculate overall_score as weighted average of criteria scores
8. Set performance_level based on overall_score:
   - excellent: 9-10
   - good: 7-8
   - fair: 5-6
   - needs_improvement: 1-4

# Important
- Return ONLY valid JSON, no additional text or markdown
- Ensure all JSON strings are properly escaped
- Include at least 3 items in strengths, improvements, and next_steps
- Rule violations array can be empty if no violations detected
"""
        return prompt
    
    async def analyze_presentation(self, transcript: str) -> SalesCoachingReport:
        """
        Analyze a sales presentation transcript and generate coaching report.
        
        Args:
            transcript: Complete presentation transcript text
            
        Returns:
            SalesCoachingReport: Structured coaching report with scores and recommendations
        """
        logger.info(f"Analyzing presentation transcript ({len(transcript)} characters)")
        
        try:
            # Call GPT-4o for analysis
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Analyze this sales presentation transcript:\n\n{transcript}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000
            )
            
            # Parse JSON response
            result_json = response.choices[0].message.content
            logger.debug(f"Received analysis response: {result_json[:200]}...")
            
            result_data = json.loads(result_json)
            
            # Validate and parse into Pydantic model
            report = SalesCoachingReport(**result_data)
            
            logger.info(f"Analysis complete. Overall score: {report.overall_score}/10")
            return report
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise ValueError(f"Invalid JSON response from AI model: {e}")
        except Exception as e:
            logger.error(f"Error during presentation analysis: {e}")
            raise
    
    def generate_coaching_script(self, report: SalesCoachingReport) -> str:
        """
        Generate a conversational coaching script for avatar delivery.
        
        Args:
            report: The coaching report to convert to speech
            
        Returns:
            str: Natural language coaching script for avatar to speak
        """
        logger.info("Generating coaching script for avatar delivery")
        
        try:
            # Create prompt for script generation
            script_prompt = f"""
Convert this sales coaching report into a natural, conversational script that an AI avatar 
will speak to the presenter. The script should be encouraging, specific, and actionable.

Coaching Report (JSON):
{report.model_dump_json(indent=2)}

Create a 60-90 second script with this structure:
1. Warm opening with overall score
2. Highlight 2-3 key strengths
3. Discuss 2-3 main improvement areas with specific examples
4. End with encouragement and 1-2 actionable next steps

Make it conversational, supportive, and professional. Use "you" to address the presenter.
Return ONLY the script text, no additional formatting or labels.
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a supportive sales coach providing feedback."},
                    {"role": "user", "content": script_prompt}
                ],
                temperature=0.8,
                max_tokens=800
            )
            
            script = response.choices[0].message.content.strip()
            logger.info(f"Generated coaching script ({len(script)} characters)")
            
            return script
            
        except Exception as e:
            logger.error(f"Error generating coaching script: {e}")
            raise
    
    async def generate_customer_question(self, recent_transcript: str) -> str:
        """
        Generate a realistic customer question based on what the presenter just said.
        
        Args:
            recent_transcript: Recent portion of the presentation transcript
            
        Returns:
            str: A natural customer question
        """
        logger.info("Generating customer question")
        
        try:
            prompt = f"""You are a potential customer listening to a sales presentation. 
Based on what the salesperson just said, ask ONE brief, natural follow-up question that a real customer would ask.

Requirements:
- Keep it conversational and natural (like real speech)
- Make it specific to what they just mentioned
- Keep it under 20 words
- Ask about clarification, details, pricing, implementation, benefits, or comparisons
- Sound genuinely curious, not confrontational

What the salesperson said:
"{recent_transcript}"

Generate ONE customer question (return only the question text, no labels):"""
            
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a curious potential customer asking natural follow-up questions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                max_tokens=50
            )
            
            question = response.choices[0].message.content.strip()
            # Remove quotes if present
            question = question.strip('"\'')
            
            logger.info(f"Generated customer question: {question}")
            return question
            
        except Exception as e:
            logger.error(f"Error generating customer question: {e}")
            # Return a generic question as fallback
            return "Could you tell me more about that?"
    
    async def generate_natural_response(self, presenter_text: str, conversation_history: list) -> str:
        """
        Generate a natural customer response - or stay silent.
        Always responds to questions, engages naturally in conversation.
        
        Args:
            presenter_text: What the presenter just said
            conversation_history: Previous conversation exchanges
            
        Returns:
            str: Avatar's response (empty string means stay silent)
        """
        logger.info(f"Considering response to: {presenter_text[:80]}...")
        
        try:
            # Build recent conversation context
            context = "\n".join([
                f"{h['speaker'].upper()}: {h['text']}" 
                for h in conversation_history[-4:]
            ])
            
            # Check if it's clearly a question DIRECTED AT THE CUSTOMER
            # Only trigger on question marks or very specific question patterns
            is_question = (
                presenter_text.strip().endswith('?') or
                presenter_text.strip().endswith('??')
            )
            
            # Only check for question phrases at the START of sentences (more likely to be questions)
            sentence_starts = [s.strip().lower()[:20] for s in presenter_text.split('.') if s.strip()]
            is_question = is_question or any(
                start.startswith(q) for start in sentence_starts
                for q in ['what do you think', 'any questions', 'does that make sense', 
                         'do you have any', 'tell me what you']
            )
            
            prompt = f"""You are a customer in a sales meeting. The salesperson just spoke.

Recent conversation:
{context if context else "(Just started)"}

Salesperson: "{presenter_text}"

HOW TO RESPOND:

If they asked a DIRECT QUESTION (ends with ? and clearly directed at you):
- Answer naturally in 10-25 words

If they made a STATEMENT or are still presenting:
- STAY SILENT - let them finish their pitch
- Salespeople need time to explain their product
- Only respond if ALL of these are true:
  * They've clearly finished a major point (not just pausing mid-thought)
  * You have a critical clarification question
  * It feels natural for a customer to interject

Be a PATIENT listener - real customers don't interrupt every 10 seconds.
Most pauses are just the salesperson gathering their thoughts.

Response (or "SILENT" to stay quiet):"""
            
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an engaged customer in a sales conversation. Respond naturally to questions and engage in dialogue."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=60
            )
            
            avatar_response = response.choices[0].message.content.strip()
            avatar_response = avatar_response.strip('"\'')
            
            # If it's clearly a question, never stay silent
            if is_question:
                if not avatar_response or avatar_response.upper() in ['SILENT', 'SILENCE']:
                    # Generate a fallback response
                    avatar_response = "That's a good question. Could you elaborate a bit more?"
                    logger.info(f"✓ Question detected, forcing response: {avatar_response}")
                else:
                    logger.info(f"✓ Question detected, responding: {avatar_response}")
                return avatar_response
            
            # Check if AI chose to stay silent
            if avatar_response.upper() in ['SILENT', 'SILENCE', 'NO RESPONSE']:
                logger.info("✓ Staying silent (mid-thought)")
                return ""
            
            # If response is too generic/empty, stay silent
            if not avatar_response or len(avatar_response.strip()) < 2:
                logger.info("✓ Empty response, staying silent")
                return ""
            
            logger.info(f"✓ Responding: {avatar_response}")
            return avatar_response
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return ""
