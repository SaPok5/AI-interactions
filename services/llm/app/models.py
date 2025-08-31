"""Data models for LLM service"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

class GenerationRequest(BaseModel):
    """LLM generation request"""
    prompt: str
    context: str = ""
    entities: List[Dict[str, Any]] = []
    max_tokens: int = 500
    temperature: float = 0.7
    top_p: float = 0.9
    tools: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None
    model: str = "default"

class ToolCall(BaseModel):
    """Tool call information"""
    name: str
    arguments: Dict[str, Any]
    call_id: str

class ToolResult(BaseModel):
    """Tool execution result"""
    call_id: str
    result: Any
    success: bool
    error: Optional[str] = None
    execution_time_ms: float

class GenerationResponse(BaseModel):
    """LLM generation response"""
    text: str
    model: str
    tokens_used: int
    generation_time_ms: float
    confidence: float
    tool_calls: List[ToolCall] = []
    session_id: Optional[str] = None

class ChatMessage(BaseModel):
    """Chat message"""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None

class ModelInfo(BaseModel):
    """Model information"""
    model_config = {"protected_namespaces": ()}
    
    model_id: str
    name: str
    provider: str
    max_tokens: int
    supports_tools: bool
    supports_streaming: bool
    cost_per_token: float = 0.0

class ToolDefinition(BaseModel):
    """Tool definition"""
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str] = []
    category: str = "general"
