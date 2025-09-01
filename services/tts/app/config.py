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
    
    # TTS engines - Free and Open Source only
    default_engine: str = "piper"  # Piper TTS - fastest offline neural TTS
    fallback_engine: str = "coqui"  # Coqui TTS - high quality neural TTS
    enable_piper_tts: bool = True  # Piper - fast neural TTS
    enable_coqui_tts: bool = True  # Coqui TTS - high quality neural TTS
    enable_espeak_ng: bool = True  # eSpeak NG - lightweight formant synthesis
    enable_pyttsx3: bool = True  # System TTS wrapper
    
    # Disabled proprietary/online engines
    enable_openai_tts: bool = False
    enable_gemini_tts: bool = False
    enable_edge_tts: bool = False
    enable_gtts: bool = False
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
    # System voice enumeration
    enable_pyttsx3_voices: bool = True
    
    # Storage
    audio_storage_path: str = "/app/data/audio"
    model_storage_path: str = "/app/data/models"
    piper_models_path: str = "/app/data/models/piper"
    coqui_models_path: str = "/app/data/models/coqui"
    max_audio_file_size_mb: int = 50
    audio_cache_ttl_hours: int = 24
    
    # Model download settings
    auto_download_models: bool = True
    default_piper_model: str = "en_US-lessac-medium"
    default_coqui_model: str = "tts_models/en/ljspeech/tacotron2-DDC"
    
    # Performance
    max_text_length: int = 5000
    max_concurrent_syntheses: int = 10
    synthesis_timeout_seconds: int = 60  # Increased for local processing
    piper_synthesis_timeout: int = 30  # Piper is faster
    coqui_synthesis_timeout: int = 90  # Coqui needs more time
    
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
