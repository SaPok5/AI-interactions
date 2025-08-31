"""
Redis connection pool manager for high-performance operations
"""

import asyncio
import redis.asyncio as redis
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

class RedisPool:
    """Redis connection pool manager"""
    
    def __init__(self):
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
    
    async def initialize(self, redis_url: str):
        """Initialize Redis connection pool"""
        try:
            # Create connection pool with optimized settings
            self._pool = redis.ConnectionPool.from_url(
                redis_url,
                max_connections=50,
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                health_check_interval=30,
                encoding="utf-8",
                decode_responses=True
            )
            
            # Create Redis client with the pool
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            
            logger.info("Redis connection pool initialized", 
                       max_connections=50,
                       health_check_interval=30)
            
        except Exception as e:
            logger.error("Failed to initialize Redis pool", error=str(e))
            raise
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client from pool"""
        if not self._client:
            raise RuntimeError("Redis pool not initialized")
        return self._client
    
    async def close(self):
        """Close Redis connection pool"""
        if self._client:
            await self._client.close()
            self._client = None
        
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
            
        logger.info("Redis connection pool closed")
    
    async def health_check(self) -> bool:
        """Check Redis connection health"""
        try:
            if self._client:
                await self._client.ping()
                return True
        except Exception as e:
            logger.error("Redis health check failed", error=str(e))
        return False

# Global Redis pool instance
redis_pool = RedisPool()

async def get_redis_client() -> redis.Redis:
    """Get Redis client from the global pool"""
    return await redis_pool.get_client()

async def execute_redis_command(command: str, *args, **kwargs):
    """Execute Redis command with automatic retry"""
    client = await get_redis_client()
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            method = getattr(client, command)
            return await method(*args, **kwargs)
        except (redis.ConnectionError, redis.TimeoutError) as e:
            if attempt == max_retries - 1:
                logger.error("Redis command failed after retries", 
                           command=command, 
                           error=str(e))
                raise
            
            logger.warning("Redis command retry", 
                          command=command, 
                          attempt=attempt + 1)
            await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
