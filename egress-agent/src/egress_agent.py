#!/usr/bin/env python3

import json
import logging
import os
import sys
import time
import ipaddress
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import requests
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]


class PolicyValidator:
    """Validates egress policy configuration"""
    
    VALID_AWS_SERVICES = {'s3', 'rds', 'ec2', 'dynamodb', 'lambda', 'ecs'}
    VALID_ACTIONS = {'allow', 'deny'}
    
    def validate(self, policy: Dict[str, Any]) -> ValidationResult:
        """Validate policy structure and content"""
        errors = []
        
        # Check default action
        default_action = policy.get('defaultAction', 'deny')
        if default_action not in self.VALID_ACTIONS:
            errors.append(f"Invalid defaultAction: {default_action}")
        
        # Validate destinations
        destinations = policy.get('allowedDestinations', [])
        if not isinstance(destinations, list):
            errors.append("allowedDestinations must be a list")
            return ValidationResult(False, errors)
        
        for i, dest in enumerate(destinations):
            self._validate_destination(dest, i, errors)
        
        return ValidationResult(len(errors) == 0, errors)
    
    def _validate_destination(self, dest: Dict[str, Any], index: int, errors: List[str]):
        """Validate individual destination"""
        if not dest.get('name'):
            errors.append(f"Destination {index}: missing 'name' field")
        
        if not dest.get('ports'):
            errors.append(f"Destination {index}: missing 'ports' field")
        
        # Must have either cidr or awsService
        has_cidr = 'cidr' in dest
        has_aws_service = 'awsService' in dest
        
        if not (has_cidr or has_aws_service):
            errors.append(f"Destination {index}: must specify either 'cidr' or 'awsService'")
        
        if has_cidr and has_aws_service:
            errors.append(f"Destination {index}: cannot specify both 'cidr' and 'awsService'")
        
        # Validate CIDR format
        if has_cidr:
            try:
                ipaddress.ip_network(dest['cidr'], strict=False)
            except ValueError:
                errors.append(f"Destination {index}: Invalid CIDR format: {dest['cidr']}")
        
        # Validate AWS service
        if has_aws_service:
            service = dest['awsService'].lower()
            if service not in self.VALID_AWS_SERVICES:
                errors.append(f"Destination {index}: Invalid AWS service: {service}")
            
            if not dest.get('regions'):
                errors.append(f"Destination {index}: AWS service requires 'regions' field")


class AWSServiceResolver:
    """Resolves AWS service names to CIDR blocks"""
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour
        self._last_fetch = 0
    
    def resolve_service_cidrs(self, service: str, regions: List[str]) -> List[str]:
        """Resolve AWS service to CIDR blocks for specified regions"""
        cache_key = f"{service}:{','.join(sorted(regions))}"
        
        # Check cache
        if cache_key in self._cache and (time.time() - self._last_fetch) < self._cache_ttl:
            return self._cache[cache_key]
        
        # Fetch AWS IP ranges
        try:
            response = requests.get('https://ip-ranges.amazonaws.com/ip-ranges.json', timeout=10)
            response.raise_for_status()
            ip_ranges = response.json()
            
            cidrs = []
            service_upper = service.upper()
            
            for prefix in ip_ranges.get('prefixes', []):
                if (prefix.get('service') == service_upper and 
                    prefix.get('region') in regions):
                    cidrs.append(prefix['ip_prefix'])
            
            # Cache result
            self._cache[cache_key] = cidrs
            self._last_fetch = time.time()
            
            logger.info(f"Resolved {service} in {regions} to {len(cidrs)} CIDR blocks")
            return cidrs
            
        except Exception as e:
            logger.error(f"Failed to resolve AWS service CIDRs: {e}")
            return []


class EgressAgent:
    """Main egress control agent"""
    
    def __init__(self, k8s_client=None):
        self.validator = PolicyValidator()
        self.aws_resolver = AWSServiceResolver()
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
        
        # Initialize Kubernetes client
        if k8s_client:
            self.k8s_client = k8s_client
        else:
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            except:
                config.load_kube_config()
                logger.info("Loaded local Kubernetes config")
            
            self.k8s_client = client.ApiClient()
        
        self.core_v1 = client.CoreV1Api(self.k8s_client)
        self.networking_v1 = client.NetworkingV1Api(self.k8s_client)
    
    def generate_network_policy(self, namespace: str, policy_data: Dict[str, str]) -> Dict[str, Any]:
        """Generate NetworkPolicy from ConfigMap data"""
        try:
            policy_json = policy_data.get('policy.json', '{}')
            policy = json.loads(policy_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in policy: {e}")
        
        # Validate policy
        validation = self.validator.validate(policy)
        if not validation.is_valid:
            raise ValueError(f"Invalid policy: {validation.errors}")
        
        # Generate NetworkPolicy
        network_policy = {
            'apiVersion': 'networking.k8s.io/v1',
            'kind': 'NetworkPolicy',
            'metadata': {
                'name': 'egress-policy-generated',
                'namespace': namespace,
                'labels': {
                    'managed-by': 'egress-agent'
                }
            },
            'spec': {
                'podSelector': {},
                'policyTypes': ['Egress'],
                'egress': []
            }
        }
        
        # Process destinations
        for dest in policy.get('allowedDestinations', []):
            egress_rule = self._create_egress_rule(dest)
            if egress_rule:
                network_policy['spec']['egress'].append(egress_rule)
        
        return network_policy
    
    def _create_egress_rule(self, destination: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create egress rule from destination config"""
        ports = [{'protocol': 'TCP', 'port': port} for port in destination.get('ports', [])]
        
        if 'cidr' in destination:
            return {
                'to': [{'ipBlock': {'cidr': destination['cidr']}}],
                'ports': ports
            }
        
        elif 'awsService' in destination:
            service = destination['awsService'].lower()
            regions = destination.get('regions', [])
            cidrs = self.aws_resolver.resolve_service_cidrs(service, regions)
            
            if not cidrs:
                logger.warning(f"No CIDRs found for {service} in {regions}")
                return None
            
            # Create rule for first CIDR (NetworkPolicy limitation)
            # TODO: Create multiple rules for multiple CIDRs
            return {
                'to': [{'ipBlock': {'cidr': cidrs[0]}}],
                'ports': ports
            }
        
        return None
    
    def apply_network_policy(self, network_policy: Dict[str, Any]):
        """Apply NetworkPolicy to cluster"""
        namespace = network_policy['metadata']['namespace']
        name = network_policy['metadata']['name']
        
        if self.dry_run:
            logger.info(f"DRY RUN: Would apply NetworkPolicy {name} in {namespace}")
            return
        
        try:
            # Try to get existing policy
            try:
                existing = self.networking_v1.read_namespaced_network_policy(
                    name=name, namespace=namespace
                )
                # Update existing
                self.networking_v1.patch_namespaced_network_policy(
                    name=name,
                    namespace=namespace,
                    body=network_policy
                )
                logger.info(f"Updated NetworkPolicy {name} in {namespace}")
            
            except ApiException as e:
                if e.status == 404:
                    # Create new
                    self.networking_v1.create_namespaced_network_policy(
                        namespace=namespace,
                        body=network_policy
                    )
                    logger.info(f"Created NetworkPolicy {name} in {namespace}")
                else:
                    raise
        
        except ApiException as e:
            logger.error(f"Failed to apply NetworkPolicy: {e}")
    
    def process_configmap_event(self, event_type: str, configmap: Dict[str, Any]):
        """Process ConfigMap watch event"""
        metadata = configmap.get('metadata', {})
        name = metadata.get('name')
        namespace = metadata.get('namespace')
        labels = metadata.get('labels', {})
        
        # Only process managed ConfigMaps
        if labels.get('egress-controller') != 'managed':
            return
        
        logger.info(f"Processing {event_type} event for ConfigMap {name} in {namespace}")
        
        if event_type in ['ADDED', 'MODIFIED']:
            try:
                policy_data = configmap.get('data', {})
                network_policy = self.generate_network_policy(namespace, policy_data)
                self.apply_network_policy(network_policy)
            
            except Exception as e:
                logger.error(f"Failed to process ConfigMap {name}: {e}")
        
        elif event_type == 'DELETED':
            # Clean up NetworkPolicy
            try:
                if not self.dry_run:
                    self.networking_v1.delete_namespaced_network_policy(
                        name='egress-policy-generated',
                        namespace=namespace
                    )
                    logger.info(f"Deleted NetworkPolicy in {namespace}")
            except ApiException as e:
                if e.status != 404:
                    logger.error(f"Failed to delete NetworkPolicy: {e}")
    
    def start_watching(self):
        """Start watching ConfigMaps"""
        logger.info("Starting ConfigMap watch...")
        
        w = watch.Watch()
        watch_namespace = os.getenv('WATCH_NAMESPACE', '')
        
        try:
            if watch_namespace:
                stream = w.stream(
                    self.core_v1.list_namespaced_config_map,
                    namespace=watch_namespace,
                    label_selector='egress-controller=managed'
                )
            else:
                stream = w.stream(
                    self.core_v1.list_config_map_for_all_namespaces,
                    label_selector='egress-controller=managed'
                )
            
            for event in stream:
                self.process_configmap_event(event['type'], event['object'])
        
        except Exception as e:
            logger.error(f"Watch failed: {e}")
            time.sleep(5)  # Wait before restart


def main():
    """Main entry point"""
    logger.info("Starting EKS Egress Control Agent")
    
    agent = EgressAgent()
    
    while True:
        try:
            agent.start_watching()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(10)


if __name__ == '__main__':
    main()
