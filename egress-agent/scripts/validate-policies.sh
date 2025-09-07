#!/bin/bash

set -e

echo "🔍 EGRESS POLICY VALIDATION"
echo "=========================="

# 1. Check ConfigMaps with egress policies
echo "📋 1. Checking egress policy ConfigMaps..."
CONFIGMAPS=$(kubectl get configmaps -A -l egress-controller=managed --no-headers 2>/dev/null || echo "")

if [ -z "$CONFIGMAPS" ]; then
  echo "   ❌ No egress policy ConfigMaps found"
  exit 1
else
  echo "$CONFIGMAPS" | while read namespace name rest; do
    echo "   ✅ $namespace/$name"
  done
fi

echo

# 2. Check generated NetworkPolicies
echo "📋 2. Checking generated NetworkPolicies..."
NETPOLS=$(kubectl get networkpolicies -A -l managed-by=egress-agent --no-headers 2>/dev/null || echo "")

if [ -z "$NETPOLS" ]; then
  echo "   ❌ No generated NetworkPolicies found"
else
  echo "$NETPOLS" | while read namespace name rest; do
    echo "   ✅ $namespace/$name"
  done
fi

echo

# 3. Check policy-configmap alignment
echo "📋 3. Checking ConfigMap → NetworkPolicy alignment..."
kubectl get configmaps -A -l egress-controller=managed --no-headers 2>/dev/null | while read namespace name rest; do
  if kubectl get networkpolicy egress-policy-generated -n $namespace >/dev/null 2>&1; then
    echo "   ✅ $namespace: ConfigMap → NetworkPolicy ✓"
  else
    echo "   ❌ $namespace: ConfigMap exists but no NetworkPolicy"
  fi
done

echo

# 4. Check webhook configuration
echo "📋 4. Checking webhook configuration..."
if kubectl get validatingadmissionwebhook egress-policy-validator >/dev/null 2>&1; then
  echo "   ✅ ValidatingAdmissionWebhook configured"
  
  # Check webhook service
  if kubectl get service egress-webhook -n egress-control >/dev/null 2>&1; then
    echo "   ✅ Webhook service exists"
  else
    echo "   ❌ Webhook service not found"
  fi
  
  # Check webhook pods
  WEBHOOK_PODS=$(kubectl get pods -n egress-control -l app=egress-webhook --no-headers 2>/dev/null || echo "")
  if [ -n "$WEBHOOK_PODS" ]; then
    echo "   ✅ Webhook pods running"
  else
    echo "   ❌ No webhook pods found"
  fi
else
  echo "   ❌ ValidatingAdmissionWebhook not configured"
fi

echo

# 5. Check namespace validation labels
echo "📋 5. Checking namespace validation labels..."
LABELED_NS=$(kubectl get namespaces -l egress-validation=enabled --no-headers 2>/dev/null || echo "")

if [ -z "$LABELED_NS" ]; then
  echo "   ⚠️  No namespaces labeled for egress validation"
  echo "   💡 Run: kubectl label namespace <namespace> egress-validation=enabled"
else
  echo "$LABELED_NS" | while read namespace rest; do
    echo "   ✅ $namespace (validation enabled)"
  done
fi

echo
echo "✨ Validation completed!"
echo
echo "💡 To test connectivity:"
echo "   ./scripts/test-egress.sh <namespace>"
echo
echo "💡 To run comprehensive tests:"
echo "   python3 src/policy_tester.py"
