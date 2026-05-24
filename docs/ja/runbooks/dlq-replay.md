# Runbook: DLQ リプレイ

## トリガー

CloudWatch Alarm: `*-dlq-depth` — Scheduler DLQ または Lambda 失敗先の `ApproximateNumberOfMessagesVisible > 0` で発火。

## 重大度

**Warning** — データ配信は遅延していますが、損失はありません。メッセージは DLQ に 14 日間保持されます。

## 診断手順

### 1. 失敗メッセージの特定

```bash
# DLQ 深度の確認
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessagesVisible \
  --region ap-northeast-1

# メッセージの確認（削除しない）
aws sqs receive-message \
  --queue-url <dlq-url> \
  --max-number-of-messages 5 \
  --visibility-timeout 0 \
  --region ap-northeast-1
```

### 2. 自動復旧の確認

ポーラーは Checkpoint を使用しているため、次のスケジュール実行で既にリトライされている可能性があります：

```bash
# 現在の Checkpoint を確認
aws ssm get-parameter \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --region ap-northeast-1

# DLQ メッセージのペイロード（Scheduler 入力を含む）と比較
# Checkpoint が DLQ メッセージのキー範囲を超えていれば、自動復旧済み
```

### 3. Lambda ログで根本原因を確認

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-<vendor>-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-3600)*1000))") \
  --filter-pattern "ERROR" \
  --region ap-northeast-1
```

## よくある根本原因

| 原因 | 症状 | 解決策 |
|------|------|--------|
| ベンダー API 障害 | Lambda ログに HTTP 5xx | ベンダー復旧を待つ；次のスケジュールで自動リトライ |
| ベンダーレート制限 | Lambda ログに HTTP 429 | MAX_KEYS_PER_RUN を削減；バックオフを追加 |
| 認証情報の無効化 | Lambda ログに HTTP 401/403 | Secrets Manager でシークレットをローテーション |
| Lambda タイムアウト | ログに "Task timed out" | タイムアウトを延長または MAX_KEYS_PER_RUN を削減 |
| 不正な監査ファイル | ログにパースエラー | Poison-pill — ファイルをスキップし、Checkpoint を手動で前進 |
| S3 AP アクセス拒否 | ログに AccessDenied | IAM + S3 AP ポリシー + ネットワークパスを確認 |

## 解決策: 手動リプレイ

自動復旧が発生していない場合（Checkpoint が前進していない）：

```bash
# オプション A: 次のスケジュール実行で自動リトライを待つ
# （デフォルト動作 — 次の 5 分間隔を待つだけ）

# オプション B: DLQ ペイロードで手動実行
aws sqs receive-message \
  --queue-url <dlq-url> \
  --max-number-of-messages 1 \
  --region ap-northeast-1 > /tmp/dlq-msg.json

# ペイロードを抽出して Lambda を実行
PAYLOAD=$(cat /tmp/dlq-msg.json | jq -r '.Messages[0].Body')
aws lambda invoke \
  --function-name fsxn-<vendor>-integration-shipper \
  --payload "$PAYLOAD" \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 \
  /tmp/replay-response.json

# 成功を確認
cat /tmp/replay-response.json

# リプレイ成功後に DLQ メッセージを削除
RECEIPT=$(cat /tmp/dlq-msg.json | jq -r '.Messages[0].ReceiptHandle')
aws sqs delete-message \
  --queue-url <dlq-url> \
  --receipt-handle "$RECEIPT" \
  --region ap-northeast-1
```

## 解決策: Poison-Pill（不正ファイル）

特定の監査ファイルが繰り返しパースに失敗する場合：

```bash
# 1. Lambda ログから問題のファイルを特定
# 例: "Failed to parse: audit/svm-prod-01/2026/01/15/audit-corrupt.json"

# 2. 不正ファイルを超えるように Checkpoint を手動で前進
aws ssm put-parameter \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --value "audit/svm-prod-01/2026/01/15/audit-corrupt.json" \
  --type String \
  --overwrite \
  --region ap-northeast-1

# 3. DLQ メッセージを削除
aws sqs purge-queue --queue-url <dlq-url> --region ap-northeast-1

# 4. スキップしたファイルを調査用に記録
```

## 確認

解決後：
1. DLQ 深度が 0 に戻ることを確認
2. 次のスケジュール実行で Checkpoint が前進することを確認
3. ベンダープラットフォームにログが到達していることを確認
4. CloudWatch アラームをクリア

## エスカレーション

30 分経過しても問題が解決しない場合：
- AWS Health Dashboard でリージョン障害を確認
- ベンダーステータスページで API 障害を確認
- パイプラインオーナーに連絡（operational-guide.md を参照）

## 予防策

- CloudWatch アラームで DLQ 深度を監視（設定済み）
- ベンダー API ヘルスチェックを設定
- Lambda エラー率を週次でレビュー
- DLQ リプレイ手順を四半期ごとにテスト
