# EKS Egress Control Agent

Multi-tenant egress policy controller for EKS clusters using AWS VPC CNI.

## Features

- **ConfigMap-based Policy Definition** - Simple YAML/JSON configuration
- **AWS Service CIDR Resolution** - Maps AWS services to IP ranges
- **Multi-tenant Isolation** - Namespace-scoped policy management
- **NetworkPolicy Generation** - Creates standard Kubernetes NetworkPolicies
- **Test-Driven Development** - Comprehensive test coverage

## Quick Start

```bash
# Local development
make test
make run-local

# Container deployment
make build
make deploy
```

## Policy Configuration

Create a ConfigMap in your tenant namespace:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: egress-policy
  namespace: tenant-a
  labels:
    egress-controller: "managed"
data:
  policy.json: |
    {
      "defaultAction": "deny",
      "allowedDestinations": [
        {
          "name": "s3-access",
          "awsService": "s3",
          "regions": ["us-east-1"],
          "ports": [443]
        },
        {
          "name": "onprem-db",
          "cidr": "10.1.100.0/24",
          "ports": [5432]
        }
      ]
    }
```

## Architecture

```
ConfigMap → Agent → NetworkPolicy → AWS VPC CNI
```

The agent watches ConfigMaps with label `egress-controller: managed` and generates corresponding NetworkPolicies.

## Development

```bash
# Run tests
make test

# Run locally (requires kubeconfig)
make run-local

# Build container
make build

# Deploy to cluster
make deploy

# View logs
make logs

# Cleanup
make clean
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `KUBECONFIG` | `~/.kube/config` | Kubernetes config file |
| `LOG_LEVEL` | `INFO` | Logging level |
| `WATCH_NAMESPACE` | `""` | Namespace to watch (empty = all) |
| `DRY_RUN` | `false` | Don't create NetworkPolicies |

## Policy Schema

```json
{
  "defaultAction": "deny|allow",
  "allowedDestinations": [
    {
      "name": "string",
      "cidr": "10.0.0.0/8",
      "ports": [80, 443]
    },
    {
      "name": "string", 
      "awsService": "s3|rds|ec2",
      "regions": ["us-east-1"],
      "ports": [443]
    }
  ]
}
```
