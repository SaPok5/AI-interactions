#!/bin/bash

# AI Voice Assistant System Startup Script
# This script starts the entire system in the correct order

set -e

echo "🚀 Starting AI Voice Assistant System..."

# Check if Docker and Docker Compose are available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed or not in PATH"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose is not installed or not in PATH"
    exit 1
fi

# Generate SSL certificates if they don't exist
if [ ! -f "infra/nginx/ssl/nginx.crt" ]; then
    echo "🔐 Generating SSL certificates..."
    ./infra/nginx/ssl/generate_certs.sh
fi

# Start infrastructure services first
echo "📊 Starting infrastructure services..."
docker compose up -d postgres redis

# Wait for Redis to be ready
echo "⏳ Waiting for Redis..."
sleep 10

# Initialize Redis
echo "🔧 Initializing Redis..."
./scripts/init-redis-cluster.sh

# Start monitoring stack
echo "📈 Starting monitoring services..."
docker compose up -d prometheus alertmanager grafana jaeger

# Start core application services
echo "🎯 Starting application services..."
docker compose up -d auth speech intent rag tts llm orchestrator analytics

# Start gateway and nginx
echo "🌐 Starting gateway and load balancer..."
docker compose up -d gateway nginx

# Start demo application
echo "🎨 Starting demo application..."
docker compose up -d demo

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Run health checks
echo "🏥 Running health checks..."
python3 scripts/health-check.py

echo ""
echo "✅ System startup complete!"
echo ""
echo "🌐 Access points:"
echo "   • Demo App: http://localhost:8090 (HTTP) or https://localhost:8443 (HTTPS)"
echo "   • API Gateway: http://localhost:8080"
echo "   • Grafana: http://localhost:3000 (admin/admin)"
echo "   • Prometheus: http://localhost:9090"
echo "   • Jaeger: http://localhost:16686"
echo ""
echo "📊 To monitor system status:"
echo "   • Health check: python3 scripts/health-check.py"
echo "   • View logs: docker compose logs -f [service-name]"
echo "   • Stop system: docker compose down"
echo ""
