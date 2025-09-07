#!/usr/bin/env python3

import json
import logging
import subprocess
import time
from kubernetes import client, config
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    namespace: str
    test_name: str
    expected: str  # "allow" or "deny"
    actual: str    # "allow" or "deny" or "error"
    success: bool
    details: str


class EgressPolicyTester:
    """Tests egress NetworkPolicy enforcement"""
    
    def __init__(self):
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.core_v1 = client.CoreV1Api()
        self.networking_v1 = client.NetworkingV1Api()
    
    def get_managed_namespaces(self) -> List[str]:
        """Get namespaces with egress policies"""
        namespaces = []
        
        # Find ConfigMaps with egress-controller label
        configmaps = self.core_v1.list_config_map_for_all_namespaces(
            label_selector="egress-controller=managed"
        )
        
        for cm in configmaps.items:
            ns = cm.metadata.namespace
            if ns not in namespaces:
                namespaces.append(ns)
        
        return namespaces
    
    def get_policy_rules(self, namespace: str) -> Dict[str, Any]:
        """Extract policy rules from ConfigMap"""
        try:
            cm = self.core_v1.read_namespaced_config_map(
                name="egress-policy", 
                namespace=namespace
            )
            
            policy_json = cm.data.get('policy.json', '{}')
            return json.loads(policy_json)
        
        except Exception as e:
            logger.error(f"Failed to get policy for {namespace}: {e}")
            return {}
    
    def check_networkpolicy_exists(self, namespace: str) -> bool:
        """Check if NetworkPolicy was generated"""
        try:
            self.networking_v1.read_namespaced_network_policy(
                name="egress-policy-generated",
                namespace=namespace
            )
            return True
        except:
            return False
    
    def create_test_pod(self, namespace: str, name: str = "egress-test-pod") -> str:
        """Create test pod for connectivity testing"""
        pod_spec = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {"test": "egress-validation"}
            },
            "spec": {
                "containers": [{
                    "name": "test",
                    "image": "curlimages/curl:latest",
                    "command": ["sleep", "3600"],
                    "resources": {
                        "requests": {"memory": "32Mi", "cpu": "10m"},
                        "limits": {"memory": "64Mi", "cpu": "50m"}
                    }
                }],
                "restartPolicy": "Never"
            }
        }
        
        try:
            self.core_v1.create_namespaced_pod(namespace=namespace, body=pod_spec)
            
            # Wait for pod to be ready
            for _ in range(30):
                pod = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
                if pod.status.phase == "Running":
                    return name
                time.sleep(2)
            
            raise Exception("Pod not ready after 60s")
        
        except Exception as e:
            logger.error(f"Failed to create test pod in {namespace}: {e}")
            raise
    
    def test_connectivity(self, namespace: str, pod_name: str, target: str, port: int, timeout: int = 5) -> TestResult:
        """Test connectivity from pod to target"""
        test_name = f"connect-to-{target}:{port}"
        
        try:
            # Use kubectl exec to test connectivity
            cmd = [
                "kubectl", "exec", "-n", namespace, pod_name, "--",
                "timeout", str(timeout), "curl", "-s", "--connect-timeout", str(timeout),
                f"http://{target}:{port}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
            
            if result.returncode == 0:
                return TestResult(namespace, test_name, "unknown", "allow", True, "Connection successful")
            elif result.returncode == 28:  # Timeout
                return TestResult(namespace, test_name, "unknown", "deny", True, "Connection blocked (timeout)")
            else:
                return TestResult(namespace, test_name, "unknown", "deny", True, f"Connection failed: {result.stderr}")
        
        except Exception as e:
            return TestResult(namespace, test_name, "unknown", "error", False, str(e))
    
    def test_allowed_destinations(self, namespace: str, policy: Dict[str, Any]) -> List[TestResult]:
        """Test that allowed destinations are reachable"""
        results = []
        
        try:
            pod_name = self.create_test_pod(namespace)
            
            for dest in policy.get('allowedDestinations', []):
                if 'cidr' in dest:
                    # Test CIDR destination (use first IP in range)
                    import ipaddress
                    network = ipaddress.ip_network(dest['cidr'], strict=False)
                    target_ip = str(list(network.hosts())[0]) if network.num_addresses > 2 else str(network.network_address)
                    
                    for port in dest.get('ports', [80]):
                        result = self.test_connectivity(namespace, pod_name, target_ip, port)
                        result.expected = "allow"
                        result.success = (result.actual == "allow")
                        results.append(result)
                
                elif 'awsService' in dest:
                    # Test AWS service (use known endpoints)
                    service_endpoints = {
                        's3': 's3.amazonaws.com',
                        'dynamodb': 'dynamodb.us-east-1.amazonaws.com',
                        'rds': 'rds.amazonaws.com'
                    }
                    
                    endpoint = service_endpoints.get(dest['awsService'])
                    if endpoint:
                        for port in dest.get('ports', [443]):
                            result = self.test_connectivity(namespace, pod_name, endpoint, port)
                            result.expected = "allow"
                            result.success = (result.actual == "allow")
                            results.append(result)
        
        except Exception as e:
            logger.error(f"Failed to test allowed destinations in {namespace}: {e}")
        
        finally:
            # Cleanup test pod
            try:
                self.core_v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            except:
                pass
        
        return results
    
    def test_blocked_destinations(self, namespace: str) -> List[TestResult]:
        """Test that blocked destinations are not reachable"""
        results = []
        blocked_targets = [
            ("8.8.8.8", 53),      # Google DNS
            ("1.1.1.1", 53),      # Cloudflare DNS
            ("httpbin.org", 80),  # External HTTP service
        ]
        
        try:
            pod_name = self.create_test_pod(namespace, "egress-block-test")
            
            for target, port in blocked_targets:
                result = self.test_connectivity(namespace, pod_name, target, port, timeout=3)
                result.expected = "deny"
                result.success = (result.actual == "deny")
                results.append(result)
        
        except Exception as e:
            logger.error(f"Failed to test blocked destinations in {namespace}: {e}")
        
        finally:
            # Cleanup test pod
            try:
                self.core_v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            except:
                pass
        
        return results
    
    def validate_namespace(self, namespace: str) -> Dict[str, Any]:
        """Validate egress policies for a namespace"""
        logger.info(f"🔍 Validating egress policies for namespace: {namespace}")
        
        validation = {
            "namespace": namespace,
            "policy_exists": False,
            "networkpolicy_exists": False,
            "tests": [],
            "summary": {"total": 0, "passed": 0, "failed": 0}
        }
        
        # Check if policy ConfigMap exists
        policy = self.get_policy_rules(namespace)
        validation["policy_exists"] = bool(policy)
        
        if not policy:
            validation["tests"].append(TestResult(
                namespace, "policy-configmap", "exists", "missing", False, 
                "No egress-policy ConfigMap found"
            ))
            return validation
        
        # Check if NetworkPolicy was generated
        validation["networkpolicy_exists"] = self.check_networkpolicy_exists(namespace)
        
        if not validation["networkpolicy_exists"]:
            validation["tests"].append(TestResult(
                namespace, "networkpolicy-generated", "exists", "missing", False,
                "NetworkPolicy not generated from ConfigMap"
            ))
        
        # Test allowed destinations
        allowed_tests = self.test_allowed_destinations(namespace, policy)
        validation["tests"].extend(allowed_tests)
        
        # Test blocked destinations
        blocked_tests = self.test_blocked_destinations(namespace)
        validation["tests"].extend(blocked_tests)
        
        # Calculate summary
        validation["summary"]["total"] = len(validation["tests"])
        validation["summary"]["passed"] = sum(1 for t in validation["tests"] if t.success)
        validation["summary"]["failed"] = validation["summary"]["total"] - validation["summary"]["passed"]
        
        return validation
    
    def run_full_validation(self) -> Dict[str, Any]:
        """Run validation across all managed namespaces"""
        logger.info("🚀 Starting full egress policy validation")
        
        namespaces = self.get_managed_namespaces()
        if not namespaces:
            logger.warning("No namespaces with egress policies found")
            return {"namespaces": [], "overall_summary": {"total": 0, "passed": 0, "failed": 0}}
        
        results = {
            "namespaces": [],
            "overall_summary": {"total": 0, "passed": 0, "failed": 0}
        }
        
        for namespace in namespaces:
            validation = self.validate_namespace(namespace)
            results["namespaces"].append(validation)
            
            # Update overall summary
            results["overall_summary"]["total"] += validation["summary"]["total"]
            results["overall_summary"]["passed"] += validation["summary"]["passed"]
            results["overall_summary"]["failed"] += validation["summary"]["failed"]
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Print validation results in a readable format"""
        print("\n" + "="*60)
        print("🎯 EGRESS POLICY VALIDATION REPORT")
        print("="*60)
        
        for ns_result in results["namespaces"]:
            namespace = ns_result["namespace"]
            summary = ns_result["summary"]
            
            print(f"\n📋 Namespace: {namespace}")
            print(f"   Policy ConfigMap: {'✅' if ns_result['policy_exists'] else '❌'}")
            print(f"   NetworkPolicy: {'✅' if ns_result['networkpolicy_exists'] else '❌'}")
            print(f"   Tests: {summary['passed']}/{summary['total']} passed")
            
            # Show failed tests
            failed_tests = [t for t in ns_result["tests"] if not t.success]
            if failed_tests:
                print("   ❌ Failed tests:")
                for test in failed_tests:
                    print(f"      - {test.test_name}: {test.details}")
        
        # Overall summary
        overall = results["overall_summary"]
        success_rate = (overall["passed"] / overall["total"] * 100) if overall["total"] > 0 else 0
        
        print(f"\n📊 OVERALL SUMMARY")
        print(f"   Total Tests: {overall['total']}")
        print(f"   Passed: {overall['passed']} ✅")
        print(f"   Failed: {overall['failed']} ❌")
        print(f"   Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("   Status: 🟢 EXCELLENT")
        elif success_rate >= 75:
            print("   Status: 🟡 GOOD")
        else:
            print("   Status: 🔴 NEEDS ATTENTION")


def main():
    """Main entry point"""
    tester = EgressPolicyTester()
    results = tester.run_full_validation()
    tester.print_results(results)


if __name__ == "__main__":
    main()
