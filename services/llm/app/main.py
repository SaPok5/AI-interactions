"""
LLM Service - Complete Implementation
Handles natural language generation with tool calling capabilities
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
from .llm_engine import LLMEngine
from .tool_manager import ToolManager
from .prompt_manager import PromptManager
from .models import GenerationRequest, GenerationResponse, ToolCall, ToolResult

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🧠 Starting LLM Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize core components
    app.state.llm_engine = LLMEngine()
    app.state.tool_manager = ToolManager()
    app.state.prompt_manager = PromptManager()
    
    # Initialize LLM models
    await app.state.llm_engine.initialize()
    await app.state.tool_manager.load_tools()
    await app.state.prompt_manager.load_templates()
    
    logger.info("✅ LLM Service initialized")
    
    yield
    
    logger.info("🛑 Shutting down LLM Service")
    await app.state.redis.close()

app = FastAPI(
    title="LLM Service",
    description="Large Language Model service with tool calling",
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

@app.post("/generate", response_model=GenerationResponse)
async def generate_text(request: GenerationRequest):
    """Generate text using LLM"""
    try:
        response = await app.state.llm_engine.generate(
            prompt=request.prompt,
            context=request.context,
            entities=request.entities,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            tools=request.tools,
            session_id=request.session_id
        )
        return response
    except Exception as e:
        logger.error("Text generation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Text generation failed")

@app.post("/chat")
async def chat_completion(
    messages: List[Dict[str, str]],
    model: str = "default",
    temperature: float = 0.7,
    max_tokens: int = 500,
    tools: Optional[List[Dict[str, Any]]] = None,
    session_id: Optional[str] = None
):
    """Chat completion with conversation history"""
    try:
        response = await app.state.llm_engine.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            session_id=session_id
        )
        return response
    except Exception as e:
        logger.error("Chat completion failed", error=str(e))
        raise HTTPException(status_code=500, detail="Chat completion failed")

@app.post("/function-call")
async def execute_function_call(
    function_name: str,
    arguments: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
):
    """Execute a function call"""
    try:
        result = await app.state.tool_manager.execute_tool(
            tool_name=function_name,
            arguments=arguments,
            context=context
        )
        return result
    except Exception as e:
        logger.error("Function call failed", function=function_name, error=str(e))
        raise HTTPException(status_code=500, detail="Function call failed")

@app.post("/analyze-intent")
async def analyze_intent(
    text: str,
    context: Optional[str] = None,
    entities: Optional[List[Dict[str, Any]]] = None
):
    """Analyze intent and generate appropriate response"""
    try:
        # Use specialized prompt for intent analysis
        prompt = await app.state.prompt_manager.get_intent_analysis_prompt(
            text=text,
            context=context,
            entities=entities or []
        )
        
        response = await app.state.llm_engine.generate(
            prompt=prompt,
            max_tokens=300,
            temperature=0.3
        )
        
        return {
            "intent_analysis": response.text,
            "suggested_actions": response.tool_calls,
            "confidence": response.confidence
        }
        
    except Exception as e:
        logger.error("Intent analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail="Intent analysis failed")

@app.post("/summarize")
async def summarize_text(
    text: str,
    max_length: int = 200,
    style: str = "concise"
):
    """Summarize text content"""
    try:
        prompt = await app.state.prompt_manager.get_summarization_prompt(
            text=text,
            max_length=max_length,
            style=style
        )
        
        response = await app.state.llm_engine.generate(
            prompt=prompt,
            max_tokens=max_length,
            temperature=0.3
        )
        
        return {
            "summary": response.text,
            "original_length": len(text),
            "summary_length": len(response.text),
            "compression_ratio": len(response.text) / len(text)
        }
        
    except Exception as e:
        logger.error("Text summarization failed", error=str(e))
        raise HTTPException(status_code=500, detail="Summarization failed")

@app.post("/translate")
async def translate_text(
    text: str,
    target_language: str,
    source_language: str = "auto",
    preserve_formatting: bool = True
):
    """Translate text to target language"""
    try:
        prompt = await app.state.prompt_manager.get_translation_prompt(
            text=text,
            source_language=source_language,
            target_language=target_language,
            preserve_formatting=preserve_formatting
        )
        
        response = await app.state.llm_engine.generate(
            prompt=prompt,
            max_tokens=len(text) * 2,  # Allow for language expansion
            temperature=0.2
        )
        
        return {
            "translated_text": response.text,
            "source_language": source_language,
            "target_language": target_language,
            "confidence": response.confidence
        }
        
    except Exception as e:
        logger.error("Translation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Translation failed")

@app.get("/models")
async def get_available_models():
    """Get list of available LLM models"""
    try:
        models = await app.state.llm_engine.get_available_models()
        return {"models": models}
    except Exception as e:
        logger.error("Failed to get models", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get models")

@app.get("/tools")
async def get_available_tools():
    """Get list of available tools"""
    try:
        tools = await app.state.tool_manager.get_available_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error("Failed to get tools", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get tools")

@app.post("/tools/register")
async def register_tool(
    tool_definition: Dict[str, Any],
    background_tasks: BackgroundTasks
):
    """Register a new tool"""
    try:
        background_tasks.add_task(
            app.state.tool_manager.register_tool,
            tool_definition
        )
        return {"message": "Tool registration started"}
    except Exception as e:
        logger.error("Tool registration failed", error=str(e))
        raise HTTPException(status_code=500, detail="Tool registration failed")

@app.delete("/cache")
async def clear_cache():
    """Clear LLM cache"""
    try:
        await app.state.llm_engine.clear_cache()
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error("Cache clearing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Cache clearing failed")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    engine_health = await app.state.llm_engine.health_check()
    
    return {
        "status": "healthy",
        "service": "llm",
        "models": engine_health,
        "available_tools": len(await app.state.tool_manager.get_available_tools()),
        "active_sessions": len(app.state.llm_engine.active_sessions),
        "cache_size": app.state.llm_engine.get_cache_size()
    }

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

llm_total_generations = Counter('llm_total_generations', 'Total LLM generations')
llm_average_generation_time = Gauge('llm_average_generation_time_ms', 'Average generation time in ms')
llm_total_tokens_generated = Counter('llm_total_tokens_generated', 'Total tokens generated')
llm_active_sessions = Gauge('llm_active_sessions', 'Number of active LLM sessions')
llm_cache_hit_rate = Gauge('llm_cache_hit_rate', 'Cache hit rate')
llm_tool_executions = Counter('llm_tool_executions', 'Total tool executions')
llm_tool_success_rate = Gauge('llm_tool_success_rate', 'Tool success rate')
llm_available_models = Gauge('llm_available_models', 'Number of available models')
llm_available_tools = Gauge('llm_available_tools', 'Number of available tools')

@app.get("/metrics")
async def get_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values
    llm_total_generations._value._value = app.state.llm_engine.total_generations
    llm_average_generation_time.set(app.state.llm_engine.get_average_generation_time())
    llm_total_tokens_generated._value._value = app.state.llm_engine.total_tokens_generated
    llm_active_sessions.set(len(app.state.llm_engine.active_sessions))
    llm_cache_hit_rate.set(app.state.llm_engine.get_cache_hit_rate())
    llm_tool_executions._value._value = app.state.tool_manager.total_executions
    llm_tool_success_rate.set(app.state.tool_manager.get_success_rate())
    llm_available_models.set(len(await app.state.llm_engine.get_available_models()))
    llm_available_tools.set(len(await app.state.tool_manager.get_available_tools()))
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
