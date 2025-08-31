"""Health check endpoints"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
import structlog
import redis.asyncio as redis
from typing import Dict, Any

logger = structlog.get_logger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    version: str
    services: Dict[str, str]


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Basic health check"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        services={}
    )


@router.get("/ready")
async def readiness_check():
    """Readiness check with dependency validation"""
    checks = {}
    
    try:
        # Check Redis connection
        from ..main import app
        redis_client = app.state.redis
        await redis_client.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        checks["redis"] = "unhealthy"
    
    # Overall status
    overall_status = "healthy" if all(
        status == "healthy" for status in checks.values()
    ) else "unhealthy"
    
    return {
        "status": overall_status,
        "checks": checks
    }


@router.get("/live")
async def liveness_check():
    """Liveness check"""
    return {"status": "alive"}
