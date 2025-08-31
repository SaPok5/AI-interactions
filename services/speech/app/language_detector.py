"""Language detection for multilingual speech processing"""

import numpy as np
import structlog
from typing import Dict, List
from langdetect import detect, detect_langs, LangDetectException
import librosa

from .config import settings
from .models import LanguageResult

logger = structlog.get_logger(__name__)

class LanguageDetector:
    """Language detection for audio content"""
    
    def __init__(self):
        self.supported_languages = [
            "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh",
            "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi", "cs",
            "hu", "ro", "bg", "hr", "sk", "sl", "et", "lv", "lt", "mt",
            "ga", "cy", "eu", "ca", "gl", "is", "mk", "sq", "sr", "bs",
            "me", "hr", "sl", "sk", "cs", "hu", "ro", "bg", "el", "he",
            "fa", "ur", "bn", "ta", "te", "ml", "kn", "gu", "pa", "or",
            "as", "ne", "si", "my", "th", "lo", "km", "vi", "id", "ms",
            "tl", "jv", "su", "mg", "haw", "mi", "cy", "br", "co", "eo"
        ]
        
        # Language code mapping for Whisper compatibility
        self.whisper_lang_map = {
            "zh": "zh-cn",  # Chinese simplified
            "ja": "ja",     # Japanese
            "ko": "ko",     # Korean
            "ar": "ar",     # Arabic
            "hi": "hi",     # Hindi
            "tr": "tr",     # Turkish
            "ru": "ru",     # Russian
            "pt": "pt",     # Portuguese
            "es": "es",     # Spanish
            "fr": "fr",     # French
            "de": "de",     # German
            "it": "it",     # Italian
            "en": "en",     # English
        }
    
    def detect(self, audio_data: np.ndarray) -> LanguageResult:
        """Detect language from audio data"""
        try:
            # For audio-based detection, we'll use a simple approach
            # In production, you'd use a proper audio language detection model
            
            # Extract features that might indicate language
            # This is a simplified approach - real implementation would use
            # trained models like wav2vec2 or similar
            
            # For now, we'll use spectral features as a proxy
            spectral_features = self._extract_spectral_features(audio_data)
            
            # Simple heuristic-based detection
            detected_lang = self._heuristic_detection(spectral_features)
            
            return LanguageResult(
                language=detected_lang,
                confidence=0.8,  # Simplified confidence
                alternatives=[
                    {"en": 0.8},
                    {"es": 0.1},
                    {"fr": 0.1}
                ]
            )
            
        except Exception as e:
            logger.error("Language detection failed", error=str(e))
            # Default to English
            return LanguageResult(
                language="en",
                confidence=0.5,
                alternatives=[{"en": 0.5}]
            )
    
    def detect_from_text(self, text: str) -> LanguageResult:
        """Detect language from transcribed text"""
        try:
            if not text or len(text.strip()) < 3:
                return LanguageResult(
                    language="en",
                    confidence=0.5,
                    alternatives=[{"en": 0.5}]
                )
            
            # Use langdetect for text-based detection
            detected_langs = detect_langs(text)
            
            primary_lang = detected_langs[0]
            alternatives = [
                {lang.lang: lang.prob} 
                for lang in detected_langs[:3]
            ]
            
            return LanguageResult(
                language=primary_lang.lang,
                confidence=primary_lang.prob,
                alternatives=alternatives
            )
            
        except LangDetectException as e:
            logger.warning("Text language detection failed", error=str(e), text=text[:50])
            return LanguageResult(
                language="en",
                confidence=0.5,
                alternatives=[{"en": 0.5}]
            )
    
    def _extract_spectral_features(self, audio_data: np.ndarray) -> Dict[str, float]:
        """Extract spectral features from audio"""
        try:
            # Ensure we have enough data
            if len(audio_data) < 1024:
                return {"spectral_centroid": 0.0, "spectral_rolloff": 0.0}
            
            # Extract features using librosa
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=audio_data, sr=settings.sample_rate))
            spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=audio_data, sr=settings.sample_rate))
            zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(audio_data))
            
            return {
                "spectral_centroid": float(spectral_centroid),
                "spectral_rolloff": float(spectral_rolloff),
                "zero_crossing_rate": float(zero_crossing_rate)
            }
            
        except Exception as e:
            logger.error("Feature extraction failed", error=str(e))
            return {"spectral_centroid": 0.0, "spectral_rolloff": 0.0, "zero_crossing_rate": 0.0}
    
    def _heuristic_detection(self, features: Dict[str, float]) -> str:
        """Simple heuristic-based language detection"""
        # This is a very simplified approach
        # In production, you'd use trained models
        
        spectral_centroid = features.get("spectral_centroid", 0.0)
        
        # Simple rules based on spectral characteristics
        # Different languages have different spectral patterns
        if spectral_centroid > 2000:
            # Higher frequencies might indicate certain languages
            return "zh"  # Chinese
        elif spectral_centroid > 1500:
            return "ja"  # Japanese
        elif spectral_centroid > 1200:
            return "en"  # English
        elif spectral_centroid > 1000:
            return "es"  # Spanish
        else:
            return "en"  # Default to English
    
    def get_whisper_language_code(self, lang_code: str) -> str:
        """Convert language code to Whisper-compatible format"""
        return self.whisper_lang_map.get(lang_code, lang_code)
    
    def is_supported(self, lang_code: str) -> bool:
        """Check if language is supported"""
        return lang_code in self.supported_languages
    
    def get_language_name(self, lang_code: str) -> str:
        """Get human-readable language name"""
        lang_names = {
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi",
            "tr": "Turkish",
            "pl": "Polish",
            "nl": "Dutch",
            "sv": "Swedish",
            "da": "Danish",
            "no": "Norwegian",
            "fi": "Finnish",
            "cs": "Czech",
            "hu": "Hungarian",
            "ro": "Romanian",
            "bg": "Bulgarian",
            "hr": "Croatian",
            "sk": "Slovak",
            "sl": "Slovenian"
        }
        
        return lang_names.get(lang_code, lang_code.upper())
