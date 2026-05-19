# Splunk Serverless Verification Scripts

🌐 [日本語](#日本語) | [English](#english)

---

## English

Verification and operational scripts for the Splunk Serverless integration. These scripts support the E2E verification pipeline documented in the setup guide.

### Scripts

| Script | Purpose | Prerequisites |
|--------|---------|---------------|
| `verify-splunk-account.sh` | Verify Splunk account access and HEC endpoint health | `curl`, Splunk account |
| `create-hec-token.sh` | Document HEC token creation steps and verify existing tokens | `curl`, Splunk account |
| `register-secret.sh` | Register HEC token in AWS Secrets Manager | AWS CLI v2, Python 3 |
| `deploy-stack.sh` | Deploy the CloudFormation stack and validate status | AWS CLI v2 |

### Usage

#### verify-splunk-account.sh

Verifies that your Splunk account is accessible and the HEC (HTTP Event Collector) endpoint is reachable.

```bash
# Without environment variable (prints manual instructions)
./verify-splunk-account.sh

# With endpoint configured (performs automated health check)
export SPLUNK_HEC_ENDPOINT='https://<your-splunk-host>:8088'
./verify-splunk-account.sh
```

**What it checks:**

1. Documents the manual steps to verify Splunk account access
2. Checks if `SPLUNK_HEC_ENDPOINT` environment variable is set
3. If set, sends a request to `/services/collector/health` and reports the result
4. Prints troubleshooting instructions if the endpoint is not reachable

**Exit codes:**

- `0` — HEC endpoint is healthy, or check was skipped (endpoint not set)
- `1` — HEC endpoint is unreachable or unhealthy

#### create-hec-token.sh

Documents the manual steps to create a HEC token in Splunk UI and provides automated verification of an existing token.

```bash
# Show manual creation steps
./create-hec-token.sh

# Verify an existing token
./create-hec-token.sh --endpoint https://<your-splunk-host>:8088 --token <HEC_TOKEN>
```

**What it does:**

1. Without arguments: prints step-by-step HEC token creation instructions
2. With `--endpoint` and `--token`: validates token format (UUID), checks HEC health, and sends a test event

#### deploy-stack.sh

Deploys the CloudFormation stack (`integrations/splunk-serverless/template.yaml`), validates the stack status, and prints stack outputs.

```bash
./deploy-stack.sh \
  --hec-endpoint https://splunk.example.com:8088 \
  --secret-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk/fsxn-hec-token-XXXXXX \
  --s3-ap-arn arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --bucket-name my-audit-log-bucket \
  --ems-api-key-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-api-key-XXXXXX \
  --region ap-northeast-1 \
  --stack-name fsxn-splunk-integration
```

**What it does:**

1. Validates the CloudFormation template with `cfn-lint` (if installed)
2. Deploys the stack using `aws cloudformation deploy`
3. Waits for stack creation/update to complete
4. Checks stack status is `CREATE_COMPLETE` or `UPDATE_COMPLETE`
5. Prints stack outputs (Lambda ARN, EMS API endpoint, DLQ ARN)

**Parameters:**

| Parameter | Description | Required |
|-----------|-------------|----------|
| `--hec-endpoint` | Splunk HEC endpoint URL | Yes |
| `--secret-arn` | Secrets Manager ARN for HEC token | Yes |
| `--s3-ap-arn` | S3 Access Point ARN for audit logs | Yes |
| `--bucket-name` | S3 bucket name for event notification | Yes |
| `--ems-api-key-arn` | Secrets Manager ARN for EMS webhook API key | Yes |
| `--region` | AWS region (default: `ap-northeast-1`) | No |
| `--stack-name` | CloudFormation stack name (default: `fsxn-splunk-integration`) | No |

**Exit codes:**

- `0` — Stack deployed successfully (CREATE_COMPLETE or UPDATE_COMPLETE)
- `1` — Deployment failed or stack in error state

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SPLUNK_HEC_ENDPOINT` | Splunk HEC endpoint URL (e.g., `https://splunk.example.com:8088`) | Optional (script provides guidance if not set) |
| `AWS_REGION` | AWS region (used as default if `--region` not specified) | Optional |

### Related Documentation

- [Setup Guide (English)](../docs/en/setup-guide.md)
- [Setup Guide (日本語)](../docs/ja/setup-guide.md)
- [E2E Verification Orchestrator](../../../scripts/verify-splunk-e2e.sh)

---

## 日本語

Splunk Serverless 統合の検証・運用スクリプト集です。セットアップガイドに記載された E2E 検証パイプラインをサポートします。

### スクリプト一覧

| スクリプト | 目的 | 前提条件 |
|-----------|------|---------|
| `verify-splunk-account.sh` | Splunk アカウントアクセスと HEC エンドポイントの正常性確認 | `curl`、Splunk アカウント |
| `create-hec-token.sh` | HEC トークン作成手順のドキュメント化と既存トークンの検証 | `curl`、Splunk アカウント |
| `register-secret.sh` | HEC トークンを AWS Secrets Manager に登録 | AWS CLI v2、Python 3 |
| `deploy-stack.sh` | CloudFormation スタックのデプロイとステータス検証 | AWS CLI v2 |

### 使い方

#### verify-splunk-account.sh

Splunk アカウントにアクセス可能であること、および HEC（HTTP Event Collector）エンドポイントが到達可能であることを確認します。

```bash
# 環境変数未設定の場合（手動確認手順を表示）
./verify-splunk-account.sh

# エンドポイント設定済みの場合（自動ヘルスチェックを実行）
export SPLUNK_HEC_ENDPOINT='https://<your-splunk-host>:8088'
./verify-splunk-account.sh
```

**確認内容:**

1. Splunk アカウントアクセスの手動確認手順をドキュメント化
2. `SPLUNK_HEC_ENDPOINT` 環境変数が設定されているか確認
3. 設定されている場合、`/services/collector/health` にリクエストを送信し結果を報告
4. エンドポイントに到達できない場合、トラブルシューティング手順を表示

**終了コード:**

- `0` — HEC エンドポイントが正常、またはチェックがスキップされた（エンドポイント未設定）
- `1` — HEC エンドポイントに到達不可または異常

#### create-hec-token.sh

Splunk UI での HEC トークン作成手順をドキュメント化し、既存トークンの自動検証を提供します。

```bash
# 手動作成手順を表示
./create-hec-token.sh

# 既存トークンを検証
./create-hec-token.sh --endpoint https://<your-splunk-host>:8088 --token <HEC_TOKEN>
```

**機能:**

1. 引数なし: HEC トークン作成のステップバイステップ手順を表示
2. `--endpoint` と `--token` 指定: トークン形式（UUID）の検証、HEC ヘルスチェック、テストイベント送信

#### deploy-stack.sh

CloudFormation スタック（`integrations/splunk-serverless/template.yaml`）をデプロイし、ステータスを検証してスタック出力を表示します。

```bash
./deploy-stack.sh \
  --hec-endpoint https://splunk.example.com:8088 \
  --secret-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk/fsxn-hec-token-XXXXXX \
  --s3-ap-arn arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --bucket-name my-audit-log-bucket \
  --ems-api-key-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-api-key-XXXXXX \
  --region ap-northeast-1 \
  --stack-name fsxn-splunk-integration
```

**機能:**

1. `cfn-lint` によるテンプレート検証（インストール済みの場合）
2. `aws cloudformation deploy` によるスタックデプロイ
3. スタック作成/更新の完了を待機
4. スタックステータスが `CREATE_COMPLETE` または `UPDATE_COMPLETE` であることを確認
5. スタック出力（Lambda ARN、EMS API エンドポイント、DLQ ARN）を表示

**パラメータ:**

| パラメータ | 説明 | 必須 |
|-----------|------|------|
| `--hec-endpoint` | Splunk HEC エンドポイント URL | はい |
| `--secret-arn` | HEC トークンの Secrets Manager ARN | はい |
| `--s3-ap-arn` | 監査ログ用 S3 Access Point ARN | はい |
| `--bucket-name` | イベント通知用 S3 バケット名 | はい |
| `--ems-api-key-arn` | EMS Webhook API キーの Secrets Manager ARN | はい |
| `--region` | AWS リージョン（デフォルト: `ap-northeast-1`） | いいえ |
| `--stack-name` | CloudFormation スタック名（デフォルト: `fsxn-splunk-integration`） | いいえ |

**終了コード:**

- `0` — スタックデプロイ成功（CREATE_COMPLETE または UPDATE_COMPLETE）
- `1` — デプロイ失敗またはスタックがエラー状態

### 環境変数

| 変数 | 説明 | 必須 |
|------|------|------|
| `SPLUNK_HEC_ENDPOINT` | Splunk HEC エンドポイント URL（例: `https://splunk.example.com:8088`） | 任意（未設定時はガイダンスを表示） |
| `AWS_REGION` | AWS リージョン（`--region` 未指定時のデフォルトとして使用） | 任意 |

### 関連ドキュメント

- [セットアップガイド（日本語）](../docs/ja/setup-guide.md)
- [セットアップガイド（English）](../docs/en/setup-guide.md)
- [E2E 検証オーケストレーター](../../../scripts/verify-splunk-e2e.sh)
