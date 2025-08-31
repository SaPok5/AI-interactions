"""Service coordination and communication layer"""

import asyncio
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

from .config import settings
from .models import ServiceHealth

logger = structlog.get_logger(__name__)

class ServiceCoordinator:
    """Coordinates communication with all microservices"""
    
    def __init__(self):
        self.service_urls = {
            "auth": settings.auth_service_url,
            "speech": settings.speech_service_url,
            "intent": settings.intent_service_url,
            "rag": settings.rag_service_url,
            "tts": settings.tts_service_url,
            "llm": settings.llm_service_url,
            "analytics": settings.analytics_service_url
        }
        
        self.service_health: Dict[str, ServiceHealth] = {}
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self.response_times: Dict[str, List[float]] = {}
        
        # Initialize circuit breakers
        for service in self.service_urls:
            self.circuit_breakers[service] = {
                "failures": 0,
                "last_failure": None,
                "state": "closed"  # closed, open, half-open
            }
            self.response_times[service] = []
    
    async def call_service(
        self,
        service: str,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP call to a service with circuit breaker pattern"""
        
        # Check circuit breaker
        if not self._is_circuit_closed(service):
            raise Exception(f"Circuit breaker open for {service}")
        
        url = f"{self.service_urls[service]}{endpoint}"
        start_time = datetime.utcnow()
        
        try:
            async with httpx.AsyncClient(timeout=settings.service_timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, json=data, params=params)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=data, params=params)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                
                # Record successful call
                response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                self._record_success(service, response_time)
                
                return response.json() if response.content else {}
                
        except Exception as e:
            # Record failure
            self._record_failure(service)
            logger.error("Service call failed", 
                        service=service, 
                        endpoint=endpoint, 
                        error=str(e))
            raise
    
    async def call_rag_service(
        self,
        query: str,
        entities: List[Dict[str, Any]] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Call RAG service for information retrieval"""
        try:
            return await self.call_service(
                service="rag",
                endpoint="/search",
                data={
                    "query": query,
                    "entities": entities or [],
                    "limit": limit
                }
            )
        except Exception as e:
            logger.error("RAG service call failed", error=str(e))
            return {"context": "", "sources": [], "error": str(e)}
    
    async def call_llm_service(
        self,
        prompt: str,
        context: str = "",
        entities: List[Dict[str, Any]] = None,
        max_tokens: int = 500
    ) -> Dict[str, Any]:
        """Call LLM service for text generation"""
        try:
            return await self.call_service(
                service="llm",
                endpoint="/generate",
                data={
                    "prompt": prompt,
                    "context": context,
                    "entities": entities or [],
                    "max_tokens": max_tokens
                }
            )
        except Exception as e:
            logger.error("LLM service call failed", error=str(e))
            return {"response": "I apologize, but I'm having trouble generating a response right now.", "error": str(e)}
    
    async def call_tts_service(
        self,
        text: str,
        voice: str = "default",
        language: str = "en"
    ) -> Dict[str, Any]:
        """Call TTS service for speech synthesis"""
        try:
            return await self.call_service(
                service="tts",
                endpoint="/synthesize",
                data={
                    "text": text,
                    "voice": voice,
                    "language": language
                }
            )
        except Exception as e:
            logger.error("TTS service call failed", error=str(e))
            return {"audio_url": None, "error": str(e)}
    
    async def call_analytics_service(
        self,
        event_type: str,
        data: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Call analytics service to record events"""
        try:
            return await self.call_service(
                service="analytics",
                endpoint="/events",
                data={
                    "event_type": event_type,
                    "data": data,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error("Analytics service call failed", error=str(e))
            return {"recorded": False, "error": str(e)}
    
    async def check_service_health(self, service: str) -> ServiceHealth:
        """Check health of a specific service"""
        start_time = datetime.utcnow()
        
        try:
            await self.call_service(service, "/health", method="GET")
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            health = ServiceHealth(
                service_name=service,
                status="healthy",
                response_time_ms=response_time,
                last_check=datetime.utcnow()
            )
            
        except Exception as e:
            health = ServiceHealth(
                service_name=service,
                status="unhealthy",
                response_time_ms=0,
                last_check=datetime.utcnow()
            )
        
        self.service_health[service] = health
        return health
    
    async def check_all_services(self) -> Dict[str, ServiceHealth]:
        """Check health of all services"""
        tasks = [
            self.check_service_health(service)
            for service in self.service_urls.keys()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        return self.service_health
    
    def _is_circuit_closed(self, service: str) -> bool:
        """Check if circuit breaker is closed (allowing requests)"""
        breaker = self.circuit_breakers[service]
        
        if breaker["state"] == "closed":
            return True
        elif breaker["state"] == "open":
            # Check if enough time has passed to try half-open
            if (breaker["last_failure"] and 
                datetime.utcnow() - breaker["last_failure"] > timedelta(seconds=60)):
                breaker["state"] = "half-open"
                return True
            return False
        elif breaker["state"] == "half-open":
            return True
        
        return False
    
    def _record_success(self, service: str, response_time: float):
        """Record successful service call"""
        breaker = self.circuit_breakers[service]
        
        # Reset circuit breaker on success
        breaker["failures"] = 0
        breaker["state"] = "closed"
        
        # Record response time
        self.response_times[service].append(response_time)
        if len(self.response_times[service]) > 100:  # Keep last 100 calls
            self.response_times[service] = self.response_times[service][-100:]
    
    def _record_failure(self, service: str):
        """Record failed service call"""
        breaker = self.circuit_breakers[service]
        
        breaker["failures"] += 1
        breaker["last_failure"] = datetime.utcnow()
        
        # Open circuit breaker if threshold exceeded
        if breaker["failures"] >= settings.circuit_breaker_threshold:
            breaker["state"] = "open"
            logger.warning("Circuit breaker opened", service=service)
    
    async def get_response_times(self) -> Dict[str, float]:
        """Get average response times for all services"""
        avg_times = {}
        
        for service, times in self.response_times.items():
            if times:
                avg_times[service] = sum(times) / len(times)
            else:
                avg_times[service] = 0.0
        
        return avg_times
    
    async def retry_with_backoff(
        self,
        service: str,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
        max_retries: int = None
    ) -> Dict[str, Any]:
        """Retry service call with exponential backoff"""
        max_retries = max_retries or settings.retry_attempts
        
        for attempt in range(max_retries):
            try:
                return await self.call_service(service, endpoint, method, data)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                
                # Exponential backoff
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
                
                logger.warning("Retrying service call", 
                              service=service, 
                              attempt=attempt + 1,
                              wait_time=wait_time)
