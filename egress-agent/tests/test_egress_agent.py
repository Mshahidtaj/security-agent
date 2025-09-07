#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from egress_agent import EgressAgent, PolicyValidator, AWSServiceResolver


class TestPolicyValidator(unittest.TestCase):
    
    def setUp(self):
        self.validator = PolicyValidator()
    
    def test_valid_policy_with_cidr(self):
        """Test valid policy with CIDR destination"""
        policy = {
            "defaultAction": "deny",
            "allowedDestinations": [
                {
                    "name": "onprem",
                    "cidr": "10.1.0.0/16",
                    "ports": [443, 80]
                }
            ]
        }
        result = self.validator.validate(policy)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
    
    def test_valid_policy_with_aws_service(self):
        """Test valid policy with AWS service destination"""
        policy = {
            "defaultAction": "allow",
            "allowedDestinations": [
                {
                    "name": "s3-access",
                    "awsService": "s3",
                    "regions": ["us-east-1"],
                    "ports": [443]
                }
            ]
        }
        result = self.validator.validate(policy)
        self.assertTrue(result.is_valid)
    
    def test_invalid_cidr_format(self):
        """Test invalid CIDR format"""
        policy = {
            "defaultAction": "deny",
            "allowedDestinations": [
                {
                    "name": "invalid",
                    "cidr": "invalid-cidr",
                    "ports": [443]
                }
            ]
        }
        result = self.validator.validate(policy)
        self.assertFalse(result.is_valid)
        self.assertIn("Invalid CIDR format", str(result.errors))
    
    def test_missing_required_fields(self):
        """Test missing required fields"""
        policy = {
            "allowedDestinations": [
                {
                    "cidr": "10.1.0.0/16"
                    # Missing name and ports
                }
            ]
        }
        result = self.validator.validate(policy)
        self.assertFalse(result.is_valid)
    
    def test_invalid_aws_service(self):
        """Test invalid AWS service name"""
        policy = {
            "defaultAction": "deny",
            "allowedDestinations": [
                {
                    "name": "invalid-service",
                    "awsService": "invalid-service",
                    "regions": ["us-east-1"],
                    "ports": [443]
                }
            ]
        }
        result = self.validator.validate(policy)
        self.assertFalse(result.is_valid)


class TestAWSServiceResolver(unittest.TestCase):
    
    def setUp(self):
        self.resolver = AWSServiceResolver()
    
    @patch('requests.get')
    def test_resolve_s3_cidrs(self, mock_get):
        """Test S3 CIDR resolution"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "prefixes": [
                {
                    "ip_prefix": "52.216.0.0/15",
                    "region": "us-east-1",
                    "service": "S3"
                },
                {
                    "ip_prefix": "54.231.0.0/17",
                    "region": "us-east-1", 
                    "service": "S3"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        cidrs = self.resolver.resolve_service_cidrs("s3", ["us-east-1"])
        
        self.assertEqual(len(cidrs), 2)
        self.assertIn("52.216.0.0/15", cidrs)
        self.assertIn("54.231.0.0/17", cidrs)
    
    def test_cache_functionality(self):
        """Test CIDR caching works"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {"prefixes": []}
            mock_get.return_value = mock_response
            
            # First call
            self.resolver.resolve_service_cidrs("s3", ["us-east-1"])
            # Second call should use cache
            self.resolver.resolve_service_cidrs("s3", ["us-east-1"])
            
            # Should only make one HTTP request
            self.assertEqual(mock_get.call_count, 1)


class TestEgressAgent(unittest.TestCase):
    
    def setUp(self):
        self.mock_k8s_client = Mock()
        self.agent = EgressAgent(k8s_client=self.mock_k8s_client)
    
    def test_configmap_to_networkpolicy_conversion(self):
        """Test ConfigMap to NetworkPolicy conversion"""
        configmap_data = {
            "policy.json": json.dumps({
                "defaultAction": "deny",
                "allowedDestinations": [
                    {
                        "name": "onprem-db",
                        "cidr": "10.1.100.0/24",
                        "ports": [5432]
                    }
                ]
            })
        }
        
        network_policy = self.agent.generate_network_policy(
            namespace="tenant-a",
            policy_data=configmap_data
        )
        
        self.assertEqual(network_policy['metadata']['name'], 'egress-policy-generated')
        self.assertEqual(network_policy['metadata']['namespace'], 'tenant-a')
        self.assertEqual(network_policy['spec']['policyTypes'], ['Egress'])
        
        # Check egress rules
        egress_rules = network_policy['spec']['egress']
        self.assertEqual(len(egress_rules), 1)
        self.assertEqual(egress_rules[0]['to'][0]['ipBlock']['cidr'], '10.1.100.0/24')
    
    def test_aws_service_to_networkpolicy(self):
        """Test AWS service resolution in NetworkPolicy"""
        # Mock the resolver directly on the agent instance
        self.agent.aws_resolver.resolve_service_cidrs = Mock(return_value=["52.216.0.0/15"])
        
        configmap_data = {
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
        
        network_policy = self.agent.generate_network_policy(
            namespace="tenant-a",
            policy_data=configmap_data
        )
        
        egress_rules = network_policy['spec']['egress']
        self.assertEqual(egress_rules[0]['to'][0]['ipBlock']['cidr'], '52.216.0.0/15')
    
    def test_invalid_policy_handling(self):
        """Test handling of invalid policy data"""
        configmap_data = {
            "policy.json": "invalid-json"
        }
        
        with self.assertRaises(ValueError):
            self.agent.generate_network_policy(
                namespace="tenant-a",
                policy_data=configmap_data
            )
    
    def test_watch_configmaps(self):
        """Test ConfigMap watching functionality"""
        # Mock kubernetes watch
        mock_watch = Mock()
        mock_event = {
            'type': 'ADDED',
            'object': {
                'metadata': {
                    'name': 'egress-policy',
                    'namespace': 'tenant-a',
                    'labels': {'egress-controller': 'managed'}
                },
                'data': {
                    'policy.json': json.dumps({
                        "defaultAction": "deny",
                        "allowedDestinations": []
                    })
                }
            }
        }
        
        with patch('kubernetes.watch.Watch') as mock_watch_class:
            mock_watch_class.return_value.stream.return_value = [mock_event]
            
            # This would normally run indefinitely, so we'll just test the setup
            self.agent.start_watching()
            
            # Verify watch was called
            mock_watch_class.assert_called_once()


if __name__ == '__main__':
    unittest.main()
