# EKS Security Health Agent

A comprehensive security compliance monitoring agent for Amazon EKS clusters that validates Gatekeeper policies, detects configuration drift, and provides actionable security insights.

## 🎯 Project Features

### **Core Security Validation**
- **Gatekeeper Policy Monitoring** - Real-time validation of OPA Gatekeeper constraints
- **Configuration Drift Detection** - Monitors ArgoCD sync status for policy drift
- **Critical Security Checks** - Validates privileged containers, root users, resource limits
- **Network Policy Validation** - Ensures proper network isolation
- **Security Health Scoring** - Calculates 0-100 security posture score

### **GitOps Integration**
- **ArgoCD Sync Monitoring** - Detects when policies drift from Git state
- **Policy Baseline Validation** - Uses Git-deployed policies as security baseline
- **Drift Alerting** - Identifies configuration inconsistencies

### **Intelligent Reporting**
- **Adaptive Scoring** - Weights violations by severity (Critical: -20, High: -10, Medium: -5)
- **Trend Analysis** - Tracks security posture over time
- **Actionable Insights** - Provides specific remediation recommendations
- **JSON Reports** - Machine-readable audit results

### **Production Ready**
- **Kubernetes Native** - Runs as scheduled CronJobs
- **RBAC Secured** - Minimal required permissions
- **Container Hardened** - Non-root user, read-only filesystem
- **Resource Efficient** - No idle containers, job-based execution

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   ArgoCD Apps   │    │  Gatekeeper OPA  │    │  EKS Workloads  │
│   (Git Sync)    │    │   Constraints    │    │   (Pods/Deps)   │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  EKS Security Agent     │
                    │  ┌─────────────────────┐│
                    │  │ • Drift Detection   ││
                    │  │ • Policy Validation ││
                    │  │ • Security Scoring  ││
                    │  │ • Report Generation ││
                    │  └─────────────────────┘│
                    └─────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Security Reports      │
                    │   (JSON + Logs)         │
                    └─────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Docker
- Minikube (running)
- kubectl (configured)
- Python 3.11+ (for local development)

### One-Command Setup
```bash
./quick-start.sh
```

### Manual Setup
```bash
# Deploy everything
make full-deploy

# Run immediate audit
make run-audit

# View results
make logs
```

## 📋 Step-by-Step Testing Guide

### **Phase 1: Basic Deployment**

1. **Environment Setup**
   ```bash
   # Start minikube
   minikube start
   
   # Verify kubectl context
   kubectl config current-context  # Should show: minikube
   
   # Clone and navigate
   cd eks-security-agent
   ```

2. **Deploy Agent**
   ```bash
   # Full deployment
   make full-deploy
   
   # Verify deployment
   kubectl get cronjobs -n security-agent
   kubectl get jobs -n security-agent
   ```

3. **Run First Audit**
   ```bash
   # Execute audit
   make run-audit
   
   # Check results (wait 10 seconds)
   make logs
   ```

   **Expected Output:**
   ```
   🎯 Security Health Score: 75-85/100
   🔴 Critical Issues: 0
   🟠 High Issues: 0-2
   🟡 Medium Issues: 3-8
   📱 ArgoCD Drift Issues: 0 (not installed)
   🌐 Network Policy Issues: 2-5
   ```

### **Phase 2: Gatekeeper Integration**

4. **Install Gatekeeper**
   ```bash
   # Install Gatekeeper
   kubectl apply -f https://raw.githubusercontent.com/open-policy-agent/gatekeeper/release-3.14/deploy/gatekeeper.yaml
   
   # Wait for deployment
   kubectl wait --for=condition=available deployment/gatekeeper-controller-manager -n gatekeeper-system --timeout=300s
   ```

5. **Deploy Sample Policies**
   ```bash
   # Create constraint template
   cat <<EOF | kubectl apply -f -
   apiVersion: templates.gatekeeper.sh/v1beta1
   kind: ConstraintTemplate
   metadata:
     name: k8srequiredlabels
   spec:
     crd:
       spec:
         names:
           kind: K8sRequiredLabels
         validation:
           properties:
             labels:
               type: array
               items:
                 type: string
     targets:
       - target: admission.k8s.gatekeeper.sh
         rego: |
           package k8srequiredlabels
           violation[{"msg": msg}] {
             required := input.parameters.labels
             provided := input.review.object.metadata.labels
             missing := required[_]
             not provided[missing]
             msg := sprintf("Missing required label: %v", [missing])
           }
   EOF
   
   # Create constraint instance
   cat <<EOF | kubectl apply -f -
   apiVersion: constraints.gatekeeper.sh/v1beta1
   kind: K8sRequiredLabels
   metadata:
     name: must-have-app-label
   spec:
     match:
       kinds:
         - apiGroups: ["apps"]
           kinds: ["Deployment"]
     parameters:
       labels: ["app"]
   EOF
   ```

6. **Test Policy Validation**
   ```bash
   # Run audit with policies
   make run-audit
   make logs
   ```

   **Expected Output:**
   ```
   🔍 Found 1 constraint types
   🔒 Gatekeeper Violations: 0-5
   📋 Active Policies: 1
   ```

### **Phase 3: ArgoCD Integration**

7. **Install ArgoCD**
   ```bash
   # Install ArgoCD
   kubectl create namespace argocd
   kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
   
   # Wait for deployment
   kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s
   ```

8. **Create Sample ArgoCD Application**
   ```bash
   cat <<EOF | kubectl apply -f -
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: sample-app
     namespace: argocd
   spec:
     project: default
     source:
       repoURL: https://github.com/argoproj/argocd-example-apps.git
       targetRevision: HEAD
       path: guestbook
     destination:
       server: https://kubernetes.default.svc
       namespace: default
     syncPolicy:
       automated:
         prune: true
         selfHeal: true
   EOF
   ```

9. **Test Drift Detection**
   ```bash
   # Run audit with ArgoCD
   make run-audit
   make logs
   ```

   **Expected Output:**
   ```
   📱 ArgoCD Drift Issues: 0-1
   ```

### **Phase 4: Violation Testing**

10. **Create Violating Workload**
    ```bash
    # Deploy workload that violates policies
    cat <<EOF | kubectl apply -f -
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: bad-deployment
      namespace: default
    spec:
      replicas: 1
      selector:
        matchLabels:
          name: bad-pod
      template:
        metadata:
          labels:
            name: bad-pod
        spec:
          containers:
          - name: bad-container
            image: nginx
            securityContext:
              privileged: true
              runAsUser: 0
    EOF
    ```

11. **Verify Violation Detection**
    ```bash
    # Wait for policy evaluation
    sleep 30
    
    # Run audit
    make run-audit
    make logs
    ```

    **Expected Output:**
    ```
    🔴 Critical Issues: 1 (Privileged Container)
    🟠 High Issues: 1 (Container Running as Root)
    🔒 Gatekeeper Violations: 1 (Missing app label)
    🎯 Security Health Score: 45-55/100
    ```

### **Phase 5: Monitoring & Maintenance**

12. **Scheduled Audits**
    ```bash
    # Check CronJob schedule
    kubectl describe cronjob security-audit -n security-agent
    
    # View job history
    kubectl get jobs -n security-agent --sort-by=.metadata.creationTimestamp
    ```

13. **Troubleshooting**
    ```bash
    # Run diagnostics
    ./troubleshoot.sh
    
    # Check failed jobs
    kubectl get jobs -n security-agent --field-selector status.successful!=1
    ```

14. **Cleanup**
    ```bash
    # Remove test workloads
    kubectl delete deployment bad-deployment
    
    # Clean up agent (optional)
    make clean
    ```

## 📊 Security Health Scoring

| Score Range | Status | Description | Action Required |
|-------------|--------|-------------|-----------------|
| 90-100 | 🟢 **EXCELLENT** | Optimal security posture | Monitor regularly |
| 80-89 | 🟡 **VERY GOOD** | Minor improvements needed | Address medium issues |
| 70-79 | 🟠 **GOOD** | Some security gaps | Fix high priority issues |
| 60-69 | 🔴 **FAIR** | Multiple issues present | Immediate attention needed |
| 0-59 | ⚫ **POOR** | Critical security risks | Emergency remediation |

## 🔧 Configuration

### Environment Variables
- `AUDIT_INTERVAL_SECONDS` - Audit frequency (default: 21600 = 6 hours)
- `RUN_MODE` - `daemon` or `oneshot` (default: oneshot for CronJob)

### CronJob Schedule Examples
```bash
# Every hour
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"schedule":"0 * * * *"}}'

# Every 6 hours (default)
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"schedule":"0 */6 * * *"}}'

# Daily at 2 AM
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"schedule":"0 2 * * *"}}'
```

## 📁 Project Structure

```
eks-security-agent/
├── src/
│   └── security_agent.py          # Main agent implementation
├── tests/
│   └── test_security_agent.py     # Test suite
├── k8s/
│   ├── deployment.yaml            # Kubernetes deployment
│   └── cronjob.yaml               # Scheduled audit job
├── docker/
│   └── Dockerfile                 # Container definition
├── k8s-rbac.yaml                  # RBAC configuration
├── Makefile                       # Build automation
├── RUNBOOK.md                     # Operations guide
├── quick-start.sh                 # One-command setup
└── troubleshoot.sh                # Diagnostic tool
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests first (TDD approach)
4. Implement the feature
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.

---

**For detailed operational procedures, see [RUNBOOK.md](RUNBOOK.md)**
