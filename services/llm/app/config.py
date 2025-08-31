"""Configuration settings for LLM service"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List, Dict


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8007
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # LLM providers
    default_provider: str = "google"  # openai, anthropic, google, local
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = Field(default="", env="GOOGLE_API_KEY")
    
    # Model settings
    default_model: str = "gemini-pro"
    max_tokens: int = 2000
    temperature: float = 0.7
    top_p: float = 0.9
    
    # Local model settings
    local_model_path: str = "/app/data/models"
    enable_local_models: bool = False
    local_model_name: str = "llama-2-7b-chat"
    
    # Tool calling
    enable_tools: bool = True
    max_tool_calls: int = 5
    tool_timeout_seconds: int = 30
    
    # Performance
    max_concurrent_requests: int = 20
    request_timeout_seconds: int = 60
    cache_ttl_hours: int = 24
    
    # Safety
    content_filter: bool = True
    max_prompt_length: int = 8000
    rate_limit_per_minute: int = 100
    
    # Pydantic v2 settings
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )


settings = Settings()
