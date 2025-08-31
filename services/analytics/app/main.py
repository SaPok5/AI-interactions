"""
Analytics Service - Complete Implementation
Real-time metrics collection, processing, and dashboard generation
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis
import pandas as pd
import numpy as np

from .config import settings
from .metrics_collector import MetricsCollector
from .data_processor import DataProcessor
from .dashboard_generator import DashboardGenerator
from .models import MetricEvent, MetricQuery, DashboardConfig, AnalyticsReport

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("📊 Starting Analytics Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize core components
    app.state.metrics_collector = MetricsCollector()
    app.state.data_processor = DataProcessor()
    app.state.dashboard_generator = DashboardGenerator()
    
    # Initialize components
    await app.state.metrics_collector.initialize()
    await app.state.data_processor.initialize()
    await app.state.dashboard_generator.initialize()
    
    # Start background tasks
    asyncio.create_task(app.state.metrics_collector.start_collection())
    asyncio.create_task(app.state.data_processor.start_processing())
    
    logger.info("✅ Analytics Service initialized")
    
    yield
    
    logger.info("🛑 Shutting down Analytics Service")
    await app.state.redis.close()

app = FastAPI(
    title="Analytics Service",
    description="Real-time analytics and metrics collection",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/events")
async def track_event(event: MetricEvent):
    """Track a metric event"""
    try:
        await app.state.metrics_collector.track_event(event)
        return {"status": "tracked", "event_id": event.event_id}
    except Exception as e:
        logger.error("Event tracking failed", error=str(e))
        raise HTTPException(status_code=500, detail="Event tracking failed")

@app.post("/events/batch")
async def track_events_batch(events: List[MetricEvent]):
    """Track multiple metric events"""
    try:
        results = await app.state.metrics_collector.track_events_batch(events)
        return {"status": "tracked", "count": len(events), "results": results}
    except Exception as e:
        logger.error("Batch event tracking failed", error=str(e))
        raise HTTPException(status_code=500, detail="Batch event tracking failed")

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

analytics_total_events = Counter('analytics_total_events', 'Total events processed')
analytics_active_sessions = Gauge('analytics_active_sessions', 'Number of active analytics sessions')
analytics_query_count = Counter('analytics_query_count', 'Total metrics queries')
analytics_processing_time = Gauge('analytics_processing_time_ms', 'Average processing time in ms')

@app.get("/metrics")
async def get_prometheus_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values (using dummy values since we don't have access to actual metrics)
    analytics_total_events._value._value = getattr(app.state.data_processor, 'total_events', 0)
    analytics_active_sessions.set(getattr(app.state.data_processor, 'active_sessions', 0))
    analytics_query_count._value._value = getattr(app.state.data_processor, 'query_count', 0)
    analytics_processing_time.set(getattr(app.state.data_processor, 'avg_processing_time', 0))
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/metrics/data")
async def get_metrics_data(
    service: Optional[str] = None,
    metric_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(default=1000, le=10000)
):
    """Get metrics data"""
    try:
        query = MetricQuery(
            service=service,
            metric_type=metric_type,
            start_time=start_time or datetime.utcnow() - timedelta(hours=24),
            end_time=end_time or datetime.utcnow(),
            limit=limit
        )
        
        metrics = await app.state.data_processor.query_metrics(query)
        return {"metrics": metrics, "count": len(metrics)}
        
    except Exception as e:
        logger.error("Metrics query failed", error=str(e))
        raise HTTPException(status_code=500, detail="Metrics query failed")

@app.get("/metrics/aggregated")
async def get_aggregated_metrics(
    service: Optional[str] = None,
    metric_type: Optional[str] = None,
    aggregation: str = "avg",  # avg, sum, count, min, max
    interval: str = "1h",  # 1m, 5m, 15m, 1h, 1d
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get aggregated metrics"""
    try:
        result = await app.state.data_processor.get_aggregated_metrics(
            service=service,
            metric_type=metric_type,
            aggregation=aggregation,
            interval=interval,
            start_time=start_time or datetime.utcnow() - timedelta(hours=24),
            end_time=end_time or datetime.utcnow()
        )
        return result
        
    except Exception as e:
        logger.error("Aggregated metrics query failed", error=str(e))
        raise HTTPException(status_code=500, detail="Aggregated metrics query failed")

@app.get("/dashboard/{dashboard_id}")
async def get_dashboard(dashboard_id: str):
    """Get dashboard configuration and data"""
    try:
        dashboard = await app.state.dashboard_generator.get_dashboard(dashboard_id)
        return dashboard
    except Exception as e:
        logger.error("Dashboard retrieval failed", dashboard_id=dashboard_id, error=str(e))
        raise HTTPException(status_code=500, detail="Dashboard retrieval failed")

@app.post("/dashboard")
async def create_dashboard(config: DashboardConfig):
    """Create a new dashboard"""
    try:
        dashboard_id = await app.state.dashboard_generator.create_dashboard(config)
        return {"dashboard_id": dashboard_id, "status": "created"}
    except Exception as e:
        logger.error("Dashboard creation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Dashboard creation failed")

@app.get("/dashboards")
async def list_dashboards():
    """List available dashboards"""
    try:
        dashboards = await app.state.dashboard_generator.list_dashboards()
        return {"dashboards": dashboards}
    except Exception as e:
        logger.error("Dashboard listing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Dashboard listing failed")

@app.get("/reports/system")
async def get_system_report():
    """Get system-wide analytics report"""
    try:
        report = await app.state.data_processor.generate_system_report()
        return report
    except Exception as e:
        logger.error("System report generation failed", error=str(e))
        raise HTTPException(status_code=500, detail="System report generation failed")

@app.get("/reports/service/{service_name}")
async def get_service_report(service_name: str):
    """Get service-specific analytics report"""
    try:
        report = await app.state.data_processor.generate_service_report(service_name)
        return report
    except Exception as e:
        logger.error("Service report generation failed", service=service_name, error=str(e))
        raise HTTPException(status_code=500, detail="Service report generation failed")

@app.get("/reports/performance")
async def get_performance_report(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
):
    """Get performance analytics report"""
    try:
        report = await app.state.data_processor.generate_performance_report(
            start_time=start_time or datetime.utcnow() - timedelta(hours=24),
            end_time=end_time or datetime.utcnow()
        )
        return report
    except Exception as e:
        logger.error("Performance report generation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Performance report generation failed")

@app.get("/alerts")
async def get_alerts(
    severity: Optional[str] = None,
    service: Optional[str] = None,
    active_only: bool = True
):
    """Get system alerts"""
    try:
        alerts = await app.state.data_processor.get_alerts(
            severity=severity,
            service=service,
            active_only=active_only
        )
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error("Alerts retrieval failed", error=str(e))
        raise HTTPException(status_code=500, detail="Alerts retrieval failed")

@app.post("/alerts/acknowledge/{alert_id}")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert"""
    try:
        result = await app.state.data_processor.acknowledge_alert(alert_id)
        return {"status": "acknowledged", "alert_id": alert_id}
    except Exception as e:
        logger.error("Alert acknowledgment failed", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail="Alert acknowledgment failed")

@app.get("/trends")
async def get_trends(
    metric_type: str,
    service: Optional[str] = None,
    period: str = "24h"  # 1h, 6h, 24h, 7d, 30d
):
    """Get trend analysis"""
    try:
        trends = await app.state.data_processor.analyze_trends(
            metric_type=metric_type,
            service=service,
            period=period
        )
        return trends
    except Exception as e:
        logger.error("Trend analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail="Trend analysis failed")

@app.get("/anomalies")
async def get_anomalies(
    service: Optional[str] = None,
    metric_type: Optional[str] = None,
    sensitivity: float = 0.95
):
    """Get anomaly detection results"""
    try:
        anomalies = await app.state.data_processor.detect_anomalies(
            service=service,
            metric_type=metric_type,
            sensitivity=sensitivity
        )
        return {"anomalies": anomalies, "count": len(anomalies)}
    except Exception as e:
        logger.error("Anomaly detection failed", error=str(e))
        raise HTTPException(status_code=500, detail="Anomaly detection failed")

@app.post("/export")
async def export_data(
    format: str = "csv",  # csv, json, parquet
    service: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    background_tasks: BackgroundTasks = None
):
    """Export analytics data"""
    try:
        export_id = await app.state.data_processor.export_data(
            format=format,
            service=service,
            start_time=start_time or datetime.utcnow() - timedelta(days=7),
            end_time=end_time or datetime.utcnow()
        )
        
        return {"export_id": export_id, "status": "started"}
        
    except Exception as e:
        logger.error("Data export failed", error=str(e))
        raise HTTPException(status_code=500, detail="Data export failed")

@app.get("/export/{export_id}/status")
async def get_export_status(export_id: str):
    """Get export status"""
    try:
        status = await app.state.data_processor.get_export_status(export_id)
        return status
    except Exception as e:
        logger.error("Export status check failed", export_id=export_id, error=str(e))
        raise HTTPException(status_code=500, detail="Export status check failed")

@app.delete("/data")
async def cleanup_data(
    older_than_days: int = 30,
    service: Optional[str] = None
):
    """Cleanup old analytics data"""
    try:
        result = await app.state.data_processor.cleanup_data(
            older_than_days=older_than_days,
            service=service
        )
        return result
    except Exception as e:
        logger.error("Data cleanup failed", error=str(e))
        raise HTTPException(status_code=500, detail="Data cleanup failed")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    collector_health = await app.state.metrics_collector.health_check()
    processor_health = await app.state.data_processor.health_check()
    dashboard_health = await app.state.dashboard_generator.health_check()
    
    return {
        "status": "healthy",
        "service": "analytics",
        "components": {
            "collector": collector_health,
            "processor": processor_health,
            "dashboard": dashboard_health
        },
        "metrics_count": await app.state.metrics_collector.get_metrics_count(),
        "active_dashboards": len(await app.state.dashboard_generator.list_dashboards())
    }

@app.get("/metrics/service")
async def get_service_metrics():
    """Get analytics service metrics"""
    return {
        "events_processed": app.state.metrics_collector.events_processed,
        "processing_rate": app.state.metrics_collector.get_processing_rate(),
        "storage_size_mb": await app.state.data_processor.get_storage_size(),
        "active_queries": app.state.data_processor.active_queries,
        "cache_hit_rate": app.state.data_processor.get_cache_hit_rate(),
        "dashboard_views": app.state.dashboard_generator.total_views,
        "alerts_active": len(await app.state.data_processor.get_alerts(active_only=True))
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
