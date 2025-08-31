"""Data models for speech processing service"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class AudioFrame(BaseModel):
    """Audio frame data model"""
    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    timestamp: datetime
    session_id: str

class WordTimestamp(BaseModel):
    """Word-level timestamp information"""
    word: str
    start: float
    end: float
    confidence: float

class ASRResult(BaseModel):
    """ASR processing result"""
    text: str
    confidence: float
    is_final: bool
    language: str
    timestamps: List[WordTimestamp] = []
    session_id: str
    processing_time_ms: float

class LanguageResult(BaseModel):
    """Language detection result"""
    language: str
    confidence: float
    alternatives: List[Dict[str, float]] = []

class VADResult(BaseModel):
    """Voice Activity Detection result"""
    is_speech: bool
    energy: float
    confidence: float
    timestamp: datetime

class SessionState(BaseModel):
    """ASR session state"""
    session_id: str
    language: Optional[str] = None
    buffer: List[float] = []
    last_activity: datetime
    total_audio_seconds: float = 0.0
    word_count: int = 0
