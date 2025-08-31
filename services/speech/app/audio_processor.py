"""Audio processing utilities"""

import numpy as np
import librosa
import io
import wave
import struct
from typing import Optional, Tuple
import structlog

from .config import settings

logger = structlog.get_logger(__name__)

class AudioProcessor:
    """Audio processing and format conversion utilities"""
    
    def __init__(self):
        self.target_sample_rate = settings.sample_rate
        self.target_channels = 1  # Mono
    
    def load_audio_from_bytes(self, audio_bytes: bytes) -> np.ndarray:
        """Load audio from bytes and convert to target format"""
        try:
            # Try to detect format and load
            audio_data = None
            
            # Try WAV format first
            try:
                audio_data = self._load_wav_from_bytes(audio_bytes)
            except:
                pass
            
            # Try using librosa for other formats
            if audio_data is None:
                try:
                    audio_data, sr = librosa.load(
                        io.BytesIO(audio_bytes), 
                        sr=self.target_sample_rate,
                        mono=True
                    )
                except:
                    # Last resort - assume raw PCM
                    audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
                    sr = self.target_sample_rate
            
            # Ensure correct sample rate
            if hasattr(audio_data, '__len__') and len(audio_data) > 0:
                return self._ensure_format(audio_data)
            else:
                raise ValueError("No audio data could be extracted")
                
        except Exception as e:
            logger.error("Failed to load audio from bytes", error=str(e))
            raise
    
    def _load_wav_from_bytes(self, audio_bytes: bytes) -> np.ndarray:
        """Load WAV audio from bytes"""
        with wave.open(io.BytesIO(audio_bytes), 'rb') as wav_file:
            frames = wav_file.readframes(-1)
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            framerate = wav_file.getframerate()
            
            # Convert to numpy array
            if sample_width == 1:
                audio_data = np.frombuffer(frames, dtype=np.uint8)
                audio_data = (audio_data.astype(np.float32) - 128) / 128.0
            elif sample_width == 2:
                audio_data = np.frombuffer(frames, dtype=np.int16)
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif sample_width == 4:
                audio_data = np.frombuffer(frames, dtype=np.int32)
                audio_data = audio_data.astype(np.float32) / 2147483648.0
            else:
                raise ValueError(f"Unsupported sample width: {sample_width}")
            
            # Handle stereo to mono conversion
            if channels == 2:
                audio_data = audio_data.reshape(-1, 2)
                audio_data = np.mean(audio_data, axis=1)
            
            # Resample if necessary
            if framerate != self.target_sample_rate:
                audio_data = librosa.resample(
                    audio_data, 
                    orig_sr=framerate, 
                    target_sr=self.target_sample_rate
                )
            
            return audio_data
    
    def _ensure_format(self, audio_data: np.ndarray) -> np.ndarray:
        """Ensure audio is in correct format (float32, mono, target sample rate)"""
        # Convert to float32 if needed
        if audio_data.dtype != np.float32:
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_data = audio_data.astype(np.float32) / 2147483648.0
            else:
                audio_data = audio_data.astype(np.float32)
        
        # Ensure mono
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)
        
        # Normalize amplitude
        if np.max(np.abs(audio_data)) > 1.0:
            audio_data = audio_data / np.max(np.abs(audio_data))
        
        return audio_data
    
    def convert_to_int16(self, audio_data: np.ndarray) -> np.ndarray:
        """Convert float32 audio to int16 for VAD"""
        return (audio_data * 32767).astype(np.int16)
    
    def split_into_chunks(self, audio_data: np.ndarray, chunk_duration_ms: int) -> list:
        """Split audio into chunks of specified duration"""
        chunk_size = int(self.target_sample_rate * chunk_duration_ms / 1000)
        chunks = []
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            if len(chunk) == chunk_size:  # Only include complete chunks
                chunks.append(chunk)
        
        return chunks
    
    def apply_noise_reduction(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply basic noise reduction"""
        try:
            # Simple spectral subtraction
            # This is a basic implementation - production would use more sophisticated methods
            
            # Compute STFT
            stft = librosa.stft(audio_data)
            magnitude = np.abs(stft)
            phase = np.angle(stft)
            
            # Estimate noise from first 0.5 seconds
            noise_frames = int(0.5 * self.target_sample_rate / 512)  # 512 is default hop_length
            noise_spectrum = np.mean(magnitude[:, :noise_frames], axis=1, keepdims=True)
            
            # Spectral subtraction
            alpha = 2.0  # Over-subtraction factor
            beta = 0.01  # Spectral floor
            
            clean_magnitude = magnitude - alpha * noise_spectrum
            clean_magnitude = np.maximum(clean_magnitude, beta * magnitude)
            
            # Reconstruct signal
            clean_stft = clean_magnitude * np.exp(1j * phase)
            clean_audio = librosa.istft(clean_stft)
            
            return clean_audio
            
        except Exception as e:
            logger.warning("Noise reduction failed, returning original audio", error=str(e))
            return audio_data
    
    def detect_silence(self, audio_data: np.ndarray, threshold: float = 0.01) -> Tuple[int, int]:
        """Detect start and end of non-silent audio"""
        # Find first and last non-silent samples
        non_silent = np.where(np.abs(audio_data) > threshold)[0]
        
        if len(non_silent) == 0:
            return 0, len(audio_data)
        
        start_idx = non_silent[0]
        end_idx = non_silent[-1] + 1
        
        return start_idx, end_idx
    
    def trim_silence(self, audio_data: np.ndarray, threshold: float = 0.01) -> np.ndarray:
        """Trim silence from beginning and end of audio"""
        start_idx, end_idx = self.detect_silence(audio_data, threshold)
        return audio_data[start_idx:end_idx]
    
    def normalize_volume(self, audio_data: np.ndarray, target_db: float = -20.0) -> np.ndarray:
        """Normalize audio volume to target dB"""
        try:
            # Calculate RMS
            rms = np.sqrt(np.mean(audio_data ** 2))
            
            if rms == 0:
                return audio_data
            
            # Convert target dB to linear scale
            target_rms = 10 ** (target_db / 20.0)
            
            # Apply gain
            gain = target_rms / rms
            normalized_audio = audio_data * gain
            
            # Prevent clipping
            if np.max(np.abs(normalized_audio)) > 1.0:
                normalized_audio = normalized_audio / np.max(np.abs(normalized_audio))
            
            return normalized_audio
            
        except Exception as e:
            logger.warning("Volume normalization failed", error=str(e))
            return audio_data
