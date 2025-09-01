"""ASR Engine with Faster Whisper implementation"""

import asyncio
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import structlog
from faster_whisper import WhisperModel

from .config import settings
from .models import ASRResult, WordTimestamp, SessionState

logger = structlog.get_logger(__name__)

class ASREngine:
    """Automatic Speech Recognition Engine"""
    
    def __init__(self):
        self.model: Optional[WhisperModel] = None
        self.active_sessions: Dict[str, SessionState] = {}
        self.total_processed: int = 0
        self._model_loaded = False
    
    async def load_model(self):
        """Load the Whisper model"""
        try:
            # Load model in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    settings.asr_model,
                    device="cpu",
                    compute_type="int8"
                )
            )
            self._model_loaded = True
            logger.info("ASR model loaded successfully", model=settings.asr_model)
        except Exception as e:
            logger.error("Failed to load ASR model", error=str(e))
            raise
    
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._model_loaded
    
    async def process_chunk(self, audio_chunk: np.ndarray, session_id: str) -> Optional[ASRResult]:
        """Process audio chunk for streaming ASR"""
        if not self.model:
            return None
        
        try:
            # Get or create session
            session = self._get_or_create_session(session_id)
            
            # Add chunk to buffer
            session.buffer.extend(audio_chunk.tolist())
            session.last_activity = datetime.utcnow()
            session.total_audio_seconds += len(audio_chunk) / settings.sample_rate
            
            # Process if buffer is large enough (500ms worth of audio)
            min_buffer_size = int(settings.sample_rate * 0.5)
            if len(session.buffer) >= min_buffer_size:
                return await self._transcribe_buffer(session)
            
            return None
            
        except Exception as e:
            logger.error("Error processing audio chunk", error=str(e), session_id=session_id)
            return None
    
    async def transcribe_complete(self, audio: np.ndarray, language: str = "auto", fast_mode: bool = False) -> Optional[ASRResult]:
        """Complete transcription of audio segment with optional fast mode"""
        if not self.model:
            logger.error("ASR model not initialized")
            return None
        
        try:
            start_time = datetime.utcnow()
            
            # Ensure audio is float32 and normalized
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            
            # Normalize if needed
            if np.max(np.abs(audio)) > 1.0:
                audio = audio / np.max(np.abs(audio))
            
            logger.info("Starting complete transcription", 
                       audio_length=len(audio), 
                       sample_rate=16000,
                       language=language,
                       fast_mode=fast_mode)
            
            # Optimize settings for fast mode
            beam_size = 1 if fast_mode else settings.beam_size
            temperature = 0.0 if fast_mode else settings.temperature
            word_timestamps = not fast_mode  # Skip word timestamps in fast mode
            
            # Run transcription in thread pool
            loop = asyncio.get_event_loop()
            segments, info = await loop.run_in_executor(
                None,
                lambda: self.model.transcribe(
                    audio,
                    beam_size=beam_size,
                    temperature=temperature,
                    language=language if language != "auto" else None,
                    word_timestamps=word_timestamps
                )
            )
            
            # Collect results
            text_parts = []
            timestamps = []
            total_confidence = 0.0
            segment_count = 0
            
            for segment in segments:
                text_parts.append(segment.text.strip())
                segment_count += 1
                
                # Add word timestamps if available
                if hasattr(segment, 'words') and segment.words:
                    for word in segment.words:
                        timestamps.append(WordTimestamp(
                            word=word.word,
                            start=word.start,
                            end=word.end,
                            confidence=getattr(word, 'probability', 0.9)
                        ))
                
                # Accumulate confidence (using avg_logprob as proxy)
                total_confidence += getattr(segment, 'avg_logprob', -0.5)
            
            # Calculate metrics
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            confidence = min(1.0, max(0.0, (total_confidence / segment_count + 1.0) / 2.0)) if segment_count > 0 else 0.0
            
            self.total_processed += 1
            
            return ASRResult(
                text=" ".join(text_parts),
                confidence=confidence,
                is_final=True,
                language=info.language,
                timestamps=timestamps,
                session_id="complete",
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error("Transcription failed", error=str(e))
            raise
    
    async def _transcribe_buffer(self, session: SessionState) -> Optional[ASRResult]:
        """Transcribe audio buffer"""
        if len(session.buffer) == 0:
            return None
        
        start_time = datetime.utcnow()
        
        try:
            # Convert buffer to numpy array
            audio_array = np.array(session.buffer, dtype=np.float32)
            
            # Run transcription
            loop = asyncio.get_event_loop()
            segments, info = await loop.run_in_executor(
                None,
                lambda: self.model.transcribe(
                    audio_array,
                    beam_size=1,  # Fast for streaming
                    temperature=0.0,
                    language=session.language if session.language != "auto" else None,
                    word_timestamps=False  # Skip for speed in streaming
                )
            )
            
            # Collect text
            text_parts = []
            total_confidence = 0.0
            segment_count = 0
            
            for segment in segments:
                text_parts.append(segment.text.strip())
                segment_count += 1
                total_confidence += getattr(segment, 'avg_logprob', -0.5)
            
            if segment_count == 0:
                return None
            
            # Update session
            if not session.language:
                session.language = info.language
            
            session.word_count += len(" ".join(text_parts).split())
            
            # Calculate confidence
            confidence = min(1.0, max(0.0, (total_confidence / segment_count + 1.0) / 2.0))
            
            # Clear buffer (keep last 100ms for context)
            context_size = int(settings.sample_rate * 0.1)
            session.buffer = session.buffer[-context_size:] if len(session.buffer) > context_size else []
            
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return ASRResult(
                text=" ".join(text_parts),
                confidence=confidence,
                is_final=False,
                language=info.language,
                timestamps=[],
                session_id=session.session_id,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error("Buffer transcription failed", error=str(e), session_id=session.session_id)
            return None
    
    def _get_or_create_session(self, session_id: str) -> SessionState:
        """Get existing session or create new one"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = SessionState(
                session_id=session_id,
                last_activity=datetime.utcnow()
            )
        
        return self.active_sessions[session_id]
    
    async def cleanup_session(self, session_id: str):
        """Clean up session resources"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.info("Session cleaned up", session_id=session_id)
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=settings.session_timeout)
        expired_sessions = [
            sid for sid, session in self.active_sessions.items()
            if session.last_activity < cutoff_time
        ]
        
        for session_id in expired_sessions:
            await self.cleanup_session(session_id)
        
        if expired_sessions:
            logger.info("Cleaned up expired sessions", count=len(expired_sessions))
    
    def get_average_confidence(self) -> float:
        """Get average confidence across all sessions"""
        if not self.active_sessions:
            return 0.0
        
        # This is a simplified metric - in production you'd track this properly
        return 0.85  # Placeholder
    
    async def finalize_session(self, session_id: str) -> Optional[ASRResult]:
        """Finalize session and get complete transcription"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        if len(session.buffer) > 0:
            # Process remaining buffer
            result = await self._transcribe_buffer(session)
            if result:
                result.is_final = True
            
            # Clean up
            await self.cleanup_session(session_id)
            
            return result
        
        await self.cleanup_session(session_id)
        return None
