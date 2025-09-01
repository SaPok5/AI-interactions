# TTS Service - Free and Open Source Implementation

A complete Text-to-Speech service using only free and open source engines, designed for the AI interaction system.

## Features

### 🎯 **100% Free and Open Source**
- **Piper TTS** - Fast neural TTS with high-quality voices
- **Coqui TTS** - Advanced neural TTS with voice cloning capabilities  
- **eSpeak NG** - Lightweight formant synthesis for all languages
- **pyttsx3** - System TTS wrapper for platform voices

### 🚀 **Performance Optimized**
- Intelligent caching system
- Fallback engine support
- Concurrent synthesis handling
- Streaming audio support
- Memory-efficient processing

### 🌍 **Multi-Language Support**
- English (multiple voices and styles)
- Spanish, French, German, Italian
- Portuguese, Russian, Japanese
- Korean, Chinese, and more via eSpeak NG

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Voice Chat    │───▶│   TTS Service   │───▶│  Audio Storage  │
│     Client      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  TTS Engines    │
                    │                 │
                    │ • Piper TTS     │
                    │ • Coqui TTS     │
                    │ • eSpeak NG     │
                    │ • pyttsx3       │
                    └─────────────────┘
```

## Quick Start

### 1. Build and Run

```bash
# Build the service
docker build -t tts-service .

# Run with docker-compose (recommended)
docker-compose up tts

# Or run standalone
docker run -p 8006:8006 -v $(pwd)/data:/app/data tts-service
```

### 2. Test the Service

```bash
# Health check
curl http://localhost:8006/health

# Get available voices
curl http://localhost:8006/voices

# Synthesize text
curl -X POST http://localhost:8006/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello, this is a test of the TTS service",
    "voice": "alloy",
    "language": "en",
    "speed": 1.0
  }'
```

## TTS Engines

### 🎵 **Piper TTS** (Primary - Fastest)
- **Type**: Neural TTS
- **Quality**: High
- **Speed**: Very Fast (< 2 seconds)
- **Models**: 
  - `en_US-lessac-medium` - Clear male voice
  - `en_US-amy-medium` - Friendly female voice
  - `en_US-ryan-high` - Professional male voice
- **Use Case**: Real-time voice chat, interactive applications

### 🧠 **Coqui TTS** (High Quality)
- **Type**: Advanced Neural TTS
- **Quality**: Highest
- **Speed**: Moderate (3-10 seconds)
- **Models**: LJSpeech, VCTK
- **Use Case**: High-quality voice generation, content creation

### 🔊 **eSpeak NG** (Lightweight)
- **Type**: Formant synthesis
- **Quality**: Basic but clear
- **Speed**: Very Fast (< 1 second)
- **Languages**: 100+ languages supported
- **Use Case**: Fallback, multi-language support, low-resource environments

### 🖥️ **pyttsx3** (System)
- **Type**: System TTS wrapper
- **Quality**: Varies by system
- **Speed**: Fast
- **Voices**: Platform-dependent
- **Use Case**: System integration, platform-specific voices

## Configuration

### Environment Variables

```bash
# Engine Selection
DEFAULT_ENGINE=piper              # Primary engine
FALLBACK_ENGINE=coqui            # Fallback when primary fails

# Engine Enablement
ENABLE_PIPER_TTS=true
ENABLE_COQUI_TTS=true
ENABLE_ESPEAK_NG=true
ENABLE_PYTTSX3=true

# Model Configuration
DEFAULT_PIPER_MODEL=en_US-lessac-medium
DEFAULT_COQUI_MODEL=tts_models/en/ljspeech/tacotron2-DDC
AUTO_DOWNLOAD_MODELS=true

# Performance Tuning
PIPER_SYNTHESIS_TIMEOUT=30
COQUI_SYNTHESIS_TIMEOUT=90
MAX_CONCURRENT_SYNTHESES=10
```

### Voice Mapping

The service maps OpenAI-style voice names to appropriate engines:

```python
voice_mapping = {
    "nova": "en_US-amy-medium",      # Piper: Friendly female
    "alloy": "en_US-lessac-medium",  # Piper: Clear male  
    "echo": "en_US-ryan-high",       # Piper: Professional male
    "fable": "en_US-amy-medium",     # Piper: Friendly female
    "onyx": "en_US-ryan-high",       # Piper: Professional male
    "shimmer": "en_US-amy-medium"    # Piper: Friendly female
}
```

## API Endpoints

### POST `/synthesize`
Synthesize text to speech with caching.

```json
{
  "text": "Hello world",
  "voice": "alloy",
  "language": "en", 
  "speed": 1.0,
  "pitch": 1.0
}
```

### GET `/audio/{audio_id}`
Retrieve generated audio file.

### WebSocket `/stream`
Real-time TTS synthesis.

### GET `/voices`
List all available voices.

### GET `/health`
Service health check with engine status.

## Integration with Voice Chat

The TTS service integrates seamlessly with the voice chat client:

1. **Client Request**: Voice chat sends TTS request via Redis
2. **Engine Selection**: Service selects best available engine
3. **Synthesis**: Text converted to speech with caching
4. **Response**: Audio data sent back to client
5. **Playback**: Client plays audio with proper timing

### Redis Channels

- `tts_input` - Incoming TTS requests
- `tts_output` - Outgoing audio responses
- `orchestrator_responses` - AI responses for synthesis

## Performance Characteristics

| Engine | Quality | Speed | Memory | CPU | Use Case |
|--------|---------|-------|--------|-----|----------|
| Piper | High | Very Fast | Low | Low | Real-time chat |
| Coqui | Highest | Moderate | High | High | Quality content |
| eSpeak | Basic | Very Fast | Very Low | Very Low | Fallback |
| pyttsx3 | Variable | Fast | Low | Low | System integration |

## Troubleshooting

### Common Issues

1. **No audio generated**
   - Check engine initialization in logs
   - Verify model downloads completed
   - Test with different engines

2. **Slow synthesis**
   - Use Piper for faster results
   - Reduce text length
   - Check system resources

3. **Model download failures**
   - Check internet connectivity
   - Verify disk space
   - Check Hugging Face access

### Debug Commands

```bash
# Check engine status
curl http://localhost:8006/health

# Test specific engine
docker exec tts-container piper --help
docker exec tts-container espeak-ng --version

# View logs
docker logs tts-container -f

# Check model files
docker exec tts-container ls -la /app/data/models/piper/
```

## Development

### Adding New Engines

1. Create engine class in `app/engines/`
2. Implement required methods: `initialize()`, `synthesize()`, `health_check()`
3. Register in `tts_engine.py`
4. Add configuration options
5. Update voice manager

### Model Management

Models are automatically downloaded on first use:
- **Piper models**: Downloaded from Hugging Face
- **Coqui models**: Downloaded via TTS library
- **eSpeak voices**: Included with system package

## Security Considerations

- All engines run locally (no external API calls)
- Input text validation and sanitization
- File system access restricted to data directories
- No network dependencies for synthesis
- Audio files automatically cleaned up

## License

This implementation uses only open source components:
- **Piper TTS**: MIT License
- **Coqui TTS**: MPL 2.0 License  
- **eSpeak NG**: GPL v3 License
- **pyttsx3**: MPL 2.0 License

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all engines work correctly
5. Submit pull request

---

**Note**: This TTS service is designed to work completely offline with no external dependencies, making it perfect for privacy-conscious applications and environments with limited internet connectivity.
