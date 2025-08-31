"""Configuration settings for Orchestrator service"""

from pydantic_settings import BaseSettings
from typing import List, Dict


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8004
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # Service URLs
    auth_service_url: str = "http://auth:8001"
    speech_service_url: str = "http://speech:8002"
    intent_service_url: str = "http://intent:8003"
    rag_service_url: str = "http://rag:8005"
    tts_service_url: str = "http://tts:8006"
    llm_service_url: str = "http://llm:8007"
    analytics_service_url: str = "http://analytics:8008"
    
    # Workflow execution
    max_concurrent_workflows: int = 100
    workflow_timeout: int = 30  # seconds
    speculative_timeout: int = 5  # seconds
    
    # Speculative execution
    enable_speculative_execution: bool = True
    speculative_prefetch_threshold: float = 0.7
    max_speculative_tasks: int = 10
    
    # Performance
    service_timeout: int = 10  # seconds
    retry_attempts: int = 3
    circuit_breaker_threshold: int = 5
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
