"""
Intent Recognition Service - Complete Implementation
Handles intent classification, entity extraction, and speculative prediction
"""

import asyncio
import json
import numpy as np
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis

from .config import settings
from .intent_classifier import IntentClassifier
from .entity_extractor import EntityExtractor
from .speculative_engine import SpeculativeEngine
from .models import IntentRequest, IntentResult, EntityResult, SpeculativeResult

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🧠 Starting Intent Recognition Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize ML components
    app.state.intent_classifier = IntentClassifier()
    app.state.entity_extractor = EntityExtractor()
    app.state.speculative_engine = SpeculativeEngine()
    
    # Load models
    await app.state.intent_classifier.load_model()
    await app.state.entity_extractor.load_model()
    await app.state.speculative_engine.load_model()
    
    logger.info("✅ All ML models loaded")
    
    # Start Redis subscriber for ASR results
    app.state.asr_subscriber = asyncio.create_task(
        asr_result_subscriber(
            app.state.redis,
            app.state.intent_classifier,
            app.state.entity_extractor,
            app.state.speculative_engine
        )
    )
    
    yield
    
    logger.info("🛑 Shutting down Intent Recognition Service")
    app.state.asr_subscriber.cancel()
    await app.state.redis.close()

app = FastAPI(
    title="Intent Recognition Service",
    description="Real-time intent classification with speculative prediction",
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

async def asr_result_subscriber(
    redis_client: redis.Redis,
    intent_classifier: IntentClassifier,
    entity_extractor: EntityExtractor,
    speculative_engine: SpeculativeEngine
):
    """Subscribe to ASR results and process them for intent recognition"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("asr_results")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                await process_asr_result(
                    data, intent_classifier, entity_extractor, 
                    speculative_engine, redis_client
                )
            except Exception as e:
                logger.error("Error processing ASR result", error=str(e))

async def process_asr_result(
    data: Dict[str, Any],
    intent_classifier: IntentClassifier,
    entity_extractor: EntityExtractor,
    speculative_engine: SpeculativeEngine,
    redis_client: redis.Redis
):
    """Process ASR result for intent recognition"""
    try:
        text = data.get("text", "")
        connection_id = data.get("connection_id")
        session_id = data.get("session_id")
        is_final = data.get("is_final", False)
        
        if not text or not connection_id:
            return
        
        # Classify intent
        intent_result = await intent_classifier.classify(text, session_id)
        
        # Extract entities
        entity_result = await entity_extractor.extract(text)
        
        # Generate speculative predictions if not final
        speculative_results = []
        if not is_final:
            speculative_results = await speculative_engine.predict_next_intents(
                text, intent_result, session_id
            )
        
        # Send results back via Redis
        await redis_client.publish("intent_results", json.dumps({
            "type": "intent_result",
            "connection_id": connection_id,
            "session_id": session_id,
            "text": text,
            "is_final": is_final,
            "intent": {
                "name": intent_result.intent,
                "confidence": intent_result.confidence,
                "alternatives": intent_result.alternatives
            },
            "entities": [
                {
                    "text": entity.text,
                    "label": entity.label,
                    "confidence": entity.confidence,
                    "start": entity.start,
                    "end": entity.end
                }
                for entity in entity_result.entities
            ],
            "speculative_intents": [
                {
                    "intent": spec.intent,
                    "confidence": spec.confidence,
                    "completion_text": spec.completion_text,
                    "trigger_words": spec.trigger_words
                }
                for spec in speculative_results
            ]
        }))
        
    except Exception as e:
        logger.error("Error processing ASR result", error=str(e))

@app.post("/classify", response_model=IntentResult)
async def classify_intent(request: IntentRequest):
    """Classify intent from text"""
    try:
        result = await app.state.intent_classifier.classify(
            request.text, 
            request.session_id
        )
        return result
    except Exception as e:
        logger.error("Intent classification failed", error=str(e))
        raise HTTPException(status_code=500, detail="Intent classification failed")

@app.post("/extract-entities", response_model=EntityResult)
async def extract_entities(request: IntentRequest):
    """Extract entities from text"""
    try:
        result = await app.state.entity_extractor.extract(request.text)
        return result
    except Exception as e:
        logger.error("Entity extraction failed", error=str(e))
        raise HTTPException(status_code=500, detail="Entity extraction failed")

@app.post("/speculative-predict")
async def speculative_predict(request: IntentRequest):
    """Generate speculative intent predictions"""
    try:
        # First classify current intent
        intent_result = await app.state.intent_classifier.classify(
            request.text, 
            request.session_id
        )
        
        # Generate speculative predictions
        speculative_results = await app.state.speculative_engine.predict_next_intents(
            request.text, intent_result, request.session_id
        )
        
        return {
            "current_intent": intent_result,
            "speculative_intents": speculative_results
        }
        
    except Exception as e:
        logger.error("Speculative prediction failed", error=str(e))
        raise HTTPException(status_code=500, detail="Speculative prediction failed")

@app.post("/train")
async def train_models(background_tasks: BackgroundTasks):
    """Trigger model training with new data"""
    try:
        background_tasks.add_task(
            app.state.intent_classifier.retrain_model
        )
        return {"message": "Training started in background"}
    except Exception as e:
        logger.error("Training initiation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Training failed")

@app.get("/intents")
async def get_supported_intents():
    """Get list of supported intents"""
    return {
        "intents": app.state.intent_classifier.get_supported_intents(),
        "entities": app.state.entity_extractor.get_supported_entities()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "intent",
        "models_loaded": {
            "intent_classifier": app.state.intent_classifier.is_loaded(),
            "entity_extractor": app.state.entity_extractor.is_loaded(),
            "speculative_engine": app.state.speculative_engine.is_loaded()
        }
    }

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

intent_total_classifications = Counter('intent_total_classifications', 'Total intent classifications')
intent_average_confidence = Gauge('intent_average_confidence', 'Average intent confidence score')
intent_active_sessions = Gauge('intent_active_sessions', 'Number of active intent sessions')
intent_supported_intents = Gauge('intent_supported_intents', 'Number of supported intents')
intent_supported_entities = Gauge('intent_supported_entities', 'Number of supported entities')

@app.get("/metrics")
async def get_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values
    intent_total_classifications._value._value = app.state.intent_classifier.total_classifications
    intent_average_confidence.set(app.state.intent_classifier.get_average_confidence())
    intent_active_sessions.set(len(app.state.speculative_engine.session_contexts))
    intent_supported_intents.set(len(app.state.intent_classifier.get_supported_intents()))
    intent_supported_entities.set(len(app.state.entity_extractor.get_supported_entities()))
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
