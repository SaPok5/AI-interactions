"""Data models for orchestrator service"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ConversationRequest(BaseModel):
    """Conversation processing request"""
    text: str
    intent: Dict[str, Any]
    entities: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ConversationResponse(BaseModel):
    """Conversation processing response"""
    response_text: str
    actions: List[Dict[str, Any]] = []
    data: Dict[str, Any] = {}
    workflow_id: Optional[str] = None
    execution_time_ms: float

class WorkflowExecution(BaseModel):
    """Workflow execution details"""
    workflow_id: str
    intent: str
    status: WorkflowStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time_ms: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class SpeculativeTask(BaseModel):
    """Speculative execution task"""
    task_id: str
    intent: str
    confidence: float
    status: WorkflowStatus
    created_at: datetime
    result: Optional[Dict[str, Any]] = None
    hit: bool = False  # Whether the speculation was used

class ServiceHealth(BaseModel):
    """Service health status"""
    service_name: str
    status: str
    response_time_ms: float
    last_check: datetime
