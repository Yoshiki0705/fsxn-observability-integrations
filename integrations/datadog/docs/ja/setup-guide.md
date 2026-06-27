# Datadog セットアップガイド

## 概要

Amazon FSx for NetApp ONTAP の監査ログを Datadog Logs に配信するサーバーレス統合のセットアップ手順です。

## 前提条件

- AWS アカウント（FSx for ONTAP 稼働中）
- Datadog アカウント（Logs 機能有効）
- AWS CLI v2 設定済み
- FSx for ONTAP 監査ログが S3 バケットに出力されていること

## Step 1: Datadog API Key の準備

### 1.1 Datadog で API Key を取得

1. Datadog コンソールにログイン
2. **Organization Settings** → **API Keys** に移動
3. **New Key** をクリックして新しい API Key を作成
4. Key 名: `fsxn-audit-log-shipper`
5. 生成された API Key をコピー

### 1.2 AWS Secrets Manager に保存

```bash
aws secretsmanager create-secret \
  --name "datadog/fsxn-api-key" \
  --description "Datadog API Key for FSx for ONTAP audit log integration" \
  --secret-string '{"api_key":"YOUR_DATADOG_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: S3 Access Point の設定

FSx for ONTAP 監査ログバケットに S3 Access Point を作成します（未作成の場合）。

```bash
aws s3control create-access-point \
  --account-id YOUR_ACCOUNT_ID \
  --name fsxn-audit-ap \
  --bucket YOUR_AUDIT_LOG_BUCKET \
  --region ap-northeast-1
```

## Step 3: CloudFormation デプロイ

```bash
cd integrations/datadog

aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog/fsxn-api-key-XXXXXX \
    DatadogSite=datadoghq.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### パラメータ説明

| パラメータ | 説明 |
|-----------|------|
| `FsxS3AccessPointArn` | FSx for ONTAP S3 Access Point の ARN（audit volume にアタッチ） |
| `DatadogApiKeySecretArn` | Secrets Manager に保存した API Key の ARN |
| `DatadogSite` | Datadog サイト（下記参照） |

### Datadog サイト一覧

| サイト | ドメイン | 用途 | Logs Intake エンドポイント |
|-------|---------|------|--------------------------|
| US1 | `datadoghq.com` | 米国東部（デフォルト） | `http-intake.logs.datadoghq.com` |
| US3 | `us3.datadoghq.com` | 米国（Azure 連携） | `http-intake.logs.us3.datadoghq.com` |
| US5 | `us5.datadoghq.com` | 米国西部 | `http-intake.logs.us5.datadoghq.com` |
| EU1 | `datadoghq.eu` | EU（フランクフルト） | `http-intake.logs.datadoghq.eu` |
| AP1 | `ap1.datadoghq.com` | アジア太平洋（東京） | `http-intake.logs.ap1.datadoghq.com` |
| AP2 | `ap2.datadoghq.com` | アジア太平洋（シドニー） | `http-intake.logs.ap2.datadoghq.com` |
| US1-FED | `ddog-gov.com` | 米国政府（FedRAMP） | `http-intake.logs.ddog-gov.com` |

> **リージョン選択の目安**:
> - APAC（日本、オーストラリア等）: `ap1.datadoghq.com` または `ap2.datadoghq.com`
> - EMEA（欧州、中東、アフリカ）: `datadoghq.eu`
> - AMERICAS（北米、南米）: `datadoghq.com`、`us3.datadoghq.com`、`us5.datadoghq.com`
> - 米国政府機関: `ddog-gov.com`

## Step 4: Datadog 側の設定

### 4.1 Log Pipeline の作成

1. Datadog コンソール → **Logs** → **Configuration** → **Pipelines**
2. **New Pipeline** をクリック
3. 設定:
   - **Filter**: `source:fsxn`
   - **Name**: `FSx for ONTAP Audit Logs`

### 4.2 Pipeline 内のプロセッサ追加

#### Grok Parser
```
# Parse rule for FSx for ONTAP audit logs
fsxn_audit %{data:attributes}
```

#### Status Remapper
- **Status attribute**: `attributes.result`

#### Date Remapper
- **Date attribute**: `attributes.timestamp`

### 4.3 Facets の作成

以下のフィールドを Facet として登録すると検索が便利になります:

| Facet | Path | Type |
|-------|------|------|
| SVM | `@attributes.svm` | String |
| User | `@attributes.user` | String |
| Operation | `@attributes.operation` | String |
| Client IP | `@attributes.client_ip` | String |
| Result | `@attributes.result` | String |
| File Path | `@attributes.path` | String |

### 4.4 ダッシュボード作成（推奨）

Datadog で FSx for ONTAP 監査ログ用のダッシュボードを作成:

- **ログ量推移**: `source:fsxn` のログカウント時系列
- **操作別内訳**: `@attributes.operation` のトップリスト
- **ユーザー別アクティビティ**: `@attributes.user` のトップリスト
- **エラー率**: `@attributes.result:failure` の割合

## Step 5: 動作確認

### 5.1 テストイベント送信

FSx for ONTAP でファイル操作を実行:

```bash
# File operations on FSx for ONTAP mount point
echo "test" > /mnt/fsxn/test-audit.txt
cat /mnt/fsxn/test-audit.txt
rm /mnt/fsxn/test-audit.txt
```

### 5.2 Datadog でログ確認

1. Datadog コンソール → **Logs** → **Search**
2. 検索クエリ: `source:fsxn`
3. 数分以内にログが表示されることを確認

### 5.3 CloudWatch でLambda 確認

```bash
aws logs tail /aws/lambda/fsxn-datadog-integration-shipper --follow
```

## トラブルシューティング

### ログが Datadog に届かない

1. **Lambda エラー確認**:
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/fsxn-datadog-integration-shipper \
     --filter-pattern "ERROR"
   ```

2. **DLQ メッセージ確認**:
   ```bash
   aws sqs get-queue-attributes \
     --queue-url https://sqs.ap-northeast-1.amazonaws.com/123456789012/fsxn-datadog-integration-dlq \
     --attribute-names ApproximateNumberOfMessages
   ```

3. **API Key 確認**: Secrets Manager の値が正しいか確認

4. **タイムスタンプの確認**: Datadog はログの `date` フィールドを使ってインデックスします。ログのタイムスタンプが古すぎる（retention window 外）場合、検索結果に表示されません。テスト時は現在時刻に近いタイムスタンプを使用してください。

5. **Datadog サイトの確認**: Lambda の環境変数 `DATADOG_SITE` が正しいサイトを指しているか確認してください。日本リージョンの場合は `ap1.datadoghq.com` を使用します。

### VPC 制限付き S3 Access Point を使用する場合

S3 Access Point が VPC に制限されている場合、Lambda も同じ VPC 内で実行する必要があります。CloudFormation デプロイ時に以下のパラメータを追加してください:

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:datadog/fsxn-api-key-XXXXXX \
    DatadogSite=ap1.datadoghq.com \
    VpcEnabled=true \
    VpcSubnetIds=subnet-xxx,subnet-yyy \
    VpcSecurityGroupIds=sg-xxx \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

> **注意**: VPC 内の Lambda から Datadog API にアクセスするには、NAT Gateway または VPC エンドポイントが必要です。Secrets Manager へのアクセスにも VPC エンドポイント（`com.amazonaws.ap-northeast-1.secretsmanager`）が必要です。

### gzip 圧縮に関する既知の問題

現在、Datadog AP1 サイト（`ap1.datadoghq.com`）で gzip 圧縮ペイロードが正しくインデックスされない事象が確認されています。Lambda は非圧縮で送信するよう設定されています。大量ログ環境でペイロードサイズが問題になる場合は、Datadog サポートに gzip 対応状況を確認してください。

### レート制限エラー

Datadog API のレート制限に達した場合、Lambda は自動的に exponential backoff でリトライします。頻繁に発生する場合は Lambda の同時実行数を制限してください。

```bash
aws lambda put-function-concurrency \
  --function-name fsxn-datadog-integration-shipper \
  --reserved-concurrent-executions 5
```

### Lambda コードのデプロイ

CloudFormation テンプレートはプレースホルダーコードでデプロイされます。実際の handler.py をデプロイするには:

```bash
# Package Lambda code
cd integrations/datadog/lambda
zip function.zip handler.py

# Update Lambda function code
aws lambda update-function-code \
  --function-name fsxn-datadog-integration-shipper \
  --zip-file fileb://function.zip \
  --region ap-northeast-1
```

> **注意**: CI/CD パイプラインでは S3 バケット経由でのデプロイを推奨します。
