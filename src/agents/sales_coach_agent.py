"""
Sales Coach Agent using Azure AI Foundry.
"""
import json
import logging
import asyncio
from typing import Dict, Any
from openai import AzureOpenAI

from src.config import config
from typing import List, Optional
from src.models.report import SalesCoachingReport, RuleViolation, ImprovementItem, CriteriaScores, VisualAnalysis

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
You are a rigorous, expert B2B sales coach. Your job is to give accurate, honest scores
that reflect the true quality of a sales presentation — not an encouraging average.

# Transcript Format
The transcript uses speaker labels:
- **PRESENTER:** — the salesperson being evaluated (the human you are coaching)
- **CUSTOMER:** — the AI-simulated prospect (ignore these lines when scoring the presenter)

Score ONLY what the PRESENTER says. Customer replies are context, not evidence.

# Scoring Principles — READ CAREFULLY
- A score of 5/10 means mediocre. It is NOT a safe default.
- If a required element is ABSENT, the score for that criterion must be 1-3.
- If the presentation is very short or contains only small talk, overall score ≤ 3.
- If no solution was presented, `value_proposition` and `call_to_action` must be ≤ 2.
- If no customer pain points were explored, `question_quality` and `active_listening` must be ≤ 3.
- Scores of 7+ require specific supporting evidence quoted from the transcript.
- The overall_score must be the weighted average of the criterion scores — do NOT round up.

# Analysis Criteria (score each 1-10 with evidence)

## 1. Value Proposition Clarity (weight 25%)
Award points ONLY if the presenter clearly explained:
- What the specific product/service/solution is (name it)
- What concrete problem it solves for THIS customer
- Quantified or specific business value (ROI, time saved, risk reduced)
Score 1-2: solution not mentioned at all
Score 3-4: solution vaguely referenced, no specifics
Score 5-6: basic explanation, missing business value quantification
Score 7-8: clear explanation with customer-relevant benefits
Score 9-10: compelling, differentiated, ROI-quantified, tied to discovered pain points

## 2. Discovery & Question Quality (weight 20%)
Award points ONLY for questions the PRESENTER asked:
Score 1-2: no discovery questions asked
Score 3-4: only surface-level or yes/no questions
Score 5-6: some open-ended questions but shallow
Score 7-8: multiple deep discovery questions uncovering real needs
Score 9-10: systematic discovery that reveals pain, impact, and priority

## 3. Objection Handling (weight 15%)
Score 1-2: no objections arose or all were ignored/dodged
Score 3-4: acknowledged but not resolved
Score 5-6: adequate response but not compelling
Score 7-8: confident, evidence-based responses
Score 9-10: masterful — turned objection into selling point

## 4. Active Listening (weight 15%)
Score 1-2: presenter ignored or talked over customer responses
Score 3-4: minimal acknowledgement of what customer said
Score 5-6: repeated customer points but didn't adapt pitch
Score 7-8: clearly built on customer input
Score 9-10: every pivot tied to something the customer said

## 5. Call-to-Action (weight 15%)
Score 1-2: no next step proposed
Score 3-4: vague "let's follow up" without specifics
Score 5-6: next step mentioned but not confirmed
Score 7-8: specific, time-bound next step proposed
Score 9-10: urgency created, next step agreed by customer

## 6. Engagement & Delivery (weight 10%)
Score 1-2: largely incoherent or very short
Score 3-4: significant fillers or lack of confidence
Score 5-6: acceptable delivery with some issues
Score 7-8: confident, clear, natural flow
Score 9-10: exceptional — energetic, precise, memorable

## Rule Compliance (weight 0% — reported separately, not in overall score)
{rules_section}

## Emotional Tone (not scored — qualitative analysis only)
Based only on PRESENTER lines, assess:
- overall_sentiment: the dominant emotional tone of the presentation (positive/neutral/negative/mixed)
- confidence_level: did the presenter sound assured and authoritative, or hesitant?
- energy_level: pace, word choice, and enthusiasm level
- key_moments: 2-3 specific moments where tone notably shifted (e.g. "became hesitant when asked about pricing")
- authenticity_note: did it sound natural and genuine, or rehearsed/robotic?

# Output Format

You MUST respond with valid JSON matching this exact structure:

{{
  "overall_score": <weighted average — do NOT round up, be honest>,
  "performance_level": "<excellent|good|fair|needs_improvement>",
  "emotional_tone": {{
    "overall_sentiment": "<positive|neutral|negative|mixed>",
    "confidence_level": "<high|moderate|low>",
    "energy_level": "<high|moderate|low>",
    "key_moments": ["<brief description of a notable emotional moment or tone shift>"],
    "authenticity_note": "<1-2 sentences: did the presenter sound genuine and engaged, or scripted/nervous?>"
  }},
  "criteria_scores": {{
    "value_proposition": <1-10>,
    "question_quality": <1-10>,
    "objection_handling": <1-10>,
    "active_listening": <1-10>,
    "call_to_action": <1-10>,
    "engagement": <1-10>,
    "rule_compliance": <1-10>
  }},
  "strengths": [
    "<specific strength with direct quote from PRESENTER lines>"
  ],
  "improvements": [
    {{
      "area": "<criterion name>",
      "current_state": "<exactly what was observed — quote where possible>",
      "recommendation": "<specific, actionable step>",
      "example": "<direct quote from PRESENTER lines, or null>"
    }}
  ],
  "rule_violations": [
    {{
      "rule_category": "<politeness|company_wording|sales_structure|engagement>",
      "rule_name": "<specific rule>",
      "severity": "<low|medium|high>",
      "description": "<what was violated>",
      "example": "<quote, or null>",
      "suggestion": "<how to fix>"
    }}
  ],
  "summary": "<2-3 honest sentences — state what was missing, not just what was good>",
  "next_steps": [
    "<specific, measurable action the presenter should practice>"
  ]
}}

# Scoring Weights for overall_score calculation
value_proposition: 0.25
question_quality: 0.20
objection_handling: 0.15
active_listening: 0.15
call_to_action: 0.15
engagement: 0.10

# Rules
1. Score ONLY the PRESENTER lines — ignore CUSTOMER lines except as context
2. If an element is absent from the transcript, the score for that criterion is 1-3 — not 5
3. Strengths must have direct quotes from PRESENTER lines
4. Improvements must identify specifically what was missing or weak
5. overall_score = weighted sum per the weights above — round to 1 decimal place
6. performance_level: excellent 9-10 | good 7-8 | fair 5-6 | needs_improvement 1-4
7. emotional_tone is required — populate all fields based on PRESENTER language and phrasing
8. Return ONLY valid JSON — no markdown, no extra text
"""
        return prompt
    
    async def analyze_visual_appearance(self, frames: List[str]) -> Optional[VisualAnalysis]:
        """
        Analyze presenter's visual appearance and body language from webcam frames.

        Args:
            frames: List of base64-encoded JPEG data URLs captured during the session

        Returns:
            VisualAnalysis or None if analysis fails (non-critical)
        """
        if not frames:
            return None

        logger.info(f"Analyzing visual appearance from {len(frames)} webcam frames")

        # Evenly sample up to the configured max to cover the full session duration
        max_count = config.settings.frame_capture_max_count
        if len(frames) > max_count:
            step = len(frames) / max_count
            sampled = [frames[int(i * step)] for i in range(max_count)]
        else:
            sampled = frames
        logger.info(f"Sampling {len(sampled)} of {len(frames)} frames for vision analysis")

        content = [
            {
                "type": "text",
                "text": (
                    "You are analyzing webcam frames captured during a sales presentation. "
                    "Assess the presenter's visual appearance and body language.\n"
                    "Be objective, professional, and constructive. "
                    "Focus on coaching-relevant observations only.\n\n"
                    "Respond with valid JSON matching this exact structure:\n"
                    "{\n"
                    '  "expressions": "<predominant facial expressions across frames — e.g. confident smile, showed uncertainty when pausing>",\n'
                    '  "eye_contact": "<eye contact quality — consistent/intermittent/minimal, and whether they looked at camera>",\n'
                    '  "posture_and_gestures": "<posture, hand movements, and any notable body language>",\n'
                    '  "professional_appearance": "<attire, background, lighting — overall professional impression>",\n'
                    '  "confidence_arc": "<how visual confidence evolved from the first to last frames>",\n'
                    '  "overall_note": "<one sentence overall visual summary of the presenter>"\n'
                    "}"
                )
            }
        ]
        for frame in sampled:
            content.append({
                "type": "image_url",
                "image_url": {"url": frame, "detail": "low"}
            })

        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[{"role": "user", "content": content}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_completion_tokens=400,
            )
            result_json = response.choices[0].message.content
            if not result_json:
                logger.warning("Visual analysis returned empty content")
                return None
            result_data = json.loads(result_json)
            visual = VisualAnalysis(**result_data)
            logger.info("Visual analysis complete")
            return visual
        except Exception as e:
            logger.warning(f"Visual analysis failed (non-critical): {e}")
            return None

    async def analyze_presentation(self, transcript: str, frames: Optional[List[str]] = None) -> SalesCoachingReport:
        """
        Analyze a sales presentation transcript and generate coaching report.
        
        Args:
            transcript: Complete presentation transcript text
            
        Returns:
            SalesCoachingReport: Structured coaching report with scores and recommendations
        """
        logger.info(f"Analyzing presentation transcript ({len(transcript)} characters)")
        
        try:
            # Call GPT-4.1 for transcript analysis
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Analyze this sales presentation transcript:\n\n{transcript}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_completion_tokens=3000
            )
            
            # Parse JSON response
            result_json = response.choices[0].message.content
            if not result_json:
                refusal = getattr(response.choices[0].message, "refusal", None)
                logger.error(f"Empty content from model. Refusal: {refusal}. Finish reason: {response.choices[0].finish_reason}")
                raise ValueError("Model returned empty content")
            # Strip markdown code fences if present (```json ... ```)
            stripped = result_json.strip()
            if stripped.startswith("```"):
                stripped = stripped.split("\n", 1)[-1]
                stripped = stripped.rsplit("```", 1)[0].strip()
            logger.debug(f"GPT raw response (first 300): {stripped[:300]}")
            logger.debug(f"GPT raw response (last 500): {stripped[-500:]}")
            
            result_data = json.loads(stripped)
            
            # Validate and parse into Pydantic model
            report = SalesCoachingReport(**result_data)
            
            logger.info(f"Analysis complete. Overall score: {report.overall_score}/10")

            # Visual analysis from webcam frames — runs after transcript analysis, non-blocking on failure
            if frames:
                report.visual_analysis = await self.analyze_visual_appearance(frames)

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
                max_completion_tokens=800
            )
            
            script = response.choices[0].message.content.strip()
            logger.info(f"Generated coaching script ({len(script)} characters)")
            
            return script
            
        except Exception as e:
            logger.error(f"Error generating coaching script: {e}")
            raise
    
    def build_voice_live_instructions(self) -> str:
        """
        Build the persona instructions for a Voice Live interactive session.
        The model plays the role of a prospect in a live B2B sales meeting.
        These instructions are sent as the 'instructions' field in session.update.
        """
        rules_section = config.get_rules_prompt_section()

        return f"""You are a potential enterprise software customer attending a live sales demo.
Behave exactly as a real-world prospect would in a genuine B2B sales meeting.

## Your Persona
- Role: VP of Operations or IT Director at a mid-to-large enterprise
- Attitude: Pragmatic, mildly skeptical, have seen many vendor pitches before
- Priorities: Clear ROI, implementation feasibility, ongoing support, total cost of ownership
- You have budget constraints and many competing priorities

## Conversation Rules
- While the salesperson is pitching, LISTEN. Do not interrupt unless the pause is natural.
- Only speak up when: they directly ask you a question, they finish a major section, or you have a critical clarification.
- Keep your responses SHORT — under 25 words. Real customers don't give speeches.
- Ask realistic follow-up questions: pricing, integration complexity, timeline, proof points, support model.
- If they haven't answered your question clearly, probe politely once.
- Do NOT coach, evaluate, or give feedback during the session — stay in character as a customer.
- When the salesperson pauses briefly mid-thought, stay silent.
- Start the conversation by greeting them briefly: "Thanks for coming in. Go ahead."

## Custom Sales Rules (evaluate silently whether the salesperson follows these)
{rules_section}
"""

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
                max_completion_tokens=50
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
                max_completion_tokens=60
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
