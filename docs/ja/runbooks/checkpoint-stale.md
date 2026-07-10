# Runbook: Checkpoint 滞留

🌐 **日本語**（このページ） | [English](../../en/runbooks/checkpoint-stale.md)

## トリガー

カスタム CloudWatch Alarm: `*-checkpoint-stale` — SSM Parameter Store の Checkpoint が 15 分以上更新されていない場合（スケジュール間隔 3 回分の未更新）に発火。

## 重大度

**Warning** — 監査ログ処理が停止しています。新しいファイルが蓄積されていますが、配信されていません。

## 診断手順

### 1. 現在の Checkpoint 経過時間を確認

```bash
# Checkpoint の最終更新時刻を取得
aws ssm get-parameter \
  --name "/fsxn/<vendor>/audit-checkpoint" \
  --region ap-northeast-1 \
  --query 'Parameter.LastModifiedDate'

# 現在時刻と比較 — 15 分以上経過していれば処理が停止
```

### 2. Scheduler が Lambda を実行しているか確認

```bash
# 最近の Lambda 実行
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-<vendor>-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-1800)*1000))") \
  --region ap-northeast-1 \
  --limit 5
```

最近の実行がない場合：Scheduler が無効化またはスロットリングされている可能性があります。

### 3. EventBridge Scheduler の状態を確認

```bash
aws scheduler get-schedule \
  --name fsxn-<vendor>-audit-schedule \
  --region ap-northeast-1 \
  --query 'State'
```

### 4. Lambda がスロットリングされていないか確認

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=fsxn-<vendor>-integration-shipper \
  --start-time $(date -u -v-30M +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region ap-northeast-1
```

## よくある根本原因

| 原因 | 症状 | 解決策 |
|------|------|--------|
| Scheduler 無効化 | Lambda 実行なし | Scheduler を再有効化 |
| Lambda スロットリング | Throttle メトリクス > 0 | 予約同時実行数の設定を確認 |
| Lambda が全ファイルでエラー | ログにエラー、Checkpoint 停止 | 根本原因を修正（lambda-errors Runbook を参照） |
| 新規監査ファイルなし | Lambda は実行されるが処理対象なし | FSx がアイドルの場合は想定内；監査ログが有効か確認 |
| SSM PutParameter 失敗 | Lambda ログに SSM エラー | SSM の IAM 権限を確認 |
| Poison-pill ファイルによるブロック | 同じファイルが繰り返し失敗 | Checkpoint を手動で前進（DLQ リプレイ Runbook を参照） |

## 解決策

### Scheduler 無効化

```bash
aws scheduler update-schedule \
  --name fsxn-<vendor>-audit-schedule \
  --state ENABLED \
  --schedule-expression "rate(5 minutes)" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target <existing-target-config> \
  --region ap-northeast-1
```

### Lambda スロットリング

```bash
# 現在の同時実行数設定を確認
aws lambda get-function-concurrency \
  --function-name fsxn-<vendor>-integration-shipper \
  --region ap-northeast-1

# 0（無効）に設定されている場合、1 に復元
aws lambda put-function-concurrency \
  --function-name fsxn-<vendor>-integration-shipper \
  --reserved-concurrent-executions 1 \
  --region ap-northeast-1
```

### 新規監査ファイルなし（想定内）

FSx for ONTAP にファイルアクティビティがない場合、新しい監査ファイルは生成されません。アイドルシステムでは正常です。確認方法：

```bash
# S3 AP 経由で最近のファイルを一覧
aws s3api list-objects-v2 \
  --bucket <s3-ap-arn> \
  --prefix "audit/" \
  --max-keys 5 \
  --query 'Contents | sort_by(@, &LastModified) | [-5:].[Key, LastModified]'
```

最新ファイルが Checkpoint と一致する場合、システムは正常です — 単にアイドル状態です。

## 確認

解決後：
1. 次のスケジュール実行を待つ（5 分）
2. Checkpoint のタイムスタンプが更新されることを確認
3. アラームが OK 状態に戻ることを確認
4. ベンダープラットフォームにログが到達していることを確認

## エスカレーション

Checkpoint が 1 時間以上滞留している場合：
- Scheduler DLQ で失敗した実行を確認
- Lambda エラーログを確認（lambda-errors Runbook を参照）
- FSx for ONTAP の監査ログが有効であることを確認
- パイプラインオーナーに連絡
