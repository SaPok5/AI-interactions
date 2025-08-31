"""Pydantic schemas for authentication service"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from .models import UserRole

class UserCreate(BaseModel):
    """Schema for user creation"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.ENTERPRISE_USER

class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """Schema for user response"""
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Schema for token data"""
    user_id: Optional[int] = None

class SessionCreate(BaseModel):
    """Schema for session creation"""
    language_preference: str = "en"
    voice_id: Optional[str] = None
    consent_audio: bool = False
    consent_text: bool = False

class SessionResponse(BaseModel):
    """Schema for session response"""
    id: int
    session_token: str
    language_preference: str
    voice_id: Optional[str]
    consent_audio: bool
    consent_text: bool
    is_active: bool
    created_at: datetime
    expires_at: datetime
    
    class Config:
        from_attributes = True

class ApiKeyCreate(BaseModel):
    """Schema for API key creation"""
    key_name: str = Field(..., min_length=1, max_length=255)
    permissions: List[str]
    expires_at: Optional[datetime] = None

class ApiKeyResponse(BaseModel):
    """Schema for API key response"""
    id: int
    key_name: str
    permissions: List[str]
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime]
    expires_at: Optional[datetime]
    
    class Config:
        from_attributes = True
