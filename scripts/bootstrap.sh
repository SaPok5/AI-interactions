#!/bin/bash
# Enterprise Voice Assistant - Bootstrap Script
# Sets up the complete development environment

set -e

echo "🚀 Enterprise Voice Assistant - Bootstrap"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.9+ first."
        exit 1
    fi
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed. Please install Node.js 18+ first."
        exit 1
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        print_error "Git is not installed. Please install Git first."
        exit 1
    fi
    
    print_success "All prerequisites are installed!"
}

# Create directory structure
create_directories() {
    print_status "Creating directory structure..."
    
    # Core directories
    mkdir -p services/{gateway,auth,speech,intent,orchestrator,rag,tts,llm,analytics,monitoring}
    mkdir -p clients/{web,mobile,sdk,demo}
    mkdir -p shared/{proto,models,utils,config}
    mkdir -p tests/{unit,integration,e2e,load,security,fixtures}
    mkdir -p data/{models,datasets,embeddings,configs}
    mkdir -p tools/{model-training,data-processing,benchmarking,deployment}
    mkdir -p infra/{terraform,kubernetes,helm,monitoring}
    mkdir -p docs/{architecture,api,deployment,security,compliance}
    mkdir -p scripts/{monitoring,deployment}
    mkdir -p .github/{workflows,ISSUE_TEMPLATE}
    
    print_success "Directory structure created!"
}

# Setup Python environment
setup_python() {
    print_status "Setting up Python environment..."
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Create requirements files
    cat > requirements.txt << EOF
# Core Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# Database & Cache
sqlalchemy==2.0.23
alembic==1.13.1
redis==5.0.1
asyncpg==0.29.0

# ML & AI
torch==2.1.1
transformers==4.36.2
sentence-transformers==2.2.2
onnxruntime==1.16.3
faster-whisper==0.10.0
TTS==0.22.0

# Audio Processing
librosa==0.10.1
soundfile==1.0.0
webrtcvad==2.0.10

# Vector Database
qdrant-client==1.7.0
chromadb==0.4.18

# Monitoring & Observability
prometheus-client==0.19.0
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
structlog==23.2.0

# Security
cryptography==41.0.8
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
httpx==0.25.2

# Development
black==23.11.0
ruff==0.1.7
mypy==1.7.1
pre-commit==3.6.0
EOF

    # Install dependencies
    pip install -r requirements.txt
    
    print_success "Python environment setup complete!"
}

# Setup Node.js environment
setup_nodejs() {
    print_status "Setting up Node.js environment..."
    
    # Create package.json for root
    cat > package.json << EOF
{
  "name": "enterprise-voice-assistant",
  "version": "1.0.0",
  "description": "Enterprise-grade multilingual voice assistant with speculative intelligence",
  "private": true,
  "workspaces": [
    "clients/*",
    "services/gateway"
  ],
  "scripts": {
    "dev": "docker compose up -d",
    "test": "npm run test --workspaces",
    "build": "npm run build --workspaces",
    "lint": "npm run lint --workspaces"
  },
  "devDependencies": {
    "@typescript-eslint/eslint-plugin": "^6.13.1",
    "@typescript-eslint/parser": "^6.13.1",
    "eslint": "^8.55.0",
    "prettier": "^3.1.0",
    "typescript": "^5.3.2"
  }
}
EOF

    # Install root dependencies
    npm install
    
    print_success "Node.js environment setup complete!"
}

# Download ML models
download_models() {
    print_status "Downloading ML models..."
    
    # Create model download script
    cat > scripts/download-models.py << 'EOF'
#!/usr/bin/env python3
"""Download pre-trained models for the voice assistant."""

import os
import requests
from pathlib import Path
from tqdm import tqdm

def download_file(url, filename):
    """Download a file with progress bar."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(filename, 'wb') as file, tqdm(
        desc=filename.name,
        total=total_size,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)
                bar.update(len(chunk))

def main():
    """Download all required models."""
    models_dir = Path("data/models")
    models_dir.mkdir(parents=True, exist_ok=True)
    
    # Model URLs (placeholder - replace with actual model URLs)
    models = {
        "whisper-small.bin": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
        "intent-classifier.onnx": "https://example.com/models/intent-classifier.onnx",
        "tts-model.pth": "https://example.com/models/tts-model.pth",
    }
    
    for filename, url in models.items():
        filepath = models_dir / filename
        if not filepath.exists():
            print(f"Downloading {filename}...")
            try:
                download_file(url, filepath)
                print(f"✅ Downloaded {filename}")
            except Exception as e:
                print(f"❌ Failed to download {filename}: {e}")
        else:
            print(f"⏭️  {filename} already exists")

if __name__ == "__main__":
    main()
EOF

    chmod +x scripts/download-models.py
    
    # Create placeholder model files for development
    mkdir -p data/models
    touch data/models/.gitkeep
    
    print_success "Model setup complete!"
}

# Setup Git hooks
setup_git_hooks() {
    print_status "Setting up Git hooks..."
    
    # Create pre-commit config
    cat > .pre-commit-config.yaml << EOF
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
  
  - repo: https://github.com/psf/black
    rev: 23.11.0
    hooks:
      - id: black
        language_version: python3
  
  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.7
    hooks:
      - id: ruff
        args: [--fix]
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
  
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.55.0
    hooks:
      - id: eslint
        files: \.(js|ts|tsx)$
        types: [file]
EOF

    # Install pre-commit hooks
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        pre-commit install
    fi
    
    print_success "Git hooks setup complete!"
}

# Create configuration files
create_configs() {
    print_status "Creating configuration files..."
    
    # Create environment file
    cat > .env.example << EOF
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/voice_assistant
REDIS_URL=redis://localhost:6379

# Security
JWT_SECRET=your-super-secret-jwt-key-change-in-production
ENCRYPTION_KEY=your-32-character-encryption-key

# External APIs
OPENAI_API_KEY=your-openai-api-key
GOOGLE_CLOUD_API_KEY=your-google-cloud-key

# Model Configuration
MODEL_PATH=./data/models
GPU_ENABLED=false

# Monitoring
PROMETHEUS_URL=http://localhost:9090
JAEGER_URL=http://localhost:14268

# Development
DEBUG=true
LOG_LEVEL=INFO
EOF

    cp .env.example .env
    
    # Create Docker ignore
    cat > .dockerignore << EOF
node_modules
npm-debug.log
.git
.gitignore
README.md
.env
.nyc_output
coverage
.vscode
.idea
*.log
venv/
__pycache__/
*.pyc
.pytest_cache/
EOF

    # Create gitignore
    cat > .gitignore << EOF
# Dependencies
node_modules/
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local
.env.production

# Logs
*.log
logs/

# Database
*.db
*.sqlite

# Models (too large for git)
data/models/*.bin
data/models/*.pth
data/models/*.onnx

# Build artifacts
build/
dist/
*.egg-info/

# Testing
.coverage
.pytest_cache/
coverage/

# OS
.DS_Store
Thumbs.db
EOF

    print_success "Configuration files created!"
}

# Setup monitoring
setup_monitoring() {
    print_status "Setting up monitoring configuration..."
    
    mkdir -p infra/monitoring
    
    # Prometheus config
    cat > infra/monitoring/prometheus.yml << EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

scrape_configs:
  - job_name: 'voice-assistant-gateway'
    static_configs:
      - targets: ['gateway:8080']
    metrics_path: /metrics
    scrape_interval: 5s

  - job_name: 'voice-assistant-services'
    static_configs:
      - targets: 
        - 'auth:8001'
        - 'speech:8002'
        - 'intent:8003'
        - 'orchestrator:8004'
        - 'rag:8005'
        - 'tts:8006'
        - 'llm:8007'
        - 'analytics:8008'
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']
EOF

    print_success "Monitoring setup complete!"
}

# Main execution
main() {
    echo
    print_status "Starting bootstrap process..."
    echo
    
    check_prerequisites
    create_directories
    setup_python
    setup_nodejs
    download_models
    setup_git_hooks
    create_configs
    setup_monitoring
    
    echo
    print_success "🎉 Bootstrap completed successfully!"
    echo
    print_status "Next steps:"
    echo "  1. Review and update .env file with your configurations"
    echo "  2. Run 'make dev-up' to start the development stack"
    echo "  3. Open http://localhost:8080 to access the API"
    echo "  4. Open http://localhost:3000 to access Grafana (admin/admin)"
    echo "  5. Open http://localhost:3001 to access the web client"
    echo
    print_status "For more information, see the README.md file"
    echo
}

# Run main function
main "$@"
