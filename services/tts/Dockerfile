FROM python:3.11-slim

# Speed up and harden pip installs
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies including curl
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    wget \
    ffmpeg \
    libsndfile1 \
    libasound2 \
    espeak-ng \
    python3-dev \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create compatibility symlink if only libespeak-ng is present
RUN set -eux; \
    so_ng="/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1"; \
    so_legacy="/usr/lib/x86_64-linux-gnu/libespeak.so.1"; \
    if [ -f "$so_ng" ] && [ ! -f "$so_legacy" ]; then \
      ln -s "$so_ng" "$so_legacy"; \
    fi

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies first
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

# Install Piper TTS binary
RUN curl -L -o /tmp/piper.tar.gz "https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz" \
    && tar -xzf /tmp/piper.tar.gz -C /usr/local/bin/ --strip-components=1 \
    && chmod +x /usr/local/bin/piper \
    && rm /tmp/piper.tar.gz

# Copy application code
COPY app/ ./app/

# Create directories for audio storage and models
RUN mkdir -p /app/data/audio /app/data/models/piper /app/data/models/coqui

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8006

# Health check
HEALTHCHECK --interval=30s --timeout=60s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
