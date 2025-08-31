"""TTS engine implementation with multiple backends"""

import asyncio
import uuid
import os
import base64
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import structlog
import soundfile as sf
import numpy as np
from TTS.api import TTS
import edge_tts
from gtts import gTTS
import io

from .config import settings
from .models import TTSResult, AudioChunk

logger = structlog.get_logger(__name__)

class TTSEngine:
    """Multi-backend TTS engine"""
    
    def __init__(self):
        self.engines = {}
        self.active_sessions = {}
        self.total_syntheses = 0
        self.synthesis_times = []
        self.files_generated = 0
        self.total_audio_duration = 0.0
        self.cache = {}
        self.cache_hits = 0
        
    async def initialize(self):
        """Initialize TTS engines"""
        try:
            # Initialize Coqui TTS
            if settings.enable_neural_voices:
                loop = asyncio.get_event_loop()
                self.engines["coqui"] = await loop.run_in_executor(
                    None,
                    lambda: TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")
                )
                logger.info("Coqui TTS engine initialized")
            
            # Initialize pyttsx3 (offline engine) if explicitly enabled
            if settings.enable_pyttsx3_voices:
                try:
                    import pyttsx3  # Import lazily to avoid failing service startup
                    engine = pyttsx3.init()
                    if engine:
                        engine.setProperty('rate', 200)
                        engine.setProperty('volume', 0.9)
                        self.engines["pyttsx3"] = engine
                        logger.info("pyttsx3 engine initialized")
                except Exception as e:
                    logger.warning("pyttsx3 not available; continuing without it", error=str(e))
            else:
                logger.debug("Skipping pyttsx3 initialization (disabled by config)")
            
            # Edge TTS and gTTS are initialized per request
            logger.info("TTS engines initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize TTS engines", error=str(e))
            raise
    
    async def synthesize(
        self,
        text: str,
        voice: str = "default",
        language: str = "en",
        speed: float = 1.0,
        pitch: float = 1.0,
        session_id: Optional[str] = None
    ) -> TTSResult:
        """Synthesize text to speech"""
        start_time = datetime.utcnow()
        
        try:
            # Validate input
            if len(text) > settings.max_text_length:
                raise ValueError(f"Text too long: {len(text)} characters")
            
            # Check cache
            cache_key = self._generate_cache_key(text, voice, language, speed, pitch)
            if cache_key in self.cache:
                cached_result = self.cache[cache_key]
                if datetime.utcnow() - cached_result["timestamp"] < timedelta(hours=settings.audio_cache_ttl_hours):
                    self.cache_hits += 1
                    return cached_result["result"]
            
            # Choose engine based on voice and settings
            engine_name = self._select_engine(voice, language)
            
            # Synthesize audio
            audio_data, sample_rate = await self._synthesize_with_engine(
                text, voice, language, speed, pitch, engine_name
            )
            
            # Save audio file
            audio_id = str(uuid.uuid4())
            audio_path = os.path.join(settings.audio_storage_path, f"{audio_id}.wav")
            
            # Ensure directory exists
            os.makedirs(settings.audio_storage_path, exist_ok=True)
            
            # Save audio with high quality settings
            sf.write(audio_path, audio_data, sample_rate, subtype='PCM_16')
            
            # Calculate duration
            duration_ms = len(audio_data) / sample_rate * 1000
            
            # Encode audio as base64 for direct transmission with high quality
            audio_bytes = io.BytesIO()
            sf.write(audio_bytes, audio_data, sample_rate, format='WAV', subtype='PCM_16')
            audio_base64 = base64.b64encode(audio_bytes.getvalue()).decode()
            
            # Create result
            synthesis_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            result = TTSResult(
                audio_url=f"/audio/{audio_id}",
                audio_data=audio_base64,
                duration_ms=duration_ms,
                text=text,
                voice=voice,
                language=language,
                synthesis_time_ms=synthesis_time
            )
            
            # Cache result
            self.cache[cache_key] = {
                "result": result,
                "timestamp": datetime.utcnow()
            }
            
            # Update metrics
            self.total_syntheses += 1
            self.synthesis_times.append(synthesis_time)
            self.files_generated += 1
            self.total_audio_duration += duration_ms / 1000
            
            if len(self.synthesis_times) > 1000:
                self.synthesis_times = self.synthesis_times[-1000:]
            
            logger.info("TTS synthesis completed",
                       text_length=len(text),
                       voice=voice,
                       language=language,
                       engine=engine_name,
                       duration_ms=duration_ms,
                       synthesis_time_ms=synthesis_time)
            
            return result
            
        except Exception as e:
            logger.error("TTS synthesis failed", text=text[:100], error=str(e))
            raise
    
    async def synthesize_streaming(
        self,
        text: str,
        voice: str = "default",
        language: str = "en",
        speed: float = 1.0,
        pitch: float = 1.0
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize text to speech with streaming output"""
        try:
            # For streaming, we'll use edge-tts which supports streaming
            if language.startswith("en"):
                voice_name = "en-US-AriaNeural"
            else:
                voice_name = f"{language}-Standard-A"
            
            communicate = edge_tts.Communicate(text, voice_name)
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
                    
        except Exception as e:
            logger.error("Streaming TTS synthesis failed", error=str(e))
            raise
    
    async def _synthesize_with_engine(
        self,
        text: str,
        voice: str,
        language: str,
        speed: float,
        pitch: float,
        engine_name: str
    ) -> tuple[np.ndarray, int]:
        """Synthesize with specific engine"""
        
        if engine_name == "coqui" and "coqui" in self.engines:
            return await self._synthesize_coqui(text, voice)
        elif engine_name == "edge":
            return await self._synthesize_edge(text, voice, language)
        elif engine_name == "gtts":
            return await self._synthesize_gtts(text, language)
        elif engine_name == "pyttsx3" and "pyttsx3" in self.engines:
            return await self._synthesize_pyttsx3(text, speed)
        else:
            # Fallback to gTTS
            return await self._synthesize_gtts(text, language)
    
    async def _synthesize_coqui(self, text: str, voice: str) -> tuple[np.ndarray, int]:
        """Synthesize with Coqui TTS"""
        loop = asyncio.get_event_loop()
        
        def synthesize():
            wav = self.engines["coqui"].tts(text)
            return np.array(wav), self.engines["coqui"].synthesizer.output_sample_rate
        
        return await loop.run_in_executor(None, synthesize)
    
    async def _synthesize_edge(self, text: str, voice: str, language: str) -> tuple[np.ndarray, int]:
        """Synthesize with Edge TTS"""
        # Map language to Edge TTS voice
        voice_map = {
            "en": "en-US-AriaNeural",
            "es": "es-ES-ElviraNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "it": "it-IT-ElsaNeural",
            "pt": "pt-BR-FranciscaNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "ja": "ja-JP-NanamiNeural",
            "ko": "ko-KR-SunHiNeural",
            "zh": "zh-CN-XiaoxiaoNeural"
        }
        
        voice_name = voice_map.get(language, "en-US-AriaNeural")
        
        communicate = edge_tts.Communicate(text, voice_name)
        
        # Collect all audio data
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        # Convert to numpy array
        audio_array, sample_rate = sf.read(io.BytesIO(audio_data))
        return audio_array, sample_rate
    
    async def _synthesize_gtts(self, text: str, language: str) -> tuple[np.ndarray, int]:
        """Synthesize with Google TTS"""
        loop = asyncio.get_event_loop()
        
        def synthesize():
            tts = gTTS(text=text, lang=language, slow=False)
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            # Convert MP3 to WAV
            audio_array, sample_rate = sf.read(audio_buffer)
            return audio_array, sample_rate
        
        return await loop.run_in_executor(None, synthesize)
    
    async def _synthesize_pyttsx3(self, text: str, speed: float) -> tuple[np.ndarray, int]:
        """Synthesize with pyttsx3"""
        loop = asyncio.get_event_loop()
        
        def synthesize():
            engine = self.engines["pyttsx3"]
            
            # Set properties
            engine.setProperty('rate', int(200 * speed))
            
            # Save to temporary file
            temp_file = f"/tmp/tts_{uuid.uuid4()}.wav"
            engine.save_to_file(text, temp_file)
            engine.runAndWait()
            
            # Read audio file
            audio_array, sample_rate = sf.read(temp_file)
            
            # Clean up
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            return audio_array, sample_rate
        
        return await loop.run_in_executor(None, synthesize)
    
    def _select_engine(self, voice: str, language: str) -> str:
        """Select appropriate TTS engine"""
        # Priority: Coqui (neural) > Edge TTS > gTTS > pyttsx3
        
        if settings.enable_neural_voices and "coqui" in self.engines and language == "en":
            return "coqui"
        elif language in ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh"]:
            return "edge"
        else:
            return "gtts"
    
    def _generate_cache_key(
        self, 
        text: str, 
        voice: str, 
        language: str, 
        speed: float, 
        pitch: float
    ) -> str:
        """Generate cache key for TTS request"""
        import hashlib
        
        key_string = f"{text}|{voice}|{language}|{speed}|{pitch}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of TTS engines"""
        # IMPORTANT: Keep health checks lightweight. Do not run real TTS synthesis here
        # as it can be very slow (seconds to minutes) and cause timeouts for Docker
        # healthchecks and upstream callers.
        health: Dict[str, Any] = {}

        # Report readiness of initialized engines without inference
        for engine_name, engine in self.engines.items():
            if engine_name == "coqui":
                # Consider Coqui ready if the engine object is initialized
                health[engine_name] = "ready" if engine is not None else "uninitialized"
            elif engine_name == "pyttsx3":
                health[engine_name] = "ready" if engine is not None else "uninitialized"
            else:
                health[engine_name] = "ready"

        # Libraries are imported at module import time; if import succeeded,
        # mark them as available without performing network calls.
        health["edge"] = "available"
        health["gtts"] = "available"

        return health
    
    def get_average_synthesis_time(self) -> float:
        """Get average synthesis time in milliseconds"""
        if not self.synthesis_times:
            return 0.0
        return sum(self.synthesis_times) / len(self.synthesis_times)
    
    def get_cache_hit_rate(self) -> float:
        """Get cache hit rate"""
        if self.total_syntheses == 0:
            return 0.0
        return self.cache_hits / self.total_syntheses
    
    def clear_cache(self):
        """Clear TTS cache"""
        self.cache.clear()
        self.cache_hits = 0
        logger.info("TTS cache cleared")
    
    async def cleanup_old_files(self):
        """Clean up old audio files"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=settings.audio_cache_ttl_hours)
            
            if os.path.exists(settings.audio_storage_path):
                for filename in os.listdir(settings.audio_storage_path):
                    file_path = os.path.join(settings.audio_storage_path, filename)
                    
                    if os.path.isfile(file_path):
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        
                        if file_time < cutoff_time:
                            os.remove(file_path)
                            logger.debug("Removed old audio file", filename=filename)
            
        except Exception as e:
            logger.error("Failed to cleanup old files", error=str(e))
