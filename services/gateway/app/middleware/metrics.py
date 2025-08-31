"""Metrics middleware for monitoring and observability"""

import time
from typing import Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_CONNECTIONS = Gauge(
    'websocket_connections_active',
    'Active WebSocket connections'
)

REQUEST_SIZE = Histogram(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint']
)

RESPONSE_SIZE = Histogram(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint']
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics"""
    
    async def dispatch(self, request, call_next):
        start_time = time.time()
        
        # Get request size
        request_size = int(request.headers.get('content-length', 0))
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Get response size
        response_size = int(response.headers.get('content-length', 0))
        
        # Extract endpoint (remove query params and IDs)
        endpoint = self._normalize_endpoint(request.url.path)
        
        # Record metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        ).inc()
        
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
        
        REQUEST_SIZE.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(request_size)
        
        RESPONSE_SIZE.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(response_size)
        
        return response
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for metrics"""
        # Remove UUIDs and numeric IDs
        import re
        
        # Replace UUIDs
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/{uuid}',
            path
        )
        
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        
        return path


def record_websocket_connection():
    """Record new WebSocket connection"""
    ACTIVE_CONNECTIONS.inc()


def record_websocket_disconnection():
    """Record WebSocket disconnection"""
    ACTIVE_CONNECTIONS.dec()
