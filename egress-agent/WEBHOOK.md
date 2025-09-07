# Egress Policy Webhook Validation

**Validating Admission Webhook** that prevents invalid egress policies from being stored in the cluster.

## 🎯 What It Does

**Before Webhook:**
```bash
$ kubectl apply -f bad-policy.yaml
configmap/bad-policy created  # ❌ Invalid policy stored

$ kubectl logs egress-agent
ERROR: Policy validation failed: Invalid CIDR format
```

**With Webhook:**
```bash
$ kubectl apply -f bad-policy.yaml
error validating data: admission webhook "validate-egress-policy" denied the request: 
Policy validation failed: Invalid CIDR format: 10.1.0.0/99
```

## 🚀 Quick Setup

```bash
# Run tests first
make test-webhook

# Deploy webhook
make webhook-full-deploy

# Test validation
make test-webhook-validation
```

## 📋 Complete Setup Guide

### 1. Build and Deploy Webhook

```bash
# Build webhook image
make webhook-build

# Deploy webhook server
make webhook-deploy

# Generate TLS certificates
make generate-certs

# Configure admission webhook
make setup-webhook
```

### 2. Enable Validation for Namespaces

```bash
# Enable validation for specific namespaces
kubectl label namespace tenant-a egress-validation=enabled
kubectl label namespace tenant-b egress-validation=enabled

# Or enable for default namespace (testing)
kubectl label namespace default egress-validation=enabled
```

### 3. Test Validation

**Valid Policy (Should Succeed):**
```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: valid-policy
  namespace: default
  labels:
    egress-controller: managed
data:
  policy.json: |
    {
      "defaultAction": "deny",
      "allowedDestinations": [
        {
          "name": "s3-access",
          "awsService": "s3",
          "regions": ["us-east-1"],
          "ports": [443]
        }
      ]
    }
EOF
```

**Invalid Policy (Should Fail):**
```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: invalid-policy
  namespace: default
  labels:
    egress-controller: managed
data:
  policy.json: |
    {
      "defaultAction": "invalid-action",
      "allowedDestinations": [
        {
          "name": "bad-cidr",
          "cidr": "10.1.0.0/99",
          "ports": [443]
        }
      ]
    }
EOF
```

## 🔧 Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   kubectl       │    │  API Server      │    │  Webhook Server │
│   apply         │───▶│  (Admission      │───▶│  (Validation)   │
│                 │    │   Controller)    │    │                 │
└─────────────────┘    └─────────┬────────┘    └─────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   ConfigMap Storage     │
                    │   (Only if valid)       │
                    └─────────────────────────┘
```

## 🧪 Validation Rules

### JSON Structure Validation
```json
{
  "defaultAction": "deny|allow",           // Required
  "allowedDestinations": [                 // Required array
    {
      "name": "string",                    // Required
      "ports": [80, 443],                  // Required array
      "cidr": "10.0.0.0/16"               // Either cidr OR awsService
    },
    {
      "name": "string",                    // Required
      "ports": [443],                      // Required array  
      "awsService": "s3",                  // Either cidr OR awsService
      "regions": ["us-east-1"]             // Required with awsService
    }
  ]
}
```

### Validation Checks

| Check | Description | Example Error |
|-------|-------------|---------------|
| **JSON Syntax** | Valid JSON format | `Invalid JSON in policy.json: Expecting ',' delimiter` |
| **CIDR Format** | Valid IP/subnet | `Invalid CIDR format: 10.1.0.0/99` |
| **AWS Service** | Supported service | `Invalid AWS service: invalid-service` |
| **Required Fields** | All mandatory fields | `Missing required field: name` |
| **Mutual Exclusion** | Either CIDR or AWS service | `Cannot specify both 'cidr' and 'awsService'` |

## 🔐 Security Features

### TLS Configuration
- **Mutual TLS** between API server and webhook
- **Certificate rotation** supported
- **CA bundle validation**

### RBAC Integration
```yaml
# Webhook uses same ServiceAccount as agent
serviceAccountName: egress-agent
```

### Namespace Isolation
```yaml
# Only validates namespaces with label
namespaceSelector:
  matchLabels:
    egress-validation: "enabled"
```

## 🛠️ Development

### Local Testing
```bash
# Install dependencies
pip3 install flask

# Run webhook server locally (no TLS)
make run-webhook-local

# Test with curl
curl -X POST http://localhost:8443/validate \
  -H "Content-Type: application/json" \
  -d @test-admission-request.json
```

### Test Suite
```bash
# Run webhook-specific tests
make test-webhook

# Test admission response creation
python3 -c "
from src.webhook_server import create_admission_response
print(create_admission_response(True, 'Valid policy', 'test-123'))
"
```

### Debug Webhook Issues
```bash
# Check webhook logs
make webhook-logs

# Check admission webhook configuration
kubectl get validatingadmissionwebhook egress-policy-validator -o yaml

# Test webhook connectivity
kubectl run test-pod --image=curlimages/curl --rm -it -- \
  curl -k https://egress-webhook.egress-control.svc:443/health
```

## 📊 Monitoring

### Health Checks
```bash
# Health endpoint
curl https://webhook-service/health

# Readiness endpoint  
curl https://webhook-service/ready
```

### Metrics (Future Enhancement)
- Validation requests per second
- Validation success/failure rate
- Policy validation latency
- Invalid policy types

## 🚨 Troubleshooting

### Common Issues

**1. Certificate Problems**
```bash
# Regenerate certificates
make generate-certs

# Check certificate validity
kubectl get secret webhook-certs -n egress-control -o yaml
```

**2. Webhook Not Called**
```bash
# Check namespace labels
kubectl get namespace default --show-labels

# Should show: egress-validation=enabled
```

**3. Validation Always Passes**
```bash
# Check ConfigMap labels
kubectl get configmap policy-name --show-labels

# Should show: egress-controller=managed
```

**4. Webhook Server Not Ready**
```bash
# Check pod status
kubectl get pods -n egress-control -l app=egress-webhook

# Check service endpoints
kubectl get endpoints egress-webhook -n egress-control
```

### Failure Modes

| Failure Policy | Behavior | Use Case |
|----------------|----------|----------|
| `Fail` | Reject if webhook unavailable | **Production** (strict validation) |
| `Ignore` | Allow if webhook unavailable | **Development** (graceful degradation) |

## 🔄 Webhook Lifecycle

### Deployment
1. **Build** webhook image
2. **Deploy** webhook server
3. **Generate** TLS certificates
4. **Configure** ValidatingAdmissionWebhook
5. **Label** namespaces for validation

### Updates
1. **Update** webhook image
2. **Rolling deployment** (zero downtime)
3. **Certificate rotation** (if needed)

### Removal
```bash
# Clean removal
kubectl delete validatingadmissionwebhook egress-policy-validator
kubectl delete deployment egress-webhook -n egress-control
kubectl delete secret webhook-certs -n egress-control
```

## 🎯 Production Considerations

### High Availability
```yaml
spec:
  replicas: 2  # Multiple webhook instances
  strategy:
    type: RollingUpdate
```

### Performance
- **Timeout**: 10s default (configurable)
- **Concurrent requests**: Handled by Flask
- **Resource limits**: 128Mi memory, 100m CPU

### Monitoring
- **Liveness probe**: `/health` endpoint
- **Readiness probe**: `/ready` endpoint
- **Logging**: Structured JSON logs
