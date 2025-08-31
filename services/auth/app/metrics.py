from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response
import time

# Auth service metrics
auth_requests_total = Counter('auth_requests_total', 'Total authentication requests', ['method', 'endpoint', 'status'])
auth_duration_seconds = Histogram('auth_duration_seconds', 'Authentication request duration')
active_sessions = Gauge('auth_active_sessions', 'Number of active user sessions')
jwt_tokens_issued = Counter('auth_jwt_tokens_issued_total', 'Total JWT tokens issued')
jwt_tokens_validated = Counter('auth_jwt_tokens_validated_total', 'Total JWT tokens validated', ['status'])

def record_request(method: str, endpoint: str, status: str, duration: float):
    """Record authentication request metrics"""
    auth_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    auth_duration_seconds.observe(duration)

def record_token_issued():
    """Record JWT token issuance"""
    jwt_tokens_issued.inc()

def record_token_validation(status: str):
    """Record JWT token validation"""
    jwt_tokens_validated.labels(status=status).inc()

def update_active_sessions(count: int):
    """Update active sessions count"""
    active_sessions.set(count)

async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")
