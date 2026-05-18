# New Relic 統合 動作確認結果

## 実施概要

- **検証日時**: <検証日時 ISO 8601 形式>
- **検証者**: <検証者名> / <役職>
- **検証環境**: 本番相当環境（ap-northeast-1）

---

## 環境情報

| 項目 | 値 |
|------|-----|
| AWS リージョン | ap-northeast-1 |
| AWS アカウント ID | ****XXXX |
| CloudFormation スタック名 | fsxn-new-relic-integration |
| Lambda 関数名 | fsxn-new-relic-integration-shipper |
| New Relic リージョン | US |
| New Relic アカウント ID | ****XXXX |
| New Relic Log API エンドポイント | https://log-api.newrelic.com/log/v1 |
| FSx ONTAP ファイルシステム ID | fs-<ファイルシステムID> |
| S3 Access Point ARN | arn:aws:s3:ap-northeast-1:****XXXX:accesspoint/<AP名> |

---

## テスト結果サマリー

| ステップ | 名称 | 結果 |
|---------|------|------|
| 1 | CloudFormation スタックデプロイ | <PASS/FAIL> |
| 2 | Lambda テストイベント送信 | <PASS/FAIL> |
| 3 | New Relic ログ到着確認 | <PASS/FAIL> |
| 4 | NRQL クエリ実行 | <PASS/FAIL> |
| 5 | Alert Condition 設定 | <PASS/FAIL> |
| 6 | デモシナリオ3「クォータ閾値超過アラート」 | <PASS/FAIL> |
| 7 | セットアップガイド日英対応確認 | <PASS/FAIL> |
| 8 | スクリーンショット検証 | <PASS/FAIL> |

---

## 各ステップの詳細結果

### ステップ 1: CloudFormation スタックデプロイ

- **結果**: <PASS/FAIL>

```bash
aws cloudformation deploy \
  --template-file integrations/new-relic/template.yaml \
  --stack-name fsxn-new-relic-integration \
  --parameter-overrides \
    NewRelicLicenseKeySecretArn=<SECRET_ARN> \
    S3AccessPointArn=<S3_AP_ARN> \
    NewRelicRegion=US \
    S3BucketName=<BUCKET_NAME> \
  --capabilities CAPABILITY_IAM \
  --region ap-northeast-1
```

- **スタックステータス**: <CREATE_COMPLETE / FAILED>
- **作成されたリソース**:
  - [ ] Lambda 関数
  - [ ] IAM ロール
  - [ ] EventBridge Rule
  - [ ] Dead Letter Queue
  - [ ] CloudWatch LogGroup
  - [ ] CloudWatch Alarm
- **備考**: <追加メモ>

---

### ステップ 2: Lambda テストイベント送信

- **結果**: <PASS/FAIL>

```bash
aws lambda invoke \
  --function-name fsxn-new-relic-integration-shipper \
  --payload file://integrations/new-relic/tests/test_data/sample_s3_event.json \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 60 \
  --region ap-northeast-1 \
  response.json
```

- **レスポンス**:
```json
{
  "statusCode": <ステータスコード>,
  "body": {
    "total_logs": <処理ログ数>,
    "total_shipped": <送信ログ数>,
    "errors": []
  }
}
```

- **確認項目**:
  - [ ] statusCode: 200
  - [ ] total_logs: ≥ 1
  - [ ] total_shipped: ≥ 1
  - [ ] errors: [] (空)
- **CloudWatch ログ確認**: <処理ログの抜粋>

---

### ステップ 3: New Relic ログ到着確認

- **結果**: <PASS/FAIL>

- **NRQL フィルタ**: `SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 5 minutes ago`
- **到着ログ数**: <件数>
- **Lambda 送信数との一致**: <一致 / 不一致>
- **到着までの時間**: <秒数>秒

- **属性確認**:
  - [ ] `source` = `fsxn-ontap`（非空）
  - [ ] `service` = `ontap-audit`（非空）
  - [ ] `event_type`（非空）
  - [ ] `svm`（非空）
  - [ ] `user`（非空）
  - [ ] `operation`（非空）
  - [ ] `result`（非空）
  - [ ] `client_ip`（任意）
  - [ ] `path`（任意）

- **属性マッピング検証**:

| ソースフィールド | New Relic 属性 | 値 | 判定 |
|----------------|---------------|-----|------|
| EventID | event_type | <値> | <OK/NG> |
| SVMName | svm | <値> | <OK/NG> |
| UserName | user | <値> | <OK/NG> |
| ClientIP | client_ip | <値> | <OK/NG> |
| Operation | operation | <値> | <OK/NG> |
| ObjectName | path | <値> | <OK/NG> |
| Result | result | <値> | <OK/NG> |

![New Relic Logs UI — ログ到着確認](../screenshots/new-relic/logs-ui-arrival.png)

---

### ステップ 4: NRQL クエリ実行

- **結果**: <PASS/FAIL>

#### クエリ 1: ログ件数確認

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago
```

- **実行時刻**: <ISO 8601 タイムスタンプ>
- **結果**: <件数>
- **判定**: <PASS/FAIL>

#### クエリ 2: 操作別内訳

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' FACET operation SINCE 1 hour ago
```

- **実行時刻**: <ISO 8601 タイムスタンプ>
- **結果**:

| operation | count |
|-----------|-------|
| <操作名1> | <件数> |
| <操作名2> | <件数> |

- **判定**: <PASS/FAIL>（2種類以上の操作タイプが存在すること）

#### クエリ 3: ユーザー別アクティビティ

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' FACET user SINCE 1 hour ago
```

- **実行時刻**: <ISO 8601 タイムスタンプ>
- **結果**: <ユーザー数>ユーザー
- **判定**: <PASS/FAIL>

#### クエリ 4: エラーフィルタリング

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND result='Failure' SINCE 1 hour ago
```

- **実行時刻**: <ISO 8601 タイムスタンプ>
- **結果**: <件数>
- **判定**: <PASS/FAIL>

#### クエリ 5: 時系列可視化

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' TIMESERIES 5 minutes SINCE 1 hour ago
```

- **実行時刻**: <ISO 8601 タイムスタンプ>
- **結果**: <データポイント数>
- **判定**: <PASS/FAIL>

![New Relic Query Builder — NRQL クエリ結果](../screenshots/new-relic/nrql-query-result.png)

---

### ステップ 5: Alert Condition 設定

- **結果**: <PASS/FAIL>

- **Alert Policy 名**: <ポリシー名>
- **Alert Condition 名**: <条件名>

#### Alert Condition 設定詳細

| 設定項目 | 値 |
|---------|-----|
| NRQL クエリ | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND result='Failure'` |
| 閾値 | ≥ 1 |
| 評価ウィンドウ | 5 分 |
| 通知チャネル | <チャネル名（Email / Slack / Webhook）> |

#### アラートテスト

- **テストトリガー時刻**: <ISO 8601 タイムスタンプ>
- **トリガーイベント**: `source='fsxn-ontap' AND result='Failure'` に一致するログ送信
- **通知受信時刻**: <ISO 8601 タイムスタンプ>
- **通知受信チャネル**: <チャネル名>
- **トリガーから通知までの時間**: <秒数>秒

![Alert Condition 設定](../screenshots/new-relic/alert-condition-config.png)

![Alert Policy 概要](../screenshots/new-relic/alert-policy-overview.png)

---

### ステップ 6: デモシナリオ3「クォータ閾値超過アラート」

- **結果**: <PASS/FAIL>

#### 実行コマンド

```bash
dd if=/dev/zero of=<mount_point>/user-data/large-file.bin bs=1M count=500
```

#### デモシナリオタイムライン

| ステージ | タイムスタンプ (ISO 8601) | 経過時間 | ステータス |
|---------|------------------------|---------|-----------|
| ファイル書き込み開始 | <タイムスタンプ> | 0s | <PASS/FAIL> |
| EMS イベント生成 | <タイムスタンプ> | <秒数>s | <PASS/FAIL> |
| S3 オブジェクト作成 | <タイムスタンプ> | <秒数>s | <PASS/FAIL> |
| Lambda 起動 | <タイムスタンプ> | <秒数>s | <PASS/FAIL> |
| New Relic ログ到着 | <タイムスタンプ> | <秒数>s | <PASS/FAIL> |

#### 検証 NRQL

```sql
SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND event_type LIKE 'wafl.quota%' SINCE 1 hour ago
```

- **実行時刻**: <ISO 8601 タイムスタンプ>
- **結果**: <件数>
- **判定**: <PASS/FAIL>（非ゼロであること）

- **最終成功ステージ**: <ステージ名>
- **失敗ステージ**（該当する場合）: <ステージ名>
- **失敗時経過時間**（該当する場合）: <秒数>秒

---

## スクリーンショット一覧

| # | ファイル名 | 内容 | 検証ステップ |
|---|-----------|------|-------------|
| 1 | `logs-ui-arrival.png` | New Relic Logs UI — FSxN 監査ログエントリ表示 | ステップ 3 |
| 2 | `nrql-query-result.png` | Query Builder — NRQL クエリテキストと結果表示 | ステップ 4 |
| 3 | `alert-condition-config.png` | Alert Condition 設定画面（閾値表示） | ステップ 5 |
| 4 | `alert-policy-overview.png` | Alert Policy 概要（条件一覧表示） | ステップ 5 |

- **保存先ディレクトリ**: `docs/screenshots/new-relic/`
- **フォーマット**: PNG
- **ファイルサイズ制限**: ≤ 500KB

---

## NRQL クエリ結果

| # | クエリ | 結果サマリー | 実行時刻 | 判定 |
|---|--------|-------------|---------|------|
| 1 | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' SINCE 1 hour ago` | <件数> | <ISO 8601> | <PASS/FAIL> |
| 2 | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' FACET operation SINCE 1 hour ago` | <操作種別数>種別 | <ISO 8601> | <PASS/FAIL> |
| 3 | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' FACET user SINCE 1 hour ago` | <ユーザー数>ユーザー | <ISO 8601> | <PASS/FAIL> |
| 4 | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND result='Failure' SINCE 1 hour ago` | <件数> | <ISO 8601> | <PASS/FAIL> |
| 5 | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' TIMESERIES 5 minutes SINCE 1 hour ago` | <データポイント数> | <ISO 8601> | <PASS/FAIL> |
| 6 | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND event_type LIKE 'wafl.quota%' SINCE 1 hour ago` | <件数> | <ISO 8601> | <PASS/FAIL> |

---

## アラート設定詳細

### Alert Policy

| 項目 | 値 |
|------|-----|
| Policy 名 | <ポリシー名> |
| Incident Preference | <Per policy / Per condition / Per condition and signal> |
| 作成日時 | <ISO 8601 タイムスタンプ> |

### Alert Condition

| 項目 | 値 |
|------|-----|
| Condition 名 | <条件名> |
| Condition タイプ | NRQL |
| NRQL クエリ | `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND result='Failure'` |
| 閾値（Critical） | ≥ 1 |
| 評価ウィンドウ | 5 分 |
| Signal aggregation window | <秒数>秒 |
| Streaming method | <Event flow / Event timer / Cadence> |
| Gap filling strategy | <None / Static / Last known> |

### Notification Channel

| 項目 | 値 |
|------|-----|
| チャネルタイプ | <Email / Slack / Webhook / PagerDuty> |
| 送信先 | <送信先情報（マスク済み）> |
| テスト通知送信 | <成功 / 失敗> |
| テスト通知受信確認 | <ISO 8601 タイムスタンプ> |

---

## デモシナリオタイムライン

### シナリオ3: クォータ閾値超過アラート

```
[ファイル書き込み] ──→ [EMS イベント生成] ──→ [S3 キャプチャ] ──→ [Lambda 起動] ──→ [New Relic 到着]
     T+0s                T+<N>s              T+<N>s            T+<N>s           T+<N>s
```

| ステージ | 開始時刻 | 完了時刻 | 所要時間 | ステータス |
|---------|---------|---------|---------|-----------|
| ファイル書き込み（500MB） | <ISO 8601> | <ISO 8601> | <秒数>s | <PASS/FAIL> |
| EMS イベント生成（wafl.quota.softlimit.exceeded） | <ISO 8601> | <ISO 8601> | <秒数>s | <PASS/FAIL> |
| S3 オブジェクト作成 | <ISO 8601> | <ISO 8601> | <秒数>s | <PASS/FAIL> |
| Lambda 起動・処理 | <ISO 8601> | <ISO 8601> | <秒数>s | <PASS/FAIL> |
| New Relic ログ到着 | <ISO 8601> | <ISO 8601> | <秒数>s | <PASS/FAIL> |

- **エンドツーエンド所要時間**: <秒数>秒（ファイル書き込み → New Relic 到着）
- **SLA 準拠**: <180秒以内: 合格 / 超過: 不合格>

---

## 既知の問題と対応策

| # | 問題内容 | 重要度 | 対処方法 | ステータス |
|---|---------|--------|---------|-----------|
| 1 | <問題の説明> | <高/中/低> | <対処方法の説明> | <✅ 対処済み / 🔄 対応中 / 📝 記録済み> |

> 問題が検出されなかった場合: 問題なし

---

## 総合判定

### 判定基準

- 全ステップが PASS: **本番環境利用可能**
- 1つ以上のステップが FAIL: **本番環境利用不可**（失敗した基準 ID を列挙）

### 判定結果

- **判定**: <✅ 本番環境利用可能 / ❌ 本番環境利用不可>
- **合格基準数**: <N> / <全基準数>
- **不合格基準**（該当する場合）:
  - <基準 ID>: <不合格理由>

---

## 検証完了確認

- [ ] 全ステップの結果が記録されている
- [ ] スクリーンショットが4枚配置されている（`docs/screenshots/new-relic/`）
- [ ] NRQL クエリ結果が記録されている
- [ ] アラート設定詳細が記録されている
- [ ] デモシナリオタイムラインが記録されている
- [ ] 既知の問題と対応策が記録されている
- [ ] セットアップガイド日英対応が確認されている
