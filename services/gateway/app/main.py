"""
Enterprise Voice Assistant - API Gateway
FastAPI-based gateway with WebSocket support for realtime communication
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import structlog
import redis.asyncio as redis

from .config import settings
from .middleware.auth import AuthMiddleware, get_current_user
from .middleware.metrics import MetricsMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .routes import health, proxy, sessions, auth, proxy
from .websocket.manager import ConnectionManager
from .websocket.handlers import WebSocketHandler
from .utils.logging import setup_logging
from .utils.http_client import http_pool
from .utils.redis_pool import redis_pool

# Setup structured logging
setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting Enterprise Voice Assistant Gateway")
    
    # Initialize Redis connection pool
    await redis_pool.initialize(settings.redis_url)
    app.state.redis = await redis_pool.get_client()
    
    logger.info("✅ Redis connection pool established")
    
    # Initialize shared connection manager
    app.state.connection_manager = ConnectionManager()
    
    # Initialize WebSocket handler with shared connection manager
    app.state.ws_handler = WebSocketHandler(app.state.redis, app.state.connection_manager)
    
    # Start Redis subscribers for service responses
    app.state.subscriber_tasks = []
    app.state.subscriber_tasks.append(
        asyncio.create_task(subscribe_to_service_responses(app.state.redis, app.state.ws_handler))
    )
    
    # Initialize HTTP client pool
    await http_pool.initialize()
    
    logger.info("✅ Gateway startup complete")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Gateway")
    
    # Cancel subscriber tasks
    for task in app.state.subscriber_tasks:
        task.cancel()
    await asyncio.gather(*app.state.subscriber_tasks, return_exceptions=True)
    
    await connection_manager.disconnect_all()
    await http_pool.close()
    await redis_pool.close()
    logger.info("✅ Gateway shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Enterprise Voice Assistant Gateway",
    description="High-performance API Gateway with realtime WebSocket support",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, tags=["auth"])
app.include_router(proxy.router, prefix="/api", tags=["proxy"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return JSONResponse(
        content=generate_latest().decode('utf-8'),
        media_type=CONTENT_TYPE_LATEST
    )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """WebSocket endpoint for real-time communication"""
    connection_id = str(uuid.uuid4())
    
    try:
        # Use the shared connection manager from app state
        await app.state.connection_manager.connect(websocket, connection_id, token)
        
        # Use the shared WebSocket handler from app state
        handler = app.state.ws_handler
        
        # Use the WebSocket handler's connection handling method
        await handler.handle_connection(websocket, connection_id)
                
    except Exception as e:
        logger.error("WebSocket connection error", error=str(e), connection_id=connection_id)
    finally:
        await app.state.connection_manager.disconnect(connection_id)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Global HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "path": request.url.path
        }
    )

@app.post("/alerts")
async def receive_alerts(alerts: Dict[str, Any]):
    """Receive alerts from Alertmanager"""
    logger.info("Received alerts from Alertmanager", alerts_count=len(alerts.get("alerts", [])))
    # Process alerts here - could forward to notification service, log, etc.
    return {"status": "received", "count": len(alerts.get("alerts", []))}

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Enterprise Voice Assistant Gateway",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.debug else "disabled"
    }

async def subscribe_to_service_responses(redis_client: redis.Redis, ws_handler: WebSocketHandler):
    """Subscribe to service response channels"""
    pubsub = None
    try:
        # Create fresh Redis connection for pubsub
        pubsub = redis_client.pubsub()
        
        # Subscribe to channels
        await pubsub.subscribe("tts_output", "speech_output", "orchestrator_output")
        logger.info("✅ Subscribed to service response channels")
        
        # Listen for messages
        async for message in pubsub.listen():
            if message["type"] == "message":
                channel = None
                try:
                    # Handle both bytes and string channel names
                    raw_channel = message["channel"]
                    channel = raw_channel.decode("utf-8") if isinstance(raw_channel, bytes) else raw_channel
                    
                    # Handle both bytes and string data
                    raw_data = message["data"]
                    data_str = raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data
                    data = json.loads(data_str)
                    
                    service = channel.replace("_output", "")
                    
                    logger.info("📨 Received service response", service=service, channel=channel, message_type=data.get("type"))
                    logger.debug("Service response data", data=data)
                    await ws_handler.handle_service_response(service, data)
                    
                except json.JSONDecodeError as e:
                    logger.error("Invalid JSON in service response", error=str(e), channel=channel or "unknown")
                except Exception as e:
                    logger.error("Error processing service response", error=str(e), channel=channel or "unknown")
                    
    except asyncio.CancelledError:
        logger.info("Service response subscriber cancelled")
    except Exception as e:
        logger.error("Redis subscriber error", error=str(e))
    finally:
        if pubsub:
            try:
                await pubsub.close()
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else 8,
        loop="uvloop",
        http="httptools"
    )
