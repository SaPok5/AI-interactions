"""Voice management and configuration"""

import asyncio
from typing import Dict, Any, List, Optional
import structlog

from .config import settings
from .models import VoiceInfo

logger = structlog.get_logger(__name__)

class VoiceManager:
    """Manage available voices and voice configurations"""
    
    def __init__(self):
        self.available_voices = []
        self.voice_cache = {}
        
    async def load_voices(self):
        """Load available voices from all engines"""
        try:
            voices = []
            
            # Piper TTS voices
            if settings.enable_piper_tts:
                voices.extend(self._get_piper_voices())
            
            # Coqui TTS voices
            if settings.enable_coqui_tts:
                voices.extend(self._get_coqui_voices())
            
            # eSpeak NG voices
            if settings.enable_espeak_ng:
                voices.extend(self._get_espeak_voices())
            
            # pyttsx3 voices (optional)
            if settings.enable_pyttsx3:
                voices.extend(await self._get_pyttsx3_voices())
            else:
                logger.debug("Skipping pyttsx3 voice enumeration (disabled by config)")
            
            self.available_voices = voices
            logger.info("Loaded voices", count=len(voices))
            
        except Exception as e:
            logger.error("Failed to load voices", error=str(e))
            # Set default voices as fallback
            self.available_voices = self._get_default_voices()
    
    def _get_piper_voices(self) -> List[VoiceInfo]:
        """Get Piper TTS voices"""
        return [
            VoiceInfo(
                voice_id="en_US-lessac-medium",
                name="Lessac (Medium)",
                language="en",
                gender="male",
                age="adult",
                style="clear",
                engine="piper",
                neural=True,
                sample_rate=22050
            ),
            VoiceInfo(
                voice_id="en_US-amy-medium",
                name="Amy (Medium)",
                language="en",
                gender="female",
                age="adult",
                style="friendly",
                engine="piper",
                neural=True,
                sample_rate=22050
            ),
            VoiceInfo(
                voice_id="en_US-ryan-high",
                name="Ryan (High)",
                language="en",
                gender="male",
                age="adult",
                style="professional",
                engine="piper",
                neural=True,
                sample_rate=22050
            )
        ]
    
    def _get_coqui_voices(self) -> List[VoiceInfo]:
        """Get Coqui TTS voices"""
        return [
            VoiceInfo(
                voice_id="coqui_ljspeech",
                name="LJSpeech",
                language="en",
                gender="female",
                age="adult",
                style="neutral",
                engine="coqui",
                neural=True,
                sample_rate=22050
            )
        ]
    
    def _get_espeak_voices(self) -> List[VoiceInfo]:
        """Get eSpeak NG voices"""
        return [
            # English voices
            VoiceInfo(
                voice_id="en",
                name="English (Default)",
                language="en",
                gender="male",
                age="adult",
                style="robotic",
                engine="espeak",
                neural=False,
                sample_rate=22050
            ),
            VoiceInfo(
                voice_id="en+f3",
                name="English (Female)",
                language="en",
                gender="female",
                age="adult",
                style="robotic",
                engine="espeak",
                neural=False,
                sample_rate=22050
            ),
            VoiceInfo(
                voice_id="en+m1",
                name="English (Male 1)",
                language="en",
                gender="male",
                age="adult",
                style="robotic",
                engine="espeak",
                neural=False,
                sample_rate=22050
            ),
            # Other languages
            VoiceInfo(
                voice_id="es",
                name="Spanish",
                language="es",
                gender="male",
                age="adult",
                style="robotic",
                engine="espeak",
                neural=False,
                sample_rate=22050
            ),
            VoiceInfo(
                voice_id="fr",
                name="French",
                language="fr",
                gender="male",
                age="adult",
                style="robotic",
                engine="espeak",
                neural=False,
                sample_rate=22050
            ),
            VoiceInfo(
                voice_id="de",
                name="German",
                language="de",
                gender="male",
                age="adult",
                style="robotic",
                engine="espeak",
                neural=False,
                sample_rate=22050
            )
        ]
    
    
    async def _get_pyttsx3_voices(self) -> List[VoiceInfo]:
        """Get pyttsx3 system voices"""
        voices = []
        
        try:
            import pyttsx3
            engine = pyttsx3.init()
            
            if engine:
                system_voices = engine.getProperty('voices')
                
                for i, voice in enumerate(system_voices):
                    # Extract gender from voice name/id
                    gender = "female" if any(term in voice.name.lower() for term in ["female", "woman", "zira", "hazel", "femme"]) else "male"
                    
                    voices.append(VoiceInfo(
                        voice_id=f"pyttsx3_{i}",
                        name=voice.name,
                        language="en",  # pyttsx3 is primarily English
                        gender=gender,
                        age="adult",
                        style="system",
                        engine="pyttsx3",
                        neural=False,
                        sample_rate=22050
                    ))
                
                engine.stop()
        
        except Exception as e:
            logger.warning("Failed to get pyttsx3 voices", error=str(e))
        
        return voices
    
    def _get_default_voices(self) -> List[VoiceInfo]:
        """Get default fallback voices"""
        return [
            VoiceInfo(
                voice_id="default",
                name="Default",
                language="en",
                gender="neutral",
                age="adult",
                style="neutral",
                engine="piper",
                neural=True,
                sample_rate=22050
            )
        ]
    
    async def get_available_voices(self) -> List[VoiceInfo]:
        """Get all available voices"""
        return self.available_voices
    
    async def get_voices_by_language(self, language: str) -> List[VoiceInfo]:
        """Get voices for specific language"""
        return [
            voice for voice in self.available_voices
            if voice.language.startswith(language) or voice.language == language
        ]
    
    async def get_voice_by_id(self, voice_id: str) -> Optional[VoiceInfo]:
        """Get voice by ID"""
        for voice in self.available_voices:
            if voice.voice_id == voice_id:
                return voice
        return None
    
    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages"""
        languages = set()
        for voice in self.available_voices:
            languages.add(voice.language)
        return sorted(list(languages))
    
    def get_voices_by_gender(self, gender: str) -> List[VoiceInfo]:
        """Get voices by gender"""
        return [
            voice for voice in self.available_voices
            if voice.gender == gender
        ]
    
    def get_neural_voices(self) -> List[VoiceInfo]:
        """Get neural/AI voices"""
        return [
            voice for voice in self.available_voices
            if voice.neural
        ]
    
    def get_recommended_voice(self, language: str, gender: Optional[str] = None) -> VoiceInfo:
        """Get recommended voice for language and gender"""
        # Filter by language
        language_voices = [
            voice for voice in self.available_voices
            if voice.language.startswith(language)
        ]
        
        if not language_voices:
            # Fallback to default
            return self.available_voices[0] if self.available_voices else self._get_default_voices()[0]
        
        # Filter by gender if specified
        if gender:
            gender_voices = [voice for voice in language_voices if voice.gender == gender]
            if gender_voices:
                language_voices = gender_voices
        
        # Prefer neural voices
        neural_voices = [voice for voice in language_voices if voice.neural]
        if neural_voices:
            return neural_voices[0]
        
        # Return first available
        return language_voices[0]
