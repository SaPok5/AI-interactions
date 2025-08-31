"""Data processing and analytics engine"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog
import redis.asyncio as redis
import pandas as pd
import numpy as np
from collections import defaultdict

from .config import settings
from .models import MetricQuery, AggregatedMetric, Alert, AnalyticsReport, TrendAnalysis, Anomaly, Severity

logger = structlog.get_logger(__name__)

class DataProcessor:
    """Process and analyze metrics data"""
    
    def __init__(self):
        self.redis_client = None
        self.active_queries = 0
        self.cache = {}
        self.cache_hits = 0
        self.total_queries = 0
        
    async def initialize(self):
        """Initialize data processor"""
        try:
            self.redis_client = redis.from_url(settings.redis_url)
            logger.info("Data processor initialized")
        except Exception as e:
            logger.error("Failed to initialize data processor", error=str(e))
            raise
    
    async def start_processing(self):
        """Start background processing tasks"""
        # Start aggregation task
        asyncio.create_task(self._run_aggregations())
        
        # Start anomaly detection
        asyncio.create_task(self._detect_anomalies_background())
        
        # Start alerting
        if settings.enable_alerting:
            asyncio.create_task(self._monitor_alerts())
        
        logger.info("Data processing started")
    
    async def query_metrics(self, query: MetricQuery) -> List[Dict[str, Any]]:
        """Query metrics data"""
        self.active_queries += 1
        self.total_queries += 1
        
        try:
            # Check cache
            cache_key = self._generate_cache_key(query)
            if cache_key in self.cache:
                self.cache_hits += 1
                return self.cache[cache_key]
            
            # Query from storage
            if settings.storage_backend == "redis":
                results = await self._query_redis(query)
            else:
                results = []  # Placeholder for other backends
            
            # Cache results
            self.cache[cache_key] = results
            
            return results
            
        finally:
            self.active_queries -= 1
    
    async def _query_redis(self, query: MetricQuery) -> List[Dict[str, Any]]:
        """Query metrics from Redis"""
        results = []
        
        try:
            # Build pattern
            pattern = f"ts:{query.service or '*'}:{query.metric_name or '*'}"
            
            # Get matching keys
            keys = await self.redis_client.keys(pattern)
            
            for key in keys[:query.limit]:
                # Get time series data
                data = await self.redis_client.zrangebyscore(
                    key,
                    query.start_time.timestamp(),
                    query.end_time.timestamp(),
                    withscores=True
                )
                
                for item, timestamp in data:
                    try:
                        event_data = json.loads(item)
                        results.append({
                            "timestamp": datetime.fromtimestamp(timestamp),
                            "service": event_data.get("service"),
                            "metric_name": event_data.get("metric_name"),
                            "value": event_data.get("value"),
                            "labels": event_data.get("labels", {}),
                            "metadata": event_data.get("metadata", {})
                        })
                    except json.JSONDecodeError:
                        continue
            
            return sorted(results, key=lambda x: x["timestamp"])
            
        except Exception as e:
            logger.error("Redis query failed", error=str(e))
            return []
    
    async def get_aggregated_metrics(
        self,
        service: Optional[str] = None,
        metric_type: Optional[str] = None,
        aggregation: str = "avg",
        interval: str = "1h",
        start_time: datetime = None,
        end_time: datetime = None
    ) -> Dict[str, Any]:
        """Get aggregated metrics"""
        try:
            # Query raw data
            query = MetricQuery(
                service=service,
                metric_type=metric_type,
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )
            
            raw_data = await self.query_metrics(query)
            
            if not raw_data:
                return {"data": [], "aggregation": aggregation, "interval": interval}
            
            # Convert to DataFrame for processing
            df = pd.DataFrame(raw_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
            
            # Group by interval
            if interval == "1m":
                grouped = df.groupby(pd.Grouper(freq='1T'))
            elif interval == "5m":
                grouped = df.groupby(pd.Grouper(freq='5T'))
            elif interval == "15m":
                grouped = df.groupby(pd.Grouper(freq='15T'))
            elif interval == "1h":
                grouped = df.groupby(pd.Grouper(freq='1H'))
            elif interval == "1d":
                grouped = df.groupby(pd.Grouper(freq='1D'))
            else:
                grouped = df.groupby(pd.Grouper(freq='1H'))
            
            # Apply aggregation
            if aggregation == "avg":
                result = grouped['value'].mean()
            elif aggregation == "sum":
                result = grouped['value'].sum()
            elif aggregation == "count":
                result = grouped['value'].count()
            elif aggregation == "min":
                result = grouped['value'].min()
            elif aggregation == "max":
                result = grouped['value'].max()
            else:
                result = grouped['value'].mean()
            
            # Convert to list of dicts
            data = []
            for timestamp, value in result.items():
                if not pd.isna(value):
                    data.append({
                        "timestamp": timestamp.isoformat(),
                        "value": float(value)
                    })
            
            return {
                "data": data,
                "aggregation": aggregation,
                "interval": interval,
                "count": len(data)
            }
            
        except Exception as e:
            logger.error("Aggregated metrics query failed", error=str(e))
            return {"data": [], "error": str(e)}
    
    async def generate_system_report(self) -> AnalyticsReport:
        """Generate system-wide analytics report"""
        try:
            now = datetime.utcnow()
            start_time = now - timedelta(hours=24)
            
            # Get metrics for all services
            services = ["speech", "intent", "orchestrator", "rag", "tts", "llm", "gateway", "auth"]
            
            summary = {}
            metrics = []
            
            for service in services:
                query = MetricQuery(
                    service=service,
                    start_time=start_time,
                    end_time=now,
                    limit=1000
                )
                
                service_metrics = await self.query_metrics(query)
                
                if service_metrics:
                    # Calculate service summary
                    df = pd.DataFrame(service_metrics)
                    summary[service] = {
                        "total_events": len(service_metrics),
                        "avg_value": df['value'].mean() if not df.empty else 0,
                        "max_value": df['value'].max() if not df.empty else 0,
                        "min_value": df['value'].min() if not df.empty else 0
                    }
                    
                    metrics.extend(service_metrics)
            
            return AnalyticsReport(
                report_id=f"system_{int(now.timestamp())}",
                title="System Analytics Report",
                generated_at=now,
                period_start=start_time,
                period_end=now,
                summary=summary,
                metrics=metrics[:100],  # Limit for response size
                insights=[
                    f"Total events processed: {sum(s.get('total_events', 0) for s in summary.values())}",
                    f"Services monitored: {len([s for s in summary.values() if s.get('total_events', 0) > 0])}"
                ]
            )
            
        except Exception as e:
            logger.error("System report generation failed", error=str(e))
            raise
    
    async def detect_anomalies(
        self,
        service: Optional[str] = None,
        metric_type: Optional[str] = None,
        sensitivity: float = 0.95
    ) -> List[Anomaly]:
        """Detect anomalies in metrics"""
        anomalies = []
        
        try:
            # Query recent data
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)
            
            query = MetricQuery(
                service=service,
                metric_type=metric_type,
                start_time=start_time,
                end_time=end_time,
                limit=5000
            )
            
            data = await self.query_metrics(query)
            
            if len(data) < 10:  # Need minimum data points
                return anomalies
            
            # Group by service and metric
            grouped_data = defaultdict(list)
            for item in data:
                key = f"{item['service']}:{item['metric_name']}"
                grouped_data[key].append(item)
            
            # Detect anomalies for each metric
            for key, metric_data in grouped_data.items():
                if len(metric_data) < 10:
                    continue
                
                service_name, metric_name = key.split(':', 1)
                values = [item['value'] for item in metric_data]
                
                # Simple statistical anomaly detection
                mean_val = np.mean(values)
                std_val = np.std(values)
                
                if std_val == 0:
                    continue
                
                # Z-score based detection
                threshold = 2.5  # Adjust based on sensitivity
                
                for item in metric_data[-10:]:  # Check recent points
                    z_score = abs((item['value'] - mean_val) / std_val)
                    
                    if z_score > threshold:
                        severity = Severity.HIGH if z_score > 3 else Severity.MEDIUM
                        
                        anomalies.append(Anomaly(
                            anomaly_id=f"anomaly_{int(datetime.utcnow().timestamp())}",
                            service=service_name,
                            metric_name=metric_name,
                            timestamp=item['timestamp'],
                            expected_value=mean_val,
                            actual_value=item['value'],
                            deviation_score=z_score,
                            severity=severity
                        ))
            
            return anomalies
            
        except Exception as e:
            logger.error("Anomaly detection failed", error=str(e))
            return []
    
    def _generate_cache_key(self, query: MetricQuery) -> str:
        """Generate cache key for query"""
        import hashlib
        
        key_data = f"{query.service}|{query.metric_type}|{query.start_time}|{query.end_time}|{query.limit}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def _run_aggregations(self):
        """Run periodic aggregations"""
        while True:
            try:
                # Run aggregations for different intervals
                for interval in settings.aggregation_intervals:
                    await self._aggregate_interval(interval)
                
                await asyncio.sleep(300)  # Run every 5 minutes
                
            except Exception as e:
                logger.error("Aggregation failed", error=str(e))
                await asyncio.sleep(60)
    
    async def _aggregate_interval(self, interval: str):
        """Aggregate data for specific interval"""
        # Implementation placeholder
        pass
    
    async def _detect_anomalies_background(self):
        """Background anomaly detection"""
        while True:
            try:
                await self.detect_anomalies()
                await asyncio.sleep(300)  # Run every 5 minutes
            except Exception as e:
                logger.error("Background anomaly detection failed", error=str(e))
                await asyncio.sleep(300)
    
    async def _monitor_alerts(self):
        """Monitor for alert conditions"""
        while True:
            try:
                # Check alert thresholds
                for metric_name, threshold in settings.alert_thresholds.items():
                    await self._check_alert_threshold(metric_name, threshold)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error("Alert monitoring failed", error=str(e))
                await asyncio.sleep(60)
    
    async def _check_alert_threshold(self, metric_name: str, threshold: float):
        """Check if metric exceeds threshold"""
        # Implementation placeholder
        pass
    
    async def get_alerts(
        self,
        severity: Optional[str] = None,
        service: Optional[str] = None,
        active_only: bool = True
    ) -> List[Alert]:
        """Get system alerts"""
        # Implementation placeholder
        return []
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        # Implementation placeholder
        return True
    
    async def analyze_trends(
        self,
        metric_type: str,
        service: Optional[str] = None,
        period: str = "24h"
    ) -> TrendAnalysis:
        """Analyze trends in metrics"""
        # Implementation placeholder
        return TrendAnalysis(
            metric_name=metric_type,
            service=service or "all",
            period=period,
            trend_direction="stable",
            change_percentage=0.0,
            confidence=0.5,
            data_points=[]
        )
    
    async def export_data(
        self,
        format: str,
        service: Optional[str] = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> str:
        """Export analytics data"""
        # Implementation placeholder
        return f"export_{int(datetime.utcnow().timestamp())}"
    
    async def get_export_status(self, export_id: str) -> Dict[str, Any]:
        """Get export status"""
        # Implementation placeholder
        return {"status": "completed", "download_url": f"/exports/{export_id}"}
    
    async def cleanup_data(
        self,
        older_than_days: int,
        service: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cleanup old data"""
        # Implementation placeholder
        return {"deleted_records": 0, "freed_space_mb": 0}
    
    async def get_storage_size(self) -> float:
        """Get storage size in MB"""
        try:
            if settings.storage_backend == "redis":
                info = await self.redis_client.info("memory")
                return info.get("used_memory", 0) / (1024 * 1024)
            return 0.0
        except:
            return 0.0
    
    def get_cache_hit_rate(self) -> float:
        """Get cache hit rate"""
        if self.total_queries == 0:
            return 0.0
        return self.cache_hits / self.total_queries
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for data processor"""
        try:
            await self.redis_client.ping()
            
            return {
                "status": "healthy",
                "active_queries": self.active_queries,
                "cache_hit_rate": self.get_cache_hit_rate(),
                "storage_backend": settings.storage_backend
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
