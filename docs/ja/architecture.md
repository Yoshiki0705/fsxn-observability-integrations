# アーキテクチャ

## 全体構成

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  FSx for ONTAP  │────▶│  S3 Access Point │────▶│   EventBridge   │
│  (監査ログ)      │     │  (ログ出力先)      │     │  / S3 Event     │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Observability  │◀────│     Lambda       │◀────│  EventBridge    │
│  Vendor API     │     │  (ログ変換・配信)  │     │  Rule           │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## コンポーネント詳細

### 1. FSx for NetApp ONTAP 監査ログ

FSx for ONTAP の監査ログ機能を有効化し、S3 バケットへ出力します。

- **ログ形式**: EVTX (Windows Event Log) または JSON
- **出力先**: S3 バケット（S3 Access Point 経由でアクセス制御）
- **ログ内容**: ファイルアクセス、管理操作、認証イベント

### 2. S3 Access Point

S3 Access Point を使用して、監査ログへのアクセスを制御します。

- **目的**: きめ細かいアクセス制御、VPC 制限
- **利点**: バケットポリシーを変更せずにアクセス管理が可能
- **VPC 制限**: VPC エンドポイント経由のみアクセス可能に設定可能

### 3. イベント通知

S3 Access Point へのオブジェクト作成をトリガーとして Lambda を起動します。

**パターン A: EventBridge**
- S3 イベント通知を EventBridge に送信
- EventBridge ルールでフィルタリング
- Lambda をターゲットとして起動

**パターン B: S3 Event Notification**
- S3 バケットのイベント通知を直接 Lambda に送信
- シンプルだがフィルタリング機能が限定的

### 4. Lambda 関数

監査ログを取得・パースし、各ベンダーの API へ配信します。

- **ランタイム**: Python 3.12
- **処理フロー**:
  1. S3 Access Point からログファイル取得
  2. EVTX/JSON パース
  3. ベンダー固有フォーマットへ変換
  4. API エンドポイントへバッチ送信
  5. 失敗時リトライ（exponential backoff）

### 5. 代替パターン: Kinesis Data Firehose

大量ログの場合、Firehose 経由で直接ベンダーへ配信します。

```
S3 AP → Lambda (変換) → Kinesis Data Firehose → ベンダー API
```

- **利点**: 自動バッファリング、リトライ、スケーリング
- **対応ベンダー**: Splunk (HEC), Datadog, New Relic, HTTP エンドポイント全般

## セキュリティ設計

### IAM 最小権限

```yaml
# Lambda 実行ロール
- s3:GetObject (Access Point ARN のみ)
- secretsmanager:GetSecretValue (API Key Secret のみ)
- logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
- kms:Decrypt (暗号化キー使用時)
```

### シークレット管理

- API キーは AWS Secrets Manager に保存
- Lambda 環境変数には ARN のみ設定
- KMS カスタマーマネージドキーで暗号化推奨

### ネットワーク

- VPC エンドポイント経由で S3 Access Point にアクセス
- Lambda は VPC 内配置（外部 API 呼び出し時は NAT Gateway 経由）
- セキュリティグループで最小限のアウトバウンドのみ許可

## 監視・アラート

- **CloudWatch Metrics**: Lambda エラー率、実行時間、スロットリング
- **CloudWatch Alarms**: 配信失敗率閾値超過時に SNS 通知
- **Dead Letter Queue**: 処理失敗イベントを SQS DLQ に退避
- **X-Ray**: 分散トレーシングによるボトルネック特定
