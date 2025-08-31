"""Configuration settings for TTS service"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8006
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # TTS engines
    default_engine: str = "edge"  # edge provides better quality than coqui for general use
    enable_neural_voices: bool = True
    enable_voice_cloning: bool = False
    
    # Audio settings
    sample_rate: int = 44100  # Higher quality sample rate
    audio_format: str = "wav"
    audio_quality: str = "high"  # low, medium, high
    bit_depth: int = 16  # 16-bit audio
    
    # Voice settings
    default_voice: str = "default"
    default_language: str = "en"
    default_speed: float = 1.0
    default_pitch: float = 1.0
    # Whether to enumerate system voices via pyttsx3 (may require libespeak)
    enable_pyttsx3_voices: bool = False
    
    # Storage
    audio_storage_path: str = "/app/data/audio"
    model_storage_path: str = "/app/data/models"
    max_audio_file_size_mb: int = 50
    audio_cache_ttl_hours: int = 24
    
    # Performance
    max_text_length: int = 5000
    max_concurrent_syntheses: int = 10
    synthesis_timeout_seconds: int = 30
    
    # Streaming
    chunk_size: int = 1024
    streaming_buffer_size: int = 8192
    
    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        # Avoid conflict with fields like `model_storage_path`
        protected_namespaces=("settings_",)
    )


settings = Settings()
