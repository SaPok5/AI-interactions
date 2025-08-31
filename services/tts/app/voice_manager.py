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
            
            # Coqui TTS voices
            if settings.enable_neural_voices:
                voices.extend(self._get_coqui_voices())
            
            # Edge TTS voices
            voices.extend(self._get_edge_voices())
            
            # gTTS voices (language-based)
            voices.extend(self._get_gtts_voices())
            
            # pyttsx3 voices (optional)
            if settings.enable_pyttsx3_voices:
                voices.extend(await self._get_pyttsx3_voices())
            else:
                logger.debug("Skipping pyttsx3 voice enumeration (disabled by config)")
            
            self.available_voices = voices
            logger.info("Loaded voices", count=len(voices))
            
        except Exception as e:
            logger.error("Failed to load voices", error=str(e))
            # Set default voices as fallback
            self.available_voices = self._get_default_voices()
    
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
            ),
            VoiceInfo(
                voice_id="coqui_vctk",
                name="VCTK",
                language="en",
                gender="mixed",
                age="adult",
                style="neutral",
                engine="coqui",
                neural=True,
                sample_rate=22050
            )
        ]
    
    def _get_edge_voices(self) -> List[VoiceInfo]:
        """Get Edge TTS voices"""
        return [
            # English voices
            VoiceInfo(
                voice_id="en-US-AriaNeural",
                name="Aria",
                language="en",
                gender="female",
                age="adult",
                style="friendly",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            VoiceInfo(
                voice_id="en-US-GuyNeural",
                name="Guy",
                language="en",
                gender="male",
                age="adult",
                style="professional",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            VoiceInfo(
                voice_id="en-GB-SoniaNeural",
                name="Sonia",
                language="en-GB",
                gender="female",
                age="adult",
                style="british",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Spanish voices
            VoiceInfo(
                voice_id="es-ES-ElviraNeural",
                name="Elvira",
                language="es",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            VoiceInfo(
                voice_id="es-MX-DaliaNeural",
                name="Dalia",
                language="es-MX",
                gender="female",
                age="adult",
                style="mexican",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # French voices
            VoiceInfo(
                voice_id="fr-FR-DeniseNeural",
                name="Denise",
                language="fr",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # German voices
            VoiceInfo(
                voice_id="de-DE-KatjaNeural",
                name="Katja",
                language="de",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Italian voices
            VoiceInfo(
                voice_id="it-IT-ElsaNeural",
                name="Elsa",
                language="it",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Portuguese voices
            VoiceInfo(
                voice_id="pt-BR-FranciscaNeural",
                name="Francisca",
                language="pt",
                gender="female",
                age="adult",
                style="brazilian",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Russian voices
            VoiceInfo(
                voice_id="ru-RU-SvetlanaNeural",
                name="Svetlana",
                language="ru",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Japanese voices
            VoiceInfo(
                voice_id="ja-JP-NanamiNeural",
                name="Nanami",
                language="ja",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Korean voices
            VoiceInfo(
                voice_id="ko-KR-SunHiNeural",
                name="SunHi",
                language="ko",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            ),
            # Chinese voices
            VoiceInfo(
                voice_id="zh-CN-XiaoxiaoNeural",
                name="Xiaoxiao",
                language="zh",
                gender="female",
                age="adult",
                style="neutral",
                engine="edge",
                neural=True,
                sample_rate=24000
            )
        ]
    
    def _get_gtts_voices(self) -> List[VoiceInfo]:
        """Get Google TTS voices (language-based)"""
        languages = [
            ("en", "English"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("de", "German"),
            ("it", "Italian"),
            ("pt", "Portuguese"),
            ("ru", "Russian"),
            ("ja", "Japanese"),
            ("ko", "Korean"),
            ("zh", "Chinese"),
            ("ar", "Arabic"),
            ("hi", "Hindi"),
            ("tr", "Turkish"),
            ("pl", "Polish"),
            ("nl", "Dutch"),
            ("sv", "Swedish"),
            ("da", "Danish"),
            ("no", "Norwegian"),
            ("fi", "Finnish")
        ]
        
        voices = []
        for lang_code, lang_name in languages:
            voices.append(VoiceInfo(
                voice_id=f"gtts_{lang_code}",
                name=f"Google {lang_name}",
                language=lang_code,
                gender="neutral",
                age="adult",
                style="neutral",
                engine="gtts",
                neural=False,
                sample_rate=24000
            ))
        
        return voices
    
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
                    gender = "female" if any(term in voice.name.lower() for term in ["female", "woman", "zira", "hazel"]) else "male"
                    
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
                engine="gtts",
                neural=False,
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
