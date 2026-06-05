# CrowdStrike Falcon LogScale Integration

🌐 [日本語](#概要) | [English](#overview)

---

## 概要

FSx for ONTAP 監査ログを CrowdStrike Falcon LogScale (Next-Gen SIEM) にサーバーレスで配信するパターンです。

Falcon LogScale は Splunk HEC 互換エンドポイントをサポートしているため、本統合は HEC フォーマットで配信します。

### 配信方式

| 方式 | エンドポイント | 認証 | 備考 |
|------|-------------|------|------|
| **HEC (推奨)** | `/api/v1/ingest/hec` | Bearer Token (Ingest Token) | Splunk HEC 互換 |
| Structured Data | `/api/v1/ingest/humio-structured` | Bearer Token | JSON 構造化データ |
| Raw | `/api/v1/ingest/raw` | Bearer Token | 非構造化テキスト |

### アーキテクチャ

```
FSx for ONTAP → S3 Access Point → EventBridge Scheduler → Lambda → LogScale HEC
```

### 前提条件

- CrowdStrike Falcon LogScale アカウント (Cloud or Self-hosted)
- LogScale Ingest Token (リポジトリに紐付け)
- AWS アカウント + FSx for ONTAP (監査ログ有効化済み)

---

## Overview

Serverless delivery of FSx for ONTAP audit logs to CrowdStrike Falcon LogScale (Next-Gen SIEM).

Falcon LogScale supports Splunk HEC-compatible endpoints, so this integration ships logs in HEC format.

### Delivery Methods

| Method | Endpoint | Auth | Notes |
|--------|----------|------|-------|
| **HEC (recommended)** | `/api/v1/ingest/hec` | Bearer Token (Ingest Token) | Splunk HEC compatible |
| Structured Data | `/api/v1/ingest/humio-structured` | Bearer Token | JSON structured data |
| Raw | `/api/v1/ingest/raw` | Bearer Token | Unstructured text |

### Architecture

```
FSx for ONTAP → S3 Access Point → EventBridge Scheduler → Lambda → LogScale HEC
```

### Prerequisites

- CrowdStrike Falcon LogScale account (Cloud or Self-hosted)
- LogScale Ingest Token (associated with a repository)
- AWS account + FSx for ONTAP (audit logging enabled)

### Quick Start

```bash
# 1. Set environment variables
export CROWDSTRIKE_LOGSCALE_URL=https://cloud.us.humio.com  # or your self-hosted URL
export CROWDSTRIKE_INGEST_TOKEN=<your-ingest-token>

# 2. Test with sample XML audit log
python3 shared/scripts/test-xml-e2e.py --vendor crowdstrike

# 3. Deploy CloudFormation stack
aws cloudformation deploy \
  --template-file integrations/crowdstrike/template.yaml \
  --stack-name fsxn-crowdstrike-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
    LogScaleIngestTokenSecretArn=<secret-arn> \
    LogScaleUrl=https://cloud.us.humio.com \
  --capabilities CAPABILITY_NAMED_IAM
```

### CrowdStrike LogScale URLs

| Region | URL |
|--------|-----|
| US (cloud) | `https://cloud.us.humio.com` |
| EU (cloud) | `https://cloud.humio.com` |
| US-2 (cloud) | `https://cloud.community.humio.com` |
| Self-hosted | Your custom URL |

### References

- [LogScale Ingest API Docs](https://library.humio.com/logscale-api/api-ingest.html)
- [LogScale HEC Endpoint](https://library.humio.com/logscale-api/log-shippers-hec.html)
- [LogScale Structured Data API](https://library.humio.com/logscale-api/api-ingest-structured-data.html)
- [CrowdStrike Developer Center](https://developer.crowdstrike.com/ngsiem/data-ingestion/)
