"""Configuration settings for the Gateway service"""

from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Server configuration
    port: int = 8080
    debug: bool = True
    
    # Security
    secret_key: str = "dev-secret-change-in-production"
    jwt_secret: str = "jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours
    
    # CORS
    allowed_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:3002",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        # Nginx-served origins
        "http://localhost",
        "https://localhost",
        "http://127.0.0.1",
        "https://127.0.0.1",
        "http://localhost:8090",
        "https://localhost:8443"
    ]
    
    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str = "redis://localhost:6379"
    redis_key_prefix: str = "voice-assistant:"
    session_ttl: int = 86400  # 24 hours
    
    # Rate limiting
    rate_limit_requests: int = 1000
    rate_limit_window: int = 900  # 15 minutes
    
    # WebSocket
    ws_max_connections: int = 10000
    ws_ping_interval: int = 30
    ws_max_message_size: int = 1048576  # 1MB
    
    # Service URLs
    auth_service_url: str = "http://auth:8001"
    speech_service_url: str = "http://speech:8002"
    intent_service_url: str = "http://intent:8003"
    llm_service_url: str = "http://llm:8004"
    tts_service_url: str = "http://tts:8005"
    rag_service_url: str = "http://rag:8006"
    analytics_service_url: str = "http://analytics:8007"
    orchestrator_url: str = "http://orchestrator:8004"
    
    # Logging
    log_level: str = "INFO"
    
    # Monitoring
    metrics_enabled: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
