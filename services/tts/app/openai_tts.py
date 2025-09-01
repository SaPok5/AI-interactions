"""OpenAI TTS integration for natural voice synthesis"""

import asyncio
import aiohttp
import base64
import io
import os
from typing import Optional, AsyncGenerator
import structlog
import soundfile as sf
import numpy as np
from datetime import datetime

logger = structlog.get_logger(__name__)

class OpenAITTS:
    """OpenAI TTS client for natural voice synthesis"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1/audio/speech"
        self.session = None
        
        # Voice options - these are the same voices ChatGPT uses
        self.voices = {
            "alloy": "Neutral, balanced voice",
            "echo": "Male voice with clarity", 
            "fable": "British accent, expressive",
            "onyx": "Deep male voice",
            "nova": "Young female voice",
            "shimmer": "Soft female voice"
        }
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def synthesize(
        self,
        text: str,
        voice: str = "nova",
        model: str = "tts-1-hd",  # High quality model
        speed: float = 1.0
    ) -> tuple[np.ndarray, int]:
        """Synthesize text using OpenAI TTS API"""
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
            
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # Validate voice
        if voice not in self.voices:
            voice = "nova"  # Default to nova
            
        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "wav",
            "speed": max(0.25, min(4.0, speed))  # Clamp speed
        }
        
        try:
            start_time = datetime.utcnow()
            
            async with self.session.post(
                self.base_url,
                headers=headers,
                json=payload
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI TTS API error {response.status}: {error_text}")
                
                # Get audio data
                audio_bytes = await response.read()
                
                # Convert to numpy array
                audio_buffer = io.BytesIO(audio_bytes)
                audio_array, sample_rate = sf.read(audio_buffer)
                
                synthesis_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                logger.info(
                    "OpenAI TTS synthesis completed",
                    text_length=len(text),
                    voice=voice,
                    model=model,
                    synthesis_time_ms=synthesis_time,
                    sample_rate=sample_rate
                )
                
                return audio_array, sample_rate
                
        except Exception as e:
            logger.error("OpenAI TTS synthesis failed", error=str(e))
            raise
    
    async def synthesize_streaming(
        self,
        text: str,
        voice: str = "nova",
        model: str = "tts-1",  # Use faster model for streaming
        speed: float = 1.0,
        chunk_size: int = 1024
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize with streaming output for real-time playback"""
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
            
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "wav",
            "speed": max(0.25, min(4.0, speed))
        }
        
        try:
            async with self.session.post(
                self.base_url,
                headers=headers,
                json=payload
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI TTS API error {response.status}: {error_text}")
                
                # Stream audio data in chunks
                async for chunk in response.content.iter_chunked(chunk_size):
                    yield chunk
                    
        except Exception as e:
            logger.error("OpenAI TTS streaming failed", error=str(e))
            raise
    
    def get_available_voices(self) -> dict:
        """Get available voice options"""
        return self.voices
    
    async def health_check(self) -> bool:
        """Check if OpenAI TTS API is accessible"""
        if not self.api_key:
            return False
            
        try:
            # Test with minimal request
            await self.synthesize("Test", voice="nova")
            return True
        except Exception:
            return False
