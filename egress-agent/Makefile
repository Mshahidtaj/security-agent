.PHONY: test build deploy clean run-local logs help webhook-build webhook-deploy

# Variables
IMAGE_NAME ?= egress-agent
WEBHOOK_IMAGE_NAME ?= egress-webhook
IMAGE_TAG ?= latest
NAMESPACE ?= egress-control
REGISTRY ?= your-registry

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

test: ## Run tests
	@echo "🧪 Running tests..."
	python3 -m pytest tests/ -v --tb=short

test-webhook: ## Run webhook tests only
	@echo "🧪 Running webhook tests..."
	python3 -m pytest tests/test_webhook_server.py -v --tb=short

test-all: ## Run all tests including webhook
	@echo "🧪 Running all tests..."
	python3 -m pytest tests/ -v --tb=short

test-watch: ## Run tests in watch mode
	@echo "🔄 Running tests in watch mode..."
	python3 -m pytest tests/ -v --tb=short -f

lint: ## Run linting
	@echo "🔍 Running linting..."
	python3 -m flake8 src/ tests/ --max-line-length=100 --ignore=E203,W503

run-local: ## Run agent locally (requires kubeconfig)
	@echo "🚀 Running agent locally..."
	cd src && python3 egress_agent.py

run-webhook-local: ## Run webhook server locally
	@echo "🚀 Running webhook server locally..."
	cd src && python3 webhook_server.py

build: ## Build Docker image
	@echo "🏗️  Building Docker image..."
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

webhook-build: ## Build webhook Docker image
	@echo "🏗️  Building webhook Docker image..."
	docker build -f webhook.Dockerfile -t $(WEBHOOK_IMAGE_NAME):$(IMAGE_TAG) .

build-all: build webhook-build ## Build both images

push: build ## Push Docker image to registry
	@echo "📤 Pushing image to registry..."
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

webhook-push: webhook-build ## Push webhook image to registry
	@echo "📤 Pushing webhook image to registry..."
	docker tag $(WEBHOOK_IMAGE_NAME):$(IMAGE_TAG) $(REGISTRY)/$(WEBHOOK_IMAGE_NAME):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(WEBHOOK_IMAGE_NAME):$(IMAGE_TAG)

push-all: push webhook-push ## Push both images

deploy: ## Deploy to Kubernetes
	@echo "🚀 Deploying to Kubernetes..."
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s/deployment.yaml -n $(NAMESPACE)

webhook-deploy: ## Deploy webhook to Kubernetes
	@echo "🚀 Deploying webhook to Kubernetes..."
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s/webhook-deployment.yaml -n $(NAMESPACE)

deploy-all: deploy-rbac deploy webhook-deploy ## Deploy everything

deploy-rbac: ## Deploy RBAC configuration
	@echo "🔐 Deploying RBAC..."
	kubectl apply -f k8s/rbac.yaml

generate-certs: ## Generate TLS certificates for webhook
	@echo "🔐 Generating certificates..."
	./scripts/generate-certs.sh $(NAMESPACE)

setup-webhook: ## Complete webhook setup
	@echo "🔧 Setting up webhook..."
	kubectl label namespace default egress-validation=enabled --overwrite
	kubectl apply -f k8s/webhook-config.yaml

webhook-full-deploy: webhook-build webhook-deploy generate-certs setup-webhook ## Full webhook deployment

logs: ## View agent logs
	@echo "📋 Viewing logs..."
	kubectl logs -f deployment/egress-agent -n $(NAMESPACE)

webhook-logs: ## View webhook logs
	@echo "📋 Viewing webhook logs..."
	kubectl logs -f deployment/egress-webhook -n $(NAMESPACE)

status: ## Check deployment status
	@echo "📊 Checking status..."
	kubectl get pods,deployments,configmaps,validatingadmissionwebhooks -n $(NAMESPACE)

clean: ## Clean up deployment
	@echo "🧹 Cleaning up..."
	kubectl delete validatingadmissionwebhook egress-policy-validator --ignore-not-found=true
	kubectl delete namespace $(NAMESPACE) --ignore-not-found=true

# Development targets
dev-setup: ## Set up development environment
	@echo "🛠️  Setting up development environment..."
	pip3 install -r requirements.txt
	pip3 install pytest flake8

create-sample-policy: ## Create sample policy ConfigMap
	@echo "📝 Creating sample policy..."
	kubectl label namespace default egress-validation=enabled --overwrite
	kubectl apply -f examples/sample-policy.yaml

test-policy: create-sample-policy ## Test with sample policy
	@echo "🧪 Testing with sample policy..."
	sleep 5
	kubectl get networkpolicies -A

validate-policies: ## Validate all egress policies are in place
	@echo "🔍 Validating egress policies..."
	./scripts/validate-policies.sh

test-egress: ## Test egress connectivity in default namespace
	@echo "🧪 Testing egress connectivity..."
	./scripts/test-egress.sh $(NAMESPACE)

test-egress-comprehensive: ## Run comprehensive egress policy tests
	@echo "🧪 Running comprehensive egress tests..."
	python3 src/policy_tester.py

test-webhook-validation: ## Test webhook validation with invalid policy
	@echo "🧪 Testing webhook validation..."
	@echo "This should fail with validation error:"
	-kubectl apply -f - <<< 'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: bad-policy\n  namespace: default\n  labels:\n    egress-controller: managed\ndata:\n  policy.json: "invalid-json"'

validate-all: validate-policies test-egress-comprehensive ## Run all validation tests

# Quick development cycle
dev: test lint run-local ## Run full development cycle
webhook-dev: test-webhook lint run-webhook-local ## Run webhook development cycle

# Production deployment
prod-deploy: test build-all push-all deploy-all ## Full production deployment
