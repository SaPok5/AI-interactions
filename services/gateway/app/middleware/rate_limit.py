"""Rate limiting middleware"""

import time
from typing import Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import HTTPException
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using sliding window"""
    
    def __init__(self, app):
        super().__init__(app)
        self.requests: Dict[str, list] = {}
    
    async def dispatch(self, request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Check rate limit
        if self._is_rate_limited(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded"
            )
        
        return await call_next(request)
    
    def _get_client_ip(self, request) -> str:
        """Extract client IP from request"""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to client host
        return request.client.host if request.client else "unknown"
    
    def _is_rate_limited(self, client_ip: str) -> bool:
        """Check if client is rate limited"""
        current_time = time.time()
        window_start = current_time - settings.rate_limit_window
        
        # Initialize or clean old requests
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        # Remove old requests outside the window
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if req_time > window_start
        ]
        
        # Check if limit exceeded
        if len(self.requests[client_ip]) >= settings.rate_limit_requests:
            return True
        
        # Add current request
        self.requests[client_ip].append(current_time)
        return False
