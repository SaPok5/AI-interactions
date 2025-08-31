"""Data models for intent recognition service"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class IntentRequest(BaseModel):
    """Intent recognition request"""
    text: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    language: Optional[str] = "en"

class IntentAlternative(BaseModel):
    """Alternative intent prediction"""
    intent: str
    confidence: float

class IntentResult(BaseModel):
    """Intent classification result"""
    intent: str
    confidence: float
    alternatives: List[IntentAlternative] = []
    session_id: Optional[str] = None
    processing_time_ms: float

class Entity(BaseModel):
    """Extracted entity"""
    text: str
    label: str
    confidence: float
    start: int
    end: int

class EntityResult(BaseModel):
    """Entity extraction result"""
    entities: List[Entity]
    processing_time_ms: float

class SpeculativeResult(BaseModel):
    """Speculative intent prediction"""
    intent: str
    confidence: float
    completion_text: str
    trigger_words: List[str]
    estimated_completion_time_ms: int

class SessionContext(BaseModel):
    """Session context for intent tracking"""
    session_id: str
    conversation_history: List[str] = []
    intent_history: List[str] = []
    entities_history: List[Dict[str, Any]] = []
    last_activity: datetime
    user_preferences: Dict[str, Any] = {}

class TrainingData(BaseModel):
    """Training data for model improvement"""
    text: str
    intent: str
    entities: List[Entity] = []
    feedback_score: Optional[float] = None
    timestamp: datetime
