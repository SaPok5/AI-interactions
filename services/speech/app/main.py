"""
Speech Processing Service - Complete Implementation
Handles audio streaming, ASR, VAD, language detection, and endpointing
"""

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import redis.asyncio as redis
import numpy as np
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
    """Subscribe to audio frames from Redis and process them with enhanced error handling"""
    while True:
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("speech_input", "speech_binary")
            logger.info("Speech service subscribed to Redis channels")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        channel = message["channel"].decode() if isinstance(message["channel"], bytes) else message["channel"]
                        logger.info("Received message on channel", channel=channel)
                        
                        if channel == "speech_input":
                            # Handle potential bytes data
                            message_data = message["data"]
                            if isinstance(message_data, bytes):
                                message_data = message_data.decode()
                            
                            data = json.loads(message_data)
                            await process_audio_message(data, asr_engine, vad_processor, redis_client)
                        elif channel == "speech_binary":
                            # Handle potential bytes data
                            message_data = message["data"]
                            if isinstance(message_data, bytes):
                                message_data = message_data.decode()
                            
                            data = json.loads(message_data)
                            await process_binary_audio(data, asr_engine, vad_processor, redis_client)
                    except json.JSONDecodeError as je:
                        logger.error("Invalid JSON in Redis message", error=str(je), raw_data=message["data"])
                    except Exception as e:
                        logger.error("Error processing audio message", error=str(e), channel=message["channel"])
                        # Continue processing other messages
                        continue
        except Exception as e:
            logger.error("Redis connection error, attempting to reconnect", error=str(e))
            # Wait before attempting to reconnect
            await asyncio.sleep(5)
            continue

async def process_audio_message(data: Dict[str, Any], asr_engine: ASREngine, vad_processor: VADProcessor, redis_client: redis.Redis):
    """Process audio frame message with enhanced error handling"""
    try:
        message_type = data.get("type")
        connection_id = data.get("connection_id")
        text_content = data.get("text", "")
        
        logger.info("Processing audio message", message_type=message_type, connection_id=connection_id)
        
        if message_type == "transcribe_audio":
            # Handle voice input transcription
            audio_data = data.get("audio_data")
            format_type = data.get("format", "webm")
            
            # Validate audio_data type to prevent "argument should be a bytes-like object or ASCII string, not 'list'" error
            if isinstance(audio_data, list):
                logger.warning("audio_data is a list instead of string, using first element", connection_id=connection_id)
                if len(audio_data) > 0:
                    audio_data = audio_data[0]
                else:
                    logger.warning("Empty audio_data list in transcribe_audio message", connection_id=connection_id)
                    return
            
            if not audio_data:
                logger.warning("Missing audio_data in transcribe_audio message", connection_id=connection_id)
                return
            
            if not connection_id:
                logger.warning("Missing connection_id in transcribe_audio message")
                return
            
            # Decode audio data (base64)
            import base64
            try:
                # Additional validation to ensure audio_data is a string
                if not isinstance(audio_data, str):
                    logger.error("audio_data is not a string after validation", type=type(audio_data), connection_id=connection_id)
                    return
                
                # Handle data URL format (data:audio/webm;base64,...)
                if audio_data.startswith('data:'):
                    audio_data = audio_data.split(',')[1]
                
                # Add padding if needed
                missing_padding = len(audio_data) % 4
                if missing_padding:
                    audio_data += '=' * (4 - missing_padding)
                
                audio_bytes = base64.b64decode(audio_data)
                logger.info("Successfully decoded audio data", size=len(audio_bytes))
                
                # Fast audio processing for reduced latency
                if format_type == "webm":
                    # Use faster audio processing for WebM
                    try:
                        import tempfile
                        import subprocess
                        import os
                        
                        # Create temporary file for audio processing
                        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_webm:
                            temp_webm.write(audio_bytes)
                            webm_path = temp_webm.name
                        
                        # Convert WebM to WAV using ffmpeg
                        wav_path = webm_path.replace(".webm", ".wav")
                        result = subprocess.run([
                            "ffmpeg", "-i", webm_path, 
                            "-acodec", "pcm_s16le", 
                            "-ar", "16000", "-ac", "1", 
                            "-y", wav_path
                        ], capture_output=True, text=True)
                        
                        if result.returncode != 0:
                            logger.error("FFmpeg conversion failed", error=result.stderr)
                            wav_bytes = audio_bytes
                        else:
                            # Read WAV file
                            with open(wav_path, "rb") as f:
                                wav_bytes = f.read()
                            
                            logger.info("Audio converted successfully", original_size=len(audio_bytes), converted_size=len(wav_bytes))
                        
                        # Clean up temporary files
                        os.unlink(webm_path)
                        if os.path.exists(wav_path):
                            os.unlink(wav_path)
                        
                    except Exception as convert_error:
                        logger.error("Audio conversion failed", error=str(convert_error))
                        wav_bytes = audio_bytes
                else:
                    wav_bytes = audio_bytes
                
                # Process voice with VAD and ASR
                is_speech = await vad_processor.is_speech(wav_bytes)
                if is_speech:
                    result = await asr_engine.transcribe(wav_bytes)
                    
                    if result and result.text.strip():
                        # Send transcription result back to client via WebSocket
                        await redis_client.publish("speech_output", json.dumps({
                            "type": "transcription",
                            "connection_id": connection_id,
                            "data": {
                                "text": result.text.strip(),
                                "language": result.language
                            }
                        }))
                        
                        # Also forward to orchestrator for AI response
                        await redis_client.publish("orchestrator_input", json.dumps({
                            "type": "voice_input",
                            "text": result.text.strip(),
                            "connection_id": connection_id,
                            "language": result.language,
                            "confidence": result.confidence
                        }))
                        logger.info("Voice transcription completed and sent", text=result.text.strip()[:50])
                    else:
                        logger.warning("Transcription resulted in empty text", connection_id=connection_id)
                        # Send empty result back to client
                        await redis_client.publish("speech_output", json.dumps({
                            "type": "transcription",
                            "connection_id": connection_id,
                            "data": {
                                "text": "I didn't catch that. Could you please try speaking again?",
                                "language": "en"
                            }
                        }))
                        
                        # Also forward to orchestrator
                        await redis_client.publish("orchestrator_input", json.dumps({
                            "type": "voice_input",
                            "text": "",
                            "connection_id": connection_id
                        }))
                else:
                    logger.warning("No transcription result or empty text", has_result=bool(result), text_length=len(result.text) if result else 0)
                
            except Exception as decode_error:
                logger.error("Audio decoding error", error=str(decode_error))
                return
        
        else:
            # Handle legacy audio frame format
            audio_data = data.get("payload")
            session_id = data.get("session_id")
            
            if not audio_data:
                return
            
            # Validate audio_data type for legacy format
            if isinstance(audio_data, list):
                logger.warning("payload is a list instead of string in legacy format, using first element", connection_id=connection_id)
                if len(audio_data) > 0:
                    audio_data = audio_data[0]
                else:
                    logger.warning("Empty payload list in legacy audio message", connection_id=connection_id)
                    return
            
            # Additional validation to ensure audio_data is a string
            if not isinstance(audio_data, str):
                logger.error("payload is not a string in legacy format", type=type(audio_data), connection_id=connection_id)
                return
            
            # Decode audio data (base64)
            import base64
            try:
                audio_bytes = base64.b64decode(audio_data.split(',')[1] if ',' in audio_data else audio_data)
            except Exception as decode_error:
                logger.error("Legacy audio decoding error", error=str(decode_error), connection_id=connection_id)
                return
            
            # Convert to numpy array
            try:
                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            except Exception as buffer_error:
                logger.error("Failed to convert audio bytes to numpy array", error=str(buffer_error), connection_id=connection_id)
                return
            
            # Process with VAD
            is_speech = vad_processor.is_speech(audio_array)
            
            if is_speech:
                # Process with ASR
                result = await asr_engine.process_chunk(audio_array, session_id)
                
                if result:
                    # Send ASR result back via Redis
                    await redis_client.publish("speech_output", json.dumps({
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
    """Process binary audio data with enhanced error handling"""
    try:
        connection_id = data.get("connection_id")
        data_key = data.get("data_key")
        user_id = data.get("user_id")
        
        if not connection_id:
            logger.warning("Missing connection_id in binary audio message")
            return
        
        # Retrieve binary data from Redis
        audio_bytes = await redis_client.get(data_key)
        if not audio_bytes:
            logger.warning("No binary audio data found for key", data_key=data_key, connection_id=connection_id)
            return
        
        # Validate audio_bytes type
        if not isinstance(audio_bytes, bytes):
            logger.error("audio_bytes is not bytes type", type=type(audio_bytes), connection_id=connection_id)
            return
        
        # Convert to numpy array with error handling
        try:
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        except Exception as buffer_error:
            logger.error("Failed to convert binary audio bytes to numpy array", error=str(buffer_error), connection_id=connection_id)
            return
        
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
