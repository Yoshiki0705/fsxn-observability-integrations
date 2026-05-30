# OTel Collector PII 墨消しクックブック

## 概要

このクックブックでは、FSx for ONTAP 監査ログ内の PII フィールドを Observability バックエンドに到達する前に墨消し、仮名化、または一般化するための、すぐに使える OTel Collector プロセッサ設定を提供します。

以下のケースで使用してください:
- JP データレジデンシーのないベンダーにログを送信する場合
- ユーザー名を見るべきでないチームとダッシュボードを共有する場合
- データ最小化要件（GDPR、APPI）に準拠する場合
- セキュリティ調査（完全忠実度）と運用監視（墨消し済み）を分離する場合

## 前提条件

- OTel Collector がデプロイ済み（[OTel Collector README](../../README.md) を参照）
- Collector バージョン 0.90 以上（`transform` プロセッサのサポートに必要）

## FSx for ONTAP 監査ログの PII フィールド

| フィールド | リスクレベル | 例 | 墨消し戦略 |
|-------|-----------|---------|-------------------|
| `user.name` / `UserName` | 高（PII） | `admin@corp.local` | ハッシュ化または削除 |
| `fsxn.path` / `ObjectName` | 中（機密） | `/vol/hr/salary.xlsx` | 一般化またはハッシュ化 |
| `source.ip` / `ClientIP` | 低（内部） | `10.0.x.x` | 通常は保持; 必要に応じて削除 |
| `fsxn.svm` | 低（インフラ） | `svm-prod-01` | 通常は保持 |

## レシピ 1: PII フィールドの削除

最もシンプルなアプローチ — フィールドを完全に削除します。

```yaml
processors:
  attributes/delete-pii:
    actions:
      - key: user.name
        action: delete
      - key: UserName
        action: delete
      - key: source.ip
        action: delete
      - key: ClientIP
        action: delete
```

**トレードオフ**: ユーザーごとのアクティビティを調査できなくなります。運用監視でユーザー識別が不要な場合に使用してください。

## レシピ 2: ユーザーフィールドのハッシュ化（仮名化）

一方向ハッシュにより、ID を明かさずに GROUP BY のカーディナリティを維持します。

```yaml
processors:
  transform/hash-users:
    log_statements:
      - context: log
        statements:
          - set(attributes["user.name.hash"], SHA256(Concat([attributes["user.name"], "your-salt-here"])))
          - delete_key(attributes, "user.name")
          - set(attributes["UserName.hash"], SHA256(Concat([attributes["UserName"], "your-salt-here"])))
          - delete_key(attributes, "UserName")
```

**トレードオフ**: ハッシュ化されたユーザーで GROUP BY は可能ですが、ソルトなしでは実際のユーザー名に逆変換できません。セキュリティチームが調査用にソルトを保持します。

## レシピ 3: ファイルパスの一般化

トップレベルのディレクトリ構造を保持し、具体的なファイル名を削除します。

```yaml
processors:
  transform/generalize-paths:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/***")
          - replace_pattern(attributes["ObjectName"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/***")
```

**結果**: `/vol/hr/employee-records/john-doe-salary-2026.xlsx` が `/vol/hr/employee-records/***` になります

**トレードオフ**: 具体的なファイル識別はできなくなりますが、ディレクトリレベルのアクセスパターンは保持されます。

## レシピ 4: 条件付き墨消し（セキュリティ用は保持、運用用は墨消し）

完全忠実度のログをセキュリティバックエンドに、墨消し済みログを運用バックエンドにルーティングします。

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  attributes/redact-for-ops:
    actions:
      - key: user.name
        action: delete
      - key: UserName
        action: delete
      - key: source.ip
        action: delete

  transform/generalize-for-ops:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+/[^/]+)/.*", "$$1/***")

exporters:
  otlphttp/security:
    endpoint: https://security-backend.example.com
    headers:
      Authorization: "Bearer ${SECURITY_TOKEN}"

  otlphttp/ops:
    endpoint: https://ops-backend.example.com
    headers:
      Authorization: "Bearer ${OPS_TOKEN}"

service:
  pipelines:
    logs/security:
      receivers: [otlp]
      processors: []
      exporters: [otlphttp/security]

    logs/ops:
      receivers: [otlp]
      processors: [attributes/redact-for-ops, transform/generalize-for-ops]
      exporters: [otlphttp/ops]
```

## レシピ 5: APPI 準拠設定（日本）

APPI の対象となる日本企業向けに、データを JP リージョンに保持しユーザー名を仮名化します:

```yaml
processors:
  transform/appi:
    log_statements:
      - context: log
        statements:
          - set(attributes["user.hash"], SHA256(Concat([attributes["user.name"], "${HASH_SALT}"])))
          - delete_key(attributes, "user.name")
          - delete_key(attributes, "UserName")

exporters:
  otlphttp/sumo-jp:
    endpoint: https://collectors.jp.sumologic.com/receiver/v1/http/${SUMO_TOKEN}
    headers:
      X-Sumo-Category: aws/fsxn/audit
```

## レシピ 6: GDPR データ最小化

EU デプロイメント向けに、厳密に必要なデータのみに最小化します:

```yaml
processors:
  attributes/gdpr-minimize:
    actions:
      - key: user.name
        action: delete
      - key: UserName
        action: delete
      - key: source.ip
        action: delete
      - key: ClientIP
        action: delete

  transform/gdpr-paths:
    log_statements:
      - context: log
        statements:
          - replace_pattern(attributes["fsxn.path"], "^(/[^/]+/[^/]+)/.*", "$$1/***")
```

## レシピ 7: 機密パスの検出とルーティング

機密パスを含むログを制限付きパイプラインにルーティングします:

```yaml
processors:
  transform/classify:
    log_statements:
      - context: log
        conditions:
          - IsMatch(attributes["fsxn.path"], ".*(confidential|restricted|hr|finance).*")
        statements:
          - set(attributes["sensitivity"], "high")
      - context: log
        conditions:
          - not IsMatch(attributes["fsxn.path"], ".*(confidential|restricted|hr|finance).*")
        statements:
          - set(attributes["sensitivity"], "normal")
```

## 墨消しのテスト

本番環境に適用する前に墨消し設定を検証してください:

```bash
# 1. debug exporter で Collector を起動
otelcol --config redaction-test-config.yaml

# 2. PII を含むテストログを送信
curl -X POST http://localhost:4318/v1/logs \
  -H "Content-Type: application/json" \
  -d '{
    "resourceLogs": [{
      "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "test"}}]},
      "scopeLogs": [{
        "logRecords": [{
          "body": {"stringValue": "test"},
          "attributes": [
            {"key": "user.name", "value": {"stringValue": "admin@corp.local"}},
            {"key": "fsxn.path", "value": {"stringValue": "/vol/hr/salary/john.xlsx"}}
          ]
        }]
      }]
    }]
  }'

# 3. debug 出力を確認 -- user.name が存在しないかハッシュ化されていること
```

## 関連ドキュメント

- [データ分類ガイド](../../../../docs/ja/data-classification.md)
- [保持ポリシーマトリクス](../../../../docs/ja/retention-policy-matrix.md)
- [OTel Collector README](../../README.md)
