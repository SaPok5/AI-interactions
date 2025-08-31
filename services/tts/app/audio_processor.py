"""Audio processing utilities for TTS service"""

import asyncio
import numpy as np
import librosa
import soundfile as sf
from typing import Tuple, Optional
import structlog

from .config import settings

logger = structlog.get_logger(__name__)

class AudioProcessor:
    """Audio processing and enhancement utilities"""
    
    def __init__(self):
        self.target_sample_rate = settings.sample_rate
    
    async def enhance_audio(self, audio_data: np.ndarray, sample_rate: int) -> Tuple[np.ndarray, int]:
        """Enhance audio quality"""
        try:
            # Resample if needed
            if sample_rate != self.target_sample_rate:
                audio_data = librosa.resample(
                    audio_data, 
                    orig_sr=sample_rate, 
                    target_sr=self.target_sample_rate
                )
                sample_rate = self.target_sample_rate
            
            # Normalize audio
            audio_data = self._normalize_audio(audio_data)
            
            # Apply noise reduction if needed
            if settings.audio_quality == "high":
                audio_data = await self._apply_noise_reduction(audio_data)
            
            return audio_data, sample_rate
            
        except Exception as e:
            logger.error("Audio enhancement failed", error=str(e))
            return audio_data, sample_rate
    
    def _normalize_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Normalize audio amplitude"""
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            return audio_data / max_val * 0.95
        return audio_data
    
    async def _apply_noise_reduction(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply basic noise reduction"""
        try:
            # Simple spectral gating
            stft = librosa.stft(audio_data)
            magnitude = np.abs(stft)
            
            # Estimate noise floor
            noise_floor = np.percentile(magnitude, 10)
            
            # Apply gating
            gate_threshold = noise_floor * 2
            mask = magnitude > gate_threshold
            
            # Apply mask
            stft_filtered = stft * mask
            
            # Reconstruct audio
            audio_filtered = librosa.istft(stft_filtered)
            
            return audio_filtered
            
        except Exception as e:
            logger.warning("Noise reduction failed", error=str(e))
            return audio_data
    
    async def adjust_speed(self, audio_data: np.ndarray, speed_factor: float) -> np.ndarray:
        """Adjust audio playback speed"""
        try:
            if speed_factor == 1.0:
                return audio_data
            
            # Use librosa for time stretching
            return librosa.effects.time_stretch(audio_data, rate=speed_factor)
            
        except Exception as e:
            logger.error("Speed adjustment failed", error=str(e))
            return audio_data
    
    async def adjust_pitch(self, audio_data: np.ndarray, sample_rate: int, pitch_factor: float) -> np.ndarray:
        """Adjust audio pitch"""
        try:
            if pitch_factor == 1.0:
                return audio_data
            
            # Convert factor to semitones
            n_steps = 12 * np.log2(pitch_factor)
            
            # Use librosa for pitch shifting
            return librosa.effects.pitch_shift(
                audio_data, 
                sr=sample_rate, 
                n_steps=n_steps
            )
            
        except Exception as e:
            logger.error("Pitch adjustment failed", error=str(e))
            return audio_data
