"""Data models for TTS service"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

class TTSRequest(BaseModel):
    """TTS synthesis request"""
    text: str
    voice: str = "default"
    language: str = "en"
    speed: float = 1.0
    pitch: float = 1.0
    session_id: Optional[str] = None
    output_format: str = "wav"

class TTSResult(BaseModel):
    """TTS synthesis result"""
    audio_url: Optional[str] = None
    audio_data: Optional[str] = None  # Base64 encoded audio
    duration_ms: float
    text: str
    voice: str
    language: str
    synthesis_time_ms: float

class VoiceInfo(BaseModel):
    """Voice information"""
    voice_id: str
    name: str
    language: str
    gender: str
    age: str = "adult"
    style: str = "neutral"
    engine: str
    neural: bool = False
    sample_rate: int = 22050

class AudioChunk(BaseModel):
    """Audio chunk for streaming"""
    data: bytes
    chunk_index: int
    is_final: bool
    timestamp: datetime
