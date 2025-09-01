"""Google Gemini TTS integration for natural voice synthesis"""

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
import json

logger = structlog.get_logger(__name__)

class GeminiTTS:
    """Google Gemini TTS client for natural voice synthesis"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.base_url = "https://texttospeech.googleapis.com/v1/text:synthesize"
        self.session = None
        
        # Voice options - Google Cloud TTS voices with natural quality
        self.voices = {
            "en-US-Journey-D": "Male, conversational",
            "en-US-Journey-F": "Female, conversational", 
            "en-US-Neural2-A": "Female, natural",
            "en-US-Neural2-C": "Female, warm",
            "en-US-Neural2-D": "Male, natural",
            "en-US-Neural2-F": "Female, clear",
            "en-US-Neural2-G": "Female, young",
            "en-US-Neural2-H": "Female, soft",
            "en-US-Neural2-I": "Male, deep",
            "en-US-Neural2-J": "Male, warm"
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
        voice: str = "en-US-Neural2-F",
        speaking_rate: float = 1.0
    ) -> tuple[np.ndarray, int]:
        """Synthesize text using Google Cloud TTS API"""
        
        if not self.api_key:
            raise ValueError("Google API key not provided")
            
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # Validate voice
        if voice not in self.voices:
            voice = "en-US-Neural2-F"  # Default to natural female voice
            
        # Prepare request
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key
        }
        
        # Extract language and voice name
        language_code = voice.split('-')[0] + '-' + voice.split('-')[1]  # e.g., "en-US"
        
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": language_code,
                "name": voice,
                "ssmlGender": "FEMALE" if "F" in voice or "A" in voice or "C" in voice or "G" in voice or "H" in voice else "MALE"
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": 24000,
                "speakingRate": max(0.25, min(4.0, speaking_rate)),
                "pitch": 0.0,
                "volumeGainDb": 0.0,
                "effectsProfileId": ["telephony-class-application"]
            }
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
                    raise Exception(f"Google TTS API error {response.status}: {error_text}")
                
                # Get response data
                response_data = await response.json()
                
                if "audioContent" not in response_data:
                    raise Exception("No audio content in response")
                
                # Decode base64 audio
                audio_bytes = base64.b64decode(response_data["audioContent"])
                
                # Convert to numpy array
                audio_buffer = io.BytesIO(audio_bytes)
                audio_array, sample_rate = sf.read(audio_buffer)
                
                synthesis_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                logger.info(
                    "Google TTS synthesis completed",
                    text_length=len(text),
                    voice=voice,
                    synthesis_time_ms=synthesis_time,
                    sample_rate=sample_rate
                )
                
                return audio_array, sample_rate
                
        except Exception as e:
            logger.error("Google TTS synthesis failed", error=str(e))
            raise
    
    async def synthesize_streaming(
        self,
        text: str,
        voice: str = "en-US-Neural2-F",
        speaking_rate: float = 1.0,
        chunk_size: int = 1024
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize with streaming output for real-time playback"""
        
        # Google TTS doesn't support true streaming, so we'll synthesize and chunk
        try:
            audio_array, sample_rate = await self.synthesize(text, voice, speaking_rate)
            
            # Convert to bytes
            audio_bytes = io.BytesIO()
            sf.write(audio_bytes, audio_array, sample_rate, format='WAV')
            audio_data = audio_bytes.getvalue()
            
            # Stream in chunks
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]
                await asyncio.sleep(0.01)  # Small delay for streaming effect
                    
        except Exception as e:
            logger.error("Google TTS streaming failed", error=str(e))
            raise
    
    def get_available_voices(self) -> dict:
        """Get available voice options"""
        return self.voices
    
    async def health_check(self) -> bool:
        """Check if Google TTS API is accessible"""
        if not self.api_key:
            return False
            
        try:
            # Test with minimal request
            await self.synthesize("Test", voice="en-US-Neural2-F")
            return True
        except Exception:
            return False
    
    def map_voice_preference(self, preference: str) -> str:
        """Map user preference to Google voice"""
        voice_mapping = {
            "nova": "en-US-Neural2-F",      # Female, clear
            "shimmer": "en-US-Neural2-H",   # Female, soft
            "alloy": "en-US-Neural2-A",     # Female, natural
            "echo": "en-US-Neural2-D",      # Male, natural
            "fable": "en-US-Journey-F",     # Female, conversational
            "onyx": "en-US-Neural2-I"       # Male, deep
        }
        return voice_mapping.get(preference, "en-US-Neural2-F")
