# Egress Control Agent - Usage Guide

## 🚀 Quick Start

### 1. Test Locally (TDD First!)
```bash
# Run tests
make test

# Test agent locally with dry-run
DRY_RUN=true make run-local
```

### 2. Deploy to Cluster
```bash
# Build and deploy
make build
make deploy-rbac
make deploy

# Check status
make status
```

### 3. Create Tenant Policy
```bash
# Apply sample policy
make create-sample-policy

# Check generated NetworkPolicy
kubectl get networkpolicies -A
```

## 📋 Policy Configuration

### Basic CIDR Policy
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: egress-policy
  namespace: tenant-a
  labels:
    egress-controller: "managed"  # Required!
data:
  policy.json: |
    {
      "defaultAction": "deny",
      "allowedDestinations": [
        {
          "name": "onprem-database",
          "cidr": "10.1.100.0/24",
          "ports": [5432, 3306]
        }
      ]
    }
```

### AWS Service Policy
```yaml
data:
  policy.json: |
    {
      "defaultAction": "deny",
      "allowedDestinations": [
        {
          "name": "s3-access",
          "awsService": "s3",
          "regions": ["us-east-1", "us-west-2"],
          "ports": [443]
        },
        {
          "name": "rds-access", 
          "awsService": "rds",
          "regions": ["us-east-1"],
          "ports": [5432]
        }
      ]
    }
```

### Mixed Policy (CIDR + AWS Services)
```yaml
data:
  policy.json: |
    {
      "defaultAction": "deny",
      "allowedDestinations": [
        {
          "name": "s3-backup",
          "awsService": "s3",
          "regions": ["us-east-1"],
          "ports": [443]
        },
        {
          "name": "onprem-api",
          "cidr": "10.0.0.0/16", 
          "ports": [80, 443]
        },
        {
          "name": "partner-service",
          "cidr": "192.168.1.0/24",
          "ports": [8080]
        }
      ]
    }
```

## 🔧 Multi-Tenant Setup

### Per-Namespace Policies
```bash
# Tenant A - S3 + Internal DB
kubectl create configmap egress-policy \
  --from-literal=policy.json='{
    "defaultAction": "deny",
    "allowedDestinations": [
      {"name": "s3", "awsService": "s3", "regions": ["us-east-1"], "ports": [443]},
      {"name": "db", "cidr": "10.1.0.0/24", "ports": [5432]}
    ]
  }' \
  -n tenant-a
kubectl label configmap egress-policy egress-controller=managed -n tenant-a

# Tenant B - DynamoDB + Different Internal Network  
kubectl create configmap egress-policy \
  --from-literal=policy.json='{
    "defaultAction": "deny", 
    "allowedDestinations": [
      {"name": "dynamodb", "awsService": "dynamodb", "regions": ["us-east-1"], "ports": [443]},
      {"name": "internal", "cidr": "10.2.0.0/24", "ports": [80, 443]}
    ]
  }' \
  -n tenant-b
kubectl label configmap egress-policy egress-controller=managed -n tenant-b
```

## 🔍 Monitoring & Troubleshooting

### Check Agent Status
```bash
# View logs
make logs

# Check deployment
kubectl get pods -n egress-control

# Check generated policies
kubectl get networkpolicies -A -l managed-by=egress-agent
```

### Debug Policy Issues
```bash
# Describe NetworkPolicy
kubectl describe networkpolicy egress-policy-generated -n tenant-a

# Check ConfigMap
kubectl get configmap egress-policy -n tenant-a -o yaml

# Test connectivity (from pod)
kubectl exec -it <pod> -n tenant-a -- curl -v https://s3.amazonaws.com
```

### Common Issues

**1. Policy Not Applied**
```bash
# Check ConfigMap has correct label
kubectl get configmap egress-policy -n tenant-a --show-labels

# Should show: egress-controller=managed
```

**2. Invalid JSON**
```bash
# Validate JSON syntax
kubectl get configmap egress-policy -n tenant-a -o jsonpath='{.data.policy\.json}' | jq .
```

**3. AWS Service Resolution Failed**
```bash
# Check agent logs for AWS API errors
kubectl logs deployment/egress-agent -n egress-control | grep "AWS"
```

## 🛠️ Development Workflow

### TDD Cycle
```bash
# 1. Write failing test
# 2. Run tests
make test

# 3. Implement feature
# 4. Run tests again
make test

# 5. Refactor and repeat
```

### Local Development
```bash
# Run with different log levels
LOG_LEVEL=DEBUG make run-local

# Test against specific namespace
WATCH_NAMESPACE=tenant-a make run-local

# Dry run mode (no actual NetworkPolicy creation)
DRY_RUN=true make run-local
```

### Container Testing
```bash
# Build and test container
make build

# Run container locally
docker run --rm -v ~/.kube:/home/egress/.kube:ro \
  -e KUBECONFIG=/home/egress/.kube/config \
  -e DRY_RUN=true \
  egress-agent:latest
```

## 📊 Supported AWS Services

| Service | Code | Regions | Notes |
|---------|------|---------|-------|
| S3 | `s3` | All | Object storage |
| RDS | `rds` | All | Managed databases |
| DynamoDB | `dynamodb` | All | NoSQL database |
| Lambda | `lambda` | All | Serverless functions |
| ECS | `ecs` | All | Container service |
| EC2 | `ec2` | All | Virtual machines |

## 🔐 Security Considerations

### RBAC Permissions
The agent requires minimal permissions:
- **ConfigMaps**: `get`, `list`, `watch`
- **NetworkPolicies**: `get`, `list`, `create`, `update`, `patch`, `delete`

### Container Security
- Runs as non-root user (UID 1000)
- Read-only root filesystem
- No privileged escalation
- Drops all capabilities

### Network Isolation
- Generated NetworkPolicies are **deny-by-default**
- Only explicitly allowed destinations are permitted
- Policies are namespace-scoped for tenant isolation

## 🚀 Production Deployment

### High Availability
```yaml
# Update deployment for HA
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
```

### Resource Limits
```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi" 
    cpu: "200m"
```

### Monitoring
```bash
# Add Prometheus metrics endpoint
# Add health check endpoints
# Set up alerting on policy failures
```

## 🔄 Migration from Manual NetworkPolicies

1. **Audit existing policies**
2. **Convert to ConfigMap format**
3. **Deploy agent in dry-run mode**
4. **Validate generated policies**
5. **Switch to active mode**
6. **Remove manual policies**
