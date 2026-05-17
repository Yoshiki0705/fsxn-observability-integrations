---
inclusion: auto
---

# Datadog E2E 検証から得た教訓 — 後続ベンダー統合への適用ガイド

**作成日**: 2026-01-20
**目的**: Datadog 統合（3部構成ブログシリーズ）の E2E 検証で得た知見を、後続ベンダー統合に適用するためのガイド

---

## 🏗️ アーキテクチャ上の重要決定

### 1. トリガーパターン: EventBridge Scheduler（ポーリング）

**正しいパターン**: FSx ONTAP S3 AP + EventBridge Scheduler（定期ポーリング + チェックポイント）

**誤ったパターン**: S3 バケット + EventBridge ObjectCreated イベント ❌

**理由**: FSx ONTAP S3 Access Points は S3 Event Notifications / EventBridge オブジェクトレベルイベントを**サポートしない**。通常の S3 バケットに監査ログが出力され、Lambda は EventBridge Scheduler で定期的に起動し、チェックポイント（DynamoDB or S3 マーカー）で処理済みファイルを追跡する。

**全ベンダー共通**: この制約はベンダーに依存しない。全統合で同じトリガーパターンを使用する。

### 2. ネットワーク: NAT Gateway 必須

**S3 Gateway VPC Endpoint は FSx ONTAP S3 AP では動作しない。**

- VPC 外 Lambda → ✅（S3 AP 読み取り専用なら最もシンプル）
- VPC 内 + NAT Gateway → ✅（本番推奨、ONTAP REST API も必要な場合）
- VPC 内 + S3 Gateway EP → ❌ タイムアウト

### 3. 監査ログ形式: EVTX または XML

FSx ONTAP 監査ログは **EVTX（Windows Event Log バイナリ）** または **XML** 形式。JSON ではない。

- `vserver audit create -format evtx` → EVTX 形式（デフォルト）
- `vserver audit create -format xml` → XML 形式
- EVTX ファイルはマジックバイト `ElfFile\x00` で始まる
- 共通パーサー: `shared/lambda-layers/log-parser/`

### 4. 配信保証: at-least-once（最低1回配信）

本アーキテクチャは **at-least-once delivery** を保証する。exactly-once ではない。

- EventBridge Scheduler → Lambda は少なくとも1回実行される
- Lambda 失敗時のリトライで重複配信が発生する可能性がある
- ベンダー側で重複排除が必要な場合は、ログに一意な ID を付与する

---

## 🚨 バッチ処理とエラーハンドリング

### 5. バッチ失敗時: 例外を raise して checkpoint 進行を防止

```python
def lambda_handler(event, context):
    try:
        process_batch(event)
    except Exception as e:
        # 例外を raise することで checkpoint が進まない
        # Lambda async retry → DLQ の流れになる
        logger.error(f"Batch processing failed: {e}")
        raise  # ← 必須: checkpoint advancement を防止
```

**理由**: 例外を握りつぶすと、Lambda は成功として扱われ、チェックポイントが進行する。未処理のログが永久に失われる。

### 6. DLQ: Lambda 非同期 DLQ を使用（SQS ソースキュー DLQ ではない）

**正しい構成**: Lambda 関数の `DeadLetterConfig` に SQS キュー ARN を指定

**誤った構成**: SQS ソースキューの DLQ（`start-message-move-task` が動作しない）❌

```yaml
# CloudFormation での正しい DLQ 設定
LambdaFunction:
  Type: AWS::Lambda::Function
  Properties:
    DeadLetterConfig:
      TargetArn: !GetAtt DeadLetterQueue.Arn
```

Lambda 非同期呼び出しの場合、Lambda サービスが2回リトライ後に DLQ に送信する。SQS をイベントソースとして使用していない場合、SQS DLQ は無関係。

### 7. リトライ: 指数バックオフ + ジッター

```python
import random
import time

def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except RetryableError:
            if attempt == max_retries - 1:
                raise
            # 指数バックオフ + ジッター
            delay = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
```

**ジッターが必要な理由**: 複数の Lambda が同時にリトライすると、ベンダー API に thundering herd が発生する。ジッターでリトライタイミングを分散させる。

---

## 📊 ベンダー API 固有の注意点

### 8. Datadog: 18時間タイムスタンプ制限

Datadog Logs API は 18 時間以上前のタイムスタンプを持つログを**受け付けるが、インデックスしない**。

- API レスポンスは 202 Accepted（成功に見える）
- しかし Logs UI には表示されない
- 監査ログのローテーション遅延が 18 時間を超えないよう注意

**後続ベンダーへの教訓**: 各ベンダーのタイムスタンプ制限を事前に確認する。

| ベンダー | タイムスタンプ制限 | 確認方法 |
|---------|-----------------|---------|
| Datadog | 18時間 | API は受理するが非インデックス |
| New Relic | 24時間 | 要確認 |
| Sumo Logic | 制限なし（ただし遅延警告あり） | 要確認 |
| Splunk | HEC 設定依存 | 要確認 |
| その他 | 各ベンダー API ドキュメント参照 | E2E 検証で確認 |

### 9. Datadog AP1 サイト: gzip 圧縮問題

Datadog AP1 サイト（`ap1.datadoghq.com`）では gzip 圧縮リクエストが正しく処理されない場合がある。

- `Content-Encoding: gzip` を使用する場合は AP1 サイトでテスト必須
- 問題が発生した場合は非圧縮で送信する
- 他のサイト（US1, US3, US5, EU1）では問題なし

**後続ベンダーへの教訓**: リージョン/サイト固有の挙動差異を E2E 検証で確認する。

### 10. Datadog Monitor クエリ形式

```
logs("source:fsxn @attributes.result:Failure").index("*").rollup("count").last("5m") > 0
```

**後続ベンダーへの教訓**: アラート/モニター設定のクエリ構文はベンダーごとに大きく異なる。E2E 検証時に実際のクエリを記録し、セットアップガイドに含める。

---

## 🔧 ONTAP 設定と検証

### 11. 監査ログローテーション: 時間ベースが検証に必須

検証時は**時間ベースのローテーション**を設定する（サイズベースだけでは不十分）。

```bash
# 検証用: 5分ごとにローテーション
vserver audit modify -vserver <svm> -rotate-schedule-minute 0,5,10,15,20,25,30,35,40,45,50,55

# 本番用: 1時間ごと + サイズ 100MB
vserver audit modify -vserver <svm> -rotate-schedule-minute 0 -rotate-size 100MB
```

**理由**: サイズベースのみだと、テストデータが少量の場合にローテーションが発生せず、ログが S3 に出力されない。検証が進まない。

### 12. SACL/NFSv4 ACL: イベント生成の前提条件

監査イベントが生成されるには、対象ファイル/ディレクトリに **SACL（System Access Control List）** または **NFSv4 ACL** が設定されている必要がある。

- CIFS/SMB: SACL を Windows セキュリティ設定で構成
- NFS: NFSv4 ACL を `nfs4_setfacl` で構成
- SACL なしではイベントが生成されない → ログが空 → 検証失敗

### 13. AuditLogPrefix: S3 AP キープレフィックスとの一致確認

`AuditLogPrefix` パラメータは、実際の S3 AP 上のキープレフィックスと一致する必要がある。

```bash
# 実際のプレフィックスを確認
aws s3api list-objects-v2 \
  --bucket "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap" \
  --prefix "audit/" \
  --max-keys 5

# 出力例:
# audit/svm-prod-01/2026/01/15/audit_0001.evtx
# → AuditLogPrefix = "audit/"
```

**後続ベンダーへの教訓**: デプロイ前に `list-objects-v2` で実際のキー構造を確認する。プレフィックスの不一致は「ログが来ない」問題の最も一般的な原因。

---

## 📝 EMS/FPolicy 固有の知見

### 14. ARP は "Autonomous Ransomware Protection"

**正しい名称**: Autonomous Ransomware Protection（ARP）
**誤った名称**: Anti-Ransomware Protection ❌

ONTAP CLI コマンド: `security anti-ransomware volume attack simulate`
（CLI コマンド名は `anti-ransomware` だが、機能名は `Autonomous Ransomware Protection`）

### 15. EMS Webhook ペイロード: 正規化が必要

ONTAP EMS Webhook のペイロードは、ONTAP ドキュメントに記載されている形式とは異なる場合がある。

- 共通パーサー `shared/lambda-layers/ems-parser/` で正規化する
- `parse_ems_event()` 関数が生の ONTAP 形式を正規化済み JSON に変換
- 各ベンダー Lambda は正規化済みイベントを受け取る

---

## ✅ 後続ベンダー統合への適用チェックリスト

### E2E 検証開始前

- [ ] ベンダー API のタイムスタンプ制限を確認
- [ ] ベンダー API のバッチサイズ制限を確認
- [ ] ベンダー API のリージョン/サイト固有の制約を確認
- [ ] 監査ログの時間ベースローテーションを設定（検証用: 5分間隔）
- [ ] SACL/NFSv4 ACL が対象ファイルに設定されていることを確認
- [ ] `list-objects-v2` で S3 AP のキープレフィックスを確認
- [ ] AuditLogPrefix パラメータが実際のプレフィックスと一致することを確認

### Lambda 実装時

- [ ] バッチ失敗時に例外を raise する（checkpoint 進行防止）
- [ ] DLQ は Lambda DeadLetterConfig で設定（SQS ソースキュー DLQ ではない）
- [ ] リトライに指数バックオフ + ジッターを実装
- [ ] at-least-once 配信を前提とした設計
- [ ] API キーは Secrets Manager から取得（環境変数に直接設定しない）
- [ ] gzip 圧縮を使用する場合はベンダーの全リージョンでテスト

### CloudFormation テンプレート

- [ ] EventBridge Scheduler をトリガーとして使用（S3 Event Notifications ではない）
- [ ] Lambda DeadLetterConfig に SQS DLQ ARN を指定
- [ ] IAM ロールは最小権限（S3 AP ARN に `/object/*` サフィックス）
- [ ] CloudWatch Alarms: Errors, Throttles, DLQ メッセージ数

### E2E 検証実行時

- [ ] テストイベント送信後、ベンダー UI でログ到着を確認（5分以内）
- [ ] タイムスタンプが正しくインデックスされていることを確認
- [ ] 18時間以上前のログが正しく処理されるか確認（ベンダー制限に注意）
- [ ] EMS ARP イベント（`arw.volume.state`）の到着確認
- [ ] FPolicy ファイル操作イベントの到着確認
- [ ] アラート/モニター設定のクエリを記録

---

## 🎯 ベンダー別の注意事項

### Sumo Logic
- HTTP Source URL が認証トークンを含む（Secrets Manager に保存）
- `X-Sumo-Category` ヘッダーでソースカテゴリを指定
- バッチサイズ制限: 1MB
- Newline-delimited JSON 形式

### Honeycomb
- Batch API: `https://api.honeycomb.io/1/batch/<dataset>`
- `X-Honeycomb-Team` ヘッダーで認証
- バッチサイズ制限: 5MB / 100 イベント
- BubbleUp 機能のデモには十分なデータ量が必要

### OTel Collector
- OTLP/HTTP: `http://<collector>:4318/v1/logs`
- ベンダー中立 — Collector 設定変更のみでバックエンド追加/削除
- Lambda コード変更不要が差別化ポイント
- OTLP Log Data Model へのフィールドマッピングが必要

### Grafana (Loki)
- Basic Auth (Instance ID + API Token)
- Push API: `https://<instance>.grafana.net/loki/api/v1/push`
- ラベルベースのクエリ（LogQL）
- バッチサイズ推奨: ~4MB

### Splunk
- HEC (HTTP Event Collector): `https://<host>:8088/services/collector/event`
- `Authorization: Splunk <token>` ヘッダー
- Firehose 統合あり（大量ログ向け）
- ハードリミットなし（ただし推奨バッチサイズあり）

### New Relic
- Log API: `https://log-api.newrelic.com/log/v1` (US)
- `Api-Key: <license>` ヘッダー
- バッチサイズ制限: 1MB
- Firehose 統合あり

### Elastic
- Bulk API: `https://<cluster>/_bulk`
- `Authorization: ApiKey <key>` ヘッダー
- バッチサイズ推奨: ~10MB
- NDJSON 形式（action + document の交互行）

### Dynatrace
- Log Ingest API: `https://<env>.live.dynatrace.com/api/v2/logs/ingest`
- `Authorization: Api-Token <token>` ヘッダー
- バッチサイズ制限: 1MB
- Firehose 統合あり
