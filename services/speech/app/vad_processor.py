"""Voice Activity Detection processor"""

import numpy as np
import webrtcvad
import structlog
from typing import List, Tuple
from .config import settings
from .models import VADResult
from datetime import datetime

logger = structlog.get_logger(__name__)

class VADProcessor:
    """Voice Activity Detection using WebRTC VAD"""
    
    def __init__(self):
        self.vad = webrtcvad.Vad(settings.vad_aggressiveness)
        self.sample_rate = settings.sample_rate
        self.frame_duration_ms = 30  # WebRTC VAD requires 10, 20, or 30ms frames
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        
    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """Detect if audio chunk contains speech"""
        try:
            # Ensure audio is in correct format (16-bit PCM)
            if audio_chunk.dtype != np.int16:
                # Convert float32 to int16
                if audio_chunk.dtype == np.float32:
                    audio_chunk = (audio_chunk * 32767).astype(np.int16)
                else:
                    audio_chunk = audio_chunk.astype(np.int16)
            
            # Pad or trim to frame size
            if len(audio_chunk) < self.frame_size:
                # Pad with zeros
                padded = np.zeros(self.frame_size, dtype=np.int16)
                padded[:len(audio_chunk)] = audio_chunk
                audio_chunk = padded
            elif len(audio_chunk) > self.frame_size:
                # Take first frame_size samples
                audio_chunk = audio_chunk[:self.frame_size]
            
            # Convert to bytes
            audio_bytes = audio_chunk.tobytes()
            
            # Run VAD
            return self.vad.is_speech(audio_bytes, self.sample_rate)
            
        except Exception as e:
            logger.error("VAD processing error", error=str(e))
            return False
    
    def process_buffer(self, audio_buffer: np.ndarray) -> List[VADResult]:
        """Process entire audio buffer and return VAD results for each frame"""
        results = []
        
        # Process in frames
        for i in range(0, len(audio_buffer), self.frame_size):
            frame = audio_buffer[i:i + self.frame_size]
            
            if len(frame) < self.frame_size:
                break
            
            is_speech = self.is_speech(frame)
            energy = float(np.mean(np.abs(frame)))
            
            results.append(VADResult(
                is_speech=is_speech,
                energy=energy,
                confidence=0.9 if is_speech else 0.1,  # Simplified confidence
                timestamp=datetime.utcnow()
            ))
        
        return results
    
    def get_speech_segments(self, audio_buffer: np.ndarray, min_speech_duration_ms: int = 100) -> List[Tuple[int, int]]:
        """Get speech segments from audio buffer"""
        vad_results = self.process_buffer(audio_buffer)
        
        segments = []
        current_start = None
        min_frames = min_speech_duration_ms // self.frame_duration_ms
        
        speech_frame_count = 0
        
        for i, result in enumerate(vad_results):
            if result.is_speech:
                if current_start is None:
                    current_start = i * self.frame_size
                speech_frame_count += 1
            else:
                if current_start is not None and speech_frame_count >= min_frames:
                    # End of speech segment
                    segments.append((current_start, i * self.frame_size))
                
                current_start = None
                speech_frame_count = 0
        
        # Handle case where speech continues to end of buffer
        if current_start is not None and speech_frame_count >= min_frames:
            segments.append((current_start, len(audio_buffer)))
        
        return segments
