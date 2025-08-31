"""Metrics collection and ingestion"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog
import redis.asyncio as redis
from collections import defaultdict, deque

from .config import settings
from .models import MetricEvent, MetricType

logger = structlog.get_logger(__name__)

class MetricsCollector:
    """Collect and ingest metrics from various sources"""
    
    def __init__(self):
        self.redis_client = None
        self.event_buffer = deque(maxlen=10000)
        self.events_processed = 0
        self.processing_rates = deque(maxlen=100)
        self.last_processing_time = datetime.utcnow()
        self.running = False
        
    async def initialize(self):
        """Initialize metrics collector"""
        try:
            self.redis_client = redis.from_url(settings.redis_url)
            logger.info("Metrics collector initialized")
        except Exception as e:
            logger.error("Failed to initialize metrics collector", error=str(e))
            raise
    
    async def start_collection(self):
        """Start background collection tasks"""
        self.running = True
        
        # Start Redis subscriber for real-time events
        asyncio.create_task(self._redis_subscriber())
        
        # Start batch processor
        asyncio.create_task(self._batch_processor())
        
        # Start system metrics collection
        asyncio.create_task(self._collect_system_metrics())
        
        logger.info("Metrics collection started")
    
    async def track_event(self, event: MetricEvent):
        """Track a single metric event"""
        try:
            # Add to buffer
            self.event_buffer.append(event)
            
            # Publish to Redis for real-time processing
            await self.redis_client.publish(
                "analytics:events",
                event.model_dump_json()
            )
            
            self.events_processed += 1
            
        except Exception as e:
            logger.error("Event tracking failed", event_id=event.event_id, error=str(e))
            raise
    
    async def track_events_batch(self, events: List[MetricEvent]) -> List[str]:
        """Track multiple events in batch"""
        results = []
        
        try:
            # Add to buffer
            for event in events:
                self.event_buffer.append(event)
                results.append(event.event_id)
            
            # Publish batch to Redis
            batch_data = [event.model_dump_json() for event in events]
            await self.redis_client.publish(
                "analytics:events:batch",
                json.dumps(batch_data)
            )
            
            self.events_processed += len(events)
            
            return results
            
        except Exception as e:
            logger.error("Batch event tracking failed", count=len(events), error=str(e))
            raise
    
    async def _redis_subscriber(self):
        """Subscribe to Redis channels for events from other services"""
        try:
            pubsub = self.redis_client.pubsub()
            
            # Subscribe to service-specific channels
            channels = [
                "speech:metrics",
                "intent:metrics", 
                "orchestrator:metrics",
                "rag:metrics",
                "tts:metrics",
                "llm:metrics",
                "gateway:metrics",
                "auth:metrics"
            ]
            
            for channel in channels:
                await pubsub.subscribe(channel)
            
            logger.info("Subscribed to Redis channels", channels=channels)
            
            while self.running:
                try:
                    message = await pubsub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        await self._process_redis_message(message)
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error("Redis message processing failed", error=str(e))
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error("Redis subscriber failed", error=str(e))
    
    async def _process_redis_message(self, message):
        """Process incoming Redis message"""
        try:
            channel = message['channel'].decode()
            data = json.loads(message['data'])
            
            # Extract service name from channel
            service = channel.split(':')[0]
            
            # Create metric event
            event = MetricEvent(
                event_id=f"{service}_{int(datetime.utcnow().timestamp())}",
                service=service,
                metric_type=data.get('type', MetricType.GAUGE),
                metric_name=data.get('name', 'unknown'),
                value=data.get('value', 0),
                timestamp=datetime.fromisoformat(data.get('timestamp', datetime.utcnow().isoformat())),
                labels=data.get('labels', {}),
                metadata=data.get('metadata', {})
            )
            
            self.event_buffer.append(event)
            self.events_processed += 1
            
        except Exception as e:
            logger.error("Redis message processing failed", error=str(e))
    
    async def _batch_processor(self):
        """Process events in batches"""
        while self.running:
            try:
                if len(self.event_buffer) >= settings.batch_size:
                    # Process batch
                    batch = []
                    for _ in range(min(settings.batch_size, len(self.event_buffer))):
                        if self.event_buffer:
                            batch.append(self.event_buffer.popleft())
                    
                    if batch:
                        await self._store_batch(batch)
                        
                        # Update processing rate
                        now = datetime.utcnow()
                        time_diff = (now - self.last_processing_time).total_seconds()
                        if time_diff > 0:
                            rate = len(batch) / time_diff
                            self.processing_rates.append(rate)
                        self.last_processing_time = now
                
                await asyncio.sleep(settings.processing_interval_seconds)
                
            except Exception as e:
                logger.error("Batch processing failed", error=str(e))
                await asyncio.sleep(5)
    
    async def _store_batch(self, batch: List[MetricEvent]):
        """Store batch of events"""
        try:
            if settings.storage_backend == "redis":
                await self._store_to_redis(batch)
            elif settings.storage_backend == "postgresql":
                await self._store_to_postgresql(batch)
            elif settings.storage_backend == "clickhouse":
                await self._store_to_clickhouse(batch)
            elif settings.storage_backend == "influxdb":
                await self._store_to_influxdb(batch)
            
            logger.debug("Batch stored", count=len(batch), backend=settings.storage_backend)
            
        except Exception as e:
            logger.error("Batch storage failed", count=len(batch), error=str(e))
    
    async def _store_to_redis(self, batch: List[MetricEvent]):
        """Store batch to Redis"""
        pipe = self.redis_client.pipeline()
        
        for event in batch:
            # Store raw event
            key = f"metrics:{event.service}:{event.metric_name}:{int(event.timestamp.timestamp())}"
            pipe.setex(
                key,
                timedelta(days=settings.data_retention_days),
                event.model_dump_json()
            )
            
            # Store in time series
            ts_key = f"ts:{event.service}:{event.metric_name}"
            pipe.zadd(ts_key, {event.model_dump_json(): event.timestamp.timestamp()})
            pipe.expire(ts_key, timedelta(days=settings.data_retention_days))
        
        await pipe.execute()
    
    async def _store_to_postgresql(self, batch: List[MetricEvent]):
        """Store batch to PostgreSQL"""
        # Implementation would use SQLAlchemy async session
        # This is a placeholder for the actual implementation
        pass
    
    async def _store_to_clickhouse(self, batch: List[MetricEvent]):
        """Store batch to ClickHouse"""
        # Implementation would use ClickHouse async client
        # This is a placeholder for the actual implementation
        pass
    
    async def _store_to_influxdb(self, batch: List[MetricEvent]):
        """Store batch to InfluxDB"""
        # Implementation would use InfluxDB async client
        # This is a placeholder for the actual implementation
        pass
    
    async def _collect_system_metrics(self):
        """Collect system-level metrics"""
        while self.running:
            try:
                import psutil
                
                # CPU metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                await self.track_event(MetricEvent(
                    event_id=f"system_cpu_{int(datetime.utcnow().timestamp())}",
                    service="system",
                    metric_type=MetricType.GAUGE,
                    metric_name="cpu_usage_percent",
                    value=cpu_percent,
                    timestamp=datetime.utcnow(),
                    labels={"host": "analytics"}
                ))
                
                # Memory metrics
                memory = psutil.virtual_memory()
                await self.track_event(MetricEvent(
                    event_id=f"system_memory_{int(datetime.utcnow().timestamp())}",
                    service="system",
                    metric_type=MetricType.GAUGE,
                    metric_name="memory_usage_percent",
                    value=memory.percent,
                    timestamp=datetime.utcnow(),
                    labels={"host": "analytics"}
                ))
                
                # Disk metrics
                disk = psutil.disk_usage('/')
                disk_percent = (disk.used / disk.total) * 100
                await self.track_event(MetricEvent(
                    event_id=f"system_disk_{int(datetime.utcnow().timestamp())}",
                    service="system",
                    metric_type=MetricType.GAUGE,
                    metric_name="disk_usage_percent",
                    value=disk_percent,
                    timestamp=datetime.utcnow(),
                    labels={"host": "analytics", "mount": "/"}
                ))
                
                await asyncio.sleep(60)  # Collect system metrics every minute
                
            except Exception as e:
                logger.error("System metrics collection failed", error=str(e))
                await asyncio.sleep(60)
    
    async def get_metrics_count(self) -> int:
        """Get total metrics count"""
        try:
            if settings.storage_backend == "redis":
                # Count keys matching pattern
                keys = await self.redis_client.keys("metrics:*")
                return len(keys)
            else:
                # For other backends, return processed count
                return self.events_processed
        except Exception as e:
            logger.error("Failed to get metrics count", error=str(e))
            return 0
    
    def get_processing_rate(self) -> float:
        """Get current processing rate (events/second)"""
        if not self.processing_rates:
            return 0.0
        return sum(self.processing_rates) / len(self.processing_rates)
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for metrics collector"""
        try:
            # Test Redis connection
            await self.redis_client.ping()
            
            return {
                "status": "healthy",
                "events_processed": self.events_processed,
                "buffer_size": len(self.event_buffer),
                "processing_rate": self.get_processing_rate(),
                "storage_backend": settings.storage_backend
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
