"""
Data models for sales coaching reports and analysis results.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class ImprovementItem(BaseModel):
    """Represents a specific area for improvement."""
    area: str = Field(..., description="Category of improvement (e.g., 'Filler Words', 'Value Proposition')")
    current_state: str = Field(..., description="What was observed in the presentation")
    recommendation: str = Field(..., description="Specific action to take for improvement")
    example: Optional[str] = Field(None, description="Direct quote from transcript illustrating the issue")


class RuleViolation(BaseModel):
    """Represents a violation of custom rules."""
    rule_category: str = Field(..., description="Category of rule violated (e.g., 'politeness', 'company_wording')")
    rule_name: str = Field(..., description="Specific rule that was violated")
    severity: str = Field(..., description="Severity level: 'low', 'medium', 'high'")
    description: str = Field(..., description="Description of the violation")
    example: Optional[str] = Field(None, description="Quote from transcript showing the violation")
    suggestion: str = Field(..., description="How to fix this violation")


class CriteriaScores(BaseModel):
    """Detailed scores for each evaluation criterion."""
    value_proposition: float = Field(..., ge=1, le=10, description="Clarity and strength of value proposition")
    objection_handling: float = Field(..., ge=1, le=10, description="Quality of addressing concerns")
    active_listening: float = Field(..., ge=1, le=10, description="Demonstration of understanding customer needs")
    question_quality: float = Field(..., ge=1, le=10, description="Effectiveness of questions asked")
    call_to_action: float = Field(..., ge=1, le=10, description="Clarity and urgency of next steps")
    engagement: float = Field(..., ge=1, le=10, description="Overall energy and communication quality")
    rule_compliance: float = Field(..., ge=1, le=10, description="Adherence to custom rules")


class SalesCoachingReport(BaseModel):
    """Comprehensive sales coaching analysis report."""
    overall_score: float = Field(..., ge=1, le=10, description="Overall presentation effectiveness score")
    performance_level: str = Field(..., description="Performance category: excellent, good, fair, needs_improvement")
    criteria_scores: CriteriaScores = Field(..., description="Detailed scores for each criterion")
    strengths: List[str] = Field(..., description="List of things done well in the presentation")
    improvements: List[ImprovementItem] = Field(..., description="Specific areas for improvement with recommendations")
    rule_violations: List[RuleViolation] = Field(default_factory=list, description="Custom rule violations detected")
    summary: str = Field(..., description="2-3 sentence overall assessment")
    next_steps: List[str] = Field(..., description="Actionable next steps for improvement")
    
    class Config:
        json_schema_extra = {
            "example": {
                "overall_score": 7,
                "performance_level": "good",
                "criteria_scores": {
                    "value_proposition": 8,
                    "objection_handling": 6,
                    "active_listening": 7,
                    "question_quality": 6,
                    "call_to_action": 8,
                    "engagement": 7,
                    "rule_compliance": 6
                },
                "strengths": [
                    "Clear articulation of product benefits with specific ROI examples",
                    "Strong opening with structured agenda",
                    "Confident closing with clear next steps"
                ],
                "improvements": [
                    {
                        "area": "Filler Words",
                        "current_state": "Frequent use of 'um' and 'like' reduced confidence",
                        "recommendation": "Practice pausing instead of using filler words",
                        "example": "So, um, like, our solution is, you know, really effective"
                    }
                ],
                "rule_violations": [
                    {
                        "rule_category": "company_wording",
                        "rule_name": "preferred_terms",
                        "severity": "medium",
                        "description": "Used 'cheap' instead of preferred company terminology",
                        "example": "This is a cheap solution",
                        "suggestion": "Use 'cost-effective' or 'competitive pricing' instead"
                    }
                ],
                "summary": "Solid presentation with clear value proposition and strong call-to-action. Main improvement area is reducing filler words for more confident delivery.",
                "next_steps": [
                    "Practice presentation without filler words - record and review",
                    "Prepare more open-ended discovery questions",
                    "Review company terminology guide for preferred wording"
                ]
            }
        }


class TranscriptSegment(BaseModel):
    """Represents a segment of transcribed speech."""
    text: str = Field(..., description="Transcribed text")
    timestamp: float = Field(..., description="Timestamp in seconds from start")
    confidence: Optional[float] = Field(None, description="Recognition confidence score")


class PresentationSession(BaseModel):
    """Complete presentation session data."""
    session_id: str = Field(..., description="Unique session identifier")
    transcript: str = Field(..., description="Full presentation transcript")
    duration_seconds: float = Field(..., description="Total presentation duration")
    segments: List[TranscriptSegment] = Field(default_factory=list, description="Individual transcript segments")
    report: Optional[SalesCoachingReport] = Field(None, description="Generated coaching report")
