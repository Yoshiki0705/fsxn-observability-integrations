# CrowdStrike Falcon LogScale セットアップガイド

## 前提条件

- CrowdStrike Falcon LogScale アカウント (Cloud or Self-hosted)
- FSx 監査ログ用の LogScale リポジトリ
- リポジトリに紐付けた Ingest Token
- AWS アカウント + FSx for ONTAP (監査ログ有効化済み)
- S3 Access Point 設定済み

## Step 1: LogScale リポジトリの作成

1. LogScale にログイン
2. **Repositories** → **New Repository**
3. 名前: `fsxn-audit`
4. 保持期間: コンプライアンス要件に応じて設定

## Step 2: Ingest Token の作成

1. リポジトリ → **Settings** → **Ingest tokens**
2. **Add token** をクリック
3. 名前: `fsxn-lambda-shipper`
4. Parser: `json`（推奨）
5. トークン値をコピー

## Step 3: AWS Secrets Manager にトークン保存

```bash
aws secretsmanager create-secret \
  --name crowdstrike/fsxn-logscale-token \
  --secret-string "<your-ingest-token>" \
  --region ap-northeast-1
```

## Step 4: CloudFormation スタックのデプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/crowdstrike/template.yaml \
  --stack-name fsxn-crowdstrike-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    LogScaleIngestTokenSecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:crowdstrike/fsxn-logscale-token \
    LogScaleUrl=https://cloud.us.humio.com \
  --capabilities CAPABILITY_NAMED_IAM
```

## Step 5: 動作確認

```bash
# Lambda ログ確認
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-crowdstrike-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-300)*1000))") \
  --region ap-northeast-1

# DLQ が空であることを確認
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages
```

LogScale で検索:
```
source = "fsxn-ontap"
```

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| HTTP 401 | Ingest Token が無効 | Secrets Manager のトークンが LogScale と一致するか確認 |
| HTTP 403 | トークンに権限なし | トークンが正しいリポジトリに紐付いているか確認 |
| LogScale にログなし | URL またはパーサーの問題 | LogScale URL がアカウントのリージョンと一致するか確認 |
| Lambda タイムアウト | ネットワーク問題 | Lambda にインターネットアクセスがあるか確認（NAT GW or VPC 外） |

## 参考リンク

- [LogScale Ingest API](https://library.humio.com/logscale-api/api-ingest.html)
- [LogScale HEC エンドポイント](https://library.humio.com/logscale-api/log-shippers-hec.html)
- [CrowdStrike Developer Center](https://developer.crowdstrike.com/ngsiem/data-ingestion/)
