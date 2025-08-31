"""Authentication middleware and utilities"""

import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)
security = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for request processing"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health checks and docs
        if request.url.path in ["/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/"]:
            return await call_next(request)
        
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = verify_token(token)
                request.state.user = payload
            except HTTPException:
                # Invalid token, but continue (some endpoints may not require auth)
                pass
        
        return await call_next(request)


def verify_token(token: str) -> Dict[str, Any]:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[Dict[str, Any]]:
    """Get current authenticated user"""
    if not credentials:
        return None
    
    try:
        return verify_token(credentials.credentials)
    except HTTPException:
        return None


async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Require authentication for endpoint"""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    return verify_token(credentials.credentials)


async def require_roles(required_roles: list):
    """Dependency to require specific roles"""
    def check_roles(user: Dict[str, Any] = Depends(require_auth)):
        user_roles = user.get("roles", [])
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check_roles
