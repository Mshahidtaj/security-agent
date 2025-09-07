.PHONY: test build deploy clean run-local

# Variables
IMAGE_NAME = eks-security-agent
IMAGE_TAG = latest
NAMESPACE = security-agent

# Test the application
test:
	@echo "Running tests..."
	python3 -m pytest tests/ -v

# Build Docker image
build:
	@echo "Building Docker image..."
	docker build -f docker/Dockerfile -t $(IMAGE_NAME):$(IMAGE_TAG) .

# Load image to minikube
load-minikube:
	@echo "Loading image to minikube..."
	minikube image load $(IMAGE_NAME):$(IMAGE_TAG)

# Deploy RBAC
deploy-rbac:
	@echo "Deploying RBAC..."
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f k8s-rbac.yaml

# Deploy to minikube
deploy: build load-minikube deploy-rbac
	@echo "Deploying to minikube..."
	kubectl apply -f k8s/

# Run locally for development
run-local:
	@echo "Running locally..."
	PYTHONPATH=src python3 src/security_agent.py

# Setup development environment
setup-dev:
	@echo "Setting up development environment..."
	pip3 install -r requirements.txt

# Full deployment pipeline
full-deploy: setup-dev test deploy
	@echo "Full deployment completed!"
	@echo "To run audit: make run-audit"
	@echo "To check logs: make logs"

# Run one-time audit job
run-audit:
	@echo "Running one-time security audit..."
	kubectl create job security-audit-$$(date +%s) --from=cronjob/security-audit -n $(NAMESPACE)

# Get audit logs
logs:
	@echo "Getting latest audit logs..."
	kubectl logs -l app=eks-security-agent -n $(NAMESPACE) --tail=100

# Clean up
clean:
	@echo "Cleaning up..."
	kubectl delete namespace $(NAMESPACE) --ignore-not-found=true
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) || true

# Check minikube status
check-minikube:
	@echo "Checking minikube status..."
	minikube status
	kubectl cluster-info
