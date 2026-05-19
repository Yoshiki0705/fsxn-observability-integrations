# 19.1 EMS Webhook 用共有テンプレートのデプロイ

## 概要

`shared/templates/ems-webhook-apigw.yaml` を使用して EMS Webhook パス（REST API Gateway, REGIONAL）をデプロイし、EMS 受信 Lambda に EMS パーサーレイヤーをアタッチして Splunk HEC へのイベント転送を設定する手順書。

## 前提条件

- AWS CLI v2 が設定済み（`ap-northeast-1` リージョン）
- Splunk HEC トークンが Secrets Manager に登録済み（`splunk/fsxn-hec-token`）
- Splunk に `fsxn_ems` Index が作成済み
- `shared/lambda-layers/ems-parser/` レイヤーがビルド済み
- EMS Webhook 用 API キーが Secrets Manager に登録済み（`ems-webhook-api-key`）

## 手順

### Step 1: EMS パーサーレイヤーの確認

```bash
# レイヤーのディレクトリ構造を確認
ls -la shared/lambda-layers/ems-parser/

# レイヤーが Lambda にデプロイ可能な状態か確認
ls shared/lambda-layers/ems-parser/python/
```

### Step 2: テンプレートの確認

```bash
# テンプレートの存在確認
ls -la shared/templates/ems-webhook-apigw.yaml

# cfn-lint でテンプレートを検証
cfn-lint shared/templates/ems-webhook-apigw.yaml
```

**確認ポイント:**
- REST API Gateway（REGIONAL エンドポイント）が定義されていること
- Lambda 関数リソースが定義されていること
- IAM ロールが最小権限で定義されていること

### Step 3: CloudFormation スタックのデプロイ

```bash
# EMS Webhook スタックのデプロイ
aws cloudformation deploy \
  --template-file shared/templates/ems-webhook-apigw.yaml \
  --stack-name fsxn-ems-webhook \
  --region ap-northeast-1 \
  --parameter-overrides \
    HecSecretArn="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk/fsxn-hec-token-XXXXXX" \
    ApiKeySecretArn="arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-webhook-api-key-XXXXXX" \
    SplunkHecEndpoint="https://<splunk-hec-host>:8088/services/collector/event" \
    EmsParserLayerArn="arn:aws:lambda:ap-northeast-1:123456789012:layer:ems-parser:1" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

### Step 4: スタックステータスの確認

```bash
# スタックステータスを確認
aws cloudformation describe-stacks \
  --stack-name fsxn-ems-webhook \
  --region ap-northeast-1 \
  --query 'Stacks[0].StackStatus' \
  --output text
```

**期待される出力:** `CREATE_COMPLETE` または `UPDATE_COMPLETE`

### Step 5: Lambda 設定の確認

```bash
# Lambda 関数の設定を確認
aws lambda get-function-configuration \
  --function-name fsxn-splunk-ems-webhook \
  --region ap-northeast-1 \
  --query '{Runtime: Runtime, Layers: Layers[*].Arn, Timeout: Timeout, MemorySize: MemorySize}'
```

**確認ポイント:**
- Runtime: `python3.12`
- Layers に `ems-parser` レイヤーが含まれること
- 環境変数に `SPLUNK_SOURCETYPE=fsxn:ems:webhook` が設定されていること
- 環境変数に `SPLUNK_SOURCE=fsxn-ems` が設定されていること

### Step 6: Lambda 環境変数の確認

```bash
# 環境変数を確認
aws lambda get-function-configuration \
  --function-name fsxn-splunk-ems-webhook \
  --region ap-northeast-1 \
  --query 'Environment.Variables'
```

**期待される設定:**
```json
{
  "SPLUNK_HEC_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk/fsxn-hec-token-XXXXXX",
  "SPLUNK_HEC_ENDPOINT": "https://<splunk-hec-host>:8088/services/collector/event",
  "SPLUNK_SOURCETYPE": "fsxn:ems:webhook",
  "SPLUNK_SOURCE": "fsxn-ems",
  "SPLUNK_INDEX": "fsxn_ems"
}
```

### Step 7: API Gateway エンドポイントの確認

```bash
# API Gateway エンドポイント URL を取得
aws cloudformation describe-stacks \
  --stack-name fsxn-ems-webhook \
  --region ap-northeast-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`EmsApiEndpoint`].OutputValue' \
  --output text
```

### Step 8: HEC 認証ヘッダーの確認

Lambda が Splunk HEC に送信する際のヘッダー形式を確認:

```
Authorization: Splunk <token>
Content-Type: application/json
```

**sourcetype/source 設定:**
- `sourcetype`: `fsxn:ems:webhook`
- `source`: `fsxn-ems`
- `index`: `fsxn_ems`

## 検証チェックリスト

- [ ] `shared/templates/ems-webhook-apigw.yaml` が cfn-lint を通過
- [ ] CloudFormation スタックステータスが `CREATE_COMPLETE`
- [ ] Lambda に `ems-parser` レイヤーがアタッチされている
- [ ] Lambda 環境変数に `SPLUNK_SOURCETYPE=fsxn:ems:webhook` が設定
- [ ] Lambda 環境変数に `SPLUNK_SOURCE=fsxn-ems` が設定
- [ ] API Gateway エンドポイントが取得できた
- [ ] HEC 認証ヘッダーが `Authorization: Splunk <token>` 形式

## トラブルシューティング

### スタックが CREATE_FAILED になる

- **原因**: IAM ロール名の競合、パラメータ不正
- **解決**: `aws cloudformation describe-stack-events` でエラー詳細を確認

### Lambda レイヤーのアタッチに失敗

- **原因**: レイヤー ARN が無効、リージョン不一致
- **解決**: `aws lambda list-layers` で正しい ARN を確認

### API Gateway が作成されない

- **原因**: テンプレートの REST API 定義に問題
- **解決**: テンプレートの `AWS::ApiGateway::RestApi` リソースを確認

## 関連タスク

- Task 19.2: ARP ランサムウェア検知アラートテスト
- Task 19.3: Quota 超過アラートテスト
- Task 17.2: デモシナリオ2「ランサムウェア検知」（シミュレーション版）
