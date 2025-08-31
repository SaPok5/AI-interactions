"""Session management endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uuid
import structlog
from datetime import datetime, timedelta

from ..middleware.auth import get_current_user, require_auth
from ..config import settings

logger = structlog.get_logger(__name__)
router = APIRouter()


class SessionCreateRequest(BaseModel):
    """Session creation request"""
    language_preference: str = "en"
    voice_id: Optional[str] = None
    consent_audio: bool = False
    consent_text: bool = False


class SessionResponse(BaseModel):
    """Session response model"""
    session_id: str
    user_id: str
    language_preference: str
    voice_id: Optional[str]
    consent_audio: bool
    consent_text: bool
    created_at: datetime
    expires_at: datetime


@router.post("/", response_model=SessionResponse)
async def create_session(
    request: SessionCreateRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """Create a new voice session"""
    session_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(seconds=settings.session_ttl)
    
    session_data = {
        "session_id": session_id,
        "user_id": user["sub"],
        "language_preference": request.language_preference,
        "voice_id": request.voice_id,
        "consent_audio": request.consent_audio,
        "consent_text": request.consent_text,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat()
    }
    
    # Store session in Redis
    from ..main import app
    redis_client = app.state.redis
    await redis_client.setex(
        f"{settings.redis_key_prefix}session:{session_id}",
        settings.session_ttl,
        str(session_data)
    )
    
    logger.info("Session created", session_id=session_id, user_id=user["sub"])
    
    return SessionResponse(**session_data)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """Get session details"""
    from ..main import app
    redis_client = app.state.redis
    
    session_data = await redis_client.get(f"{settings.redis_key_prefix}session:{session_id}")
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Parse session data (simplified - in production use proper serialization)
    import ast
    session_dict = ast.literal_eval(session_data)
    
    # Verify user owns this session
    if session_dict["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return SessionResponse(**session_dict)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """Delete a session"""
    from ..main import app
    redis_client = app.state.redis
    
    # Verify session exists and user owns it
    session_data = await redis_client.get(f"{settings.redis_key_prefix}session:{session_id}")
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    import ast
    session_dict = ast.literal_eval(session_data)
    if session_dict["user_id"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete session
    await redis_client.delete(f"{settings.redis_key_prefix}session:{session_id}")
    
    logger.info("Session deleted", session_id=session_id, user_id=user["sub"])
    
    return {"message": "Session deleted successfully"}
