"""Configuration settings for Speech service"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8002
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # Model paths
    model_path: str = "/models"
    # Faster-Whisper expects a CTranslate2-converted model id or local dir (e.g., "tiny", "small", or "Systran/faster-whisper-small").
    # Using the upstream HF repo id (e.g., "openai/whisper-small") downloads PyTorch weights and fails with missing model.bin.
    asr_model: str = "small"
    
    # Audio processing
    sample_rate: int = 16000
    chunk_duration_ms: int = 100
    vad_aggressiveness: int = 2
    
    # ASR settings
    beam_size: int = 1
    temperature: float = 0.0
    language: str = "auto"
    
    # Performance
    max_concurrent_sessions: int = 100
    session_timeout: int = 300  # 5 minutes
    
    # Pydantic v2 settings
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        # Avoid conflicts with fields like `model_path`
        protected_namespaces=("settings_",),
    )


settings = Settings()
