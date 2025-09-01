"""eSpeak NG TTS engine implementation - Lightweight formant synthesis"""

import asyncio
import os
import tempfile
import subprocess
from typing import Optional, Tuple, List
import numpy as np
import soundfile as sf
import structlog

logger = structlog.get_logger(__name__)

class ESpeakTTS:
    """eSpeak NG TTS engine for lightweight text-to-speech synthesis"""
    
    def __init__(self):
        self.available_voices = {}
        self.default_voice = "en"
        
    async def initialize(self) -> bool:
        """Initialize eSpeak NG TTS engine"""
        try:
            # Check if espeak-ng is available
            process = await asyncio.create_subprocess_exec(
                "espeak-ng", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.warning("eSpeak NG not found, trying espeak")
                return await self._try_espeak_fallback()
            
            # Get available voices
            await self._load_voices()
            logger.info("eSpeak NG initialized successfully", voices=len(self.available_voices))
            return True
            
        except Exception as e:
            logger.error("Failed to initialize eSpeak NG", error=str(e))
            return False
    
    async def _try_espeak_fallback(self) -> bool:
        """Try fallback to regular espeak"""
        try:
            process = await asyncio.create_subprocess_exec(
                "espeak", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                await self._load_voices(command="espeak")
                logger.info("eSpeak (fallback) initialized successfully", voices=len(self.available_voices))
                return True
            
            return False
            
        except Exception as e:
            logger.error("eSpeak fallback failed", error=str(e))
            return False
    
    async def _load_voices(self, command: str = "espeak-ng"):
        """Load available voices"""
        try:
            process = await asyncio.create_subprocess_exec(
                command, "--voices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                lines = stdout.decode().strip().split('\n')[1:]  # Skip header
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        lang_code = parts[1]
                        voice_name = parts[3]
                        self.available_voices[lang_code] = {
                            "name": voice_name,
                            "language": lang_code,
                            "command": command
                        }
            
        except Exception as e:
            logger.error("Failed to load eSpeak voices", error=str(e))
    
    async def synthesize(
        self, 
        text: str, 
        voice: str = "en",
        speed: float = 1.0,
        pitch: float = 1.0
    ) -> Tuple[Optional[np.ndarray], Optional[int]]:
        """Synthesize text using eSpeak NG"""
        try:
            # Map voice preferences to eSpeak voices
            voice_map = {
                "nova": "en+f3",      # Female voice
                "alloy": "en",        # Default male
                "echo": "en+m1",      # Male voice 1
                "fable": "en+f1",     # Female voice 1
                "onyx": "en+m2",      # Male voice 2
                "shimmer": "en+f2"    # Female voice 2
            }
            
            espeak_voice = voice_map.get(voice, voice)
            
            # Use available voice or fallback
            if espeak_voice not in self.available_voices and voice in self.available_voices:
                espeak_voice = voice
            elif espeak_voice not in self.available_voices:
                espeak_voice = self.default_voice
            
            # Get command (espeak-ng or espeak)
            command = self.available_voices.get(espeak_voice, {}).get("command", "espeak-ng")
            
            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # Build command
                cmd = [
                    command,
                    "-v", espeak_voice,
                    "-w", temp_path,
                    "-s", str(int(175 * speed)),  # Speed in words per minute
                    "-p", str(int(50 + (pitch - 1.0) * 50)),  # Pitch adjustment
                    text
                ]
                
                # Run eSpeak
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error("eSpeak synthesis failed", 
                               stderr=stderr.decode(), 
                               returncode=process.returncode)
                    return None, None
                
                # Read generated audio
                if os.path.exists(temp_path):
                    audio_data, sample_rate = sf.read(temp_path)
                    return audio_data, sample_rate
                else:
                    logger.error("eSpeak did not generate audio file")
                    return None, None
                    
            finally:
                # Clean up
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error("eSpeak synthesis error", error=str(e))
            return None, None
    
    def get_available_voices(self) -> dict:
        """Get available voices"""
        return self.available_voices.copy()
    
    def get_supported_languages(self) -> List[str]:
        """Get supported languages"""
        return list(self.available_voices.keys())
    
    async def health_check(self) -> dict:
        """Check health of eSpeak TTS"""
        try:
            # Try espeak-ng first
            process = await asyncio.create_subprocess_exec(
                "espeak-ng", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                version = stdout.decode().strip().split('\n')[0]
                return {
                    "status": "healthy",
                    "engine": "espeak-ng",
                    "version": version,
                    "available_voices": len(self.available_voices),
                    "voices": list(self.available_voices.keys())
                }
            
            # Try regular espeak
            process = await asyncio.create_subprocess_exec(
                "espeak", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                version = stdout.decode().strip().split('\n')[0]
                return {
                    "status": "healthy",
                    "engine": "espeak",
                    "version": version,
                    "available_voices": len(self.available_voices),
                    "voices": list(self.available_voices.keys())
                }
            
            return {
                "status": "unhealthy",
                "error": "Neither espeak-ng nor espeak available"
            }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
