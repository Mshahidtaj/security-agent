#!/usr/bin/env python3
import unittest
import json
import sys
import os
from unittest.mock import patch, MagicMock
from kubernetes import client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from security_agent import EKSSecurityHealthAgent

class TestEKSSecurityHealthAgent(unittest.TestCase):
    def setUp(self):
        with patch('kubernetes.config.load_incluster_config'), \
             patch('kubernetes.config.load_kube_config'):
            self.agent = EKSSecurityHealthAgent()

    def test_calculate_health_score_perfect(self):
        """Test health score calculation with no violations"""
        score = self.agent.calculate_health_score(0, 0, 0)
        self.assertEqual(score, 100)

    def test_calculate_health_score_with_violations(self):
        """Test health score calculation with violations"""
        score = self.agent.calculate_health_score(1, 2, 3)
        expected = 100 - (1*20) - (2*10) - (3*5)
        self.assertEqual(score, expected)

    def test_calculate_health_score_minimum(self):
        """Test health score doesn't go below 0"""
        score = self.agent.calculate_health_score(10, 10, 10)
        self.assertEqual(score, 0)

if __name__ == '__main__':
    unittest.main()
