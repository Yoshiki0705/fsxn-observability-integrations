# Elastic セットアップガイド

🌐 [English](../en/setup-guide.md)

## 概要

FSx for ONTAP 監査ログを Elasticsearch Bulk API で配信し、Kibana で可視化するセットアップ手順です。

## 前提条件

- Elastic Cloud または自己ホスト Elasticsearch クラスタ
- [前提リソース](../../../docs/ja/prerequisites.md)デプロイ済み

## Step 1: Elasticsearch API Key の作成

```bash
# Elastic Cloud の場合: Kibana → Stack Management → API Keys → Create
aws secretsmanager create-secret \
  --name "elastic/fsxn-api-key" \
  --secret-string '{"api_key":"YOUR_ENCODED_API_KEY"}' \
  --region ap-northeast-1
```

## Step 2: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/elastic/template.yaml \
  --stack-name fsxn-elastic-integration \
  --parameter-overrides \
    S3AccessPointArn=$AP_ARN \
    ElasticApiKeySecretArn=arn:aws:secretsmanager:...:secret:elastic/fsxn-api-key-XXXXX \
    ElasticEndpoint=https://my-cluster.es.ap-northeast-1.aws.found.io:9243 \
    S3BucketName=$BUCKET_NAME \
    IndexPrefix=fsxn-audit \
  --capabilities CAPABILITY_IAM
```

## Step 3: Kibana 設定

### Index Pattern 作成
1. Kibana → **Stack Management** → **Index Patterns**
2. Pattern: `fsxn-audit-*`
3. Time field: `@timestamp`

### Discover で確認
- フィルタ: `fsxn.operation: ReadData`
- 時間範囲: Last 1 hour

### ダッシュボード例
- 操作別円グラフ: `fsxn.operation.keyword`
- ユーザー別棒グラフ: `user.name.keyword`
- 失敗アクセスタイムライン: `fsxn.result: Failure`

## インデックス管理

日次インデックス `fsxn-audit-YYYY.MM.DD` が自動作成されます。ILM (Index Lifecycle Management) で自動削除を設定:

```json
PUT _ilm/policy/fsxn-audit-policy
{
  "policy": {
    "phases": {
      "hot": {"actions": {"rollover": {"max_age": "30d"}}},
      "delete": {"min_age": "90d", "actions": {"delete": {}}}
    }
  }
}
```
