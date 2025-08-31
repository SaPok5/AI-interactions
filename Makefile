# Enterprise Voice Assistant - Build Automation
# Makefile for development, testing, and deployment

.PHONY: help bootstrap dev-up dev-down test lint security-scan build deploy clean

# Default target
help: ## Show this help message
	@echo "Enterprise Voice Assistant - Build Commands"

# Development Environment
bootstrap: ## Bootstrap development environment
	@echo "🚀 Bootstrapping development environment..."
	@./scripts/bootstrap.sh
	@echo "✅ Environment ready!"

dev-up: ## Start development stack
	@echo "🔧 Starting development stack..."
	@docker compose up -d
	@echo "✅ Development stack running at http://localhost:8080"

dev-down: ## Stop development stack
	@echo "🛑 Stopping development stack..."
	@docker compose down
	@echo "✅ Development stack stopped"

dev-logs: ## Show development logs
	@docker compose logs -f

dev-shell: ## Open shell in development container
	@docker compose exec gateway bash

# Testing
test: ## Run all tests
	@echo "🧪 Running test suite..."
	@./scripts/test.sh
	@echo "✅ All tests passed!"

test-unit: ## Run unit tests
	@echo "🔬 Running unit tests..."
	@pytest tests/unit/ -v --cov=services --cov-report=html

test-integration: ## Run integration tests
	@echo "🔗 Running integration tests..."
	@pytest tests/integration/ -v

test-e2e: ## Run end-to-end tests
	@echo "🎭 Running E2E tests..."
	@pytest tests/e2e/ -v

test-load: ## Run load tests
	@echo "⚡ Running load tests..."
	@k6 run tests/load/voice-assistant-load.js

# Code Quality
lint: ## Run code linting
	@echo "🧹 Running code linting..."
	@ruff check services/ clients/ shared/
	@mypy services/ --strict
	@eslint clients/web/src --ext .ts,.tsx
	@echo "✅ Code quality checks passed!"

format: ## Format code
	@echo "🎨 Formatting code..."
	@ruff format services/ clients/ shared/
	@prettier --write "clients/web/src/**/*.{ts,tsx,json,css}"

security-scan: ## Run security scans
	@echo "🔒 Running security scans..."
	@bandit -r services/ -f json -o reports/security.json
	@safety check --json --output reports/safety.json
	@trivy fs --format json --output reports/trivy.json .
	@echo "✅ Security scans completed!"

# Build & Deploy
build: ## Build all services
	@echo "🏗️ Building all services..."
	@docker compose -f docker compose.prod.yml build
	@echo "✅ Build completed!"

build-push: ## Build and push images
	@echo "📦 Building and pushing images..."
	@./scripts/build-push.sh
	@echo "✅ Images pushed to registry!"

deploy-staging: ## Deploy to staging
	@echo "🚀 Deploying to staging..."
	@./scripts/deploy.sh staging
	@echo "✅ Staging deployment completed!"

deploy-prod: ## Deploy to production
	@echo "🚀 Deploying to production..."
	@./scripts/deploy.sh production
	@echo "✅ Production deployment completed!"

# Infrastructure
infra-plan: ## Plan infrastructure changes
	@echo "📋 Planning infrastructure changes..."
	@cd infra/terraform && terraform plan

infra-apply: ## Apply infrastructure changes
	@echo "🏗️ Applying infrastructure changes..."
	@cd infra/terraform && terraform apply

infra-destroy: ## Destroy infrastructure
	@echo "💥 Destroying infrastructure..."
	@cd infra/terraform && terraform destroy

# Monitoring & Observability
logs: ## View production logs
	@kubectl logs -f deployment/voice-assistant-gateway -n voice-assistant

metrics: ## Open metrics dashboard
	@open http://grafana.voice-assistant.local

traces: ## Open tracing dashboard
	@open http://jaeger.voice-assistant.local

# Database
db-migrate: ## Run database migrations
	@echo "🗄️ Running database migrations..."
	@alembic upgrade head

db-seed: ## Seed database with test data
	@echo "🌱 Seeding database..."
	@python scripts/seed-database.py

# ML Models
models-download: ## Download pre-trained models
	@echo "🤖 Downloading ML models..."
	@python scripts/download-models.py

models-train: ## Train custom models
	@echo "🎓 Training custom models..."
	@python tools/model-training/train.py

models-benchmark: ## Benchmark model performance
	@echo "⏱️ Benchmarking models..."
	@python tools/benchmarking/benchmark.py

# Demo & Documentation
demo: ## Run demo application
	@echo "🎬 Starting demo application..."
	@cd clients/demo && npm start
	@echo "✅ Demo running at http://localhost:3000"

docs: ## Generate documentation
	@echo "📚 Generating documentation..."
	@mkdocs build
	@echo "✅ Documentation available at docs/site/"

docs-serve: ## Serve documentation locally
	@mkdocs serve

# Utilities
clean: ## Clean up build artifacts
	@echo "🧹 Cleaning up..."
	@docker system prune -f
	@rm -rf build/ dist/ *.egg-info/
	@find . -type d -name __pycache__ -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@echo "✅ Cleanup completed!"

health-check: ## Check system health
	@echo "🏥 Checking system health..."
	@curl -f http://localhost:8080/health || exit 1
	@echo "✅ System is healthy!"

performance-test: ## Run performance benchmarks
	@echo "⚡ Running performance tests..."
	@python tools/benchmarking/performance-test.py

# Enterprise Features
compliance-check: ## Run compliance checks
	@echo "📋 Running compliance checks..."
	@python scripts/compliance-check.py

backup: ## Create system backup
	@echo "💾 Creating system backup..."
	@./scripts/backup.sh

restore: ## Restore from backup
	@echo "🔄 Restoring from backup..."
	@./scripts/restore.sh $(BACKUP_FILE)

# Development Helpers
install-hooks: ## Install git hooks
	@echo "🪝 Installing git hooks..."
	@pre-commit install

update-deps: ## Update dependencies
	@echo "📦 Updating dependencies..."
	@pip-compile requirements.in
	@npm update --prefix clients/web

generate-api: ## Generate API documentation
	@echo "📖 Generating API documentation..."
	@openapi-generator generate -i docs/api/openapi.yaml -g html2 -o docs/api/html/
