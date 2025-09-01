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
    """Subscribe to intent results and trigger workflows with enhanced error handling"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("intent_results", "orchestrator_input")
    
    logger.info("Orchestrator service subscribed to Redis channels")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                logger.info("Received Redis message", channel=message["channel"].decode(), data=message["data"])
                
                # Handle potential binary data
                message_data = message["data"]
                if isinstance(message_data, bytes):
                    message_data = message_data.decode()
                
                data = json.loads(message_data)
                logger.info("Processing message", message_type=data.get("type"), connection_id=data.get("connection_id"))
                
                await process_intent_result(
                    data, workflow_engine, speculative_executor, redis_client
                )
            except json.JSONDecodeError as je:
                logger.error("Invalid JSON in Redis message", error=str(je), raw_data=message["data"])
            except Exception as e:
                logger.error("Error processing intent result", error=str(e), message_data=message["data"])

async def process_intent_result(
    data: Dict[str, Any],
    workflow_engine: WorkflowEngine,
    speculative_executor: SpeculativeExecutor,
    redis_client: redis.Redis
):
    """Process intent result and orchestrate response with enhanced error handling"""
    try:
        connection_id = data.get("connection_id")
        message_type = data.get("type")
        text = data.get("text", "")
        
        logger.info("Processing intent result", message_type=message_type, connection_id=connection_id, has_text=bool(text))
        
        if not connection_id:
            logger.warning("Missing connection_id in message", data=data)
            return
        
        # Handle voice input directly with RAG-powered AI response
        if message_type == "voice_input":
            if not text or text.strip() == "":
                logger.warning("Empty voice input received", connection_id=connection_id)
                # Send a response indicating empty input
                response = {
                    "type": "ai_response",
                    "connection_id": connection_id,
                    "data": {
                        "text": "I didn't catch that. Could you please try speaking again?",
                        "auto_generated": False
                    }
                }
                await redis_client.publish("orchestrator_output", json.dumps(response))
                return
            
            logger.info("Processing voice input", text=text, connection_id=connection_id)
            # Generate AI response using RAG and LLM services
            ai_response = await generate_ai_response_with_rag(text, redis_client)
            
            if not ai_response:
                logger.warning("Empty AI response generated", connection_id=connection_id)
                ai_response = "I'm sorry, I couldn't process that request."
            
            logger.info("Generated AI response", response=ai_response[:100], connection_id=connection_id)
            
            # Send AI response back to gateway
            response = {
                "type": "ai_response",
                "connection_id": connection_id,
                "data": {
                    "text": ai_response,
                    "auto_generated": False
                }
            }
            
            logger.info("Publishing AI response to orchestrator_output", connection_id=connection_id)
            await redis_client.publish("orchestrator_output", json.dumps(response))
            return
        
        # Handle legacy intent-based processing
        session_id = data.get("session_id")
        is_final = data.get("is_final", False)
        intent = data.get("intent", {})
        entities = data.get("entities", [])
        speculative_intents = data.get("speculative_intents", [])
        
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
        
        await redis_client.publish("orchestrator_output", json.dumps(response))
        
    except Exception as e:
        logger.error("Error processing intent result", error=str(e))

async def generate_ai_response_with_rag(user_text: str, redis_client: redis.Redis) -> str:
    """Generate AI response using RAG and LLM services"""
    try:
        import aiohttp
        
        # First, search for relevant documents using RAG service
        rag_response = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://rag:8005/search",
                    json={
                        "query": user_text,
                        "limit": 3,
                        "threshold": 0.7
                    }
                ) as resp:
                    if resp.status == 200:
                        rag_response = await resp.json()
        except Exception as e:
            logger.warning("RAG service unavailable, using fallback", error=str(e))
        
        # Prepare context for LLM
        context = ""
        if rag_response and rag_response.get("chunks"):
            context = "\n\n".join([
                f"Document: {chunk.get('metadata', {}).get('filename', 'Unknown')}\n{chunk.get('content', '')}"
                for chunk in rag_response["chunks"][:3]
            ])
        
        # Generate response using LLM service
        try:
            async with aiohttp.ClientSession() as session:
                messages = [
                    {
                        "role": "system",
                        "content": f"""You are a helpful AI assistant. Answer the user's question based on the provided context from their uploaded documents.

Context from documents:
{context if context else "No relevant documents found."}

Instructions:
- If you have relevant context, provide a detailed answer based on the documents
- If no relevant context is available, provide a helpful general response
- Be conversational and engaging
- Keep responses concise but informative"""
                    },
                    {
                        "role": "user", 
                        "content": user_text
                    }
                ]
                
                async with session.post(
                    "http://llm:8007/chat",
                    json={
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 300
                    }
                ) as resp:
                    if resp.status == 200:
                        llm_response = await resp.json()
                        return llm_response.get("content", "I'm sorry, I couldn't generate a response at the moment.")
        except Exception as e:
            logger.warning("LLM service unavailable, using fallback", error=str(e))
        
        # Fallback responses if services are unavailable
        user_text_lower = user_text.lower().strip()
        
        if any(greeting in user_text_lower for greeting in ["hello", "hi", "hey", "good morning", "good afternoon"]):
            return "Hello! I'm here to help you with your documents and answer any questions you have. What would you like to know?"
        
        elif any(question in user_text_lower for question in ["what", "how", "why", "when", "where", "who"]):
            return f"That's an interesting question about '{user_text}'. I'd be happy to help you understand this better. Could you provide more details or upload a document for me to analyze?"
        
        else:
            return f"I understand you're asking about '{user_text}'. I'm here to help you explore topics and analyze documents. Please feel free to upload documents or ask more specific questions."
            
    except Exception as e:
        logger.error("Error generating AI response", error=str(e))
        return "I apologize, but I'm having trouble processing your request right now. Please try again."

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
