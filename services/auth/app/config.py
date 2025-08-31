"""Configuration settings for Authentication service"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8001
    debug: bool = False
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@postgres:5432/voice_assistant"
    
    # Security
    secret_key: str = "auth-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # CORS
    allowed_origins: List[str] = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
