"""
Orchestrator Service - Complete Implementation
Coordinates all microservices and implements speculative execution
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis

from .config import settings
from .workflow_engine import WorkflowEngine
from .speculative_executor import SpeculativeExecutor
from .service_coordinator import ServiceCoordinator
from .models import ConversationRequest, ConversationResponse, WorkflowStatus

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🎭 Starting Orchestrator Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize core components
    app.state.service_coordinator = ServiceCoordinator()
    app.state.workflow_engine = WorkflowEngine(app.state.service_coordinator)
    app.state.speculative_executor = SpeculativeExecutor(app.state.service_coordinator)
    
    # Start Redis subscribers
    app.state.intent_subscriber = asyncio.create_task(
        intent_result_subscriber(
            app.state.redis,
            app.state.workflow_engine,
            app.state.speculative_executor
        )
    )
    
    yield
    
    logger.info("🛑 Shutting down Orchestrator Service")
    app.state.intent_subscriber.cancel()
    await app.state.redis.close()

app = FastAPI(
    title="Orchestrator Service",
    description="Workflow orchestration with speculative execution",
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

async def intent_result_subscriber(
    redis_client: redis.Redis,
    workflow_engine: WorkflowEngine,
    speculative_executor: SpeculativeExecutor
):
    """Subscribe to intent results and trigger workflows"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("intent_results")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                await process_intent_result(
                    data, workflow_engine, speculative_executor, redis_client
                )
            except Exception as e:
                logger.error("Error processing intent result", error=str(e))

async def process_intent_result(
    data: Dict[str, Any],
    workflow_engine: WorkflowEngine,
    speculative_executor: SpeculativeExecutor,
    redis_client: redis.Redis
):
    """Process intent result and orchestrate response"""
    try:
        connection_id = data.get("connection_id")
        session_id = data.get("session_id")
        text = data.get("text", "")
        is_final = data.get("is_final", False)
        intent = data.get("intent", {})
        entities = data.get("entities", [])
        speculative_intents = data.get("speculative_intents", [])
        
        if not connection_id:
            return
        
        # Execute main workflow
        workflow_result = await workflow_engine.execute_workflow(
            intent=intent,
            entities=entities,
            text=text,
            session_id=session_id,
            is_final=is_final
        )
        
        # Execute speculative workflows if not final
        speculative_results = []
        if not is_final and speculative_intents:
            speculative_results = await speculative_executor.execute_speculative_workflows(
                speculative_intents=speculative_intents,
                entities=entities,
                session_id=session_id
            )
        
        # Send orchestrated response
        response = {
            "type": "orchestrator_response",
            "connection_id": connection_id,
            "session_id": session_id,
            "workflow_result": workflow_result,
            "speculative_results": speculative_results,
            "is_final": is_final
        }
        
        await redis_client.publish("orchestrator_responses", json.dumps(response))
        
    except Exception as e:
        logger.error("Error processing intent result", error=str(e))

@app.post("/conversation", response_model=ConversationResponse)
async def process_conversation(request: ConversationRequest):
    """Process a complete conversation request"""
    try:
        # Execute workflow
        workflow_result = await app.state.workflow_engine.execute_workflow(
            intent=request.intent,
            entities=request.entities,
            text=request.text,
            session_id=request.session_id,
            is_final=True
        )
        
        return ConversationResponse(
            response_text=workflow_result.get("response_text", ""),
            actions=workflow_result.get("actions", []),
            data=workflow_result.get("data", {}),
            workflow_id=workflow_result.get("workflow_id"),
            execution_time_ms=workflow_result.get("execution_time_ms", 0)
        )
        
    except Exception as e:
        logger.error("Conversation processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Conversation processing failed")

@app.post("/execute-workflow")
async def execute_workflow(
    intent: Dict[str, Any],
    entities: List[Dict[str, Any]] = [],
    text: str = "",
    session_id: Optional[str] = None
):
    """Execute a specific workflow"""
    try:
        result = await app.state.workflow_engine.execute_workflow(
            intent=intent,
            entities=entities,
            text=text,
            session_id=session_id,
            is_final=True
        )
        return result
    except Exception as e:
        logger.error("Workflow execution failed", error=str(e))
        raise HTTPException(status_code=500, detail="Workflow execution failed")

@app.get("/workflows")
async def get_available_workflows():
    """Get list of available workflows"""
    return {
        "workflows": app.state.workflow_engine.get_available_workflows()
    }

@app.get("/workflow-status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get status of a specific workflow"""
    try:
        status = await app.state.workflow_engine.get_workflow_status(workflow_id)
        return status
    except Exception as e:
        logger.error("Failed to get workflow status", error=str(e))
        raise HTTPException(status_code=404, detail="Workflow not found")

@app.post("/cancel-workflow/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """Cancel a running workflow"""
    try:
        result = await app.state.workflow_engine.cancel_workflow(workflow_id)
        return {"cancelled": result}
    except Exception as e:
        logger.error("Failed to cancel workflow", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to cancel workflow")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Check service connectivity
    service_health = await app.state.service_coordinator.check_all_services()
    
    return {
        "status": "healthy",
        "service": "orchestrator",
        "services": service_health,
        "active_workflows": len(app.state.workflow_engine.active_workflows),
        "speculative_tasks": len(app.state.speculative_executor.active_tasks)
    }

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

orchestrator_total_workflows = Counter('orchestrator_total_workflows_executed', 'Total workflows executed')
orchestrator_active_workflows = Gauge('orchestrator_active_workflows', 'Number of active workflows')
orchestrator_avg_execution_time = Gauge('orchestrator_average_execution_time_ms', 'Average execution time in ms')
orchestrator_speculative_tasks = Counter('orchestrator_speculative_tasks_executed', 'Total speculative tasks executed')
orchestrator_speculative_hit_rate = Gauge('orchestrator_speculative_hit_rate', 'Speculative execution hit rate')

@app.get("/metrics")
async def get_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values
    orchestrator_total_workflows._value._value = app.state.workflow_engine.total_executed
    orchestrator_active_workflows.set(len(app.state.workflow_engine.active_workflows))
    orchestrator_avg_execution_time.set(app.state.workflow_engine.get_average_execution_time())
    orchestrator_speculative_tasks._value._value = app.state.speculative_executor.total_executed
    orchestrator_speculative_hit_rate.set(app.state.speculative_executor.get_hit_rate())
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
