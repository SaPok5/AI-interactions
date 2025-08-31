"""Service proxy endpoints"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx
import uuid
from typing import Dict, Any
import structlog

from ..middleware.auth import require_auth
from ..config import settings

logger = structlog.get_logger(__name__)
router = APIRouter()

# Service URL mapping
SERVICE_URLS = {
    "auth": settings.auth_service_url,
    "speech": settings.speech_service_url,
    "intent": settings.intent_service_url,
    "orchestrator": settings.orchestrator_url,
    "rag": settings.rag_service_url,
    "tts": settings.tts_service_url,
    "llm": settings.llm_service_url,
    "analytics": settings.analytics_service_url,
}


async def proxy_request(
    service: str,
    path: str,
    request: Request,
    user: Dict[str, Any] = None
):
    """Proxy request to backend service"""
    if service not in SERVICE_URLS:
        raise HTTPException(status_code=404, detail="Service not found")
    
    target_url = f"{SERVICE_URLS[service]}{path}"
    
    # Prepare headers
    headers = dict(request.headers)
    headers.pop("host", None)  # Remove host header
    
    # Add user context if authenticated
    if user:
        headers["X-User-ID"] = user["sub"]
        headers["X-User-Roles"] = ",".join(user.get("roles", []))
    
    # Add correlation ID for tracing
    correlation_id = headers.get("X-Correlation-ID") or str(uuid.uuid4())
    headers["X-Correlation-ID"] = correlation_id
    
    async with httpx.AsyncClient() as client:
        try:
            # Forward request
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=request.query_params,
                content=await request.body(),
                timeout=30.0
            )
            
            # Return response
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type")
            )
            
        except httpx.TimeoutException:
            logger.error("Service timeout", service=service, path=path)
            raise HTTPException(status_code=504, detail="Service timeout")
        except httpx.ConnectError:
            logger.error("Service unavailable", service=service, path=path)
            raise HTTPException(status_code=503, detail="Service unavailable")
        except Exception as e:
            logger.error("Proxy error", service=service, path=path, error=str(e))
            raise HTTPException(status_code=502, detail="Proxy error")


# Auth service (no auth required for login/register)
@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_auth(path: str, request: Request):
    """Proxy to authentication service"""
    return await proxy_request("auth", f"/{path}", request)


# Protected service endpoints
@router.api_route("/speech/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_speech(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to speech service"""
    return await proxy_request("speech", f"/{path}", request, user)


@router.api_route("/intent/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_intent(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to intent service"""
    return await proxy_request("intent", f"/{path}", request, user)


@router.api_route("/orchestrator/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orchestrator(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to orchestrator service"""
    return await proxy_request("orchestrator", f"/{path}", request, user)


@router.api_route("/rag/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_rag(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to RAG service"""
    return await proxy_request("rag", f"/{path}", request, user)


@router.api_route("/tts/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_tts(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to TTS service"""
    return await proxy_request("tts", f"/{path}", request, user)


@router.api_route("/llm/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_llm(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to LLM service"""
    return await proxy_request("llm", f"/{path}", request, user)


@router.api_route("/analytics/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_analytics(path: str, request: Request, user: Dict[str, Any] = Depends(require_auth)):
    """Proxy to analytics service"""
    return await proxy_request("analytics", f"/{path}", request, user)
