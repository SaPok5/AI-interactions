"""Data models for Analytics service"""

from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

class MetricType(str, Enum):
    """Metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

class Severity(str, Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class MetricEvent(BaseModel):
    """Metric event data"""
    event_id: str
    service: str
    metric_type: MetricType
    metric_name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str] = {}
    metadata: Dict[str, Any] = {}

class MetricQuery(BaseModel):
    """Metric query parameters"""
    service: Optional[str] = None
    metric_type: Optional[str] = None
    metric_name: Optional[str] = None
    start_time: datetime
    end_time: datetime
    labels: Dict[str, str] = {}
    limit: int = 1000

class AggregatedMetric(BaseModel):
    """Aggregated metric result"""
    service: str
    metric_name: str
    aggregation: str
    interval: str
    timestamp: datetime
    value: float
    count: int

class Alert(BaseModel):
    """System alert"""
    alert_id: str
    service: str
    metric_name: str
    severity: Severity
    message: str
    threshold: float
    current_value: float
    timestamp: datetime
    acknowledged: bool = False
    resolved: bool = False

class DashboardWidget(BaseModel):
    """Dashboard widget configuration"""
    widget_id: str
    title: str
    type: str  # chart, gauge, table, stat
    query: MetricQuery
    visualization_config: Dict[str, Any] = {}

class DashboardConfig(BaseModel):
    """Dashboard configuration"""
    dashboard_id: Optional[str] = None
    title: str
    description: str = ""
    widgets: List[DashboardWidget]
    refresh_interval_seconds: int = 30
    is_public: bool = False

class AnalyticsReport(BaseModel):
    """Analytics report"""
    report_id: str
    title: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    summary: Dict[str, Any]
    metrics: List[Dict[str, Any]]
    insights: List[str] = []

class TrendAnalysis(BaseModel):
    """Trend analysis result"""
    metric_name: str
    service: str
    period: str
    trend_direction: str  # up, down, stable
    change_percentage: float
    confidence: float
    data_points: List[Dict[str, Any]]

class Anomaly(BaseModel):
    """Detected anomaly"""
    anomaly_id: str
    service: str
    metric_name: str
    timestamp: datetime
    expected_value: float
    actual_value: float
    deviation_score: float
    severity: Severity
