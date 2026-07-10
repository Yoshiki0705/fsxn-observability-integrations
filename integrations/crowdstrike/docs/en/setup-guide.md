# CrowdStrike Falcon LogScale Setup Guide

🌐 [日本語](../ja/setup-guide.md) | **English** (this page)

## Prerequisites

- CrowdStrike Falcon LogScale account (Cloud or Self-hosted)
- A LogScale repository created for FSx audit logs
- An Ingest Token associated with the repository
- AWS account with FSx for ONTAP (audit logging enabled)
- S3 Access Point configured for audit log access

## Step 1: Create a LogScale Repository

1. Log in to your LogScale instance
2. Navigate to **Repositories** → **New Repository**
3. Name: `fsxn-audit` (or your preferred name)
4. Retention: Configure based on compliance requirements

## Step 2: Create an Ingest Token

1. Navigate to your repository → **Settings** → **Ingest tokens**
2. Click **Add token**
3. Name: `fsxn-lambda-shipper`
4. Parser: `json` (recommended) or create a custom parser
5. Copy the token value

## Step 3: Store Token in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name crowdstrike/fsxn-logscale-token \
  --secret-string "<your-ingest-token>" \
  --region ap-northeast-1
```

## Step 4: Deploy CloudFormation Stack

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

## Step 5: Verify

```bash
# Check Lambda logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-crowdstrike-integration-shipper \
  --start-time $(python3 -c "import time; print(int((time.time()-300)*1000))") \
  --region ap-northeast-1

# Check DLQ is empty
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages
```

In LogScale, search:
```
source = "fsxn-ontap"
```

## LogScale Parser (Optional)

For richer field extraction, create a custom parser in LogScale:

```
parseJson()
| rename(field=event_type, as=EventID)
| rename(field=client_ip, as=ClientIP)
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| HTTP 401 | Invalid ingest token | Verify token in Secrets Manager matches LogScale |
| HTTP 403 | Token lacks permissions | Check token is associated with correct repository |
| No logs in LogScale | Wrong URL or parser issue | Verify LogScale URL region matches your account |
| Lambda timeout | Network issue | Ensure Lambda has internet access (NAT GW or non-VPC) |

## References

- [LogScale Ingest API](https://library.humio.com/logscale-api/api-ingest.html)
- [LogScale HEC Endpoint](https://library.humio.com/logscale-api/log-shippers-hec.html)
- [CrowdStrike Developer Center](https://developer.crowdstrike.com/ngsiem/data-ingestion/)
