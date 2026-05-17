# 運用ガイド

## 概要

FSx for ONTAP Observability パイプラインの日常運用（監視、トラブルシューティング、メンテナンス）をカバーするガイドです。

## 監視

### 主要 CloudWatch メトリクス

| メトリクス | アラーム閾値 | アクション |
|-----------|-------------|----------|
| Lambda Errors | 10分間で5回超 | CloudWatch Logs でエラー詳細を確認 |
| Lambda Throttles | 1回以上 | 同時実行数の引き上げまたはスケジュール間隔の延長 |
| DLQ Messages Visible | 1件以上 | 失敗イベントを調査し、修正後にリプレイ |
| Lambda Duration | タイムアウトの80%超 | タイムアウト延長またはバッチサイズ最適化 |

### 運用ヘルスダッシュボード

パイプラインの健全性を監視するメトリクス:
- Lambda エラー率と実行時間
- チェックポイントラグ（最後に処理したファイルからの経過時間）
- DLQ 深度
- ベンダー API レスポンスコード（Lambda ログ経由）
- 1回の起動あたりの配信ログ数

## DLQ リプレイ手順

イベント処理が失敗し DLQ に到達した場合:

```bash
# 1. DLQ メッセージ数を確認
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages

# 2. サンプルメッセージを確認
aws sqs receive-message \
  --queue-url <dlq-url> \
  --max-number-of-messages 1

# 3. 根本原因を修正後、メッセージをリプレイ
aws sqs start-message-move-task \
  --source-arn <dlq-arn> \
  --destination-arn <main-queue-arn>
```

## チェックポイント管理

パイプラインはチェックポイントを使用して処理済み監査ログファイルを追跡します。

### チェックポイントリセット（全ファイル再処理）

```bash
# 特定 SVM のチェックポイントエントリを削除
aws dynamodb delete-item \
  --table-name fsxn-observability-audit-checkpoint \
  --key '{"svm_name": {"S": "svm-prod-01"}, "file_key": {"S": "LATEST"}}'
```

### 特定ファイルのリプレイ

```bash
# 特定のファイルキーで Lambda を起動
aws lambda invoke \
  --function-name fsxn-datadog-integration-shipper \
  --payload '{"Records":[{"s3":{"bucket":{"name":"<fsx-s3-ap-arn>"},"object":{"key":"audit/svm-prod-01/audit_2026.evtx"}}}]}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/response.json
```

## Secrets Manager ローテーション

API キーは定期的にローテーションすべきです:

```bash
# シークレット値を更新
aws secretsmanager put-secret-value \
  --secret-id <secret-arn> \
  --secret-string '{"api_key": "<new-key>"}'
```

Lambda は実行コンテキストごとに API キーをキャッシュします。ローテーション後、新しいキーは次のコールドスタート時（通常数分以内）に取得されます。

## コスト最適化

### 主要コスト変数

| コンポーネント | コストドライバー | 最適化 |
|-------------|---------------|--------|
| Lambda | 起動回数 × 実行時間 | 低ボリューム SVM ではスケジュール間隔を延長 |
| NAT Gateway | $0.045/時 + $0.045/GB | 可能なら Lambda を VPC 外に配置 |
| EventBridge Scheduler | 100万起動あたり$1 | 最小コスト |
| DynamoDB (checkpoint) | リクエスト課金 | 最小コスト |
| ベンダー取り込み | GB/イベント単位 | 監査ポリシーレベルで不要イベントをフィルタ |

### コスト削減のヒント

1. **read auditing を無効化** — 特に必要でない限り（最もボリュームが多い）
2. **Lambda を VPC 外に配置** — NAT Gateway コストを回避（S3 AP がインターネットアクセス可能な場合）
3. **スケジュール間隔を延長** — 低アクティビティ SVM の場合（例: `rate(15 minutes)`）
4. **ソースでフィルタ** — ONTAP 監査ポリシーで必要なイベントのみをキャプチャ

## マルチアカウントデプロイ

このパターンは2つのデプロイモデルをサポートします:

### アカウント単位（分散型）
- 各ワークロードアカウントが独自のスタックをデプロイ
- 監査ログはアカウント境界内に留まる
- シンプルな IAM、クロスアカウントアクセス不要

### 集約型（ロギングアカウント）
- 全監査ログを専用のロギング/セキュリティアカウントで処理
- クロスアカウント S3 Access Point アクセスが必要
- セキュリティ監視の集約に適している

## アップグレード戦略

```bash
# CloudFormation スタックを更新（ゼロダウンタイム）
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides <同じパラメータ> \
  --capabilities CAPABILITY_NAMED_IAM

# Lambda コードを個別に更新
cd integrations/datadog/lambda
zip function.zip handler.py
aws lambda update-function-code \
  --function-name fsxn-datadog-integration-shipper \
  --zip-file fileb://function.zip
```

## セキュリティレビューチェックリスト

- [ ] IAM ロールが最小権限に従っている（S3 AP ARN のみ、特定の Secret ARN のみ）
- [ ] S3 Access Point ポリシーが Lambda 実行ロールにのみアクセスを制限
- [ ] Secrets Manager シークレットが KMS CMK で暗号化されている
- [ ] DLQ が KMS で暗号化されている
- [ ] Lambda がパブリックサブネットに配置されていない
- [ ] CloudWatch Logs の保持期間が設定されている
- [ ] Lambda 環境変数にシークレットがない（ARN 参照のみ）
- [ ] VPC セキュリティグループが最小限のアウトバウンドのみ許可
