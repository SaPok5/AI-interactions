"""Piper TTS engine implementation - Fast neural TTS"""

import asyncio
import os
import subprocess
import tempfile
import json
import urllib.request
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import soundfile as sf
import structlog

logger = structlog.get_logger(__name__)

class PiperTTS:
    """Piper TTS engine for fast neural text-to-speech synthesis"""
    
    def __init__(self, models_path: str = "/app/data/models/piper"):
        self.models_path = Path(models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
        self.available_models = {}
        self.loaded_models = {}
        
        # Model configurations
        self.model_configs = {
            "en_US-lessac-medium": {
                "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
                "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
                "language": "en",
                "quality": "medium",
                "speaker": "lessac"
            },
            "en_US-amy-medium": {
                "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
                "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
                "language": "en",
                "quality": "medium",
                "speaker": "amy"
            },
            "en_US-ryan-high": {
                "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx",
                "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/high/en_US-ryan-high.onnx.json",
                "language": "en",
                "quality": "high",
                "speaker": "ryan"
            }
        }
        
    async def initialize(self):
        """Initialize Piper TTS engine"""
        try:
            # Check if piper is available
            result = await asyncio.create_subprocess_exec(
                "piper", "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
            if result.returncode != 0:
                logger.warning("Piper TTS not found in PATH, trying alternative methods")
                return False
            
            # Download default model if not exists
            await self.ensure_model_available("en_US-lessac-medium")
            logger.info("Piper TTS engine initialized successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to initialize Piper TTS", error=str(e))
            return False
    
    async def ensure_model_available(self, model_name: str) -> bool:
        """Ensure a model is downloaded and available"""
        if model_name not in self.model_configs:
            logger.error("Unknown model", model=model_name)
            return False
        
        model_path = self.models_path / f"{model_name}.onnx"
        config_path = self.models_path / f"{model_name}.onnx.json"
        
        # Check if model files exist
        if model_path.exists() and config_path.exists():
            self.available_models[model_name] = {
                "model_path": str(model_path),
                "config_path": str(config_path),
                **self.model_configs[model_name]
            }
            return True
        
        # Download model files
        try:
            logger.info("Downloading Piper model", model=model_name)
            config = self.model_configs[model_name]
            
            # Download model
            await self._download_file(config["url"], model_path)
            # Download config
            await self._download_file(config["config_url"], config_path)
            
            self.available_models[model_name] = {
                "model_path": str(model_path),
                "config_path": str(config_path),
                **config
            }
            
            logger.info("Model downloaded successfully", model=model_name)
            return True
            
        except Exception as e:
            logger.error("Failed to download model", model=model_name, error=str(e))
            return False
    
    async def _download_file(self, url: str, path: Path):
        """Download a file from URL"""
        def download():
            urllib.request.urlretrieve(url, path)
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, download)
    
    async def synthesize(
        self, 
        text: str, 
        model_name: str = "en_US-lessac-medium",
        speed: float = 1.0
    ) -> Tuple[Optional[np.ndarray], Optional[int]]:
        """Synthesize text using Piper TTS"""
        try:
            # Ensure model is available
            if not await self.ensure_model_available(model_name):
                logger.error("Model not available", model=model_name)
                return None, None
            
            model_info = self.available_models[model_name]
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as text_file:
                text_file.write(text)
                text_file_path = text_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as audio_file:
                audio_file_path = audio_file.name
            
            try:
                # Build piper command
                cmd = [
                    "piper",
                    "--model", model_info["model_path"],
                    "--config", model_info["config_path"],
                    "--output_file", audio_file_path
                ]
                
                # Add speed control if supported
                if speed != 1.0:
                    cmd.extend(["--length_scale", str(1.0 / speed)])
                
                # Run piper
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate(input=text.encode())
                
                if process.returncode != 0:
                    logger.error("Piper synthesis failed", 
                               stderr=stderr.decode(), 
                               returncode=process.returncode)
                    return None, None
                
                # Read generated audio
                if os.path.exists(audio_file_path):
                    audio_data, sample_rate = sf.read(audio_file_path)
                    return audio_data, sample_rate
                else:
                    logger.error("Piper did not generate audio file")
                    return None, None
                    
            finally:
                # Clean up temporary files
                try:
                    os.unlink(text_file_path)
                    os.unlink(audio_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error("Piper synthesis error", error=str(e))
            return None, None
    
    def get_available_models(self) -> dict:
        """Get list of available models"""
        return self.available_models.copy()
    
    def get_supported_languages(self) -> list:
        """Get list of supported languages"""
        languages = set()
        for model_config in self.model_configs.values():
            languages.add(model_config["language"])
        return list(languages)
    
    async def health_check(self) -> dict:
        """Check health of Piper TTS"""
        try:
            # Check if piper is available
            process = await asyncio.create_subprocess_exec(
                "piper", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                version = stdout.decode().strip()
                return {
                    "status": "healthy",
                    "version": version,
                    "available_models": len(self.available_models),
                    "models": list(self.available_models.keys())
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "Piper not available"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
