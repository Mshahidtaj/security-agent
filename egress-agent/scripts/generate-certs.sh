#!/bin/bash

set -e

NAMESPACE=${1:-egress-control}
SERVICE_NAME="egress-webhook"
SECRET_NAME="webhook-certs"

echo "🔐 Generating TLS certificates for webhook..."

# Create temporary directory
TMPDIR=$(mktemp -d)
cd $TMPDIR

# Generate CA private key
openssl genrsa -out ca.key 2048

# Generate CA certificate
openssl req -new -x509 -key ca.key -sha256 -subj "/C=US/ST=CA/O=EgressAgent/CN=EgressCA" -days 3650 -out ca.crt

# Generate server private key
openssl genrsa -out tls.key 2048

# Create certificate signing request
cat > csr.conf <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
C=US
ST=CA
O=EgressAgent
CN=${SERVICE_NAME}.${NAMESPACE}.svc

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${SERVICE_NAME}
DNS.2 = ${SERVICE_NAME}.${NAMESPACE}
DNS.3 = ${SERVICE_NAME}.${NAMESPACE}.svc
DNS.4 = ${SERVICE_NAME}.${NAMESPACE}.svc.cluster.local
EOF

# Generate certificate signing request
openssl req -new -key tls.key -out server.csr -config csr.conf

# Generate server certificate
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out tls.crt -days 365 -extensions req_ext -extfile csr.conf

echo "📋 Creating Kubernetes secret..."

# Create namespace if it doesn't exist
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Create secret with certificates
kubectl create secret tls $SECRET_NAME \
    --cert=tls.crt \
    --key=tls.key \
    --namespace=$NAMESPACE \
    --dry-run=client -o yaml | kubectl apply -f -

# Get CA bundle for webhook configuration
CA_BUNDLE=$(base64 < ca.crt | tr -d '\n')

echo "🔧 Updating webhook configuration..."

# Update webhook configuration with CA bundle
kubectl patch validatingadmissionwebhook egress-policy-validator \
    --type='json' \
    -p="[{'op': 'replace', 'path': '/webhooks/0/clientConfig/caBundle', 'value': '$CA_BUNDLE'}]"

echo "✅ Certificates generated and configured successfully!"
echo "📁 CA Bundle: $CA_BUNDLE"

# Cleanup
cd - > /dev/null
rm -rf $TMPDIR
