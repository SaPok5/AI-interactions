"""TTS engine implementation with multiple backends"""

import asyncio
import time
import asyncio
import base64
import io
import os
from typing import Dict, Any, List, Optional, AsyncGenerator
import numpy as np
import structlog
import soundfile as sf

# Free and Open Source TTS engines
try:
    from TTS.api import TTS
except ImportError:
    TTS = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

# Import our local TTS engines
from .piper_tts import PiperTTS
from .espeak_tts import ESpeakTTS
from .config import settings
from .models import TTSResult, AudioChunk

logger = structlog.get_logger(__name__)

class TTSEngine:
    """Multi-backend TTS engine with caching and streaming support"""
    
    def __init__(self):
        self.engines = {}
        self.cache = {}
        self.audio_storage_path = settings.audio_storage_path
        self.sample_rate = settings.sample_rate
        self.channels = 1
        self.cache_ttl = settings.audio_cache_ttl_hours * 3600
        self.max_cache_size = 100
        
        # Create storage directories
        os.makedirs(self.audio_storage_path, exist_ok=True)
        os.makedirs(settings.piper_models_path, exist_ok=True)
        os.makedirs(settings.coqui_models_path, exist_ok=True)
        
        # Initialize engine instances
        self.piper_tts = None
        self.espeak_tts = None
        self.coqui_tts = None
        
        # Metrics
        self.cache_hits = 0
        self.active_sessions = {}
        self.total_syntheses = 0
        self.synthesis_times = []
        self.files_generated = 0
        self.total_audio_duration = 0.0
        
    async def initialize(self):
        """Initialize free and open source TTS engines"""
        try:
            # Initialize Piper TTS (fastest neural TTS)
            if settings.enable_piper_tts:
                try:
                    self.piper_tts = PiperTTS(settings.piper_models_path)
                    if await self.piper_tts.initialize():
                        self.engines["piper"] = self.piper_tts
                        logger.info("Piper TTS engine initialized")
                    else:
                        logger.warning("Piper TTS initialization failed")
                except Exception as e:
                    logger.warning("Piper TTS not available", error=str(e))
            
            # Initialize Coqui TTS (high quality neural TTS)
            if settings.enable_coqui_tts and TTS is not None:
                try:
                    loop = asyncio.get_event_loop()
                    self.coqui_tts = await loop.run_in_executor(
                        None,
                        lambda: TTS(model_name=settings.default_coqui_model)
                    )
                    if self.coqui_tts:
                        self.engines["coqui"] = self.coqui_tts
                        logger.info("Coqui TTS engine initialized")
                except Exception as e:
                    logger.warning("Coqui TTS not available", error=str(e))
            
            # Initialize eSpeak NG (lightweight formant synthesis)
            if settings.enable_espeak_ng:
                try:
                    self.espeak_tts = ESpeakTTS()
                    if await self.espeak_tts.initialize():
                        self.engines["espeak"] = self.espeak_tts
                        logger.info("eSpeak NG engine initialized")
                    else:
                        logger.warning("eSpeak NG initialization failed")
                except Exception as e:
                    logger.warning("eSpeak NG not available", error=str(e))
            
            # Initialize pyttsx3 (system TTS wrapper)
            if settings.enable_pyttsx3 and pyttsx3 is not None:
                try:
                    engine = pyttsx3.init()
                    if engine:
                        engine.setProperty('rate', 200)
                        engine.setProperty('volume', 0.9)
                        self.engines["pyttsx3"] = engine
                        logger.info("pyttsx3 engine initialized")
                except Exception as e:
                    logger.warning("pyttsx3 not available", error=str(e))
            
            if not self.engines:
                raise Exception("No TTS engines available")
            
            logger.info("TTS engines initialized", engines=list(self.engines.keys()))
            
        except Exception as e:
            logger.error("Failed to initialize TTS engines", error=str(e))
            raise
    
    async def synthesize(
        self, 
        text: str, 
        voice: str = "alloy", 
        language: str = "en", 
        speed: float = 1.0, 
        pitch: float = 0.0, 
        session_id: Optional[str] = None
    ) -> Optional[TTSResult]:
        """Synthesize text to speech with optimized caching"""
        try:
            # Generate cache key
            cache_key = self._generate_cache_key(text, voice, language, speed, pitch)
            
            # Check cache first for instant response
            if cache_key in self.cache:
                cached_result = self.cache[cache_key]
                # Check if cache entry is still valid (within TTL)
                if time.time() - cached_result.get('timestamp', 0) < self.cache_ttl:
                    logger.info("Cache hit for TTS request", cache_key=cache_key[:8])
                    self.cache_hits += 1
                    return cached_result['result']
                else:
                    # Remove expired cache entry
                    del self.cache[cache_key]
            
            start_time = time.time()
            
            # Select appropriate engine (prioritize local engines)
            engine_name = self._select_engine(voice, language)
            logger.info("Using TTS engine", engine=engine_name, voice=voice, language=language)
            
            # Synthesize audio with appropriate timeout
            timeout = self._get_engine_timeout(engine_name)
            try:
                audio_data, sample_rate = await asyncio.wait_for(
                    self._synthesize_with_engine(text, voice, language, speed, pitch, engine_name),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("TTS synthesis timeout, trying fallback", engine=engine_name)
                fallback_engine = self._get_fallback_engine(engine_name)
                if fallback_engine:
                    audio_data, sample_rate = await self._synthesize_with_engine(
                        text, voice, language, speed, pitch, fallback_engine
                    )
                else:
                    raise Exception("All TTS engines failed")
            
            if audio_data is None:
                logger.error("TTS synthesis failed")
                return None
            
            # Calculate duration
            duration_ms = int((len(audio_data) / sample_rate) * 1000)
            
            # Save audio file
            audio_id = f"tts_{int(time.time())}_{hash(text) % 10000}"
            audio_path = os.path.join(self.audio_storage_path, f"{audio_id}.wav")
            
            # Convert to WAV format and save
            wav_data = self._convert_to_wav(audio_data, sample_rate)
            with open(audio_path, "wb") as f:
                f.write(wav_data)
            
            # Convert to base64 for transmission
            audio_base64 = base64.b64encode(wav_data).decode('utf-8')
            
            # Calculate synthesis time
            synthesis_time_ms = (time.time() - start_time) * 1000
            
            # Create result
            result = TTSResult(
                audio_url=f"/audio/{audio_id}",
                audio_data=audio_base64,
                duration_ms=duration_ms,
                text=text,
                voice=voice,
                language=language,
                synthesis_time_ms=synthesis_time_ms
            )
            
            # Cache result with timestamp for TTL
            self.cache[cache_key] = {
                'result': result,
                'timestamp': time.time()
            }
            
            # Limit cache size for memory efficiency
            if len(self.cache) > self.max_cache_size:
                # Remove oldest entries
                sorted_cache = sorted(self.cache.items(), key=lambda x: x[1]['timestamp'])
                for key, _ in sorted_cache[:20]:  # Remove 20 oldest entries
                    del self.cache[key]
            
            # Update metrics
            synthesis_time = time.time() - start_time
            self.total_syntheses += 1
            self.synthesis_times.append(synthesis_time)
            self.files_generated += 1
            self.total_audio_duration += duration_ms / 1000.0
            
            logger.info(
                "TTS synthesis complete", 
                engine=engine_name,
                duration_ms=duration_ms,
                synthesis_time_s=round(synthesis_time, 2),
                audio_id=audio_id,
                cache_size=len(self.cache)
            )
            
            return result
            
        except Exception as e:
            logger.error("TTS synthesis failed", error=str(e), text=text[:50])
            return None
    
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
        
        if engine_name == "piper" and "piper" in self.engines:
            return await self._synthesize_piper(text, voice, speed)
        elif engine_name == "coqui" and "coqui" in self.engines:
            return await self._synthesize_coqui(text, voice, speed)
        elif engine_name == "espeak" and "espeak" in self.engines:
            return await self._synthesize_espeak(text, voice, speed, pitch)
        elif engine_name == "pyttsx3" and "pyttsx3" in self.engines:
            return await self._synthesize_pyttsx3(text, speed)
        else:
            raise Exception(f"Engine {engine_name} not available")
    
    async def _synthesize_piper(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        """Synthesize with Piper TTS"""
        # Map voice preferences to Piper models
        model_map = {
            "nova": "en_US-amy-medium",
            "alloy": "en_US-lessac-medium", 
            "echo": "en_US-ryan-high",
            "fable": "en_US-amy-medium",
            "onyx": "en_US-ryan-high",
            "shimmer": "en_US-amy-medium"
        }
        
        model_name = model_map.get(voice, settings.default_piper_model)
        return await self.piper_tts.synthesize(text, model_name, speed)
    
    async def _synthesize_coqui(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        """Synthesize with Coqui TTS"""
        loop = asyncio.get_event_loop()
        
        def synthesize():
            wav = self.coqui_tts.tts(text)
            return np.array(wav), self.coqui_tts.synthesizer.output_sample_rate
        
        return await loop.run_in_executor(None, synthesize)
    
    async def _synthesize_espeak(self, text: str, voice: str, speed: float, pitch: float) -> tuple[np.ndarray, int]:
        """Synthesize with eSpeak NG"""
        return await self.espeak_tts.synthesize(text, voice, speed, pitch)
    
    
    async def _synthesize_pyttsx3(self, text: str, speed: float) -> tuple[np.ndarray, int]:
        """Synthesize with pyttsx3"""
        import uuid
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
        """Select the best TTS engine based on availability and quality"""
        # Priority order: Piper (fastest) -> Coqui (highest quality) -> eSpeak (lightweight) -> pyttsx3 (system)
        
        if settings.default_engine == "piper" and "piper" in self.engines:
            return "piper"
        elif settings.default_engine == "coqui" and "coqui" in self.engines:
            return "coqui"
        elif "piper" in self.engines:
            return "piper"
        elif "coqui" in self.engines:
            return "coqui"
        elif "espeak" in self.engines:
            return "espeak"
        elif "pyttsx3" in self.engines:
            return "pyttsx3"
        else:
            raise Exception("No TTS engines available")
    
    def _get_engine_timeout(self, engine_name: str) -> float:
        """Get timeout for specific engine"""
        timeouts = {
            "piper": settings.piper_synthesis_timeout,
            "coqui": settings.coqui_synthesis_timeout,
            "espeak": 15.0,  # eSpeak is very fast
            "pyttsx3": 30.0
        }
        return timeouts.get(engine_name, settings.synthesis_timeout_seconds)
    
    def _get_fallback_engine(self, failed_engine: str) -> Optional[str]:
        """Get fallback engine when primary fails"""
        fallback_order = {
            "piper": ["coqui", "espeak", "pyttsx3"],
            "coqui": ["piper", "espeak", "pyttsx3"],
            "espeak": ["piper", "pyttsx3"],
            "pyttsx3": ["espeak"]
        }
        
        for fallback in fallback_order.get(failed_engine, []):
            if fallback in self.engines:
                return fallback
        return None
    
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
        health: Dict[str, Any] = {}

        # Check each initialized engine
        for engine_name, engine in self.engines.items():
            if engine_name == "piper" and self.piper_tts:
                health[engine_name] = await self.piper_tts.health_check()
            elif engine_name == "coqui" and self.coqui_tts:
                health[engine_name] = "ready" if engine is not None else "uninitialized"
            elif engine_name == "espeak" and self.espeak_tts:
                health[engine_name] = await self.espeak_tts.health_check()
            elif engine_name == "pyttsx3":
                health[engine_name] = "ready" if engine is not None else "uninitialized"
            else:
                health[engine_name] = "ready"

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
    
    def _convert_to_wav(self, audio_data: np.ndarray, sample_rate: int) -> bytes:
        """Convert audio data to WAV format"""
        import wave
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            
            # Convert float audio to 16-bit PCM
            if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
                audio_data = (audio_data * 32767).astype(np.int16)
            
            wav_file.writeframes(audio_data.tobytes())
        
        wav_buffer.seek(0)
        return wav_buffer.read()
    
    async def cleanup_old_files(self):
        """Clean up old audio files"""
        try:
            from datetime import datetime, timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=settings.audio_cache_ttl_hours)
            
            if os.path.exists(self.audio_storage_path):
                for filename in os.listdir(self.audio_storage_path):
                    file_path = os.path.join(self.audio_storage_path, filename)
                    
                    if os.path.isfile(file_path):
                        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                        
                        if file_time < cutoff_time:
                            os.remove(file_path)
                            logger.debug("Removed old audio file", filename=filename)
            
        except Exception as e:
            logger.error("Failed to cleanup old files", error=str(e))
