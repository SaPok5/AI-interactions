"""Dashboard generation and management"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog
import redis.asyncio as redis
from uuid import uuid4

from .config import settings
from .models import DashboardConfig, DashboardWidget, MetricQuery

logger = structlog.get_logger(__name__)

class DashboardGenerator:
    """Generate and manage analytics dashboards"""
    
    def __init__(self):
        self.redis_client = None
        self.dashboards = {}
        self.total_views = 0
        
    async def initialize(self):
        """Initialize dashboard generator"""
        try:
            self.redis_client = redis.from_url(settings.redis_url)
            await self._load_default_dashboards()
            logger.info("Dashboard generator initialized")
        except Exception as e:
            logger.error("Failed to initialize dashboard generator", error=str(e))
            raise
    
    async def _load_default_dashboards(self):
        """Load default dashboards"""
        try:
            # System Overview Dashboard
            system_dashboard = DashboardConfig(
                dashboard_id="system-overview",
                title="System Overview",
                description="High-level system metrics and health",
                widgets=[
                    DashboardWidget(
                        widget_id="cpu-usage",
                        title="CPU Usage",
                        type="gauge",
                        query=MetricQuery(
                            service="system",
                            metric_name="cpu_usage_percent",
                            start_time=datetime.utcnow(),
                            end_time=datetime.utcnow(),
                            limit=1
                        ),
                        visualization_config={
                            "min": 0,
                            "max": 100,
                            "unit": "%",
                            "thresholds": [70, 85]
                        }
                    ),
                    DashboardWidget(
                        widget_id="memory-usage",
                        title="Memory Usage",
                        type="gauge",
                        query=MetricQuery(
                            service="system",
                            metric_name="memory_usage_percent",
                            start_time=datetime.utcnow(),
                            end_time=datetime.utcnow(),
                            limit=1
                        ),
                        visualization_config={
                            "min": 0,
                            "max": 100,
                            "unit": "%",
                            "thresholds": [80, 90]
                        }
                    )
                ],
                refresh_interval_seconds=30,
                is_public=True
            )
            
            # Service Performance Dashboard
            performance_dashboard = DashboardConfig(
                dashboard_id="service-performance",
                title="Service Performance",
                description="Performance metrics for all services",
                widgets=[
                    DashboardWidget(
                        widget_id="response-times",
                        title="Response Times",
                        type="chart",
                        query=MetricQuery(
                            metric_name="response_time",
                            start_time=datetime.utcnow(),
                            end_time=datetime.utcnow(),
                            limit=100
                        ),
                        visualization_config={
                            "chart_type": "line",
                            "unit": "ms",
                            "y_axis_label": "Response Time (ms)"
                        }
                    ),
                    DashboardWidget(
                        widget_id="error-rates",
                        title="Error Rates",
                        type="chart",
                        query=MetricQuery(
                            metric_name="error_rate",
                            start_time=datetime.utcnow(),
                            end_time=datetime.utcnow(),
                            limit=100
                        ),
                        visualization_config={
                            "chart_type": "area",
                            "unit": "%",
                            "y_axis_label": "Error Rate (%)"
                        }
                    )
                ],
                refresh_interval_seconds=60,
                is_public=True
            )
            
            await self.create_dashboard(system_dashboard)
            await self.create_dashboard(performance_dashboard)
            
        except Exception as e:
            logger.error("Failed to load default dashboards", error=str(e))
    
    async def create_dashboard(self, config: DashboardConfig) -> str:
        """Create a new dashboard"""
        try:
            # Generate ID if not provided
            if not config.dashboard_id:
                config.dashboard_id = str(uuid4())
            
            # Validate config
            if len(config.widgets) > settings.max_dashboard_widgets:
                raise ValueError(f"Too many widgets (max: {settings.max_dashboard_widgets})")
            
            # Store dashboard
            dashboard_key = f"dashboard:{config.dashboard_id}"
            await self.redis_client.setex(
                dashboard_key,
                86400 * 30,  # 30 days TTL
                config.model_dump_json()
            )
            
            # Add to index
            await self.redis_client.sadd("dashboards:index", config.dashboard_id)
            
            self.dashboards[config.dashboard_id] = config
            
            logger.info("Dashboard created", dashboard_id=config.dashboard_id)
            return config.dashboard_id
            
        except Exception as e:
            logger.error("Dashboard creation failed", error=str(e))
            raise
    
    async def get_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        """Get dashboard with data"""
        try:
            # Get dashboard config
            dashboard_key = f"dashboard:{dashboard_id}"
            config_data = await self.redis_client.get(dashboard_key)
            
            if not config_data:
                raise ValueError(f"Dashboard not found: {dashboard_id}")
            
            config = DashboardConfig.model_validate_json(config_data)
            
            # Get data for each widget
            widgets_with_data = []
            
            for widget in config.widgets:
                widget_data = await self._get_widget_data(widget)
                widgets_with_data.append({
                    "config": widget.model_dump(),
                    "data": widget_data
                })
            
            self.total_views += 1
            
            return {
                "dashboard_id": dashboard_id,
                "title": config.title,
                "description": config.description,
                "refresh_interval_seconds": config.refresh_interval_seconds,
                "widgets": widgets_with_data,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Dashboard retrieval failed", dashboard_id=dashboard_id, error=str(e))
            raise
    
    async def _get_widget_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get data for a dashboard widget"""
        try:
            # Import here to avoid circular imports
            from .data_processor import DataProcessor
            
            processor = DataProcessor()
            await processor.initialize()
            
            # Query data based on widget type
            if widget.type == "gauge":
                # Get latest value
                data = await processor.query_metrics(widget.query)
                if data:
                    return {
                        "value": data[-1]["value"],
                        "timestamp": data[-1]["timestamp"].isoformat()
                    }
                else:
                    return {"value": 0, "timestamp": datetime.utcnow().isoformat()}
            
            elif widget.type == "chart":
                # Get time series data
                data = await processor.query_metrics(widget.query)
                return {
                    "series": [
                        {
                            "timestamp": item["timestamp"].isoformat(),
                            "value": item["value"]
                        }
                        for item in data
                    ]
                }
            
            elif widget.type == "table":
                # Get tabular data
                data = await processor.query_metrics(widget.query)
                return {
                    "rows": [
                        {
                            "timestamp": item["timestamp"].isoformat(),
                            "service": item["service"],
                            "metric": item["metric_name"],
                            "value": item["value"]
                        }
                        for item in data
                    ]
                }
            
            elif widget.type == "stat":
                # Get statistical summary
                data = await processor.query_metrics(widget.query)
                if data:
                    values = [item["value"] for item in data]
                    return {
                        "count": len(values),
                        "avg": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "latest": values[-1] if values else 0
                    }
                else:
                    return {
                        "count": 0,
                        "avg": 0,
                        "min": 0,
                        "max": 0,
                        "latest": 0
                    }
            
            else:
                return {"error": f"Unknown widget type: {widget.type}"}
                
        except Exception as e:
            logger.error("Widget data retrieval failed", widget_id=widget.widget_id, error=str(e))
            return {"error": str(e)}
    
    async def list_dashboards(self) -> List[Dict[str, Any]]:
        """List all available dashboards"""
        try:
            dashboard_ids = await self.redis_client.smembers("dashboards:index")
            dashboards = []
            
            for dashboard_id in dashboard_ids:
                dashboard_key = f"dashboard:{dashboard_id.decode()}"
                config_data = await self.redis_client.get(dashboard_key)
                
                if config_data:
                    config = DashboardConfig.model_validate_json(config_data)
                    dashboards.append({
                        "dashboard_id": config.dashboard_id,
                        "title": config.title,
                        "description": config.description,
                        "widget_count": len(config.widgets),
                        "is_public": config.is_public
                    })
            
            return dashboards
            
        except Exception as e:
            logger.error("Dashboard listing failed", error=str(e))
            return []
    
    async def update_dashboard(self, dashboard_id: str, config: DashboardConfig) -> bool:
        """Update existing dashboard"""
        try:
            # Check if dashboard exists
            dashboard_key = f"dashboard:{dashboard_id}"
            exists = await self.redis_client.exists(dashboard_key)
            
            if not exists:
                raise ValueError(f"Dashboard not found: {dashboard_id}")
            
            # Update config
            config.dashboard_id = dashboard_id
            await self.redis_client.setex(
                dashboard_key,
                86400 * 30,  # 30 days TTL
                config.model_dump_json()
            )
            
            self.dashboards[dashboard_id] = config
            
            logger.info("Dashboard updated", dashboard_id=dashboard_id)
            return True
            
        except Exception as e:
            logger.error("Dashboard update failed", dashboard_id=dashboard_id, error=str(e))
            raise
    
    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """Delete dashboard"""
        try:
            # Remove from storage
            dashboard_key = f"dashboard:{dashboard_id}"
            await self.redis_client.delete(dashboard_key)
            
            # Remove from index
            await self.redis_client.srem("dashboards:index", dashboard_id)
            
            # Remove from memory
            if dashboard_id in self.dashboards:
                del self.dashboards[dashboard_id]
            
            logger.info("Dashboard deleted", dashboard_id=dashboard_id)
            return True
            
        except Exception as e:
            logger.error("Dashboard deletion failed", dashboard_id=dashboard_id, error=str(e))
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for dashboard generator"""
        try:
            await self.redis_client.ping()
            
            return {
                "status": "healthy",
                "dashboards_count": len(await self.list_dashboards()),
                "total_views": self.total_views
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
