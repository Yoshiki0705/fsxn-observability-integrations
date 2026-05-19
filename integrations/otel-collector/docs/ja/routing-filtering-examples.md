# ルーティングとフィルタリングの例: OTel Collector

## Filter プロセッサー: セキュリティイベントのみ

セキュリティ関連イベント（削除、権限変更、アクセス失敗）のみを抽出:

```yaml
processors:
  filter/security_only:
    logs:
      include:
        match_type: regexp
        record_attributes:
          - key: fsxn.operation
            value: "^(DELETE|SET_ATTR|SET_SECURITY|RENAME|FAILED_.*)$"
```

## Routing コネクター: 重要度/操作種別によるルーティング

操作種別に基づいてイベントを異なるパイプラインにルーティング:

```yaml
connectors:
  routing:
    default_pipelines: [logs/general]
    table:
      # Security-critical operations → SIEM + Grafana + Archive
      - statement: route() where attributes["fsxn.operation"] == "DELETE"
        pipelines: [logs/security]
      - statement: route() where attributes["fsxn.operation"] == "SET_SECURITY"
        pipelines: [logs/security]
      - statement: route() where attributes["fsxn.operation"] == "SET_ATTR"
        pipelines: [logs/security]

      # Failed access attempts → SIEM
      - statement: route() where IsMatch(attributes["fsxn.operation"], "FAILED_.*")
        pipelines: [logs/siem]

      # High-volume read events → cheap storage or drop
      - statement: route() where attributes["fsxn.operation"] == "READ"
        pipelines: [logs/cheap]
      - statement: route() where attributes["fsxn.operation"] == "READDIR"
        pipelines: [logs/cheap]
```

## Redaction プロセッサー: PII マスキング

バックエンドへのエクスポート前に個人識別情報をマスク:

```yaml
processors:
  # Option 1: Redaction processor (block patterns)
  redaction/pii:
    allow_all_keys: true
    blocked_values:
      # IPv4 addresses
      - '(\d{1,3}\.){3}\d{1,3}'
      # Email addresses
      - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
      # Windows domain\user format
      - '[A-Z]+\\[a-zA-Z0-9._-]+'
    blocked_key_values:
      client.address:
        - '.*'
      user.name:
        - '.*'

  # Option 2: Transform processor (selective replacement)
  transform/mask_ip:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["client.address"], "\\d+\\.\\d+\\.\\d+\\.\\d+", "x.x.x.x")
          - replace_pattern(attributes["user.name"], "(.{2}).*", "$1***")
```

## バックエンド別パイプライン分離

バックエンドごとに分離されたパイプラインの完全な設定:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1000

  filter/security_only:
    logs:
      include:
        match_type: regexp
        record_attributes:
          - key: fsxn.operation
            value: "^(DELETE|SET_ATTR|SET_SECURITY|RENAME|FAILED_.*)$"

  filter/drop_reads:
    logs:
      exclude:
        match_type: regexp
        record_attributes:
          - key: fsxn.operation
            value: "^(READ|READDIR|LOOKUP|GETATTR)$"

exporters:
  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

  otlp_http/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${env:HONEYCOMB_API_KEY}
      x-honeycomb-dataset: ${env:HONEYCOMB_DATASET}

  otlp_http/siem:
    endpoint: ${env:SIEM_ENDPOINT}
    headers:
      Authorization: "Bearer ${env:SIEM_API_KEY}"

  otlp_http/archive:
    endpoint: ${env:ARCHIVE_ENDPOINT}

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    # All events (minus reads) → Grafana + Honeycomb
    logs/general:
      receivers: [otlp]
      processors: [filter/drop_reads, batch]
      exporters: [otlp_http/grafana, otlp_http/honeycomb]

    # Security events only → SIEM
    logs/security:
      receivers: [otlp]
      processors: [filter/security_only, batch]
      exporters: [otlp_http/siem]

    # All events (unfiltered) → Archive
    logs/archive:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_http/archive]
```

## ノイジーイベント抑制

Filter プロセッサーを使用して高頻度・低価値イベントを抑制:

```yaml
processors:
  # Drop noisy operations that provide minimal security value
  filter/suppress_noisy:
    logs:
      exclude:
        match_type: regexp
        record_attributes:
          # Drop GETATTR (stat) calls - extremely high volume
          - key: fsxn.operation
            value: "^GETATTR$"
          # Drop LOOKUP (name resolution) - high volume
          - key: fsxn.operation
            value: "^LOOKUP$"
          # Drop ACCESS (permission check) - high volume
          - key: fsxn.operation
            value: "^ACCESS$"

  # Alternative: Probabilistic sampling for read events
  probabilistic_sampler:
    sampling_percentage: 1  # Keep 1% of events
```

## パターン: 削除/権限変更 → セキュリティバックエンド

```yaml
# Route destructive and permission-changing operations to security SIEM
processors:
  filter/destructive:
    logs:
      include:
        match_type: regexp
        record_attributes:
          - key: fsxn.operation
            value: "^(DELETE|RENAME|SET_SECURITY|SET_ATTR|WRITE)$"
          - key: fsxn.result
            value: ".*"  # Include both success and failure

service:
  pipelines:
    logs/security_events:
      receivers: [otlp]
      processors: [filter/destructive, batch]
      exporters: [otlp_http/siem, otlp_http/grafana]
```

## パターン: 読み取りイベント → 安価バックエンドまたはアーカイブ

```yaml
# Route high-volume read events to cost-effective storage
processors:
  filter/reads_only:
    logs:
      include:
        match_type: regexp
        record_attributes:
          - key: fsxn.operation
            value: "^(READ|READDIR|GETATTR|LOOKUP|ACCESS)$"

service:
  pipelines:
    logs/read_events:
      receivers: [otlp]
      processors: [filter/reads_only, batch]
      exporters: [otlp_http/archive]  # Cheap S3-based storage
```

## パターン: アクセス失敗 → SIEM

```yaml
# Route all failed access attempts to SIEM for security alerting
processors:
  filter/failed_access:
    logs:
      include:
        match_type: regexp
        record_attributes:
          - key: fsxn.result
            value: "^(DENIED|FAILED|ERROR|UNAUTHORIZED)$"

service:
  pipelines:
    logs/failed_access:
      receivers: [otlp]
      processors: [filter/failed_access, batch]
      exporters: [otlp_http/siem]
```

## パターン: 大量読み取りログ → サンプリングまたはドロップ

```yaml
# Sample high-volume read events (keep 1%) or drop entirely
connectors:
  routing/volume:
    default_pipelines: [logs/full]
    table:
      - statement: route() where attributes["fsxn.operation"] == "READ"
        pipelines: [logs/sampled_reads]
      - statement: route() where attributes["fsxn.operation"] == "READDIR"
        pipelines: [logs/sampled_reads]
      - statement: route() where attributes["fsxn.operation"] == "GETATTR"
        pipelines: [logs/dropped]

processors:
  probabilistic_sampler/reads:
    sampling_percentage: 1  # Keep 1% of read events

service:
  pipelines:
    logs/input:
      receivers: [otlp]
      processors: [batch]
      exporters: [routing/volume]

    logs/full:
      receivers: [routing/volume]
      exporters: [otlp_http/grafana, otlp_http/honeycomb]

    logs/sampled_reads:
      receivers: [routing/volume]
      processors: [probabilistic_sampler/reads]
      exporters: [otlp_http/grafana]

    # Dropped pipeline - no exporters (events are discarded)
    logs/dropped:
      receivers: [routing/volume]
      processors: []
      exporters: []  # Intentionally empty - events are dropped
```

## パターン: 機密パス → 制限付きバックエンドのみ

```yaml
processors:
  filter/sensitive_path:
    logs:
      include:
        match_type: regexp
        record_attributes:
          - key: fsxn.path
            value: "^/vol.*/confidential/.*"

service:
  pipelines:
    logs/restricted:
      receivers: [otlp]
      processors: [filter/sensitive_path, batch]
      exporters: [otlp_http/siem]  # Only to security backend
```

## 完全なマルチパターン例

すべてのパターンを組み合わせた本番対応設定:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch/default:
    timeout: 5s
    send_batch_size: 1000

  batch/security:
    timeout: 1s
    send_batch_size: 100

  redaction/pii:
    allow_all_keys: true
    blocked_values:
      - '(\d{1,3}\.){3}\d{1,3}'
      - '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

connectors:
  routing/main:
    default_pipelines: [logs/operational]
    table:
      - statement: route() where attributes["fsxn.operation"] == "DELETE" or attributes["fsxn.operation"] == "SET_SECURITY"
        pipelines: [logs/security]
      - statement: route() where IsMatch(attributes["fsxn.result"], "DENIED|FAILED")
        pipelines: [logs/security]
      - statement: route() where attributes["fsxn.operation"] == "READ" or attributes["fsxn.operation"] == "READDIR"
        pipelines: [logs/high_volume]
      - statement: route() where attributes["fsxn.operation"] == "GETATTR" or attributes["fsxn.operation"] == "LOOKUP"
        pipelines: [logs/noise]

exporters:
  otlp_http/grafana:
    endpoint: ${env:GRAFANA_OTLP_ENDPOINT}
    headers:
      Authorization: "Basic ${env:GRAFANA_BASIC_AUTH}"

  otlp_http/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${env:HONEYCOMB_API_KEY}
      x-honeycomb-dataset: ${env:HONEYCOMB_DATASET}

  otlp_http/siem:
    endpoint: ${env:SIEM_ENDPOINT}
    headers:
      Authorization: "Bearer ${env:SIEM_API_KEY}"

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    logs/input:
      receivers: [otlp]
      exporters: [routing/main]

    logs/security:
      receivers: [routing/main]
      processors: [batch/security]
      exporters: [otlp_http/siem, otlp_http/grafana]

    logs/operational:
      receivers: [routing/main]
      processors: [redaction/pii, batch/default]
      exporters: [otlp_http/grafana, otlp_http/honeycomb]

    logs/high_volume:
      receivers: [routing/main]
      processors: [batch/default]
      exporters: [otlp_http/grafana]  # Single backend, no SIEM

    logs/noise:
      receivers: [routing/main]
      processors: []
      exporters: []  # Dropped
```
