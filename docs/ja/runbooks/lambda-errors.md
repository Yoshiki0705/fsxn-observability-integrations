# Runbook: Lambda エラーアラーム

## トリガー

CloudWatch Alarm: `*-lambda-errors` — Lambda Errors が 10 分間で 5 回を超えた場合に発火。

## 重大度

**Warning** — パイプライン配信が劣化しています。一部の監査ログが遅延する可能性があります。

## 診断手順

### 1. Lambda エラーログの確認

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-<vendor>-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-1800)*1000))") \
  --filter-pattern "ERROR" \
  --region ap-northeast-1 \
  --limit 20
```

### 2. エラーパターンの特定

| エラーパターン | 想定される原因 | 解決策 |
|--------------|--------------|--------|
| `Task timed out after X seconds` | Lambda タイムアウト | タイムアウトを延長または MAX_KEYS_PER_RUN を削減 |
| `AccessDenied` on S3 | IAM または S3 AP ポリシー | IAM ロール + S3 AP リソースポリシーを確認 |
| `HTTP 401` / `HTTP 403` | ベンダー認証情報の期限切れ | Secrets Manager でシークレットをローテーション |
| `HTTP 429` | ベンダーレート制限 | バッチサイズを削減、バックオフを追加 |
| `HTTP 5xx` | ベンダー API 障害 | 待機；ベンダーステータスページを確認 |
| `ConnectionError` / `Timeout` | ネットワーク問題 | VPC 設定、NAT Gateway、セキュリティグループを確認 |
| `JSONDecodeError` / `ParseError` | 不正な監査ファイル | Poison-pill — DLQ リプレイ Runbook を参照 |
| `ResourceNotFoundException` | SSM パラメータまたはシークレットが削除済み | 不足リソースを再作成 |

### 3. DLQ にメッセージがあるか確認

```bash
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessagesVisible
```

DLQ にメッセージがある場合は、[DLQ リプレイ Runbook](dlq-replay.md) に従ってください。

## 根本原因別の解決策

### ベンダー認証情報の期限切れ

```bash
# シークレット値を更新
aws secretsmanager update-secret \
  --secret-id <vendor>/fsxn-credentials \
  --secret-string '{"api_key":"<new-key>"}' \
  --region ap-northeast-1
```

Lambda は次のコールドスタート時（数分以内）に新しい認証情報を取得します。

### Lambda タイムアウト

```bash
# 実行あたりの処理量を削減
aws lambda update-function-configuration \
  --function-name fsxn-<vendor>-integration-shipper \
  --environment "Variables={MAX_KEYS_PER_RUN=50,SAFETY_THRESHOLD_MS=45000}" \
  --region ap-northeast-1
```

### ネットワーク問題（VPC Lambda）

以下を確認：
1. セキュリティグループがアウトバウンド HTTPS（ポート 443）を許可
2. NAT Gateway が正常（Lambda がインターネットアクセスを必要とする場合）
3. S3 Gateway Endpoint が存在（VPC から S3 AP にアクセスする場合）

### ベンダー API 障害

1. ベンダーステータスページを確認
2. ベンダー復旧時にエラーは自動解消
3. DLQ が失敗した Scheduler 実行をリプレイ用に保持
4. 次のスケジュール実行が Checkpoint からリトライ

## 確認

解決後：
1. 次のスケジュール実行を待つ（5 分）
2. Lambda が成功することを確認（ログにエラーなし）
3. Checkpoint が前進することを確認
4. アラームが OK 状態に戻ることを確認

## エスカレーション

解決試行後 1 時間以上エラーが継続する場合：
- CloudWatch Logs Insights でエラートレンドを確認
- AWS Health Dashboard でリージョン障害を確認
- パイプラインオーナーに連絡
