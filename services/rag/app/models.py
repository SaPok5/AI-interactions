"""Data models for RAG service"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

class SearchRequest(BaseModel):
    """Search request model"""
    query: str
    entities: List[Dict[str, Any]] = []
    limit: int = 10
    threshold: float = 0.7
    filters: Optional[Dict[str, Any]] = None

class DocumentChunk(BaseModel):
    """Document chunk model"""
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    start_char: int = 0
    end_char: int = 0

class ProcessedDocument(BaseModel):
    """Processed document model"""
    document_id: str
    title: str
    content: str
    chunks: List[DocumentChunk]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class SearchResult(BaseModel):
    """Search result model"""
    query: str
    results: List[Dict[str, Any]]
    context: str
    sources: List[Dict[str, Any]]
    total_results: int
    search_time_ms: float

class DocumentMetadata(BaseModel):
    """Document metadata model"""
    document_id: str
    title: str
    filename: str
    content_type: str
    size: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    tags: List[str] = []
    category: Optional[str] = None
