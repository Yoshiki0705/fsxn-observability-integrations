# CloudWatch Log Alarm — FSx for ONTAP 監査ログからのダイレクトアラーム

> **テンプレート**: `shared/templates/cloudwatch-log-alarm.yaml`
> **前提**: FSx for ONTAP 管理監査ログが CloudWatch Logs に配信済み（[Syslog VPC Endpoint セットアップ](./syslog-vpce-setup-guide.md) 参照）
> **AWS 発表日**: 2026-07-01
> **所要時間**: デプロイ約 5 分、初回評価まで約 10 分（合計 15 分で動作確認可能）

---

## クイックスタート成功判断基準

| # | 確認項目 | 方法 |
|---|---------|------|
| 1 | CloudFormation スタックが CREATE_COMPLETE | `aws cloudformation describe-stacks` |
| 2 | アラーム状態が INSUFFICIENT_DATA → OK に遷移 | コンソール or CLI (5〜10 分待機) |
| 3 | テスト操作で ALARM に遷移 + SNS 通知受信 | ONTAP CLI で操作実行後、メール確認 |

---

## 想定利用者

| 利用者 | 利用目的 |
|--------|---------|
| セキュリティ運用チーム | 不正アクセス・機密ファイルアクセスの即時検知 |
| SRE / インフラ運用チーム | ストレージ異常（大量削除、ボリュームオフライン）の検知 |
| コンプライアンス担当 | 規制対象データへのアクセス証跡と自動アラート |
| ストレージ管理者 | 特権ユーザー操作の監視 |

## 対象ログの種類

FSx for ONTAP には 2 種類の監査ログがあります。本テンプレートの主な対象は**管理監査ログ**です。

| ログ種別 | 配信経路 | フォーマット | Log Alarm 対象 |
|---------|---------|------------|--------------|
| **管理監査ログ** (Admin Audit) | Syslog → VPC Endpoint → CloudWatch Logs | Syslog テキスト | ✅ 本テンプレート |
| **ファイルアクセス監査ログ** (File Access Audit) | S3 バケット → Lambda → 各ベンダー | EVTX / XML バイナリ | ❌ 別パイプライン |

管理監査ログには ONTAP CLI/API の操作記録が含まれます（例: ボリューム操作、Snapshot 操作、ユーザー管理、セキュリティ設定変更）。

### 実際のログフォーマット（E2E 検証で確認）

CloudWatch Logs に到達する ONTAP 管理監査ログのフォーマット:

```
<190>Jul  2 03:17:37 FsxId...-02: FsxId...-02: 0000001c.000b7609 00f10e98
Thu Jul 02 2026 03:17:35 +00:00 [kern_audit:info:6392]
8003e90000027e24:8003e90000027e26 :: FsxId...:ssh :: <source-ip>:unknown ::
FsxId...:fsx-control-plane:admin ::
system node systemshell -node * -command "top -d 1 -s 1" :: Success: 2 entries were acted on.
```

**主要フィールド**:
- `[kern_audit:info:6392]` — 監査カテゴリとレベル
- `FsxId...:ssh` / `FsxId...:http` — アクセスプロトコル
- `<source-ip>` — 操作元 IP
- `fsx-control-plane:admin` — 実行ユーザー
- `system node systemshell ...` — 実行コマンド
- `Success` / `Failure` — 結果

> **ファイルアクセス監査ログ**（NFS/SMB のファイル操作記録）を CloudWatch Logs に配信して Log Alarm を使いたい場合は、Lambda で EVTX/XML をパースして CloudWatch Logs に転送するカスタムパイプラインが必要です。

## 概要

2026 年 7 月に発表された **CloudWatch Log Alarm** を利用し、FSx for ONTAP の監査ログから**メトリクスフィルターなし**でアラームを作成します。

従来のフロー:

```
CloudWatch Logs → メトリクスフィルター → カスタムメトリクス → CloudWatch Alarm
```

新しいフロー（Log Alarm）:

```
CloudWatch Logs → Logs Insights クエリ (スケジュール実行) → Log Alarm → SNS
```

中間ステップが不要になり、ログ分析からアラート設定までを一元化できます。

---

## アーキテクチャ

```
┌────────────────────────────────────────────────────────────────┐
│  FSx for ONTAP                                                 │
│  (Syslog log-forwarding)                                       │
└───────────────┬────────────────────────────────────────────────┘
                │ Syslog TCP
                ▼
┌────────────────────────────────────────────────────────────────┐
│  CloudWatch Logs (/syslog/fsxn-admin-audit)                    │
└───────────────┬────────────────────────────────────────────────┘
                │ Scheduled Query (rate: 5 min)
                ▼
┌────────────────────────────────────────────────────────────────┐
│  CloudWatch Log Alarm                                          │
│  - Logs Insights クエリ (文字列フィルタ)                          │
│  - 集約式: count(*)                                             │
│  - 閾値: count > 0 → ALARM                                     │
└───────────────┬────────────────────────────────────────────────┘
                │ AlarmActions
                ▼
┌────────────────────────────────────────────────────────────────┐
│  Amazon SNS → Email / Slack / PagerDuty / EventBridge          │
│  (通知にログ行を含めることも可能)                                  │
└────────────────────────────────────────────────────────────────┘
```

---

## 核心アイデア: 文字列マッチング → カウント → 閾値アラート

CloudWatch Log Alarm は「ログ内の文字列に直接アラートする」機能ではなく、**Logs Insights クエリで文字列にマッチしたイベントを数え、その数が閾値を超えたら発火する**仕組みです。

例:

| ユースケース | クエリのフィルタ部分 | 集約式 | 閾値 |
|-------------|-------------------|--------|------|
| 機密ファイルへのアクセス | `filter @message like /confidential/` | `count(*)` | `> 0` |
| 認証失敗の急増 | `filter @message like /Failure/` | `count(*)` | `> 10` |
| 大量ファイル削除 | `filter @message like /DELETE/` | `count(*)` | `> 50` |
| 特定ユーザーの操作 | `filter @message like /admin/` | `count(*)` | `> 0` |

つまり:

1. **文字列にマッチした数を数える** (count)
2. **その数が 0 より大きければアラート** (threshold > 0)

これにより、「特定のファイルにアクセスしたら即座にアラート」という要件を実現できます。

---

## デプロイ

### デプロイスクリプト（推奨）

```bash
# 機密ファイルアクセス検知
DETECTION_TYPE=sensitive-file-access \
TARGET_PATTERN="/vol/data/confidential" \
SNS_TOPIC_ARN=arn:aws:sns:ap-northeast-1:123456789012:fsxn-alerts \
  bash shared/scripts/deploy-log-alarm.sh

# SNS トピックも自動作成する場合
DETECTION_TYPE=sensitive-file-access \
TARGET_PATTERN="/vol/data/confidential" \
CREATE_SNS_TOPIC=true \
SNS_TOPIC_NAME=fsxn-security-alerts \
  bash shared/scripts/deploy-log-alarm.sh
```

### 事前準備

1. FSx for ONTAP 監査ログが CloudWatch Logs に到達していること
2. 通知先の SNS トピックが作成済みであること

### 機密ファイルアクセス検知

```bash
aws cloudformation deploy \
  --template-file shared/templates/cloudwatch-log-alarm.yaml \
  --stack-name fsxn-log-alarm-sensitive-access \
  --parameter-overrides \
    LogGroupName=/syslog/fsxn-admin-audit \
    DetectionType=sensitive-file-access \
    TargetPattern="/vol/data/confidential" \
    AlarmThreshold=0 \
    EvaluationFrequencyMinutes=5 \
    QueryResultsToEvaluate=3 \
    QueryResultsToAlarm=1 \
    AlarmSnsTopicArn=arn:aws:sns:ap-northeast-1:123456789012:fsxn-security-alerts \
    ActionLogLineCount=5 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 認証失敗検知

```bash
aws cloudformation deploy \
  --template-file shared/templates/cloudwatch-log-alarm.yaml \
  --stack-name fsxn-log-alarm-failed-access \
  --parameter-overrides \
    LogGroupName=/syslog/fsxn-admin-audit \
    DetectionType=failed-access-attempts \
    AlarmThreshold=10 \
    EvaluationFrequencyMinutes=5 \
    AlarmSnsTopicArn=arn:aws:sns:ap-northeast-1:123456789012:fsxn-security-alerts \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 大量削除検知（ランサムウェア指標）

```bash
aws cloudformation deploy \
  --template-file shared/templates/cloudwatch-log-alarm.yaml \
  --stack-name fsxn-log-alarm-bulk-delete \
  --parameter-overrides \
    LogGroupName=/syslog/fsxn-admin-audit \
    DetectionType=bulk-delete-operations \
    AlarmThreshold=50 \
    EvaluationFrequencyMinutes=5 \
    QueryResultsToEvaluate=3 \
    QueryResultsToAlarm=2 \
    AlarmSnsTopicArn=arn:aws:sns:ap-northeast-1:123456789012:fsxn-security-alerts \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### カスタムクエリ

```bash
aws cloudformation deploy \
  --template-file shared/templates/cloudwatch-log-alarm.yaml \
  --stack-name fsxn-log-alarm-custom \
  --parameter-overrides \
    LogGroupName=/syslog/fsxn-admin-audit \
    DetectionType=custom \
    CustomQueryString="fields @timestamp, @message | filter @message like /volume.offline/ or @message like /vol.unmount/" \
    CustomAggregation="count(*)" \
    AlarmThreshold=0 \
    EvaluationFrequencyMinutes=1 \
    AlarmSnsTopicArn=arn:aws:sns:ap-northeast-1:123456789012:fsxn-security-alerts \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

---

## AWS CLI でのダイレクト作成（テンプレートなし）

CloudFormation を使わず、`put-log-alarm` コマンドで直接作成することも可能です:

```bash
aws cloudwatch put-log-alarm \
    --alarm-name "fsxn-sensitive-file-access" \
    --alarm-description "Alert on access to /vol/data/confidential" \
    --comparison-operator GreaterThanThreshold \
    --threshold 0 \
    --query-results-to-evaluate 3 \
    --query-results-to-alarm 1 \
    --treat-missing-data notBreaching \
    --alarm-actions "arn:aws:sns:ap-northeast-1:123456789012:fsxn-security-alerts" \
    --scheduled-query-configuration '{
        "QueryString": "fields @timestamp, @message | filter @message like /\\/vol\\/data\\/confidential/",
        "LogGroupIdentifiers": ["/syslog/fsxn-admin-audit"],
        "ScheduledQueryRoleARN": "arn:aws:iam::123456789012:role/fsxn-log-alarm-scheduled-query-role",
        "AggregationExpression": "count(*)",
        "ScheduleConfiguration": {
            "ScheduleExpression": "rate(5 minutes)",
            "StartTimeOffset": 300
        }
    }' \
    --action-log-line-count 5 \
    --action-log-line-role-arn "arn:aws:iam::123456789012:role/fsxn-log-alarm-log-line-role"
```

---

## 従来アプローチとの比較

| 項目 | メトリクスフィルター方式 | Log Alarm 方式 (新) |
|------|----------------------|-------------------|
| 設定ステップ | 3 (フィルター → メトリクス → アラーム) | 1 (Log Alarm のみ) |
| クエリ柔軟性 | パターン構文のみ | Logs Insights フル構文 |
| 集約オプション | Count / Sum / Avg 等 | Logs Insights の全集約関数 |
| 通知にログ行含む | ❌ | ✅ (最大 50 行) |
| IAM 要件 | なし（Logs → Metrics は自動） | ScheduledQueryRole + LogLineRole |
| CloudFormation | `AWS::Logs::MetricFilter` + `AWS::CloudWatch::Alarm` | `AWS::CloudWatch::LogAlarm` |
| コスト | メトリクス従量 + アラーム料金 | Scheduled Query 実行 + アラーム料金 |
| 遡及クエリ | ❌ (フィルタ適用後のデータのみ) | ✅ (既存ログに対してクエリ可能) |

### いつ Log Alarm を選ぶか

- ログの文字列パターンに基づいてアラートしたい
- Logs Insights の柔軟なクエリ構文を使いたい
- 通知にログ行そのものを含めたい（調査を加速）
- 中間メトリクスの管理を避けたい
- **既存のログ**に対しても遡及的にアラートしたい

### いつメトリクスフィルター方式を選ぶか

- 時系列メトリクスとしてダッシュボード表示したい
- Anomaly Detection を使いたい
- 数学式（Metric Math）で複数メトリクスを組み合わせたい
- 追加 IAM ロールを避けたい

---

## FSx for ONTAP 監査ログの検知パターン集

### パターン 1: 特定パスへのアクセス検知

「`/vol/finance/` 配下のファイルにアクセスがあったら即アラート」

```
fields @timestamp, @message
| filter @message like /\/vol\/finance\//
| limit 20
```

集約: `count(*)` / 閾値: `> 0`

### パターン 2: 営業時間外のアクセス検知

```
fields @timestamp, @message
| filter @message like /\/vol\/data\//
| filter datefloor(@timestamp, 1h) not between
    concat(formatTimestamp(@timestamp, 'yyyy-MM-dd'), 'T09:00:00')
    and concat(formatTimestamp(@timestamp, 'yyyy-MM-dd'), 'T18:00:00')
| limit 20
```

集約: `count(*)` / 閾値: `> 0`

### パターン 3: 特定ユーザーによる管理操作

```
fields @timestamp, @message
| filter @message like /admin/ and (@message like /volume/ or @message like /vserver/)
| limit 20
```

集約: `count(*)` / 閾値: `> 0`

### パターン 4: ボリュームオフライン/アンマウント

```
fields @timestamp, @message
| filter @message like /volume.offline/ or @message like /vol.unmount/ or @message like /vol.restrict/
| limit 20
```

集約: `count(*)` / 閾値: `> 0`

### パターン 5: Snapshot 削除（大量削除の検知）

```
fields @timestamp, @message
| filter @message like /snapshot.delete/ or @message like /snap.delete/
| limit 20
```

集約: `count(*)` / 閾値: `> 5`（5 分間で 5 回以上の Snapshot 削除は異常）

---

## IAM ロール要件

Log Alarm には 2 つの IAM ロールが必要です:

### 1. Scheduled Query Execution Role（必須）

CloudWatch Logs がスケジュールクエリを実行するためのロール:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "logs.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

権限:

```json
{
  "Effect": "Allow",
  "Action": [
    "logs:StartQuery",
    "logs:StopQuery",
    "logs:GetQueryResults",
    "logs:DescribeLogGroups"
  ],
  "Resource": "arn:aws:logs:<region>:<account-id>:log-group:/syslog/fsxn-admin-audit:*"
}
```

### 2. Log Line Role（オプション — SNS 通知にログ行を含める場合）

CloudWatch がログ行を取得して SNS 通知に含めるためのロール:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "cloudwatch.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

権限:

```json
{
  "Effect": "Allow",
  "Action": ["logs:GetQueryResults"],
  "Resource": "arn:aws:logs:<region>:<account-id>:log-group:/syslog/fsxn-admin-audit:*"
}
```

> **注**: テンプレート `cloudwatch-log-alarm.yaml` はこれらのロールを自動作成します。

---

## M-out-of-N 評価

Log Alarm は M-out-of-N モデルで評価します:

- **N** = `QueryResultsToEvaluate` — 直近 N 回のクエリ結果を評価
- **M** = `QueryResultsToAlarm` — うち M 回が閾値を超えたら ALARM

### 推奨設定

| ユースケース | N (評価) | M (アラーム) | 理由 |
|-------------|---------|-------------|------|
| 機密ファイルアクセス | 3 | 1 | 1 回でも検知したら即通知 |
| 認証失敗スパイク | 5 | 3 | 一時的なミスタイプを除外 |
| 大量削除 | 3 | 2 | 連続した異常を確認 |
| 監視ユーザー | 3 | 1 | 1 回でも即通知 |

---

## コスト見積もり

### Log Alarm 単体

| ログ量/日 | 月額概算 | 備考 |
|----------|---------|------|
| 100 MB | ~$6.6 | 小規模環境 |
| 500 MB | ~$33 | 中規模環境 |
| 1 GB | ~$66 | 大規模環境 |

### メトリクスフィルター方式との比較

| 項目 | メトリクスフィルター方式 | Log Alarm 方式 |
|------|----------------------|--------------|
| カスタムメトリクス | ~$0.30/メトリクス/月 | 不要 |
| アラーム | ~$0.10/アラーム/月 | ~$0.30/アラーム/月 |
| Scheduled Query | 不要 | $0.0076/GB スキャン |
| **100MB/日の月額合計** | **~$3** | **~$6.6** |

Log Alarm は約 2 倍のコストですが、以下で回収可能:
- 通知にログ行が含まれるため**調査時間を短縮**（人件費削減）
- 遡及クエリ可能で**過去ログに対しても適用**
- 設定が 1 ステップで**運用の複雑性を削減**

5 分間隔 × 1 アラーム × 1 日 288 回 = 約 288 クエリ/日。

> **コスト最適化**: `EvaluationFrequencyMinutes` を長めに設定するか、クエリの `limit` でスキャン範囲を制限するとコスト削減可能。

---

## リージョン利用可能性

2026 年 7 月時点で、以下を除く全商用リージョンで利用可能:

- ❌ Middle East (UAE)
- ❌ Middle East (Bahrain)

`ap-northeast-1`（東京）は ✅ 利用可能。

---

## セキュリティおよびプライバシーの考慮事項

### SNS 通知に含まれるログ行

`ActionLogLineCount > 0` を設定すると、アラート通知メールにマッチしたログ行が含まれます。ログ行には以下の情報が含まれる可能性があります:

- ユーザー名 / アカウント名
- ファイルパス（機密ファイル名を含む可能性）
- クライアント IP アドレス
- 操作内容の詳細

**推奨**:
- 機密レベルの高いログに対しては `ActionLogLineCount=0` を検討
- SNS トピックの購読者を最小限に制限
- SNS トピックに暗号化（SSE-KMS）を設定

### KMS 暗号化されたロググループ（E2E 検証で確認）

**結論: `ScheduledQueryExecutionRole` に `kms:Decrypt` は不要です。** 復号は CloudWatch Logs サービスが KMS キーポリシー経由で行うため、ロールに必要なのは `logs:*` のクエリ権限だけです。

代わりに、**KMS キーポリシー**で CloudWatch Logs サービスプリンシパルに復号を許可します:

```json
{
  "Sid": "AllowCloudWatchLogs",
  "Effect": "Allow",
  "Principal": { "Service": "logs.<region>.amazonaws.com" },
  "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"],
  "Resource": "*",
  "Condition": {
    "ArnEquals": {
      "kms:EncryptionContext:aws:logs:arn": "arn:aws:logs:<region>:<account-id>:log-group:<log-group-name>"
    }
  }
}
```

> **検証（2026-07-02）**: `kms:Decrypt` を**持たない**ロールで、KMS 暗号化ロググループに対する Log Alarm を作成。上記キーポリシーのみで、アラームは INSUFFICIENT_DATA ではなく正常に評価され（マッチ時に ALARM へ遷移し SNS 通知も発火）、クエリ成功を確認しました。ロール側の `kms:Decrypt` は不要です。
>
> **注**: `cloudwatch-log-alarm.yaml` テンプレートは既存の外部 KMS キーのキーポリシーを変更しません。KMS 暗号化ロググループを使う場合、上記のキーポリシー付与は**利用者が別途**設定してください。

### SNS トピックのアクセスポリシー

CloudWatch がアラームアクションとして SNS に通知を送るためには、SNS トピックのリソースポリシーで CloudWatch サービスからのアクセスを許可する必要があります。通常、CloudWatch Alarm → SNS は IAM なしで動作しますが、クロスアカウントの場合はリソースポリシーが必要です。

---

## 運用ノート

### Scheduled Query 実行の監視

Log Alarm の基盤である Scheduled Query 自体の実行失敗を検知するには:

```
CloudWatch Console → Logs → Scheduled Queries → ステータス確認
```

Scheduled Query が失敗し続けると、アラームは `INSUFFICIENT_DATA` 状態になります。

### テスト手順

アラームが正常に発火するかテストするには:

1. ONTAP CLI で意図的にマッチする操作を実行（例: テスト用ボリュームで操作）
2. Syslog 配信を確認（CloudWatch Logs にイベントが到達）
3. 次のスケジュール実行（最大 `EvaluationFrequencyMinutes` 分待機）でアラーム発火を確認

### よくある落とし穴: 疎なパターンは ALARM になりにくい（E2E 検証で確認）

`count(*) > 0`（閾値 0）のアラームを作ったのに、いつまでも OK のまま ALARM にならない——これは E2E 検証で実際に遭遇した挙動です。原因は次の 2 点です。

1. **`stats count(*)` は 0 件のとき「結果行なし」を返す**（`0` という行ではなく、行そのものが存在しない）。これは欠損データ扱いになり、`TreatMissingData: notBreaching` では OK と判定されます。
2. **評価ウィンドウ内にマッチが 1 件も入らないと発火しない**。例えばあるパターンが 1 時間に 12 件しか出ない場合、5 分ウィンドウの大半は 0 件です。実測では 6 個中 5 個のウィンドウが 0 件、1 個だけ 4 件でした。

つまり、疎なイベントを `count(*) > 0` で拾う設計は「マッチを含むウィンドウが評価された瞬間だけ ALARM になり、直後に OK へ戻る」動作になります。SNS 通知は OK→ALARM の遷移時に飛ぶので検知自体は機能しますが、**動作確認の際は密なパターン（例: `ssh`。10 分で数百件）を使うか、テスト直前にマッチするイベントをまとめて発生させる**のが確実です。

> 疎なパターンでも「起きたら必ず気づきたい」場合は、この挙動で問題ありません（1 件でも入れば通知が飛ぶ）。ただし「一定期間ずっと OK であること」を可視化したい用途には向きません。

### StartTimeOffset の推奨

ログ到着遅延を考慮し、`StartTimeOffset` をクエリ頻度より少し長く設定することを推奨します:

| EvaluationFrequencyMinutes | 推奨 StartTimeOffset (秒) | 理由 |
|---------------------------|--------------------------|------|
| 1 | 90 | 30秒のバッファ |
| 5 | 330 | 30秒のバッファ |
| 10 | 660 | 60秒のバッファ |
| 15 | 960 | 60秒のバッファ |

> **注**: 現在のテンプレートでは `StartTimeOffset = EvaluationFrequencyMinutes × 60` を使用しています。到着遅延が問題になる場合は、`DetectionType=custom` で `StartTimeOffset` を手動調整するか、テンプレートを直接編集してください。

## CloudWatch Log Alarm vs OTel Collector アラートルール

本プロジェクトでは OTel Collector 経由で各ベンダーにログを配信するパスも提供しています。使い分けの指針:

### 選択フローチャート

```mermaid
flowchart TD
    A[ログベースのアラートが必要] --> B{メトリクスの時系列表示が必要?}
    B -->|Yes| C[メトリクスフィルター方式]
    B -->|No| D{Anomaly Detection が必要?}
    D -->|Yes| C
    D -->|No| E{複数メトリクスの数学式が必要?}
    E -->|Yes| C
    E -->|No| F{高度な相関分析やダッシュボードが必要?}
    F -->|Yes| G[OTel Collector + ベンダーアラートルール]
    F -->|No| H[CloudWatch Log Alarm ✅]
```

### パイプライン内の位置づけ

| パス | 適用場面 | 追加インフラ | コスト |
|------|---------|------------|--------|
| **Log Alarm** (本テンプレート) | シンプルな閾値アラート、即時検知 | なし（マネージド） | ~$6.6/月 (100MB/日) |
| **Lambda → ベンダー** | 高度なダッシュボード、相関分析、SIEM | Lambda | ベンダー課金依存 |
| **OTel Collector** | マルチバックエンド、PII 除去、プロトコル変換 | Collector | Collector 運用 + ベンダー |

> Log Alarm だけで監視が「完結」するわけではありません。セキュリティ検知の第一報として Log Alarm を使い、詳細調査はベンダーツールで行う組み合わせが推奨です。

### 詳細比較

| 観点 | CloudWatch Log Alarm | OTel + ベンダーアラート |
|------|---------------------|---------------------|
| 追加インフラ | なし（マネージド） | Collector インスタンス |
| クエリ柔軟性 | Logs Insights 構文 | ベンダー固有の強力なクエリ |
| 相関分析 | 限定的（ログのみ） | メトリクス + トレース + ログ |
| コスト | Scheduled Query 従量 | Collector 運用 + ベンダー課金 |
| ベンダーロックイン | なし (AWS ネイティブ) | 中程度（バックエンド依存） |
| 適用場面 | シンプルな閾値アラート | 高度な分析・相関・ダッシュボード |

**推奨**: 即時性が重要な単純パターンマッチは Log Alarm、複合条件や相関分析が必要なケースはベンダーアラートルールを使用。

---

## Runbook

アラーム発火時の対応手順: [Log Alarm Runbook](./runbooks/log-alarm-triggered.md)

---

## E2E 検証結果（2026-07-02）

以下の E2E 検証を `ap-northeast-1` で実施し、動作を確認しました。

| 検証項目 | 結果 | 備考 |
|---------|------|------|
| CloudFormation デプロイ | ✅ 成功 | `AWS::CloudWatch::LogAlarm` がサポートされている |
| IAM ロール自動作成 | ✅ 成功 | ScheduledQueryRole + LogLineRole |
| Scheduled Query 実行 | ✅ 成功 | INSUFFICIENT_DATA → OK に遷移で確認 |
| コンソール表示 | ✅「Log alarm」タイプ | Metric alarm と区別される |
| Logs Insights クエリ | ✅ 正常動作 | `filter @message like /ssh/` → 472 件 (10分間) |
| SNS 連携 | ✅ 設定完了 | サブスクリプション確認メール送信 |

### 状態遷移の観察

```
作成直後: INSUFFICIENT_DATA (クエリ未実行)
  ↓ (~5-10 分後)
OK (クエリ実行完了、閾値以下)
  ↓ (マッチするログが閾値を超えた場合)
ALARM (SNS 通知発火)
```

### 注意事項（検証で判明）

1. **AWS CLI 未対応**: `put-log-alarm` コマンドは CLI v2.35.x 時点で未実装。CloudFormation または コンソールを使用
2. **cfn-lint 未認識**: `AWS::CloudWatch::LogAlarm` は cfn-lint のリソーススペックに未反映（E3006）。デプロイは正常に動作する
3. **初回評価遅延**: スタック作成後、最初のクエリ実行まで 5〜10 分かかる
4. **M-out-of-N**: 閾値 > 0 の場合、M 回連続でブリーチしないと ALARM にならない。即時検知には `QueryResultsToAlarm=1` を設定

### クリーンアップ

```bash
# 個別スタック削除
STACK_NAME=fsxn-log-alarm-sensitive-file-access \
  bash shared/scripts/cleanup-log-alarm.sh

# 全 Log Alarm スタック削除
bash shared/scripts/cleanup-log-alarm.sh --all

# SNS トピックも含めて削除
STACK_NAME=fsxn-log-alarm-e2e-test \
SNS_TOPIC_ARN=arn:aws:sns:ap-northeast-1:123456789012:fsxn-log-alarm-test \
  bash shared/scripts/cleanup-log-alarm.sh --delete-sns
```

---

## 関連ドキュメント

- [Syslog VPC Endpoint セットアップガイド](./syslog-vpce-setup-guide.md) — 監査ログを CloudWatch Logs に配信する前提条件
- [検知ユースケース](./detection-use-cases.md) — イベントソース別の検知パターン一覧
- [パイプライン SLO](./pipeline-slo.md) — 監視パイプラインのサービスレベル目標
- [セキュリティベストプラクティス](./security-best-practices.md)
- [AWS ドキュメント: Alarming on logs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Alarm-On-Logs.html)
- [AWS What's New: CloudWatch Log Alarms](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-cloudwatch-log-alarms/)
