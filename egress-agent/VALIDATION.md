# Egress Policy Validation Guide

## 🎯 How to Validate Egress Policies

### Quick Validation Commands

```bash
# 1. Check all policies are in place
make validate-policies

# 2. Test connectivity in specific namespace
make test-egress NAMESPACE=tenant-a

# 3. Run comprehensive tests
make test-egress-comprehensive

# 4. Run all validations
make validate-all
```

## 📋 Validation Checklist

### 1. Policy Configuration Check
```bash
# Check ConfigMaps exist
kubectl get configmaps -A -l egress-controller=managed

# Check NetworkPolicies generated
kubectl get networkpolicies -A -l managed-by=egress-agent

# Check webhook is configured
kubectl get validatingadmissionwebhook egress-policy-validator
```

### 2. Connectivity Testing

**Manual Test (Quick)**
```bash
# Test from a pod in the namespace
kubectl run test-pod --image=curlimages/curl --rm -it -- /bin/sh

# Inside pod, test allowed destinations
curl -v --connect-timeout 5 https://s3.amazonaws.com  # Should work if S3 allowed
curl -v --connect-timeout 3 http://10.1.0.1:80       # Should work if CIDR allowed

# Test blocked destinations  
curl -v --connect-timeout 3 http://8.8.8.8:53        # Should timeout/fail
curl -v --connect-timeout 3 http://httpbin.org:80    # Should timeout/fail
```

**Automated Test**
```bash
# Test specific namespace
./scripts/test-egress.sh tenant-a

# Expected output:
# ✅ Testing allowed destinations:
#   S3 (s3.amazonaws.com:443): ✅ ALLOWED
#   Internal (10.1.0.1:80): ✅ ALLOWED
# ❌ Testing blocked destinations:
#   Google DNS (8.8.8.8:53): ✅ BLOCKED
#   External HTTP (httpbin.org:80): ✅ BLOCKED
```

### 3. Comprehensive Validation

**Policy Tester (Advanced)**
```bash
python3 src/policy_tester.py

# Expected output:
# 🎯 EGRESS POLICY VALIDATION REPORT
# ========================================
# 📋 Namespace: tenant-a
#    Policy ConfigMap: ✅
#    NetworkPolicy: ✅  
#    Tests: 4/5 passed
# 📊 OVERALL SUMMARY
#    Success Rate: 80.0%
#    Status: 🟡 GOOD
```

## 🔍 What Each Validation Checks

### Configuration Validation
| Check | Purpose | Fix If Failed |
|-------|---------|---------------|
| **ConfigMap exists** | Policy defined | Create egress-policy ConfigMap |
| **NetworkPolicy exists** | Policy applied | Check agent logs, restart agent |
| **Webhook configured** | Validation active | Run `make setup-webhook` |
| **Namespace labeled** | Validation enabled | `kubectl label namespace <ns> egress-validation=enabled` |

### Connectivity Validation  
| Test | Expected | Meaning |
|------|----------|---------|
| **Allowed destinations** | ✅ ALLOWED | Policy permits traffic |
| **Blocked destinations** | ✅ BLOCKED | Policy denies traffic |
| **AWS services** | ✅ ALLOWED | Service CIDRs resolved correctly |
| **Internal networks** | ✅ ALLOWED | CIDR ranges work |

## 🚨 Troubleshooting Failed Validations

### ConfigMap Exists but No NetworkPolicy
```bash
# Check agent logs
kubectl logs deployment/egress-agent -n egress-control

# Common issues:
# - Invalid JSON in policy.json
# - Agent not running
# - RBAC permissions missing
```

### NetworkPolicy Exists but Traffic Not Blocked
```bash
# Check NetworkPolicy details
kubectl describe networkpolicy egress-policy-generated -n <namespace>

# Check CNI supports NetworkPolicy
kubectl get nodes -o wide

# Verify AWS VPC CNI version
kubectl describe daemonset aws-node -n kube-system
```

### Allowed Traffic is Blocked
```bash
# Check policy rules
kubectl get configmap egress-policy -n <namespace> -o yaml

# Check AWS service CIDR resolution
kubectl logs deployment/egress-agent -n egress-control | grep "AWS"

# Test DNS resolution
nslookup s3.amazonaws.com
```

### Webhook Not Validating
```bash
# Check webhook pods
kubectl get pods -n egress-control -l app=egress-webhook

# Check webhook logs
kubectl logs deployment/egress-webhook -n egress-control

# Test webhook directly
curl -k https://egress-webhook.egress-control.svc:443/health
```

## 📊 Validation Metrics

### Success Criteria
- **Configuration**: 100% (all policies have NetworkPolicies)
- **Allowed Traffic**: ≥90% (most allowed destinations work)
- **Blocked Traffic**: 100% (all blocked destinations fail)
- **Overall Score**: ≥85% for production readiness

### Performance Benchmarks
- **Policy Application**: <30 seconds after ConfigMap creation
- **Connectivity Test**: <5 seconds per destination
- **Webhook Response**: <1 second validation time

## 🔄 Continuous Validation

### Automated Testing (CI/CD)
```yaml
# Add to your pipeline
- name: Validate Egress Policies
  run: |
    make validate-all
    if [ $? -ne 0 ]; then
      echo "❌ Egress policy validation failed"
      exit 1
    fi
```

### Monitoring Integration
```bash
# Export metrics for Prometheus
python3 src/policy_tester.py --format=prometheus > /tmp/egress_metrics.prom

# Sample metrics:
# egress_policy_tests_total{namespace="tenant-a"} 5
# egress_policy_tests_passed{namespace="tenant-a"} 4
# egress_policy_success_rate{namespace="tenant-a"} 0.8
```

### Scheduled Validation
```yaml
# CronJob for regular validation
apiVersion: batch/v1
kind: CronJob
metadata:
  name: egress-policy-validator
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: validator
            image: egress-agent:latest
            command: ["python3", "src/policy_tester.py"]
```

## 💡 Best Practices

### Before Deployment
1. **Test policies locally** with dry-run mode
2. **Validate JSON syntax** before applying
3. **Check CIDR ranges** are correct
4. **Verify AWS service names** are supported

### After Deployment  
1. **Run validation immediately** after policy changes
2. **Monitor connectivity** from application pods
3. **Check agent logs** for errors
4. **Test webhook validation** with invalid policies

### Regular Maintenance
1. **Weekly validation runs** in production
2. **Update AWS service CIDRs** monthly
3. **Review blocked traffic** for false positives
4. **Audit policy changes** for compliance
