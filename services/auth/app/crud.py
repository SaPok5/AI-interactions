"""CRUD operations for authentication service"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timedelta

from .models import User, Session, ApiKey, AuditLog
from .schemas import UserCreate, SessionCreate, ApiKeyCreate

async def create_user(db: AsyncSession, user_data: UserCreate, hashed_password: str) -> User:
    """Create a new user"""
    user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        role=user_data.role
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email"""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get user by ID"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

async def update_last_login(db: AsyncSession, user_id: int) -> None:
    """Update user's last login timestamp"""
    user = await get_user_by_id(db, user_id)
    if user:
        user.last_login = datetime.utcnow()
        await db.commit()

async def create_session(db: AsyncSession, user_id: int, session_data: SessionCreate, session_token: str) -> Session:
    """Create a new user session"""
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    session = Session(
        user_id=user_id,
        session_token=session_token,
        language_preference=session_data.language_preference,
        voice_id=session_data.voice_id,
        consent_audio=session_data.consent_audio,
        consent_text=session_data.consent_text,
        expires_at=expires_at
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def get_session_by_token(db: AsyncSession, session_token: str) -> Optional[Session]:
    """Get session by token"""
    result = await db.execute(
        select(Session).where(
            Session.session_token == session_token,
            Session.is_active == True,
            Session.expires_at > datetime.utcnow()
        )
    )
    return result.scalar_one_or_none()

async def deactivate_session(db: AsyncSession, session_token: str) -> bool:
    """Deactivate a session"""
    session = await get_session_by_token(db, session_token)
    if session:
        session.is_active = False
        await db.commit()
        return True
    return False

async def create_api_key(db: AsyncSession, user_id: int, api_key_data: ApiKeyCreate, key_hash: str) -> ApiKey:
    """Create a new API key"""
    api_key = ApiKey(
        user_id=user_id,
        key_name=api_key_data.key_name,
        key_hash=key_hash,
        permissions=",".join(api_key_data.permissions),
        expires_at=api_key_data.expires_at
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key

async def log_audit_event(
    db: AsyncSession,
    user_id: Optional[int],
    action: str,
    resource: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    success: bool = True,
    details: Optional[str] = None
) -> None:
    """Log an audit event"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        details=details
    )
    db.add(audit_log)
    await db.commit()
