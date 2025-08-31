"""
Speech Processing Service - Complete Implementation
Handles audio streaming, ASR, VAD, language detection, and endpointing
"""

import asyncio
import json
import numpy as np
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis

from .config import settings
from .asr_engine import ASREngine
from .vad_processor import VADProcessor
from .language_detector import LanguageDetector
from .audio_processor import AudioProcessor
from .models import AudioFrame, ASRResult, LanguageResult

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🎤 Starting Speech Processing Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize speech components
    app.state.asr_engine = ASREngine()
    app.state.vad_processor = VADProcessor()
    app.state.language_detector = LanguageDetector()
    app.state.audio_processor = AudioProcessor()
    
    # Load models
    await app.state.asr_engine.load_model()
    logger.info("✅ ASR model loaded")
    
    # Start Redis subscriber for audio frames
    app.state.audio_subscriber = asyncio.create_task(
        audio_frame_subscriber(app.state.redis, app.state.asr_engine, app.state.vad_processor)
    )
    
    yield
    
    logger.info("🛑 Shutting down Speech Processing Service")
    app.state.audio_subscriber.cancel()
    await app.state.redis.close()

app = FastAPI(
    title="Speech Processing Service",
    description="Real-time speech recognition with VAD and language detection",
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

async def audio_frame_subscriber(redis_client: redis.Redis, asr_engine: ASREngine, vad_processor: VADProcessor):
    """Subscribe to audio frames from Redis and process them"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("speech_input", "speech_binary")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                if message["channel"] == b"speech_input":
                    data = json.loads(message["data"])
                    await process_audio_message(data, asr_engine, vad_processor, redis_client)
                elif message["channel"] == b"speech_binary":
                    data = json.loads(message["data"])
                    await process_binary_audio(data, asr_engine, vad_processor, redis_client)
            except Exception as e:
                logger.error("Error processing audio message", error=str(e))

async def process_audio_message(data: Dict[str, Any], asr_engine: ASREngine, vad_processor: VADProcessor, redis_client: redis.Redis):
    """Process audio frame message"""
    try:
        audio_data = data.get("payload")
        connection_id = data.get("connection_id")
        session_id = data.get("session_id")
        
        if not audio_data:
            return
        
        # Decode audio data (base64)
        import base64
        audio_bytes = base64.b64decode(audio_data.split(',')[1] if ',' in audio_data else audio_data)
        
        # Convert to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Process with VAD
        is_speech = vad_processor.is_speech(audio_array)
        
        if is_speech:
            # Process with ASR
            result = await asr_engine.process_chunk(audio_array, session_id)
            
            if result:
                # Send ASR result back via Redis
                await redis_client.publish("asr_results", json.dumps({
                    "type": "asr_partial",
                    "connection_id": connection_id,
                    "session_id": session_id,
                    "text": result.text,
                    "confidence": result.confidence,
                    "is_final": result.is_final,
                    "language": result.language,
                    "timestamps": result.timestamps
                }))
        
    except Exception as e:
        logger.error("Error processing audio message", error=str(e))

async def process_binary_audio(data: Dict[str, Any], asr_engine: ASREngine, vad_processor: VADProcessor, redis_client: redis.Redis):
    """Process binary audio data"""
    try:
        connection_id = data.get("connection_id")
        data_key = data.get("data_key")
        user_id = data.get("user_id")
        
        # Retrieve binary data from Redis
        audio_bytes = await redis_client.get(data_key)
        if not audio_bytes:
            return
        
        # Convert to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Process with VAD
        is_speech = vad_processor.is_speech(audio_array)
        
        if is_speech:
            # Process with ASR
            result = await asr_engine.process_chunk(audio_array, connection_id)
            
            if result:
                # Send result back
                await redis_client.publish("asr_results", json.dumps({
                    "type": "asr_partial",
                    "connection_id": connection_id,
                    "user_id": user_id,
                    "text": result.text,
                    "confidence": result.confidence,
                    "is_final": result.is_final,
                    "language": result.language
                }))
        
        # Clean up binary data
        await redis_client.delete(data_key)
        
    except Exception as e:
        logger.error("Error processing binary audio", error=str(e))

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio file"""
    try:
        # Read audio file
        audio_bytes = await file.read()
        
        # Process audio
        audio_array = app.state.audio_processor.load_audio_from_bytes(audio_bytes)
        
        # Detect language
        language_result = app.state.language_detector.detect(audio_array)
        
        # Transcribe
        result = await app.state.asr_engine.transcribe_complete(audio_array, language_result.language)
        
        return {
            "text": result.text,
            "confidence": result.confidence,
            "language": result.language,
            "duration": len(audio_array) / 16000,  # Assuming 16kHz
            "words": result.timestamps
        }
        
    except Exception as e:
        logger.error("Transcription error", error=str(e))
        raise HTTPException(status_code=500, detail="Transcription failed")

@app.post("/detect-language")
async def detect_language(file: UploadFile = File(...)):
    """Detect language of uploaded audio"""
    try:
        audio_bytes = await file.read()
        audio_array = app.state.audio_processor.load_audio_from_bytes(audio_bytes)
        
        result = app.state.language_detector.detect(audio_array)
        
        return {
            "language": result.language,
            "confidence": result.confidence,
            "alternatives": result.alternatives
        }
        
    except Exception as e:
        logger.error("Language detection error", error=str(e))
        raise HTTPException(status_code=500, detail="Language detection failed")

@app.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time audio streaming"""
    await websocket.accept()
    session_id = f"ws_{id(websocket)}"
    
    try:
        while True:
            # Receive audio data
            data = await websocket.receive_bytes()
            
            # Convert to numpy array
            audio_array = np.frombuffer(data, dtype=np.float32)
            
            # Process with VAD
            is_speech = app.state.vad_processor.is_speech(audio_array)
            
            if is_speech:
                # Process with ASR
                result = await app.state.asr_engine.process_chunk(audio_array, session_id)
                
                if result:
                    await websocket.send_json({
                        "type": "asr_result",
                        "text": result.text,
                        "confidence": result.confidence,
                        "is_final": result.is_final,
                        "language": result.language
                    })
            
            # Send VAD result
            await websocket.send_json({
                "type": "vad_result",
                "is_speech": is_speech,
                "energy": float(np.mean(np.abs(audio_array)))
            })
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", session_id=session_id)
        # Cleanup session
        await app.state.asr_engine.cleanup_session(session_id)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "speech",
        "models_loaded": {
            "asr": app.state.asr_engine.is_loaded(),
            "vad": True,
            "language_detector": True
        }
    }

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

speech_active_sessions = Gauge('speech_active_sessions', 'Number of active speech sessions')
speech_total_processed = Counter('speech_total_processed', 'Total speech requests processed')
speech_average_confidence = Gauge('speech_average_confidence', 'Average confidence score')

@app.get("/metrics")
async def get_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values
    speech_active_sessions.set(len(app.state.asr_engine.active_sessions))
    speech_total_processed._value._value = app.state.asr_engine.total_processed
    speech_average_confidence.set(app.state.asr_engine.get_average_confidence())
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
