#!/usr/bin/env python3

import unittest
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from webhook_server import app, create_admission_response


class TestWebhookServer(unittest.TestCase):
    
    def setUp(self):
        """Set up test client"""
        self.app = app.test_client()
        self.app.testing = True
    
    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['service'], 'egress-policy-webhook')
    
    def test_readiness_endpoint(self):
        """Test readiness check endpoint"""
        response = self.app.get('/ready')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'ready')
    
    def test_valid_egress_policy_configmap(self):
        """Test validation of valid egress policy ConfigMap"""
        admission_request = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "request": {
                "uid": "test-uid-123",
                "operation": "CREATE",
                "object": {
                    "metadata": {
                        "name": "egress-policy",
                        "namespace": "tenant-a",
                        "labels": {
                            "egress-controller": "managed"
                        }
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
        
        response = self.app.post('/validate',
                                data=json.dumps(admission_request),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['response']['allowed'])
        self.assertEqual(data['response']['uid'], 'test-uid-123')
    
    def test_invalid_json_in_policy(self):
        """Test validation with invalid JSON in policy"""
        admission_request = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "request": {
                "uid": "test-uid-456",
                "operation": "CREATE",
                "object": {
                    "metadata": {
                        "name": "bad-policy",
                        "namespace": "tenant-a",
                        "labels": {
                            "egress-controller": "managed"
                        }
                    },
                    "data": {
                        "policy.json": "invalid-json-here"
                    }
                }
            }
        }
        
        response = self.app.post('/validate',
                                data=json.dumps(admission_request),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['response']['allowed'])
        self.assertIn("Invalid JSON", data['response']['status']['message'])
    
    def test_invalid_policy_structure(self):
        """Test validation with invalid policy structure"""
        admission_request = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "request": {
                "uid": "test-uid-789",
                "operation": "UPDATE",
                "object": {
                    "metadata": {
                        "name": "invalid-policy",
                        "namespace": "tenant-b",
                        "labels": {
                            "egress-controller": "managed"
                        }
                    },
                    "data": {
                        "policy.json": json.dumps({
                            "defaultAction": "invalid-action",
                            "allowedDestinations": [
                                {
                                    "name": "bad-dest",
                                    "cidr": "invalid-cidr",
                                    "ports": [443]
                                }
                            ]
                        })
                    }
                }
            }
        }
        
        response = self.app.post('/validate',
                                data=json.dumps(admission_request),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['response']['allowed'])
        self.assertIn("Policy validation failed", data['response']['status']['message'])
    
    def test_non_managed_configmap_allowed(self):
        """Test that non-managed ConfigMaps are allowed through"""
        admission_request = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "request": {
                "uid": "test-uid-000",
                "operation": "CREATE",
                "object": {
                    "metadata": {
                        "name": "regular-configmap",
                        "namespace": "default",
                        "labels": {
                            "app": "some-app"
                        }
                    },
                    "data": {
                        "config.yaml": "some: config"
                    }
                }
            }
        }
        
        response = self.app.post('/validate',
                                data=json.dumps(admission_request),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['response']['allowed'])
        self.assertIn("Not an egress policy ConfigMap", data['response']['status']['message'])
    
    def test_missing_policy_json(self):
        """Test validation with missing policy.json"""
        admission_request = {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "request": {
                "uid": "test-uid-missing",
                "operation": "CREATE",
                "object": {
                    "metadata": {
                        "name": "empty-policy",
                        "namespace": "tenant-c",
                        "labels": {
                            "egress-controller": "managed"
                        }
                    },
                    "data": {
                        "other-data": "not-policy"
                    }
                }
            }
        }
        
        response = self.app.post('/validate',
                                data=json.dumps(admission_request),
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['response']['allowed'])
        self.assertIn("Missing policy.json", data['response']['status']['message'])
    
    def test_empty_admission_request(self):
        """Test handling of empty admission request"""
        response = self.app.post('/validate',
                                data='',
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
    
    def test_malformed_admission_request(self):
        """Test handling of malformed admission request"""
        response = self.app.post('/validate',
                                data='invalid-json',
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 400)


class TestAdmissionResponse(unittest.TestCase):
    
    def test_create_allowed_response(self):
        """Test creating allowed admission response"""
        response = create_admission_response(True, "All good", "test-uid")
        
        self.assertEqual(response['apiVersion'], 'admission.k8s.io/v1')
        self.assertEqual(response['kind'], 'AdmissionReview')
        self.assertTrue(response['response']['allowed'])
        self.assertEqual(response['response']['uid'], 'test-uid')
        self.assertEqual(response['response']['status']['code'], 200)
        self.assertEqual(response['response']['status']['message'], 'All good')
    
    def test_create_denied_response(self):
        """Test creating denied admission response"""
        response = create_admission_response(False, "Validation failed", "test-uid")
        
        self.assertEqual(response['apiVersion'], 'admission.k8s.io/v1')
        self.assertEqual(response['kind'], 'AdmissionReview')
        self.assertFalse(response['response']['allowed'])
        self.assertEqual(response['response']['uid'], 'test-uid')
        self.assertEqual(response['response']['status']['code'], 400)
        self.assertEqual(response['response']['status']['message'], 'Validation failed')


if __name__ == '__main__':
    unittest.main()
