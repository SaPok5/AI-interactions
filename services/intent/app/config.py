"""Configuration settings for Intent Recognition service"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8003
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # Model settings
    intent_model: str = "microsoft/DialoGPT-medium"
    entity_model: str = "dbmdz/bert-large-cased-finetuned-conll03-english"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Intent classification
    confidence_threshold: float = 0.7
    max_alternatives: int = 3
    
    # Speculative prediction
    speculative_lookahead: int = 3
    speculative_threshold: float = 0.6
    max_speculative_intents: int = 5
    
    # Session management
    session_timeout: int = 1800  # 30 minutes
    max_context_length: int = 512
    
    # Performance
    batch_size: int = 8
    max_concurrent_requests: int = 50
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
