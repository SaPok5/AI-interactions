"""Configuration settings for Analytics service"""

from pydantic_settings import BaseSettings
from typing import List, Dict


class Settings(BaseSettings):
    """Application settings"""
    
    # Server
    port: int = 8008
    debug: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379"
    
    # Database settings
    database_url: str = "postgresql+asyncpg://user:password@postgres:5432/analytics"
    clickhouse_url: str = "clickhouse://clickhouse:9000/analytics"
    influxdb_url: str = "http://influxdb:8086"
    influxdb_token: str = ""
    influxdb_org: str = "voice-assistant"
    influxdb_bucket: str = "metrics"
    
    # Storage settings
    storage_backend: str = "redis"  # redis, postgresql, clickhouse, influxdb
    data_retention_days: int = 90
    aggregation_intervals: List[str] = ["1m", "5m", "15m", "1h", "6h", "1d"]
    
    # Processing settings
    batch_size: int = 1000
    processing_interval_seconds: int = 30
    max_concurrent_queries: int = 10
    
    # Alerting
    enable_alerting: bool = True
    alert_thresholds: Dict[str, float] = {
        "error_rate": 0.05,
        "response_time_p95": 2000,
        "cpu_usage": 0.8,
        "memory_usage": 0.85,
        "disk_usage": 0.9
    }
    
    # Dashboard settings
    default_dashboard_refresh_seconds: int = 30
    max_dashboard_widgets: int = 20
    
    # Export settings
    export_formats: List[str] = ["csv", "json", "parquet"]
    max_export_rows: int = 1000000
    export_ttl_hours: int = 24
    
    # Performance
    cache_ttl_seconds: int = 300
    query_timeout_seconds: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
