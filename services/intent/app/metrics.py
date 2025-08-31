from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# Intent service metrics
intent_requests_total = Counter('intent_requests_total', 'Total intent recognition requests', ['status'])
intent_duration_seconds = Histogram('intent_duration_seconds', 'Intent recognition duration')
intent_confidence_score = Histogram('intent_confidence_score', 'Intent confidence scores')
intent_types_detected = Counter('intent_types_detected_total', 'Intent types detected', ['intent_type'])

def record_intent_request(status: str, duration: float, confidence: float = None, intent_type: str = None):
    """Record intent recognition metrics"""
    intent_requests_total.labels(status=status).inc()
    intent_duration_seconds.observe(duration)
    if confidence is not None:
        intent_confidence_score.observe(confidence)
    if intent_type:
        intent_types_detected.labels(intent_type=intent_type).inc()

async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")
