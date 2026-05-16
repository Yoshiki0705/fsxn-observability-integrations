# Datadog 統合 動作確認結果

- **検証日時**: 2026-05-16T21:33:03+09:00
- **検証者**: Yoshiki Fujiwara / Solutions Architect

### 検証環境

- **AWS リージョン**: ap-northeast-1
- **CloudFormation スタック名**: fsxn-datadog-integration
- **Lambda 関数名**: fsxn-datadog-integration-shipper
- **Datadog サイト**: ap1.datadoghq.com (AP1 Tokyo)
- **FSx ONTAP ファイルシステム**: fs-09ffe72a3b2b7dbbd
- **S3 Access Point**: arn:aws:s3:ap-northeast-1:178625946981:accesspoint/fsxn-audit-observability

---

## 検証ステップ

### ステップ 1: CloudFormation スタックデプロイ

- **結果**: ✅ 成功

```bash
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:178625946981:accesspoint/fsxn-audit-observability \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:178625946981:secret:fsxn-datadog-api-key-7Ti8iQ \
    DatadogSite=ap1.datadoghq.com \
    S3BucketName=fsxn-audit-obser-cbsi8mwwgahuh7sans3bbtxijig4sapn1b-ext-s3alias \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

- **出力**: `Successfully created/updated stack - fsxn-datadog-integration`
- **スタックステータス**: CREATE_COMPLETE
- **作成されたリソース**: Lambda 関数、IAM ロール、DLQ、CloudWatch Alarms、EventBridge Rule、Log Group

---

### ステップ 2: Lambda コードデプロイ

- **結果**: ✅ 成功

```bash
cd integrations/datadog/lambda
zip function.zip handler.py
aws lambda update-function-code \
  --function-name fsxn-datadog-integration-shipper \
  --zip-file fileb://function.zip \
  --region ap-northeast-1
```

- **備考**: CloudFormation テンプレートはプレースホルダーコードでデプロイされるため、実際の handler.py を別途デプロイする必要がある

---

### ステップ 3: Lambda テストイベント送信

- **結果**: ✅ 成功

```bash
aws lambda invoke \
  --function-name fsxn-datadog-integration-shipper \
  --payload '{"Records":[{"s3":{"bucket":{"name":"fsxn-audit-logs-observability-test"},"object":{"key":"audit/svm-prod-01/current/audit_current.json"}}}]}' \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 \
  response.json
```

- **レスポンス**:
```json
{"statusCode": 200, "body": {"total_logs": 5, "total_shipped": 5, "errors": []}}
```

- **確認項目**:
  - [x] statusCode: 200
  - [x] total_logs: 5
  - [x] total_shipped: 5
  - [x] errors: [] (空)

---

### ステップ 4: Datadog ログ到着確認

- **結果**: ✅ 成功

- **検索クエリ**: `source:fsxn`
- **到着ログ数**: 5件（Lambda 送信分）+ 2件（直接 API テスト分）
- **到着までの時間**: 約30-45秒

- **確認項目**:
  - [x] `source:fsxn` で1件以上のログが表示される
  - [x] 各ログに `attributes.svm` = `svm-prod-01`
  - [x] 各ログに `attributes.user` = `admin@corp.local` 等
  - [x] 各ログに `attributes.operation` = `ReadData` 等
  - [x] 各ログに `attributes.client_ip` = `10.0.1.50` 等
  - [x] 各ログに `attributes.result` = `Success` / `Failure`
  - [x] 各ログに `attributes.path` = `/vol/data/reports/quarterly.xlsx` 等

![Datadog ログ到着確認](../screenshots/datadog-logs-arrival.png)

---

### ステップ 5: Log Pipeline 設定

- **結果**: ✅ 成功

- **Pipeline 名**: FSx ONTAP Audit Logs
- **フィルタ**: `source:fsxn`
- **作成方法**: Datadog UI (Logs → Configuration → Pipelines → New Pipeline)

![Log Pipeline 設定](../screenshots/datadog-pipeline-config.png)

---

### ステップ 6: ダッシュボード作成

- **結果**: ✅ 成功

- **ダッシュボード名**: FSx ONTAP Audit Log Overview
- **ダッシュボード ID**: ggx-7ad-6e4
- **作成方法**: Datadog Dashboard API (`POST /api/v1/dashboard`)
- **ウィジェット**:
  - ログ量推移 (Timeseries)
  - 操作別内訳 (Top List)
  - ユーザー別アクティビティ (Top List)
  - エラー率 (Query Value)

![ダッシュボード](../screenshots/datadog-dashboard.png)

---

### ステップ 7: デモシナリオ1「不正アクセス検知」

- **結果**: ✅ 成功

- **検索クエリ**: `source:fsxn @attributes.result:Failure`
- **検出されたイベント**:
  - ユーザー: `unknown@external.com`
  - 操作: `Open`
  - パス: `/vol/data/confidential/secret.pdf`
  - クライアントIP: `192.168.1.100`
  - 結果: `Failure`

- **確認項目**:
  - [x] `@attributes.result:Failure` で1件以上表示
  - [x] `@attributes.user` が空でない（`unknown@external.com`）
  - [x] `@attributes.path` が空でない（`/vol/data/confidential/secret.pdf`）
  - [x] `@attributes.client_ip` が空でない（`192.168.1.100`）

![不正アクセス検知](../screenshots/datadog-unauthorized-access.png)

---

### ステップ 8: セットアップガイド日英対応確認

- **結果**: ⚠️ 条件付き合格

```bash
python3 scripts/compare-bilingual.py \
  --ja integrations/datadog/docs/ja/setup-guide.md \
  --en integrations/datadog/docs/en/setup-guide.md
```

- **見出し数**: 25（一致）
- **コードブロック数**: 9
- **テーブル数**: 3（一致）
- **差異件数**: 2件（コードブロック内コメントのローカライズ — 意図的）

| # | セクション | 差異種別 | 内容 |
|---|-----------|---------|------|
| 1 | Grok Parser | code_block | コメント行が日本語/英語で異なる（意図的） |
| 2 | 動作確認 | code_block | コメント行が日本語/英語で異なる（意図的） |

> **判定**: コードブロック内のコメントは各言語で自然な表現を使用しており、実行に影響しないため合格とする。

---

## 検出された問題点と対処

| # | 問題内容 | 重要度 | 対処方法 | ステータス |
|---|---------|--------|---------|-----------|
| 1 | gzip 圧縮ペイロードが AP1 サイトでインデックスされない | 高 | Lambda で ENABLE_GZIP 環境変数で制御可能に。デフォルト無効。Datadog 公式は gzip 推奨だが urllib3 の Lambda ランタイム版との互換性問題の可能性。 | ✅ 対処済み |
| 2 | テストデータのタイムスタンプが古いと検索に表示されない | 高 | Datadog は18時間以上前のタイムスタンプを拒否（公式仕様）。テストデータ生成スクリプト追加。handler.py にコメントで制限を記載。 | ✅ 対処済み |
| 3 | CloudFormation テンプレートに VPC 設定オプションがない | 中 | VpcEnabled/VpcSubnetIds/VpcSecurityGroupIds パラメータ追加（条件付き） | ✅ 対処済み |
| 4 | Lambda コードデプロイ手順が未文書化 | 中 | セットアップガイド（日英）にデプロイ手順を追加 | ✅ 対処済み |
| 5 | Datadog サイト一覧が不完全 | 中 | 全7サイト（US1/US3/US5/EU1/AP1/AP2/US1-FED）を CloudFormation と docs に追加 | ✅ 対処済み |
| 6 | ハードコードされた値がある | 中 | DD_ENV, ENABLE_GZIP を環境変数化。全設定を変数駆動に変更。 | ✅ 対処済み |
| 7 | Facets 設定が UI エラーで1つしか作成できなかった | 低 | `scripts/setup-datadog-facets.py` スクリプト追加（サンプルログ送信 + UI 手順案内） | ✅ 対処済み |
| 8 | Datadog UI が無料トライアルで一部エラー | 低 | API 経由での操作は正常動作。有料プラン移行後に UI 再確認。 | 📝 記録済み |
| 9 | .env にパスワードが含まれていた | 高 | パスワードを削除。API Key と App Key のみ保持。 | ✅ 対処済み |

---

## 検証完了サマリ

| ステップ | 名称 | 結果 |
|---------|------|------|
| 1 | CloudFormation スタックデプロイ | ✅ 成功 |
| 2 | Lambda コードデプロイ | ✅ 成功 |
| 3 | Lambda テストイベント送信 | ✅ 成功 |
| 4 | Datadog ログ到着確認 | ✅ 成功 |
| 5 | Log Pipeline 設定 | ✅ 成功 |
| 6 | ダッシュボード作成 | ✅ 成功 |
| 7 | デモシナリオ1「不正アクセス検知」 | ✅ 成功 |
| 8 | セットアップガイド日英対応確認 | ⚠️ 条件付き合格 |

**総合判定**: ✅ 合格（E2E 動作確認完了）
