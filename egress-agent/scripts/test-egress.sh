#!/bin/bash

set -e

NAMESPACE=${1:-default}
TEST_POD="egress-test-$(date +%s)"

echo "🧪 Testing egress policies in namespace: $NAMESPACE"

# Create test pod
echo "📦 Creating test pod..."
kubectl run $TEST_POD \
  --image=curlimages/curl:latest \
  --namespace=$NAMESPACE \
  --restart=Never \
  --rm -i --tty \
  --command -- /bin/sh -c "

echo '🔍 Testing egress connectivity...'

# Test allowed destinations (should work)
echo '✅ Testing allowed destinations:'

# Test S3 (if allowed)
echo -n '  S3 (s3.amazonaws.com:443): '
if timeout 5 curl -s --connect-timeout 3 https://s3.amazonaws.com > /dev/null 2>&1; then
  echo '✅ ALLOWED'
else
  echo '❌ BLOCKED'
fi

# Test internal network (if allowed)
echo -n '  Internal (10.0.0.1:80): '
if timeout 3 curl -s --connect-timeout 2 http://10.0.0.1:80 > /dev/null 2>&1; then
  echo '✅ ALLOWED'
else
  echo '❌ BLOCKED'
fi

echo
echo '❌ Testing blocked destinations:'

# Test external services (should be blocked)
echo -n '  Google DNS (8.8.8.8:53): '
if timeout 3 curl -s --connect-timeout 2 http://8.8.8.8:53 > /dev/null 2>&1; then
  echo '❌ ALLOWED (should be blocked!)'
else
  echo '✅ BLOCKED'
fi

echo -n '  External HTTP (httpbin.org:80): '
if timeout 3 curl -s --connect-timeout 2 http://httpbin.org:80 > /dev/null 2>&1; then
  echo '❌ ALLOWED (should be blocked!)'
else
  echo '✅ BLOCKED'
fi

echo
echo '📋 Test completed!'
"

echo "✨ Egress test completed for namespace: $NAMESPACE"
