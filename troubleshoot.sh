#!/bin/bash

echo "🔧 EKS Security Health Agent - Troubleshooting"
echo "=============================================="

# Check deployment status
echo "📊 Deployment Status:"
kubectl get pods -n security-agent -o wide

echo ""
echo "📋 Recent Events:"
kubectl get events -n security-agent --sort-by='.lastTimestamp' | tail -10

echo ""
echo "🔍 Service Account Permissions:"
echo "  Pods: $(kubectl auth can-i get pods --as=system:serviceaccount:security-agent:security-agent)"
echo "  ArgoCD Apps: $(kubectl auth can-i list applications.argoproj.io --as=system:serviceaccount:security-agent:security-agent)"
echo "  Gatekeeper: $(kubectl auth can-i list constrainttemplates.templates.gatekeeper.sh --as=system:serviceaccount:security-agent:security-agent)"

echo ""
echo "📈 Resource Usage:"
kubectl top pods -n security-agent 2>/dev/null || echo "  Metrics server not available"

echo ""
echo "🔄 Recent Jobs:"
kubectl get jobs -n security-agent

echo ""
echo "📝 Latest Logs (last 20 lines):"
kubectl logs -l app=eks-security-agent -n security-agent --tail=20

echo ""
echo "🏥 Health Check:"
POD=$(kubectl get pods -n security-agent -l app=eks-security-agent -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -n "$POD" ]]; then
    echo "  Testing Kubernetes API connectivity..."
    kubectl exec $POD -n security-agent -- python -c "from kubernetes import client, config; config.load_incluster_config(); print('✅ API connectivity OK')" 2>/dev/null || echo "❌ API connectivity failed"
else
    echo "❌ No running pods found"
fi

echo ""
echo "🔧 Quick Fixes:"
echo "  Restart deployment: kubectl rollout restart deployment/eks-security-agent -n security-agent"
echo "  Force new audit: make run-audit"
echo "  View full logs: kubectl logs deployment/eks-security-agent -n security-agent"
echo "  Clean and redeploy: make clean && make full-deploy"
