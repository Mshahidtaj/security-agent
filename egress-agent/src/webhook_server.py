#!/usr/bin/env python3

import json
import logging
import os
import base64
from flask import Flask, request, jsonify
from egress_agent import PolicyValidator

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
validator = PolicyValidator()


def create_admission_response(allowed: bool, message: str = "", uid: str = ""):
    """Create Kubernetes admission response"""
    return {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": allowed,
            "status": {
                "code": 200 if allowed else 400,
                "message": message
            }
        }
    }


@app.route('/validate', methods=['POST'])
def validate_configmap():
    """Validate egress policy ConfigMaps"""
    uid = ""  # Initialize uid early
    
    try:
        # Handle JSON parsing errors gracefully
        try:
            admission_review = request.get_json(force=True)
        except Exception as json_error:
            logger.error(f"Failed to parse JSON request: {json_error}")
            return jsonify(create_admission_response(False, "Invalid JSON request", uid)), 400
        
        if not admission_review:
            logger.error("No admission review data received")
            return jsonify(create_admission_response(False, "No data received", uid)), 400
        
        # Extract request details
        req = admission_review.get('request', {})
        uid = req.get('uid', '')
        configmap = req.get('object', {})
        operation = req.get('operation', '')
        
        logger.info(f"Validating {operation} operation for ConfigMap {configmap.get('metadata', {}).get('name', 'unknown')}")
        
        # Only validate egress policy ConfigMaps
        labels = configmap.get('metadata', {}).get('labels', {})
        if labels.get('egress-controller') != 'managed':
            logger.debug("ConfigMap not managed by egress-controller, allowing")
            return jsonify(create_admission_response(True, "Not an egress policy ConfigMap", uid))
        
        # Validate policy data
        data = configmap.get('data', {})
        policy_json = data.get('policy.json', '')
        
        if not policy_json.strip():
            return jsonify(create_admission_response(
                False, "Missing policy.json in ConfigMap data", uid
            )), 400
        
        # Parse and validate JSON
        try:
            policy = json.loads(policy_json)
        except json.JSONDecodeError as e:
            return jsonify(create_admission_response(
                False, f"Invalid JSON in policy.json: {str(e)}", uid
            )), 400
        
        # Validate policy structure
        validation_result = validator.validate(policy)
        
        if validation_result.is_valid:
            logger.info(f"Policy validation successful for ConfigMap {configmap.get('metadata', {}).get('name')}")
            return jsonify(create_admission_response(True, "Policy validation successful", uid))
        else:
            error_msg = f"Policy validation failed: {'; '.join(validation_result.errors)}"
            logger.warning(error_msg)
            return jsonify(create_admission_response(False, error_msg, uid)), 400
    
    except Exception as e:
        logger.error(f"Webhook validation error: {str(e)}")
        return jsonify(create_admission_response(
            False, f"Internal validation error: {str(e)}", uid
        )), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "egress-policy-webhook"}), 200


@app.route('/ready', methods=['GET'])
def readiness_check():
    """Readiness check endpoint"""
    return jsonify({"status": "ready", "service": "egress-policy-webhook"}), 200


if __name__ == '__main__':
    # Get configuration
    port = int(os.getenv('WEBHOOK_PORT', 8443))
    host = os.getenv('WEBHOOK_HOST', '0.0.0.0')
    
    # TLS configuration for production
    cert_file = os.getenv('TLS_CERT_FILE', '/etc/certs/tls.crt')
    key_file = os.getenv('TLS_KEY_FILE', '/etc/certs/tls.key')
    
    logger.info(f"Starting webhook server on {host}:{port}")
    
    # Run with TLS in production, without in development
    if os.path.exists(cert_file) and os.path.exists(key_file):
        logger.info("Running with TLS enabled")
        app.run(host=host, port=port, ssl_context=(cert_file, key_file))
    else:
        logger.warning("Running without TLS (development mode)")
        app.run(host=host, port=port, debug=True)
