"""Configuration settings for RAG service"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8005
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # Vector database
    vector_db_type: str = "chroma"  # chroma, faiss, or pinecone
    vector_db_path: str = "/app/data/vectors"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    
    # Document processing
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_file_size_mb: int = 50
    supported_formats: List[str] = [
        "pdf", "docx", "pptx", "xlsx", "txt", "md", "html"
    ]
    
    # Search settings
    default_search_limit: int = 10
    similarity_threshold: float = 0.7
    max_search_results: int = 50
    
    # Performance
    batch_size: int = 32
    max_concurrent_processing: int = 5
    cache_ttl_seconds: int = 3600
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
