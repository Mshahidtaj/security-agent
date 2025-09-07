#!/bin/bash
set -e

echo "🚀 EKS Security Health Agent - Quick Start"
echo "=========================================="

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker."
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl."
    exit 1
fi

if ! command -v minikube &> /dev/null; then
    echo "❌ minikube not found. Please install minikube."
    exit 1
fi

# Check minikube status
echo "🔍 Checking minikube status..."
if ! minikube status &> /dev/null; then
    echo "⚠️  Minikube not running. Starting minikube..."
    minikube start
else
    echo "✅ Minikube is running"
fi

# Check kubectl context
CONTEXT=$(kubectl config current-context)
if [[ "$CONTEXT" != "minikube" ]]; then
    echo "⚠️  kubectl context is not minikube. Current: $CONTEXT"
    echo "   Switching to minikube context..."
    kubectl config use-context minikube
fi

echo "✅ Prerequisites check complete"

# Deploy the agent
echo ""
echo "🔧 Deploying EKS Security Health Agent..."
make setup-dev
make deploy

echo ""
echo "⏳ Waiting for deployment to be ready..."
kubectl wait --for=condition=available deployment/eks-security-agent -n security-agent --timeout=300s

echo ""
echo "🔍 Running initial security audit..."
make run-audit

echo ""
echo "⏳ Waiting for audit to complete..."
sleep 10

echo ""
echo "📊 Audit Results:"
make logs

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "📋 Quick Commands:"
echo "  make run-audit    - Run security audit"
echo "  make logs         - View audit logs"
echo "  make clean        - Clean up resources"
echo ""
echo "📖 For detailed operations, see RUNBOOK.md"
