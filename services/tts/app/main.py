"""
TTS Service - Complete Implementation
Handles text-to-speech synthesis with streaming audio support
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis

from .config import settings
from .tts_engine import TTSEngine
from .voice_manager import VoiceManager
from .audio_processor import AudioProcessor
from .models import TTSRequest, TTSResult, VoiceInfo

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🔊 Starting TTS Service")
    
    # Initialize Redis connection
    app.state.redis = redis.from_url(settings.redis_url)
    
    # Initialize core components
    app.state.tts_engine = TTSEngine()
    app.state.voice_manager = VoiceManager()
    app.state.audio_processor = AudioProcessor()
    
    # Initialize TTS engines
    await app.state.tts_engine.initialize()
    await app.state.voice_manager.load_voices()
    
    # Start Redis subscriber for orchestrator responses
    app.state.orchestrator_subscriber = asyncio.create_task(
        orchestrator_response_subscriber(
            app.state.redis,
            app.state.tts_engine,
            app.state.audio_processor
        )
    )
    
    # Start Redis subscriber for direct TTS requests
    app.state.tts_subscriber = asyncio.create_task(
        tts_input_subscriber(
            app.state.redis,
            app.state.tts_engine,
            app.state.audio_processor
        )
    )
    
    logger.info("✅ TTS Service initialized")
    
    yield
    
    logger.info("🛑 Shutting down TTS Service")
    app.state.orchestrator_subscriber.cancel()
    app.state.tts_subscriber.cancel()
    await app.state.redis.close()

app = FastAPI(
    title="TTS Service",
    description="Text-to-Speech synthesis with streaming audio",
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

async def orchestrator_response_subscriber(
    redis_client: redis.Redis,
    tts_engine: TTSEngine,
    audio_processor: AudioProcessor
):
    """Subscribe to orchestrator responses and generate speech"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("orchestrator_responses")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                await process_orchestrator_response(
                    data, tts_engine, audio_processor, redis_client
                )
            except Exception as e:
                logger.error("Error processing orchestrator response", error=str(e))

async def tts_input_subscriber(
    redis_client: redis.Redis,
    tts_engine: TTSEngine,
    audio_processor: AudioProcessor
):
    """Subscribe to direct TTS requests from gateway"""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("tts_input")
    logger.info("🎤 Subscribed to tts_input channel")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                logger.info("📥 Received TTS request", data=data)
                await process_tts_request(
                    data, tts_engine, audio_processor, redis_client
                )
            except Exception as e:
                logger.error("Error processing TTS request", error=str(e))

async def process_orchestrator_response(
    data: Dict[str, Any],
    tts_engine: TTSEngine,
    audio_processor: AudioProcessor,
    redis_client: redis.Redis
):
    """Process orchestrator response and generate speech"""
    try:
        connection_id = data.get("connection_id")
        session_id = data.get("session_id")
        workflow_result = data.get("workflow_result", {})
        is_final = data.get("is_final", False)
        
        if not connection_id:
            return
        
        # Extract text to synthesize
        response_text = workflow_result.get("response_text", "")
        
        if not response_text:
            return
        
        # Generate speech
        tts_result = await tts_engine.synthesize(
            text=response_text,
            voice="default",
            language="en",
            session_id=session_id
        )
        
        if tts_result and tts_result.audio_data:
            # Send audio response
            await redis_client.publish("tts_responses", json.dumps({
                "type": "tts_response",
                "connection_id": connection_id,
                "session_id": session_id,
                "audio_url": tts_result.audio_url,
                "audio_data": tts_result.audio_data,
                "duration_ms": tts_result.duration_ms,
                "is_final": is_final
            }))
        
    except Exception as e:
        logger.error("Error processing orchestrator response", error=str(e))

async def process_tts_request(
    data: Dict[str, Any],
    tts_engine: TTSEngine,
    audio_processor: AudioProcessor,
    redis_client: redis.Redis
):
    """Process direct TTS request from gateway"""
    try:
        connection_id = data.get("connection_id")
        text = data.get("text", "")
        voice_settings = data.get("voice_settings", {})
        auto_play = data.get("auto_play", False)
        
        if not connection_id or not text:
            logger.warning("Missing connection_id or text in TTS request")
            return
        
        # Extract voice settings
        voice = voice_settings.get("voice", "alloy")
        speed = voice_settings.get("speed", 1.0)
        
        logger.info("🎵 Synthesizing TTS", text=text[:50], voice=voice, connection_id=connection_id)
        
        # Generate speech
        tts_result = await tts_engine.synthesize(
            text=text,
            voice=voice,
            language="en",
            speed=speed,
            session_id=connection_id
        )
        
        if tts_result and tts_result.audio_data:
            logger.info("✅ TTS synthesis complete", duration_ms=tts_result.duration_ms)
            
            # Send audio response back to gateway
            logger.info("📤 Publishing TTS response to gateway", connection_id=connection_id, channel="tts_output")
            await redis_client.publish("tts_output", json.dumps({
                "type": "audio_ready",
                "connection_id": connection_id,
                "audio_url": tts_result.audio_url,
                "audio_data": tts_result.audio_data,
                "duration_ms": tts_result.duration_ms,
                "auto_play": auto_play
            }))
        else:
            logger.error("TTS synthesis failed")
            
    except Exception as e:
        logger.error("Error processing TTS request", error=str(e))

@app.post("/synthesize", response_model=TTSResult)
async def synthesize_text(request: TTSRequest):
    """Synthesize text to speech"""
    try:
        result = await app.state.tts_engine.synthesize(
            text=request.text,
            voice=request.voice,
            language=request.language,
            speed=request.speed,
            pitch=request.pitch,
            session_id=request.session_id
        )
        return result
    except Exception as e:
        logger.error("TTS synthesis failed", error=str(e))
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

@app.post("/synthesize-stream")
async def synthesize_streaming(request: TTSRequest):
    """Synthesize text to speech with streaming response"""
    try:
        audio_generator = app.state.tts_engine.synthesize_streaming(
            text=request.text,
            voice=request.voice,
            language=request.language,
            speed=request.speed,
            pitch=request.pitch
        )
        
        return StreamingResponse(
            audio_generator,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )
    except Exception as e:
        logger.error("Streaming TTS synthesis failed", error=str(e))
        raise HTTPException(status_code=500, detail="Streaming synthesis failed")

@app.get("/audio/{audio_id}")
async def get_audio_file(audio_id: str):
    """Get synthesized audio file"""
    try:
        audio_path = os.path.join(settings.audio_storage_path, f"{audio_id}.wav")
        
        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        return FileResponse(
            audio_path,
            media_type="audio/wav",
            filename=f"{audio_id}.wav"
        )
    except Exception as e:
        logger.error("Failed to get audio file", audio_id=audio_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get audio file")

@app.websocket("/stream")
async def websocket_tts_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time TTS"""
    await websocket.accept()
    session_id = f"tts_ws_{id(websocket)}"
    
    try:
        while True:
            # Receive text data
            data = await websocket.receive_json()
            
            text = data.get("text", "")
            voice = data.get("voice", "default")
            language = data.get("language", "en")
            
            if not text:
                continue
            
            # Generate speech
            result = await app.state.tts_engine.synthesize(
                text=text,
                voice=voice,
                language=language,
                session_id=session_id
            )
            
            if result:
                await websocket.send_json({
                    "type": "tts_result",
                    "audio_url": result.audio_url,
                    "audio_data": result.audio_data,
                    "duration_ms": result.duration_ms,
                    "text": text
                })
            
    except WebSocketDisconnect:
        logger.info("TTS WebSocket disconnected", session_id=session_id)
    except Exception as e:
        logger.error("TTS WebSocket error", session_id=session_id, error=str(e))

@app.get("/voices", response_model=List[VoiceInfo])
async def get_available_voices():
    """Get list of available voices"""
    try:
        voices = await app.state.voice_manager.get_available_voices()
        return voices
    except Exception as e:
        logger.error("Failed to get voices", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get voices")

@app.get("/voices/{language}")
async def get_voices_by_language(language: str):
    """Get voices for specific language"""
    try:
        voices = await app.state.voice_manager.get_voices_by_language(language)
        return {"language": language, "voices": voices}
    except Exception as e:
        logger.error("Failed to get voices by language", language=language, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get voices")

@app.post("/voice/clone")
async def clone_voice(
    voice_name: str,
    audio_samples: List[str]  # URLs or base64 encoded audio
):
    """Clone a voice from audio samples"""
    try:
        # This would implement voice cloning functionality
        # For now, return a placeholder
        return {
            "message": "Voice cloning initiated",
            "voice_name": voice_name,
            "status": "processing"
        }
    except Exception as e:
        logger.error("Voice cloning failed", error=str(e))
        raise HTTPException(status_code=500, detail="Voice cloning failed")

@app.delete("/audio/{audio_id}")
async def delete_audio_file(audio_id: str):
    """Delete synthesized audio file"""
    try:
        audio_path = os.path.join(settings.audio_storage_path, f"{audio_id}.wav")
        
        if os.path.exists(audio_path):
            os.remove(audio_path)
            return {"message": "Audio file deleted"}
        else:
            raise HTTPException(status_code=404, detail="Audio file not found")
    except Exception as e:
        logger.error("Failed to delete audio file", audio_id=audio_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete audio file")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    engine_health = await app.state.tts_engine.health_check()
    
    return {
        "status": "healthy",
        "service": "tts",
        "engines": engine_health,
        "available_voices": len(await app.state.voice_manager.get_available_voices()),
        "supported_languages": app.state.voice_manager.get_supported_languages()
    }

# Initialize Prometheus metrics globally
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

tts_total_syntheses = Counter('tts_total_syntheses', 'Total TTS syntheses')
tts_average_synthesis_time = Gauge('tts_average_synthesis_time_ms', 'Average synthesis time in ms')
tts_active_sessions = Gauge('tts_active_sessions', 'Number of active TTS sessions')
tts_audio_files_generated = Counter('tts_audio_files_generated', 'Total audio files generated')
tts_total_audio_duration = Gauge('tts_total_audio_duration_seconds', 'Total audio duration in seconds')
tts_cache_hit_rate = Gauge('tts_cache_hit_rate', 'Cache hit rate')
tts_supported_languages = Gauge('tts_supported_languages', 'Number of supported languages')
tts_available_voices = Gauge('tts_available_voices', 'Number of available voices')

@app.get("/metrics")
async def get_metrics():
    """Get service metrics in Prometheus format"""
    from fastapi import Response
    
    # Set current values
    tts_total_syntheses._value._value = app.state.tts_engine.total_syntheses
    tts_average_synthesis_time.set(app.state.tts_engine.get_average_synthesis_time())
    tts_active_sessions.set(len(app.state.tts_engine.active_sessions))
    tts_audio_files_generated._value._value = app.state.tts_engine.files_generated
    tts_total_audio_duration.set(app.state.tts_engine.total_audio_duration)
    tts_cache_hit_rate.set(app.state.tts_engine.get_cache_hit_rate())
    tts_supported_languages.set(len(app.state.voice_manager.get_supported_languages()))
    tts_available_voices.set(len(await app.state.voice_manager.get_available_voices()))
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
