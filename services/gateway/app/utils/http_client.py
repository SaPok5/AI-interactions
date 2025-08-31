"""
High-performance HTTP client with connection pooling
"""

import asyncio
import httpx
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

class HTTPClientPool:
    """Singleton HTTP client with connection pooling"""
    
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """Initialize the HTTP client with optimized settings"""
        if self._client is None:
            # High-performance connection pool settings
            limits = httpx.Limits(
                max_keepalive_connections=100,
                max_connections=200,
                keepalive_expiry=30.0
            )
            
            timeout = httpx.Timeout(
                connect=5.0,
                read=30.0,
                write=10.0,
                pool=5.0
            )
            
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                http2=True,  # Enable HTTP/2
                verify=False,  # For development - enable SSL verification in production
                follow_redirects=True
            )
            
            logger.info("HTTP client pool initialized", 
                       max_connections=200, 
                       max_keepalive=100,
                       http2_enabled=True)
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get the shared HTTP client"""
        if self._client is None:
            await self.initialize()
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client pool closed")

# Global instance
http_pool = HTTPClientPool()

async def get_http_client() -> httpx.AsyncClient:
    """Get the shared HTTP client instance"""
    return await http_pool.get_client()

async def make_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None
) -> httpx.Response:
    """Make an HTTP request using the connection pool"""
    client = await get_http_client()
    
    kwargs = {
        "method": method,
        "url": url,
        "headers": headers or {}
    }
    
    if json_data:
        kwargs["json"] = json_data
    
    if timeout:
        kwargs["timeout"] = timeout
    
    try:
        response = await client.request(**kwargs)
        return response
    except Exception as e:
        logger.error("HTTP request failed", 
                    method=method, 
                    url=url, 
                    error=str(e))
        raise
