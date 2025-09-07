# EKS Security Health Agent - Operations Runbook

## Quick Reference

| Command | Purpose |
|---------|---------|
| `make full-deploy` | Build and deploy everything |
| `make run-audit` | Run one-time security audit |
| `make logs` | View audit logs |
| `make clean` | Clean up all resources |
| `./troubleshoot.sh` | Run diagnostics |

## Architecture Overview

The agent runs as **Kubernetes CronJobs** and validates security compliance by:
- Monitoring Gatekeeper policy violations
- Detecting ArgoCD configuration drift
- Checking critical security configurations
- Generating actionable security reports

## Prerequisites

- Docker installed and running
- Minikube running (`minikube start`)
- kubectl configured for minikube
- Python 3.11+ (for local development)

## Initial Setup

### 1. Environment Verification
```bash
# Check minikube status
minikube status

# Verify kubectl context
kubectl config current-context  # Should show: minikube

# Check cluster info
kubectl cluster-info
```

### 2. Deploy Security Agent
```bash
cd eks-security-agent

# Complete deployment
make full-deploy

# Verify deployment
kubectl get all -n security-agent
```

## Daily Operations

### Security Audits

#### Run Immediate Audit
```bash
# Execute one-time audit
make run-audit

# Check job status
kubectl get jobs -n security-agent

# View results
make logs
```

#### Monitor Scheduled Audits
```bash
# Check CronJob status
kubectl get cronjobs -n security-agent

# View job history
kubectl get jobs -n security-agent --sort-by=.metadata.creationTimestamp

# Check recent job logs
kubectl logs -l job-name -n security-agent --tail=50
```

### Report Access

#### Get Latest Report
```bash
# Find latest completed job
LATEST_JOB=$(kubectl get jobs -n security-agent --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')

# Get pod from job
POD=$(kubectl get pods -n security-agent -l job-name=$LATEST_JOB -o jsonpath='{.items[0].metadata.name}')

# Copy report (if pod still exists)
kubectl cp security-agent/$POD:/tmp/security-health-*.json ./reports/
```

#### View Report Contents
```bash
# View latest report
ls -la reports/
cat reports/security-health-*.json | jq .

# Check security score
cat reports/security-health-*.json | jq '.security_health_score'

# View violations summary
cat reports/security-health-*.json | jq '.summary'
```

## GitOps Baseline Validation

### ArgoCD Integration

#### Monitor Policy Drift
```bash
# Check ArgoCD applications
kubectl get applications -n argocd

# View application sync status
kubectl get applications -n argocd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\t"}{.status.health.status}{"\n"}{end}'

# Run audit to detect drift
make run-audit
```

#### Baseline Policy Validation
When you have Gatekeeper policies deployed via ArgoCD:

1. **Policies as Baseline**: The agent uses deployed Gatekeeper constraints as the security baseline
2. **Drift Detection**: Monitors if ArgoCD applications containing policies are out of sync
3. **Violation Tracking**: Reports violations against your Git-defined policy baseline

```bash
# Check policy deployment status
kubectl get constrainttemplates
kubectl get constraints --all-namespaces

# Verify ArgoCD sync for policy applications
kubectl get applications -n argocd | grep -i policy

# Run comprehensive audit
make run-audit
```

## Troubleshooting

### Common Issues

#### Jobs Not Running
```bash
# Check CronJob status
kubectl describe cronjob security-audit -n security-agent

# Verify if suspended
kubectl get cronjob security-audit -n security-agent -o jsonpath='{.spec.suspend}'

# Resume if suspended
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"suspend":false}}'
```

#### Job Failures
```bash
# Check failed jobs
kubectl get jobs -n security-agent --field-selector status.successful!=1

# Get failure details
kubectl describe job <failed-job-name> -n security-agent

# Check pod logs
kubectl logs job/<failed-job-name> -n security-agent
```

#### Permission Issues
```bash
# Verify service account
kubectl get sa security-agent -n security-agent

# Check RBAC
kubectl describe clusterrolebinding security-agent

# Test permissions
kubectl auth can-i get pods --as=system:serviceaccount:security-agent:security-agent
kubectl auth can-i list applications.argoproj.io --as=system:serviceaccount:security-agent:security-agent
```

#### ArgoCD Integration Issues
```bash
# Check ArgoCD installation
kubectl get pods -n argocd

# Verify ArgoCD CRDs
kubectl get crd applications.argoproj.io

# Test ArgoCD API access
kubectl get applications -n argocd
```

### Diagnostic Tools

#### Run Full Diagnostics
```bash
./troubleshoot.sh
```

#### Manual Diagnostics
```bash
# Check agent health
kubectl get pods -n security-agent
kubectl describe cronjob security-audit -n security-agent

# Verify image
kubectl get cronjob security-audit -n security-agent -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'

# Check resource usage
kubectl top pods -n security-agent

# View events
kubectl get events -n security-agent --sort-by='.lastTimestamp'
```

## Maintenance

### Update Agent
```bash
# Rebuild and update
make clean
make full-deploy

# Rolling update
kubectl apply -f k8s/cronjob.yaml
```

### Scale Operations

#### Adjust Audit Frequency
```bash
# Every 2 hours
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"schedule":"0 */2 * * *"}}'

# Every 6 hours (default)
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"schedule":"0 */6 * * *"}}'

# Daily at 2 AM
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"schedule":"0 2 * * *"}}'
```

#### Manage Job History
```bash
# Set history limits
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"successfulJobsHistoryLimit":5,"failedJobsHistoryLimit":2}}'

# Clean old jobs
kubectl delete jobs -n security-agent --field-selector status.successful=1
```

#### Suspend/Resume Audits
```bash
# Suspend audits
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"suspend":true}}'

# Resume audits
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"suspend":false}}'
```

## Security Health Interpretation

### Score Ranges
- **90-100**: 🟢 Excellent - Maintain current practices
- **80-89**: 🟡 Very Good - Minor improvements needed
- **70-79**: 🟠 Good - Address medium priority issues
- **60-69**: 🔴 Fair - Multiple issues need attention
- **0-59**: ⚫ Poor - Critical security risks present

### Violation Priorities
1. **Critical** (-20 points): Privileged containers, security bypasses
2. **High** (-10 points): Root users, missing security contexts
3. **Medium** (-5 points): Resource limits, network policies

### Recommended Actions by Score

#### Score < 60 (Emergency)
```bash
# Immediate actions
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.securityContext.runAsUser}{"\n"}{end}' | grep -E '\t0$'

# Find privileged containers
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.securityContext.privileged}{"\t"}{$.metadata.namespace}{"\t"}{$.metadata.name}{"\n"}{end}{end}' | grep true
```

#### Score 60-79 (Attention Needed)
```bash
# Check resource limits
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.resources.limits}{"\t"}{$.metadata.namespace}{"\t"}{$.metadata.name}{"\n"}{end}{end}' | grep null

# Review network policies
kubectl get networkpolicies --all-namespaces
```

## GitOps Workflow Integration

### Policy Development Workflow
1. **Develop Policies**: Create Gatekeeper policies in Git repository
2. **Deploy via ArgoCD**: Use ArgoCD to deploy policies to cluster
3. **Validate Deployment**: Agent detects new policies automatically
4. **Monitor Compliance**: Scheduled audits validate against deployed policies
5. **Detect Drift**: Agent alerts when cluster state differs from Git

### Baseline Management
```bash
# View current policy baseline
kubectl get constrainttemplates -o name
kubectl get constraints --all-namespaces -o wide

# Check ArgoCD sync status for policy apps
kubectl get applications -n argocd -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\n"}{end}'

# Validate against baseline
make run-audit
```

## Emergency Procedures

### Complete System Reset
```bash
# Stop all audits
kubectl patch cronjob security-audit -n security-agent -p '{"spec":{"suspend":true}}'

# Clean up
make clean

# Redeploy
make full-deploy
```

### Force Immediate Audit
```bash
# Create emergency audit job
kubectl create job emergency-audit-$(date +%s) --from=cronjob/security-audit -n security-agent

# Monitor progress
kubectl get jobs -n security-agent -w

# Get results
kubectl logs job/emergency-audit-$(date +%s) -n security-agent
```

### Policy Emergency Response
```bash
# Suspend policy enforcement (if needed)
kubectl patch <constraint-name> -p '{"spec":{"enforcementAction":"warn"}}'

# Check immediate impact
make run-audit

# Review and fix issues
kubectl get events --sort-by='.lastTimestamp' | grep -i violation
```

## Monitoring Integration

### Prometheus Metrics (Future)
- Security health score trends
- Violation counts by type
- Policy compliance rates
- Audit execution metrics

### Alerting Setup (Future)
- Critical security violations
- Policy drift detection
- Audit job failures
- Score degradation alerts

## Contact and Support

- **Repository**: `/Users/muhammadshahid/eks-security-agent`
- **Logs Location**: `/tmp/security-health-*.json` (inside job pods)
- **Namespace**: `security-agent`
- **Service Account**: `security-agent`

For issues:
1. Run `./troubleshoot.sh`
2. Check logs with `make logs`
3. Review job status with `kubectl get jobs -n security-agent`
4. Consult this runbook for common solutions
