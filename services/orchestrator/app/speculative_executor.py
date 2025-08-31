"""Speculative execution engine for prefetching and caching responses"""

import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

from .config import settings
from .service_coordinator import ServiceCoordinator
from .models import SpeculativeTask, WorkflowStatus

logger = structlog.get_logger(__name__)

class SpeculativeExecutor:
    """Executes workflows speculatively based on predicted intents"""
    
    def __init__(self, service_coordinator: ServiceCoordinator):
        self.service_coordinator = service_coordinator
        self.active_tasks: Dict[str, SpeculativeTask] = {}
        self.completed_cache: Dict[str, Dict[str, Any]] = {}
        self.total_executed = 0
        self.total_hits = 0
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_expired_tasks())
    
    async def execute_speculative_workflows(
        self,
        speculative_intents: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute speculative workflows for predicted intents"""
        if not settings.enable_speculative_execution:
            return []
        
        results = []
        
        for spec_intent in speculative_intents:
            intent_name = spec_intent.get("intent", "")
            confidence = spec_intent.get("confidence", 0.0)
            
            # Only execute if confidence is above threshold
            if confidence < settings.speculative_prefetch_threshold:
                continue
            
            # Check if we already have a cached result
            cache_key = self._generate_cache_key(intent_name, entities, session_id)
            if cache_key in self.completed_cache:
                cached_result = self.completed_cache[cache_key]
                cached_result["from_cache"] = True
                results.append(cached_result)
                continue
            
            # Check if we're already processing this
            if any(task.intent == intent_name and task.status == WorkflowStatus.RUNNING 
                   for task in self.active_tasks.values()):
                continue
            
            # Start speculative execution
            task = await self._start_speculative_task(
                intent_name, entities, confidence, session_id
            )
            
            if task:
                results.append({
                    "task_id": task.task_id,
                    "intent": intent_name,
                    "confidence": confidence,
                    "status": "processing",
                    "estimated_completion_ms": spec_intent.get("estimated_completion_time_ms", 1000)
                })
        
        return results
    
    async def _start_speculative_task(
        self,
        intent: str,
        entities: List[Dict[str, Any]],
        confidence: float,
        session_id: Optional[str] = None
    ) -> Optional[SpeculativeTask]:
        """Start a speculative execution task"""
        
        # Check if we've reached max concurrent tasks
        active_count = len([t for t in self.active_tasks.values() 
                           if t.status == WorkflowStatus.RUNNING])
        
        if active_count >= settings.max_speculative_tasks:
            logger.debug("Max speculative tasks reached, skipping", intent=intent)
            return None
        
        task_id = str(uuid.uuid4())
        task = SpeculativeTask(
            task_id=task_id,
            intent=intent,
            confidence=confidence,
            status=WorkflowStatus.PENDING,
            created_at=datetime.utcnow()
        )
        
        self.active_tasks[task_id] = task
        
        # Execute in background
        asyncio.create_task(self._execute_speculative_workflow(
            task, entities, session_id
        ))
        
        return task
    
    async def _execute_speculative_workflow(
        self,
        task: SpeculativeTask,
        entities: List[Dict[str, Any]],
        session_id: Optional[str] = None
    ):
        """Execute speculative workflow"""
        try:
            task.status = WorkflowStatus.RUNNING
            
            # Execute workflow based on intent
            result = await self._execute_intent_workflow(
                task.intent, entities, session_id
            )
            
            task.status = WorkflowStatus.COMPLETED
            task.result = result
            
            # Cache the result
            cache_key = self._generate_cache_key(task.intent, entities, session_id)
            self.completed_cache[cache_key] = {
                "result": result,
                "created_at": datetime.utcnow(),
                "intent": task.intent,
                "confidence": task.confidence
            }
            
            self.total_executed += 1
            
            logger.debug("Speculative workflow completed", 
                        task_id=task.task_id, 
                        intent=task.intent)
            
        except asyncio.TimeoutError:
            task.status = WorkflowStatus.FAILED
            logger.warning("Speculative workflow timed out", 
                          task_id=task.task_id, 
                          intent=task.intent)
            
        except Exception as e:
            task.status = WorkflowStatus.FAILED
            logger.error("Speculative workflow failed", 
                        task_id=task.task_id, 
                        intent=task.intent, 
                        error=str(e))
    
    async def _execute_intent_workflow(
        self,
        intent: str,
        entities: List[Dict[str, Any]],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute workflow for specific intent"""
        
        # Add timeout for speculative execution
        try:
            return await asyncio.wait_for(
                self._run_intent_workflow(intent, entities, session_id),
                timeout=settings.speculative_timeout
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(f"Speculative workflow for {intent} timed out")
    
    async def _run_intent_workflow(
        self,
        intent: str,
        entities: List[Dict[str, Any]],
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the actual workflow logic"""
        
        if intent == "question":
            # Pre-fetch common information
            return await self._prefetch_question_response(entities)
            
        elif intent == "weather":
            # Pre-fetch weather data
            return await self._prefetch_weather_data(entities)
            
        elif intent == "navigation":
            # Pre-fetch navigation data
            return await self._prefetch_navigation_data(entities)
            
        elif intent == "booking":
            # Pre-fetch booking options
            return await self._prefetch_booking_options(entities)
            
        elif intent == "shopping":
            # Pre-fetch product information
            return await self._prefetch_shopping_results(entities)
            
        else:
            # Generic prefetch using LLM
            return await self._prefetch_generic_response(intent, entities)
    
    async def _prefetch_question_response(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prefetch response for question intent"""
        # Use RAG service to get relevant context
        query = " ".join([entity.get("text", "") for entity in entities])
        
        rag_result = await self.service_coordinator.call_rag_service(
            query=query,
            entities=entities,
            limit=3
        )
        
        return {
            "type": "question_prefetch",
            "context": rag_result.get("context", ""),
            "sources": rag_result.get("sources", []),
            "entities": entities
        }
    
    async def _prefetch_weather_data(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prefetch weather data"""
        location = self._extract_location(entities)
        
        # In real implementation, call weather API
        return {
            "type": "weather_prefetch",
            "location": location or "current_location",
            "data": {
                "temperature": "72°F",
                "condition": "sunny",
                "forecast": "Partly cloudy later"
            }
        }
    
    async def _prefetch_navigation_data(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prefetch navigation data"""
        destination = self._extract_location(entities)
        
        return {
            "type": "navigation_prefetch",
            "destination": destination,
            "routes": [
                {"type": "driving", "duration": "15 mins", "distance": "5.2 miles"},
                {"type": "walking", "duration": "45 mins", "distance": "2.1 miles"}
            ]
        }
    
    async def _prefetch_booking_options(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prefetch booking options"""
        return {
            "type": "booking_prefetch",
            "options": [
                {"name": "Restaurant A", "time": "7:00 PM", "price": "$50"},
                {"name": "Restaurant B", "time": "8:00 PM", "price": "$75"}
            ],
            "entities": entities
        }
    
    async def _prefetch_shopping_results(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prefetch shopping results"""
        product = self._extract_product(entities)
        
        return {
            "type": "shopping_prefetch",
            "product": product,
            "results": [
                {"name": "Product A", "price": "$29.99", "rating": 4.5},
                {"name": "Product B", "price": "$39.99", "rating": 4.2}
            ]
        }
    
    async def _prefetch_generic_response(
        self, 
        intent: str, 
        entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prefetch generic response using LLM"""
        prompt = f"Prepare response for {intent} intent"
        
        llm_result = await self.service_coordinator.call_llm_service(
            prompt=prompt,
            context="",
            entities=entities,
            max_tokens=200
        )
        
        return {
            "type": "generic_prefetch",
            "intent": intent,
            "response": llm_result.get("response", ""),
            "entities": entities
        }
    
    def get_cached_result(
        self, 
        intent: str, 
        entities: List[Dict[str, Any]], 
        session_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get cached speculative result if available"""
        cache_key = self._generate_cache_key(intent, entities, session_id)
        
        if cache_key in self.completed_cache:
            cached = self.completed_cache[cache_key]
            
            # Check if cache is still valid (5 minutes)
            if datetime.utcnow() - cached["created_at"] < timedelta(minutes=5):
                # Mark as hit
                self.total_hits += 1
                
                # Find and mark the task as hit
                for task in self.active_tasks.values():
                    if task.intent == intent and not task.hit:
                        task.hit = True
                        break
                
                return cached["result"]
        
        return None
    
    def _generate_cache_key(
        self, 
        intent: str, 
        entities: List[Dict[str, Any]], 
        session_id: Optional[str] = None
    ) -> str:
        """Generate cache key for speculative result"""
        entity_text = "|".join([
            f"{e.get('label', '')}:{e.get('text', '')}" 
            for e in entities
        ])
        
        return f"{intent}:{entity_text}:{session_id or 'anonymous'}"
    
    def _extract_location(self, entities: List[Dict[str, Any]]) -> Optional[str]:
        """Extract location from entities"""
        for entity in entities:
            if entity.get("label", "").lower() in ["gpe", "loc", "location"]:
                return entity.get("text", "")
        return None
    
    def _extract_product(self, entities: List[Dict[str, Any]]) -> Optional[str]:
        """Extract product from entities"""
        for entity in entities:
            if entity.get("label", "").lower() in ["product", "org"]:
                return entity.get("text", "")
        return None
    
    async def _cleanup_expired_tasks(self):
        """Clean up expired speculative tasks"""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                cutoff_time = datetime.utcnow() - timedelta(minutes=10)
                expired_tasks = [
                    task_id for task_id, task in self.active_tasks.items()
                    if task.created_at < cutoff_time
                ]
                
                for task_id in expired_tasks:
                    del self.active_tasks[task_id]
                
                # Clean up old cache entries
                expired_cache = [
                    key for key, cached in self.completed_cache.items()
                    if cached["created_at"] < cutoff_time
                ]
                
                for key in expired_cache:
                    del self.completed_cache[key]
                
                if expired_tasks or expired_cache:
                    logger.debug("Cleaned up expired speculative data", 
                                tasks=len(expired_tasks), 
                                cache=len(expired_cache))
                
            except Exception as e:
                logger.error("Error in speculative cleanup", error=str(e))
    
    def get_hit_rate(self) -> float:
        """Get speculative execution hit rate"""
        if self.total_executed == 0:
            return 0.0
        return self.total_hits / self.total_executed
    
    def get_active_task_count(self) -> int:
        """Get number of active speculative tasks"""
        return len([t for t in self.active_tasks.values() 
                   if t.status == WorkflowStatus.RUNNING])
    
    def cancel_all_tasks(self):
        """Cancel all active speculative tasks"""
        for task in self.active_tasks.values():
            if task.status == WorkflowStatus.RUNNING:
                task.status = WorkflowStatus.CANCELLED
