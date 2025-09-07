#!/usr/bin/env python3
import json
import os
import time
import sys
from kubernetes import client, config
from datetime import datetime
from typing import List, Dict, Tuple

class EKSSecurityHealthAgent:
    def __init__(self):
        self.security_violations = []
        self.drift_issues = []
        self.policy_status = {}
        self.argocd_apps = []
        self._init_k8s_client()

    def _init_k8s_client(self):
        """Initialize Kubernetes client for in-cluster or local execution"""
        try:
            config.load_incluster_config()
            print("🔗 Using in-cluster Kubernetes configuration")
        except config.ConfigException:
            config.load_kube_config()
            print("🔗 Using local kubeconfig")
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.networking_v1 = client.NetworkingV1Api()
        self.custom_api = client.CustomObjectsApi()

    def check_argocd_sync_status(self) -> List[Dict]:
        """Check ArgoCD application sync status for drift detection"""
        try:
            apps = self.custom_api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace="argocd",
                plural="applications"
            )
            
            self.argocd_apps = apps.get('items', [])
            
            for app in self.argocd_apps:
                status = app.get('status', {})
                sync_status = status.get('sync', {}).get('status', 'Unknown')
                health_status = status.get('health', {}).get('status', 'Unknown')
                
                if sync_status != 'Synced' or health_status != 'Healthy':
                    self.drift_issues.append({
                        'type': 'ArgoCD Drift',
                        'app': app['metadata']['name'],
                        'sync_status': sync_status,
                        'health_status': health_status
                    })
            
            return self.drift_issues
        except client.ApiException as e:
            print(f"⚠️  ArgoCD not found or not accessible: {e.status}")
            return []

    def validate_gatekeeper_constraints(self) -> List[Dict]:
        """Validate existing Gatekeeper constraints and their violations"""
        try:
            # Get constraint templates
            templates = self.custom_api.list_cluster_custom_object(
                group="templates.gatekeeper.sh",
                version="v1beta1",
                plural="constrainttemplates"
            )
            
            constraint_types = []
            for template in templates.get('items', []):
                crd = template.get('spec', {}).get('crd', {})
                names = crd.get('spec', {}).get('names', {})
                if names.get('kind'):
                    constraint_types.append(names['kind'].lower())
            
            print(f"🔍 Found {len(constraint_types)} constraint types")
            
            # Check each constraint type for violations
            for ctype in constraint_types:
                try:
                    constraints = self.custom_api.list_cluster_custom_object(
                        group="constraints.gatekeeper.sh",
                        version="v1beta1",
                        plural=ctype
                    )
                    
                    for constraint in constraints.get('items', []):
                        name = constraint['metadata']['name']
                        violations = constraint.get('status', {}).get('violations', [])
                        
                        self.policy_status[name] = {
                            'type': ctype,
                            'violations': len(violations),
                            'enforcement_action': constraint.get('spec', {}).get('enforcementAction', 'warn')
                        }
                        
                        for violation in violations:
                            self.security_violations.append({
                                'constraint': name,
                                'type': ctype,
                                'resource': violation.get('name', 'Unknown'),
                                'namespace': violation.get('namespace', 'Unknown'),
                                'message': violation.get('message', 'No message')
                            })
                except client.ApiException:
                    continue
                    
        except client.ApiException as e:
            print(f"❌ Failed to validate Gatekeeper constraints: {e.status}")
        
        return self.security_violations

    def check_critical_security_policies(self) -> List[Dict]:
        """Check for critical security policy violations"""
        critical_checks = []
        
        try:
            pods = self.v1.list_pod_for_all_namespaces()
            
            for pod in pods.items:
                namespace = pod.metadata.namespace
                name = pod.metadata.name
                
                # Skip system namespaces
                if namespace in ['kube-system', 'kube-public', 'argocd', 'gatekeeper-system']:
                    continue
                
                spec = pod.spec
                
                # Check pod security context
                if not spec.security_context:
                    critical_checks.append({
                        'severity': 'HIGH',
                        'type': 'Missing Pod Security Context',
                        'resource': f"Pod/{name}",
                        'namespace': namespace
                    })
                
                # Check containers
                for container in spec.containers:
                    container_name = container.name
                    
                    # Check resource limits
                    if not (container.resources and container.resources.limits):
                        critical_checks.append({
                            'severity': 'MEDIUM',
                            'type': 'Missing Resource Limits',
                            'resource': f"Pod/{name}",
                            'namespace': namespace,
                            'container': container_name
                        })
                    
                    # Check security context
                    if container.security_context:
                        # Check for privileged containers
                        if container.security_context.privileged:
                            critical_checks.append({
                                'severity': 'CRITICAL',
                                'type': 'Privileged Container',
                                'resource': f"Pod/{name}",
                                'namespace': namespace,
                                'container': container_name
                            })
                        
                        # Check for root user
                        if container.security_context.run_as_user == 0:
                            critical_checks.append({
                                'severity': 'HIGH',
                                'type': 'Container Running as Root',
                                'resource': f"Pod/{name}",
                                'namespace': namespace,
                                'container': container_name
                            })
        
        except client.ApiException as e:
            print(f"❌ Failed to check critical security policies: {e.status}")
        
        return critical_checks

    def check_network_policies(self) -> List[Dict]:
        """Check for missing network policies"""
        network_issues = []
        
        try:
            namespaces = self.v1.list_namespace()
            netpols = self.networking_v1.list_network_policy_for_all_namespaces()
            netpol_namespaces = {np.metadata.namespace for np in netpols.items}
            
            for ns in namespaces.items:
                ns_name = ns.metadata.name
                if (ns_name not in ['kube-system', 'kube-public', 'kube-node-lease'] and 
                    ns_name not in netpol_namespaces):
                    network_issues.append({
                        'severity': 'MEDIUM',
                        'type': 'Missing Network Policy',
                        'namespace': ns_name,
                        'message': 'Namespace has no network policies defined'
                    })
        
        except client.ApiException as e:
            print(f"⚠️  Failed to check network policies: {e.status}")
        
        return network_issues

    def calculate_health_score(self, critical: int, high: int, medium: int) -> int:
        """Calculate security health score (0-100)"""
        base_score = 100
        base_score -= critical * 20
        base_score -= high * 10
        base_score -= medium * 5
        return max(0, base_score)

    def generate_security_report(self) -> Tuple[str, Dict]:
        """Generate comprehensive security health report"""
        critical_checks = self.check_critical_security_policies()
        network_issues = self.check_network_policies()
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = f"/tmp/security-health-{timestamp}.json"
        
        critical_count = len([v for v in critical_checks if v.get('severity') == 'CRITICAL'])
        high_count = len([v for v in critical_checks if v.get('severity') == 'HIGH'])
        medium_count = len([v for v in critical_checks if v.get('severity') == 'MEDIUM']) + len(network_issues)
        
        report = {
            'timestamp': timestamp,
            'security_health_score': self.calculate_health_score(critical_count, high_count, medium_count),
            'summary': {
                'gatekeeper_violations': len(self.security_violations),
                'drift_issues': len(self.drift_issues),
                'critical_issues': critical_count,
                'high_issues': high_count,
                'medium_issues': medium_count,
                'network_issues': len(network_issues),
                'active_policies': len(self.policy_status)
            },
            'gatekeeper_violations': self.security_violations,
            'configuration_drift': self.drift_issues,
            'critical_security_checks': critical_checks,
            'network_policy_issues': network_issues,
            'policy_status': self.policy_status
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report_file, report

    def print_security_summary(self, report):
        """Print security health summary"""
        score = report['security_health_score']
        summary = report['summary']
        
        print("\n" + "="*60)
        print("🛡️  EKS CLUSTER SECURITY HEALTH REPORT")
        print("="*60)
        print(f"🎯 Security Health Score: {score}/100")
        
        if score >= 80:
            print("✅ EXCELLENT - Your cluster security posture is strong")
        elif score >= 60:
            print("⚠️  GOOD - Some security improvements needed")
        elif score >= 40:
            print("🟡 FAIR - Multiple security issues require attention")
        else:
            print("🔴 POOR - Critical security issues need immediate attention")
        
        print(f"\n📊 VIOLATION SUMMARY:")
        print(f"  🔴 Critical Issues: {summary['critical_issues']}")
        print(f"  🟠 High Issues: {summary['high_issues']}")
        print(f"  🟡 Medium Issues: {summary['medium_issues']}")
        print(f"  📱 ArgoCD Drift Issues: {summary['drift_issues']}")
        print(f"  🌐 Network Policy Issues: {summary['network_issues']}")
        print(f"  🔒 Gatekeeper Violations: {summary['gatekeeper_violations']}")
        print(f"  📋 Active Policies: {summary['active_policies']}")

    def run_security_audit(self) -> Dict:
        """Execute comprehensive security health audit"""
        print("🛡️  Starting EKS Security Health Audit...")
        
        # Clear previous results
        self.security_violations = []
        self.drift_issues = []
        self.policy_status = {}
        self.argocd_apps = []
        
        print("📱 Checking ArgoCD sync status...")
        self.check_argocd_sync_status()
        
        print("🔒 Validating Gatekeeper constraints...")
        self.validate_gatekeeper_constraints()
        
        print("📊 Generating security report...")
        report_file, report = self.generate_security_report()
        
        self.print_security_summary(report)
        print(f"📄 Report saved: {report_file}")
        
        return report

if __name__ == "__main__":
    agent = EKSSecurityHealthAgent()
    agent.run_security_audit()
    
    print("🚀 Agent completed audit. Use CronJob for scheduled audits.")
    print("💤 Sleeping indefinitely...")
    
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("👋 Agent stopped")
        sys.exit(0)
