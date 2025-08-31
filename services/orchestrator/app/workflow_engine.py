"""Workflow execution engine for orchestrating service calls"""

import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

from .config import settings
from .service_coordinator import ServiceCoordinator
from .models import WorkflowExecution, WorkflowStatus

logger = structlog.get_logger(__name__)

class WorkflowEngine:
    """Workflow execution and orchestration engine"""
    
    def __init__(self, service_coordinator: ServiceCoordinator):
        self.service_coordinator = service_coordinator
        self.active_workflows: Dict[str, WorkflowExecution] = {}
        self.total_executed = 0
        self.execution_times = []
        
        # Define workflow templates
        self.workflow_templates = {
            "greeting": self._greeting_workflow,
            "question": self._question_workflow,
            "request": self._request_workflow,
            "booking": self._booking_workflow,
            "weather": self._weather_workflow,
            "navigation": self._navigation_workflow,
            "shopping": self._shopping_workflow,
            "complaint": self._complaint_workflow,
            "goodbye": self._goodbye_workflow
        }
    
    async def execute_workflow(
        self,
        intent: Dict[str, Any],
        entities: List[Dict[str, Any]],
        text: str,
        session_id: Optional[str] = None,
        is_final: bool = True
    ) -> Dict[str, Any]:
        """Execute workflow based on intent"""
        workflow_id = str(uuid.uuid4())
        intent_name = intent.get("name", "unknown")
        
        # Create workflow execution record
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            intent=intent_name,
            status=WorkflowStatus.PENDING,
            start_time=datetime.utcnow()
        )
        
        self.active_workflows[workflow_id] = execution
        
        try:
            execution.status = WorkflowStatus.RUNNING
            
            # Get workflow template
            workflow_func = self.workflow_templates.get(intent_name, self._default_workflow)
            
            # Execute workflow
            result = await workflow_func(
                intent=intent,
                entities=entities,
                text=text,
                session_id=session_id,
                is_final=is_final
            )
            
            # Update execution record
            execution.status = WorkflowStatus.COMPLETED
            execution.end_time = datetime.utcnow()
            execution.execution_time_ms = (execution.end_time - execution.start_time).total_seconds() * 1000
            execution.result = result
            
            # Track metrics
            self.total_executed += 1
            self.execution_times.append(execution.execution_time_ms)
            if len(self.execution_times) > 1000:  # Keep last 1000 executions
                self.execution_times = self.execution_times[-1000:]
            
            # Add workflow metadata to result
            result["workflow_id"] = workflow_id
            result["execution_time_ms"] = execution.execution_time_ms
            
            return result
            
        except Exception as e:
            execution.status = WorkflowStatus.FAILED
            execution.error = str(e)
            execution.end_time = datetime.utcnow()
            
            logger.error("Workflow execution failed", 
                        workflow_id=workflow_id, 
                        intent=intent_name, 
                        error=str(e))
            
            return {
                "workflow_id": workflow_id,
                "error": str(e),
                "response_text": "I apologize, but I encountered an error processing your request.",
                "actions": [],
                "data": {}
            }
        
        finally:
            # Clean up completed workflow after delay
            asyncio.create_task(self._cleanup_workflow(workflow_id, delay=300))
    
    async def _greeting_workflow(self, **kwargs) -> Dict[str, Any]:
        """Handle greeting intents"""
        return {
            "response_text": "Hello! How can I assist you today?",
            "actions": [
                {"type": "display_suggestions", "suggestions": [
                    "Ask a question",
                    "Make a booking",
                    "Get weather info"
                ]}
            ],
            "data": {"intent": "greeting", "next_expected": ["question", "request", "booking"]}
        }
    
    async def _question_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle question intents"""
        # Use RAG service to find relevant information
        rag_result = await self.service_coordinator.call_rag_service(
            query=text,
            entities=entities
        )
        
        # Use LLM service to generate response
        llm_result = await self.service_coordinator.call_llm_service(
            prompt=f"Answer this question: {text}",
            context=rag_result.get("context", ""),
            entities=entities
        )
        
        return {
            "response_text": llm_result.get("response", "I'm not sure about that. Could you rephrase your question?"),
            "actions": [
                {"type": "display_sources", "sources": rag_result.get("sources", [])}
            ],
            "data": {
                "intent": "question",
                "confidence": llm_result.get("confidence", 0.8),
                "sources": rag_result.get("sources", [])
            }
        }
    
    async def _request_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle request intents"""
        # Determine what kind of help is needed
        help_type = self._classify_request_type(text, entities)
        
        if help_type == "information":
            # Use RAG + LLM for information requests
            rag_result = await self.service_coordinator.call_rag_service(
                query=text,
                entities=entities
            )
            
            llm_result = await self.service_coordinator.call_llm_service(
                prompt=f"Help with this request: {text}",
                context=rag_result.get("context", ""),
                entities=entities
            )
            
            response_text = llm_result.get("response", "I'd be happy to help! Could you provide more details?")
            
        elif help_type == "booking":
            response_text = "I can help you make a booking. What would you like to book?"
            
        else:
            response_text = "I'm here to help! Could you tell me more about what you need?"
        
        return {
            "response_text": response_text,
            "actions": [
                {"type": "request_clarification" if help_type == "unknown" else "provide_options"}
            ],
            "data": {"intent": "request", "help_type": help_type}
        }
    
    async def _booking_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle booking intents"""
        # Extract booking details from entities
        booking_details = self._extract_booking_details(entities)
        
        # Check if we have enough information
        missing_info = self._check_missing_booking_info(booking_details)
        
        if missing_info:
            return {
                "response_text": f"I'd be happy to help you make a booking. I need some more information: {', '.join(missing_info)}",
                "actions": [
                    {"type": "request_info", "required_fields": missing_info}
                ],
                "data": {"intent": "booking", "partial_details": booking_details}
            }
        else:
            # Process booking (in real implementation, this would call external booking APIs)
            return {
                "response_text": "Great! I've found some options for your booking. Let me show you what's available.",
                "actions": [
                    {"type": "display_booking_options", "options": [
                        {"name": "Option 1", "price": "$50", "time": "2:00 PM"},
                        {"name": "Option 2", "price": "$75", "time": "4:00 PM"}
                    ]}
                ],
                "data": {"intent": "booking", "details": booking_details}
            }
    
    async def _weather_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle weather intents"""
        # Extract location from entities
        location = self._extract_location(entities)
        
        if not location:
            return {
                "response_text": "I can help you with weather information. Which location would you like to know about?",
                "actions": [{"type": "request_location"}],
                "data": {"intent": "weather", "needs_location": True}
            }
        
        # In real implementation, call weather API
        return {
            "response_text": f"The weather in {location} is currently sunny with a temperature of 72°F. There's a slight chance of rain later today.",
            "actions": [
                {"type": "display_weather", "location": location, "temperature": "72°F", "condition": "sunny"}
            ],
            "data": {"intent": "weather", "location": location}
        }
    
    async def _navigation_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle navigation intents"""
        destination = self._extract_location(entities)
        
        if not destination:
            return {
                "response_text": "I can help you with directions. Where would you like to go?",
                "actions": [{"type": "request_destination"}],
                "data": {"intent": "navigation", "needs_destination": True}
            }
        
        return {
            "response_text": f"I can help you get to {destination}. Would you like driving or walking directions?",
            "actions": [
                {"type": "display_navigation_options", "destination": destination}
            ],
            "data": {"intent": "navigation", "destination": destination}
        }
    
    async def _shopping_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle shopping intents"""
        product = self._extract_product(entities)
        
        if not product:
            return {
                "response_text": "I can help you find products. What are you looking for?",
                "actions": [{"type": "request_product"}],
                "data": {"intent": "shopping", "needs_product": True}
            }
        
        return {
            "response_text": f"I found several options for {product}. Here are some popular choices:",
            "actions": [
                {"type": "display_products", "query": product}
            ],
            "data": {"intent": "shopping", "product": product}
        }
    
    async def _complaint_workflow(self, text: str, entities: List[Dict], **kwargs) -> Dict[str, Any]:
        """Handle complaint intents"""
        return {
            "response_text": "I'm sorry to hear you're having an issue. I'm here to help resolve this. Could you tell me more about the problem?",
            "actions": [
                {"type": "escalate_to_support"},
                {"type": "request_details"}
            ],
            "data": {"intent": "complaint", "priority": "high"}
        }
    
    async def _goodbye_workflow(self, **kwargs) -> Dict[str, Any]:
        """Handle goodbye intents"""
        return {
            "response_text": "Thank you for chatting with me! Have a great day!",
            "actions": [
                {"type": "end_session"}
            ],
            "data": {"intent": "goodbye", "session_end": True}
        }
    
    async def _default_workflow(self, text: str, **kwargs) -> Dict[str, Any]:
        """Default workflow for unknown intents"""
        # Use LLM service for general response
        llm_result = await self.service_coordinator.call_llm_service(
            prompt=f"Respond to: {text}",
            context="",
            entities=kwargs.get("entities", [])
        )
        
        return {
            "response_text": llm_result.get("response", "I'm not sure how to help with that. Could you rephrase your request?"),
            "actions": [
                {"type": "request_clarification"}
            ],
            "data": {"intent": "unknown", "needs_clarification": True}
        }
    
    def _classify_request_type(self, text: str, entities: List[Dict]) -> str:
        """Classify the type of request"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ["book", "reserve", "schedule"]):
            return "booking"
        elif any(word in text_lower for word in ["find", "search", "tell me", "what is"]):
            return "information"
        else:
            return "unknown"
    
    def _extract_booking_details(self, entities: List[Dict]) -> Dict[str, Any]:
        """Extract booking details from entities"""
        details = {}
        
        for entity in entities:
            label = entity.get("label", "").lower()
            text = entity.get("text", "")
            
            if label in ["date", "time"]:
                details[label] = text
            elif label in ["person", "org"]:
                details["service"] = text
            elif label in ["cardinal", "quantity"]:
                details["quantity"] = text
        
        return details
    
    def _check_missing_booking_info(self, details: Dict[str, Any]) -> List[str]:
        """Check what booking information is missing"""
        required = ["date", "time"]
        missing = []
        
        for field in required:
            if field not in details or not details[field]:
                missing.append(field)
        
        return missing
    
    def _extract_location(self, entities: List[Dict]) -> Optional[str]:
        """Extract location from entities"""
        for entity in entities:
            if entity.get("label", "").lower() in ["gpe", "loc", "location"]:
                return entity.get("text", "")
        return None
    
    def _extract_product(self, entities: List[Dict]) -> Optional[str]:
        """Extract product from entities"""
        for entity in entities:
            if entity.get("label", "").lower() in ["product", "org"]:
                return entity.get("text", "")
        return None
    
    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get status of a workflow"""
        if workflow_id not in self.active_workflows:
            raise ValueError("Workflow not found")
        
        execution = self.active_workflows[workflow_id]
        return {
            "workflow_id": workflow_id,
            "status": execution.status,
            "intent": execution.intent,
            "start_time": execution.start_time.isoformat(),
            "end_time": execution.end_time.isoformat() if execution.end_time else None,
            "execution_time_ms": execution.execution_time_ms,
            "error": execution.error
        }
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow"""
        if workflow_id not in self.active_workflows:
            return False
        
        execution = self.active_workflows[workflow_id]
        if execution.status == WorkflowStatus.RUNNING:
            execution.status = WorkflowStatus.CANCELLED
            execution.end_time = datetime.utcnow()
            return True
        
        return False
    
    def get_available_workflows(self) -> List[str]:
        """Get list of available workflow templates"""
        return list(self.workflow_templates.keys())
    
    def get_average_execution_time(self) -> float:
        """Get average execution time"""
        if not self.execution_times:
            return 0.0
        return sum(self.execution_times) / len(self.execution_times)
    
    async def _cleanup_workflow(self, workflow_id: str, delay: int = 300):
        """Clean up workflow after delay"""
        await asyncio.sleep(delay)
        if workflow_id in self.active_workflows:
            del self.active_workflows[workflow_id]
