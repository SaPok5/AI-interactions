from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# Analytics service metrics
analytics_requests_total = Counter('analytics_requests_total', 'Total analytics requests', ['endpoint', 'status'])
analytics_duration_seconds = Histogram('analytics_duration_seconds', 'Analytics request duration')
events_processed_total = Counter('analytics_events_processed_total', 'Total events processed', ['event_type'])
user_sessions_tracked = Gauge('analytics_user_sessions_tracked', 'Number of user sessions being tracked')
data_points_stored = Counter('analytics_data_points_stored_total', 'Total data points stored')

def record_request(endpoint: str, status: str, duration: float):
    """Record analytics request metrics"""
    analytics_requests_total.labels(endpoint=endpoint, status=status).inc()
    analytics_duration_seconds.observe(duration)

def record_event_processed(event_type: str):
    """Record processed event"""
    events_processed_total.labels(event_type=event_type).inc()

def update_tracked_sessions(count: int):
    """Update tracked sessions count"""
    user_sessions_tracked.set(count)

def record_data_point():
    """Record data point storage"""
    data_points_stored.inc()

async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")
