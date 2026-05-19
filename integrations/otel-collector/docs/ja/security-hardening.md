# セキュリティハードニングガイド: OTel Collector

## Collector を信頼境界として

OTel Collector はログプロデューサー（Lambda）と外部バックエンド間の信頼境界として機能する。すべての認証情報、ルーティング判断、データ変換がこのレイヤーに集約される。

```
┌─────────────────┐     ┌──────────────────────────────────┐     ┌──────────┐
│  Lambda (VPC)   │────▶│  OTel Collector (Trust Boundary)  │────▶│ Backends │
│  No backend     │OTLP │  - Credentials                    │     │ (Public) │
│  credentials    │     │  - Redaction                      │     └──────────┘
└─────────────────┘     │  - Routing                        │
                        └──────────────────────────────────┘
```

## ハードニングチェックリスト

- [ ] **プライベートサブネット**: Collector をプライベートサブネットにデプロイ（パブリック IP なし）
- [ ] **Security Group ルール**: インバウンド 4318（OTLP）は Lambda SG からのみ; アウトバウンド 443 はバックエンドエンドポイントのみ
- [ ] **Secrets Manager 注入**: すべての認証情報は `${env:SECRET_NAME}` で Secrets Manager から注入
- [ ] **最小権限 IAM**: タスクロールは特定のシークレット ARN に対する `secretsmanager:GetSecretValue` のみ
- [ ] **シークレットリテラル禁止**: 設定 YAML や環境変数にハードコードされたシークレットがゼロ
- [ ] **エグレス制限**: アウトバウンドトラフィックを既知のバックエンドエンドポイントに SG または VPC エンドポイントで制限
- [ ] **ログにシークレットなし**: Collector ログレベルを `info` に設定（`debug` ではない）; debug モードはヘッダーをログに出力する可能性あり
- [ ] **設定レビュー**: すべての設定変更はデプロイ前に PR レビュー
- [ ] **イメージ固定**: Collector イメージを特定バージョンタグに固定（例: `0.152.0`）、`latest` は使用しない
- [ ] **読み取り専用ファイルシステム**: コンテナファイルシステムを可能な限り読み取り専用でマウント

## ECS タスク実行ロール vs タスクロールの分離

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

**重要な区別**:
- **実行ロール**: コンテナ起動時にシークレットを取得し、環境変数として注入
- **タスクロール**: ランタイム権限のみ（ロギング、メトリクス）; ランタイム時のシークレットアクセスなし

## シークレットローテーションパターン

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

**ローテーションワークフロー**:
1. Secrets Manager がローテーション Lambda を呼び出し
2. ローテーション Lambda がバックエンドで新しい認証情報を生成
3. 新しいシークレットバージョンが `AWSPENDING` として保存
4. ECS タスクが再デプロイされ新しいシークレットを取得
5. 旧バージョンが `AWSPREVIOUS` としてマーク

## Lambda と Collector 間の TLS/mTLS

### オプション A: TLS（サーバー側のみ）

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

### オプション B: mTLS（相互認証）

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

**mTLS を使用する場合**: Collector が単一 VPC を超えて公開される場合、またはゼロトラストネットワーキングが必要な場合。

**TLS で十分な場合**: Lambda と Collector が同一 VPC 内で Security Group による分離がある場合。

## Collector Auth Extension

`basicauth` エクステンションを使用して OTLP レシーバーに認証を要求:

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

## PII/機密フィールドのリダクションプロセッサー

`redaction` プロセッサーを使用してエクスポート前に機密データをマスク:

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

## プライベートエンドポイント設計

### バックエンドアクセス用 VPC エンドポイント

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

### ネットワークアーキテクチャ

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

### Security Group ルール

| SG | 方向 | ポート | ソース/宛先 | 目的 |
|----|------|--------|-------------|------|
| SG-A (Lambda) | アウトバウンド | 4318 | SG-B | OTLP を Collector へ |
| SG-B (Collector) | インバウンド | 4318 | SG-A | Lambda からの OTLP 受信 |
| SG-B (Collector) | アウトバウンド | 443 | 0.0.0.0/0 (またはエンドポイント SG) | バックエンドへのエクスポート |
| SG-B (Collector) | インバウンド | 13133 | SG-A (またはモニタリング) | ヘルスチェック |
