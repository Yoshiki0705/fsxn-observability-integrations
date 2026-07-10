# Security Hardening Guide: OTel Collector

🌐 [日本語](../ja/security-hardening.md) | **English** (this page)

## Collector as Trust Boundary

The OTel Collector acts as a trust boundary between log producers (Lambda) and external backends. All credentials, routing decisions, and data transformations are centralized at this layer.

```
┌─────────────────┐     ┌──────────────────────────────────┐     ┌──────────┐
│  Lambda (VPC)   │────▶│  OTel Collector (Trust Boundary)  │────▶│ Backends │
│  No backend     │OTLP │  - Credentials                    │     │ (Public) │
│  credentials    │     │  - Redaction                      │     └──────────┘
└─────────────────┘     │  - Routing                        │
                        └──────────────────────────────────┘
```

## Hardening Checklist

- [ ] **Private subnet**: Collector deployed in private subnet (no public IP)
- [ ] **Security Group rules**: Inbound 4318 (OTLP) from Lambda SG only; outbound 443 to backend endpoints only
- [ ] **Secrets Manager injection**: All credentials injected via `${env:SECRET_NAME}` from Secrets Manager
- [ ] **Least privilege IAM**: Task role has only `secretsmanager:GetSecretValue` for specific secret ARNs
- [ ] **No secret literals**: Zero hardcoded secrets in config YAML or environment variables
- [ ] **Egress restriction**: Outbound traffic limited to known backend endpoints via SG or VPC endpoint
- [ ] **No secrets in logs**: Collector log level set to `info` (not `debug`); debug mode may log headers
- [ ] **Config review**: All config changes reviewed via PR before deployment
- [ ] **Image pinning**: Collector image pinned to specific version tag (e.g., `0.152.0`), not `latest`
- [ ] **Read-only filesystem**: Container filesystem mounted read-only where possible

## ECS Task Execution Role vs Task Role Separation

```yaml
# Task Execution Role: Used by ECS agent to pull image and inject secrets
TaskExecutionRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    Policies:
      - PolicyName: SecretsAccess
        PolicyDocument:
          Statement:
            - Effect: Allow
              Action:
                - secretsmanager:GetSecretValue
              Resource:
                - arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fsxn/otel/*

# Task Role: Used by the Collector container at runtime
TaskRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: MinimalRuntime
        PolicyDocument:
          Statement:
            - Effect: Allow
              Action:
                - logs:CreateLogStream
                - logs:PutLogEvents
              Resource: "*"
```

**Key distinction**:
- **Execution Role**: Pulls secrets at container start, injects as env vars
- **Task Role**: Runtime permissions only (logging, metrics); NO secret access at runtime

## Secret Rotation Pattern

```bash
# 1. Create secret with rotation enabled
aws secretsmanager create-secret \
  --name fsxn/otel/grafana-auth \
  --secret-string '{"basic_auth":"<base64-encoded>"}' \
  --tags Key=Environment,Value=production

# 2. Configure rotation (Lambda-based)
aws secretsmanager rotate-secret \
  --secret-id fsxn/otel/grafana-auth \
  --rotation-lambda-arn arn:aws:lambda:ap-northeast-1:123456789012:function:secret-rotator \
  --rotation-rules AutomaticallyAfterDays=90
```

**Rotation workflow**:
1. Secrets Manager invokes rotation Lambda
2. Rotation Lambda generates new credential at backend
3. New secret version stored as `AWSPENDING`
4. ECS task redeployed to pick up new secret
5. Old version marked `AWSPREVIOUS`

## TLS/mTLS Between Lambda and Collector

### Option A: TLS (Server-side only)

```yaml
# Collector config: Enable TLS on receiver
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /etc/otel/tls/server.crt
          key_file: /etc/otel/tls/server.key
```

### Option B: mTLS (Mutual authentication)

```yaml
# Collector config: Require client certificate
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /etc/otel/tls/server.crt
          key_file: /etc/otel/tls/server.key
          client_ca_file: /etc/otel/tls/ca.crt
```

**When to use mTLS**: When Collector is exposed beyond a single VPC or when zero-trust networking is required.

**When TLS is sufficient**: When Lambda and Collector are in the same VPC with Security Group isolation.

## Collector Auth Extension

Use the `basicauth` extension to require authentication on the OTLP receiver:

```yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
  basicauth/server:
    htpasswd:
      inline: |
        ${env:OTEL_RECEIVER_USERNAME}:${env:OTEL_RECEIVER_PASSWORD}

receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        auth:
          authenticator: basicauth/server

service:
  extensions: [health_check, basicauth/server]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_http/grafana]
```

## Redaction Processor for PII/Sensitive Fields

Use the `redaction` processor to mask sensitive data before export:

```yaml
processors:
  redaction:
    allow_all_keys: true
    blocked_values:
      # Mask IP addresses
      - '(\d{1,3}\.){3}\d{1,3}'
      # Mask email addresses
      - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    blocked_key_values:
      # Mask specific attribute values
      client.address:
        - '.*'
      user.email:
        - '.*'
    summary: debug

  # Alternative: Use transform processor for selective redaction
  transform:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["client.address"], "\\d+\\.\\d+\\.\\d+\\.\\d+", "***REDACTED***")
```

## Private Endpoint Design

### VPC Endpoints for Backend Access

```yaml
# VPC Endpoint for Secrets Manager
SecretsManagerEndpoint:
  Type: AWS::EC2::VPCEndpoint
  Properties:
    VpcId: !Ref VpcId
    ServiceName: !Sub com.amazonaws.${AWS::Region}.secretsmanager
    VpcEndpointType: Interface
    SubnetIds: !Ref PrivateSubnetIds
    SecurityGroupIds:
      - !Ref EndpointSecurityGroup
    PrivateDnsEnabled: true

# Security Group for VPC Endpoints
EndpointSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: VPC Endpoint access from Collector
    VpcId: !Ref VpcId
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 443
        ToPort: 443
        SourceSecurityGroupId: !Ref CollectorSecurityGroup
```

### Network Architecture

```
┌─────────────────────────────────────────────────────────┐
│  VPC (Private Subnets)                                   │
│                                                          │
│  ┌──────────┐    ┌───────────────┐    ┌──────────────┐  │
│  │  Lambda  │───▶│ OTel Collector │───▶│ NAT Gateway  │──┼──▶ Backends
│  │  (SG-A)  │4318│   (SG-B)      │443 │              │  │
│  └──────────┘    └───────────────┘    └──────────────┘  │
│                         │                                │
│                         │ 443                            │
│                         ▼                                │
│                  ┌──────────────┐                        │
│                  │ VPC Endpoint │                        │
│                  │ (Secrets Mgr)│                        │
│                  └──────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

### Security Group Rules

| SG | Direction | Port | Source/Dest | Purpose |
|----|-----------|------|-------------|---------|
| SG-A (Lambda) | Outbound | 4318 | SG-B | OTLP to Collector |
| SG-B (Collector) | Inbound | 4318 | SG-A | Accept OTLP from Lambda |
| SG-B (Collector) | Outbound | 443 | 0.0.0.0/0 (or endpoint SG) | Export to backends |
| SG-B (Collector) | Inbound | 13133 | SG-A (or monitoring) | Health check |
