#!/usr/bin/env python3

import json
import requests
import time
import subprocess
import sys
from threading import Thread

def start_webhook_server():
    """Start webhook server in background"""
    try:
        subprocess.run([sys.executable, "src/webhook_server.py"], 
                      cwd="/Users/muhammadshahid/eks-security-agent/egress-agent",
                      check=False)
    except Exception as e:
        print(f"Failed to start webhook server: {e}")

def test_webhook_validation():
    """Test webhook validation with sample requests"""
    base_url = "http://localhost:8443"
    
    # Wait for server to start
    print("🚀 Starting webhook server...")
    time.sleep(3)
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"✅ Health check: {response.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return
    
    # Test valid policy
    print("\n🧪 Testing valid policy...")
    valid_request = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "request": {
            "uid": "demo-valid-123",
            "operation": "CREATE",
            "object": {
                "metadata": {
                    "name": "valid-policy",
                    "namespace": "demo",
                    "labels": {"egress-controller": "managed"}
                },
                "data": {
                    "policy.json": json.dumps({
                        "defaultAction": "deny",
                        "allowedDestinations": [
                            {
                                "name": "s3-access",
                                "awsService": "s3",
                                "regions": ["us-east-1"],
                                "ports": [443]
                            }
                        ]
                    })
                }
            }
        }
    }
    
    try:
        response = requests.post(f"{base_url}/validate", 
                               json=valid_request, timeout=5)
        result = response.json()
        if result['response']['allowed']:
            print("✅ Valid policy accepted")
        else:
            print(f"❌ Valid policy rejected: {result['response']['status']['message']}")
    except Exception as e:
        print(f"❌ Valid policy test failed: {e}")
    
    # Test invalid policy
    print("\n🧪 Testing invalid policy...")
    invalid_request = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "request": {
            "uid": "demo-invalid-456",
            "operation": "CREATE",
            "object": {
                "metadata": {
                    "name": "invalid-policy",
                    "namespace": "demo",
                    "labels": {"egress-controller": "managed"}
                },
                "data": {
                    "policy.json": json.dumps({
                        "defaultAction": "invalid-action",
                        "allowedDestinations": [
                            {
                                "name": "bad-cidr",
                                "cidr": "10.1.0.0/99",  # Invalid CIDR
                                "ports": [443]
                            }
                        ]
                    })
                }
            }
        }
    }
    
    try:
        response = requests.post(f"{base_url}/validate", 
                               json=invalid_request, timeout=5)
        result = response.json()
        if not result['response']['allowed']:
            print(f"✅ Invalid policy rejected: {result['response']['status']['message']}")
        else:
            print("❌ Invalid policy was accepted (should be rejected)")
    except Exception as e:
        print(f"❌ Invalid policy test failed: {e}")
    
    # Test non-managed ConfigMap
    print("\n🧪 Testing non-managed ConfigMap...")
    non_managed_request = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "request": {
            "uid": "demo-non-managed-789",
            "operation": "CREATE",
            "object": {
                "metadata": {
                    "name": "regular-config",
                    "namespace": "demo",
                    "labels": {"app": "some-app"}  # No egress-controller label
                },
                "data": {
                    "config.yaml": "some: config"
                }
            }
        }
    }
    
    try:
        response = requests.post(f"{base_url}/validate", 
                               json=non_managed_request, timeout=5)
        result = response.json()
        if result['response']['allowed']:
            print("✅ Non-managed ConfigMap allowed")
        else:
            print(f"❌ Non-managed ConfigMap rejected: {result['response']['status']['message']}")
    except Exception as e:
        print(f"❌ Non-managed ConfigMap test failed: {e}")

if __name__ == "__main__":
    print("🎯 Egress Policy Webhook Demo")
    print("=" * 40)
    
    # Start webhook server in background thread
    server_thread = Thread(target=start_webhook_server, daemon=True)
    server_thread.start()
    
    # Run tests
    test_webhook_validation()
    
    print("\n✨ Demo completed!")
    print("💡 To deploy to Kubernetes: make webhook-full-deploy")
