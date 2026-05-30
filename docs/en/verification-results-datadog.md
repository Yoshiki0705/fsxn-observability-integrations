# Datadog Integration Verification Results

- **Verification Date**: 2026-05-16T21:33:03+09:00
- **Verifier**: Yoshiki Fujiwara / Solutions Architect

### Verification Environment

- **AWS Region**: ap-northeast-1
- **CloudFormation Stack Name**: fsxn-datadog-integration
- **Lambda Function Name**: fsxn-datadog-integration-shipper
- **Datadog Site**: ap1.datadoghq.com (AP1 Tokyo)
- **FSx for ONTAP File System**: fs-0123456789abcdef0
- **S3 Access Point**: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-observability

---

## Verification Steps

### Step 1: CloudFormation Stack Deployment

- **Result**: ✅ Success

```bash
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    S3AccessPointArn=arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-observability \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fsxn-datadog-api-key-XXXXXX \
    DatadogSite=ap1.datadoghq.com \
    S3BucketName=fsxn-audit-obser-cbsi8mwwgahuh7sans3bbtxijig4sapn1b-ext-s3alias \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

- **Output**: `Successfully created/updated stack - fsxn-datadog-integration`
- **Stack Status**: CREATE_COMPLETE
- **Created Resources**: Lambda function, IAM role, DLQ, CloudWatch Alarms, EventBridge Rule, Log Group

---

### Step 2: Lambda Code Deployment

- **Result**: ✅ Success

```bash
cd integrations/datadog/lambda
zip function.zip handler.py
aws lambda update-function-code \
  --function-name fsxn-datadog-integration-shipper \
  --zip-file fileb://function.zip \
  --region ap-northeast-1
```

- **Note**: The CloudFormation template deploys with placeholder code, so the actual handler.py must be deployed separately.

---

### Step 3: Lambda Test Event Invocation

- **Result**: ✅ Success

```bash
aws lambda invoke \
  --function-name fsxn-datadog-integration-shipper \
  --payload '{"Records":[{"s3":{"bucket":{"name":"fsxn-audit-logs-observability-test"},"object":{"key":"audit/svm-prod-01/current/audit_current.json"}}}]}' \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 \
  response.json
```

- **Response**:
```json
{"statusCode": 200, "body": {"total_logs": 5, "total_shipped": 5, "errors": []}}
```

- **Checklist**:
  - [x] statusCode: 200
  - [x] total_logs: 5
  - [x] total_shipped: 5
  - [x] errors: [] (empty)

---

### Step 4: Datadog Log Arrival Confirmation

- **Result**: ✅ Success

- **Search Query**: `source:fsxn`
- **Arrived Logs**: 5 (from Lambda) + 2 (from direct API test)
- **Time to Arrival**: ~30-45 seconds

- **Checklist**:
  - [x] At least 1 log displayed with `source:fsxn`
  - [x] Each log has `attributes.svm` = `svm-prod-01`
  - [x] Each log has `attributes.user` = `admin@corp.local` etc.
  - [x] Each log has `attributes.operation` = `ReadData` etc.
  - [x] Each log has `attributes.client_ip` = `10.0.1.50` etc.
  - [x] Each log has `attributes.result` = `Success` / `Failure`
  - [x] Each log has `attributes.path` = `/vol/data/reports/quarterly.xlsx` etc.

![Datadog Log Arrival](../screenshots/datadog-logs-arrival.png)

---

### Step 5: Log Pipeline Configuration

- **Result**: ✅ Success

- **Pipeline Name**: FSx for ONTAP Audit Logs
- **Filter**: `source:fsxn`
- **Method**: Datadog UI (Logs → Configuration → Pipelines → New Pipeline)

![Log Pipeline Configuration](../screenshots/datadog-pipeline-config.png)

---

### Step 6: Dashboard Creation

- **Result**: ✅ Success

- **Dashboard Name**: FSx for ONTAP Audit Log Overview
- **Dashboard ID**: ggx-7ad-6e4
- **Method**: Datadog Dashboard API (`POST /api/v1/dashboard`)
- **Widgets**:
  - Log Volume Over Time (Timeseries)
  - Operations Breakdown (Top List)
  - User Activity (Top List)
  - Error Rate (Query Value)

![Dashboard](../screenshots/datadog-dashboard.png)

---

### Step 7: Demo Scenario 1 "Unauthorized Access Detection"

- **Result**: ✅ Success

- **Search Query**: `source:fsxn @attributes.result:Failure`
- **Detected Event**:
  - User: `unknown@external.com`
  - Operation: `Open`
  - Path: `/vol/data/confidential/secret.pdf`
  - Client IP: `192.168.1.100`
  - Result: `Failure`

- **Checklist**:
  - [x] At least 1 result with `@attributes.result:Failure`
  - [x] `@attributes.user` is not empty (`unknown@external.com`)
  - [x] `@attributes.path` is not empty (`/vol/data/confidential/secret.pdf`)
  - [x] `@attributes.client_ip` is not empty (`192.168.1.100`)

![Unauthorized Access Detection](../screenshots/datadog-unauthorized-access.png)

---

### Step 8: Setup Guide Bilingual Comparison

- **Result**: ⚠️ Conditional Pass

```bash
python3 scripts/compare-bilingual.py \
  --ja integrations/datadog/docs/ja/setup-guide.md \
  --en integrations/datadog/docs/en/setup-guide.md
```

- **Heading Count**: 25 (matched)
- **Code Block Count**: 9
- **Table Count**: 3 (matched)
- **Differences**: 2 (code block comment localization — intentional)

| # | Section | Diff Type | Details |
|---|---------|-----------|---------|
| 1 | Grok Parser | code_block | Comment lines differ between Japanese/English (intentional) |
| 2 | Verification | code_block | Comment lines differ between Japanese/English (intentional) |

> **Judgment**: Code block comments use natural expressions in each language and do not affect execution. Passed.

---

## Detected Issues and Resolutions

| # | Issue | Severity | Resolution | Status |
|---|-------|----------|------------|--------|
| 1 | gzip-compressed payload not indexed on AP1 site | High | Added ENABLE_GZIP env var to Lambda for control. Default disabled. Datadog officially recommends gzip but possible compatibility issue with urllib3 in Lambda runtime. | ✅ Resolved |
| 2 | Test data with old timestamps not appearing in search | High | Datadog rejects timestamps older than 18 hours (official spec). Added test data generation script. Documented limit in handler.py comments. | ✅ Resolved |
| 3 | CloudFormation template missing VPC configuration options | Medium | Added VpcEnabled/VpcSubnetIds/VpcSecurityGroupIds parameters (conditional) | ✅ Resolved |
| 4 | Lambda code deployment procedure undocumented | Medium | Added deployment steps to setup guide (ja/en) | ✅ Resolved |
| 5 | Datadog site list incomplete | Medium | Added all 7 sites (US1/US3/US5/EU1/AP1/AP2/US1-FED) to CloudFormation and docs | ✅ Resolved |
| 6 | Hardcoded values present | Medium | Converted DD_ENV, ENABLE_GZIP to environment variables. All config now variable-driven. | ✅ Resolved |
| 7 | Facets configuration — only 1 created due to UI error | Low | Added `scripts/setup-datadog-facets.py` script (sends sample logs + UI guidance) | ✅ Resolved |
| 8 | Datadog UI errors on free trial | Low | API operations work correctly. Re-verify UI after paid plan migration. | 📝 Documented |
| 9 | Password found in .env file | High | Removed password. Only API Key and App Key retained. | ✅ Resolved |

---

## Verification Summary

| Step | Name | Result |
|------|------|--------|
| 1 | CloudFormation Stack Deployment | ✅ Success |
| 2 | Lambda Code Deployment | ✅ Success |
| 3 | Lambda Test Event Invocation | ✅ Success |
| 4 | Datadog Log Arrival Confirmation | ✅ Success |
| 5 | Log Pipeline Configuration | ✅ Success |
| 6 | Dashboard Creation | ✅ Success |
| 7 | Demo Scenario 1 "Unauthorized Access Detection" | ✅ Success |
| 8 | Setup Guide Bilingual Comparison | ⚠️ Conditional Pass |

**Overall Judgment**: ✅ PASS (E2E verification complete)

---

## EMS/FPolicy Verification Results

### Additional Verification Environment

- **EMS/FPolicy Stack Name**: fsxn-datadog-ems-fpolicy
- **EMS Lambda Function Name**: fsxn-datadog-ems-fpolicy-ems
- **FPolicy Lambda Function Name**: fsxn-datadog-ems-fpolicy-fpolicy
- **EMS Webhook Stack**: fsxn-ems-webhook (existing)
- **FPolicy Server Stack**: fsxn-fp-srv (existing)

---

### Step E1: EMS/FPolicy Lambda Deployment

- **Result**: ✅ Success

```bash
aws cloudformation deploy \
  --template-file integrations/datadog/template-ems-fpolicy.yaml \
  --stack-name fsxn-datadog-ems-fpolicy \
  --parameter-overrides \
    DatadogApiKeySecretArn=arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:fsxn-datadog-api-key-XXXXXX \
    DatadogSite=ap1.datadoghq.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

- **Stack Status**: CREATE_COMPLETE
- **Created Resources**: EMS Lambda, FPolicy Lambda, IAM Roles, EventBridge Rule, Log Groups

![EMS Lambda CloudWatch Logs](../screenshots/aws-ems-lambda-logs.png)

---

### Step E2: ARP Ransomware Detection Test (EMS → Datadog)

- **Result**: ✅ Success

```bash
aws lambda invoke \
  --function-name fsxn-datadog-ems-fpolicy-ems \
  --payload '{"body":"{\"messageName\":\"arw.volume.state\",\"severity\":\"alert\",...}","requestContext":{}}' \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 response.json
```

- **Lambda Response**: `{"statusCode": 200, "body": {"total_events": 1, "shipped": 1}}`
- **Datadog Search**: `source:fsxn-ems` → 1 log confirmed
- **Log Content**: `Anti-ransomware: Volume vol_data state changed to attack-detected`
- **Time to Arrival**: ~30 seconds

![ARP Ransomware Detection — Datadog Log List](../screenshots/datadog-arp-detection.png)

![ARP Ransomware Detection — Log Detail](../screenshots/datadog-arp-log-detail.png)

---

### Step E3: Quota Threshold Exceeded Test (EMS → Datadog)

- **Result**: ✅ Success

- **Lambda Response**: `{"statusCode": 200, "body": {"total_events": 1, "shipped": 1}}`
- **Event Name**: `wafl.quota.softlimit.exceeded`
- **Parameters**: volume_name=vol_data, quota_target=user1, used_bytes=62914560, limit_bytes=52428800

---

### Step E4: FPolicy File Operation Test (FPolicy → Datadog)

- **Result**: ✅ Success

```bash
aws lambda invoke \
  --function-name fsxn-datadog-ems-fpolicy-fpolicy \
  --payload '{"source":"fpolicy.fsxn","detail-type":"FPolicy File Operation","detail":{"operation":"create","file_path":"/vol/data/test-fpolicy.txt","user":"admin@corp.local","client_ip":"10.0.1.50","vserver":"FPolicySMB","timestamp":"2026-05-16T23:56:00Z","protocol":"cifs"}}' \
  --cli-binary-format raw-in-base64-out \
  --region ap-northeast-1 response.json
```

- **Lambda Response**: `{"statusCode": 200, "body": {"total_events": 1, "shipped": 1}}`
- **Datadog Search**: `source:fsxn-fpolicy` → 1 log confirmed
- **Log Content**: `FPolicy: create /vol/data/test-fpolicy.txt by admin@corp.local from 10.0.1.50`
- **Time to Arrival**: ~30 seconds

![FPolicy File Operation — Datadog Log List](../screenshots/datadog-fpolicy-suspect-activity.png)

---

### EMS/FPolicy Verification Summary

| Step | Name | Result |
|------|------|--------|
| E1 | EMS/FPolicy Lambda Deployment | ✅ Success |
| E2 | ARP Ransomware Detection Test | ✅ Success |
| E3 | Quota Threshold Exceeded Test | ✅ Success |
| E4 | FPolicy File Operation Test | ✅ Success |

**EMS/FPolicy Overall Judgment**: ✅ PASS

---

## FPolicy Full-Path E2E Verification (via ECS Fargate)

- **Verification Date**: 2026-05-17T23:35–23:50 JST
- **Stacks**: fsxn-fpolicy-server (Fargate) + fsxn-datadog-ems-fpolicy (Lambda)
- **Pipeline**: ONTAP FPolicy → ECS Fargate (TCP:9898) → SQS → Lambda → Datadog

### Environment

| Component | Value |
|-----------|-------|
| ECS Cluster | fsxn-fpolicy-server-cluster |
| Fargate Task IP | 10.0.x.x |
| SQS Queue | fsxn-fpolicy-server-fpolicy-queue |
| Lambda Function | fsxn-datadog-ems-fpolicy-fpolicy |
| FSx for ONTAP SVM | FPolicySMB (svm-0123456789abcdef0) |
| FPolicy Engine | fpolicy_aws_engine |
| FPolicy Policy | fpolicy_aws (async, cifs) |
| Monitored Volume | smb_test_vol |
| SMB Share | //10.0.x.x/smb_test |

### Step F1: Fargate Deployment

- **Result**: ✅ Success
- **Key Finding**: ECR image MUST be built for `linux/amd64` (Apple Silicon builds produce arm64-only images, causing Fargate task pull failures)
- **Command**:
```bash
docker buildx build --platform linux/amd64 \
  -t <account>.dkr.ecr.<region>.amazonaws.com/fsxn-fpolicy-server:v2-timeout-fix \
  --push shared/fpolicy-server/
```

### Step F2: ONTAP FPolicy Connection

- **Result**: ✅ Success
- **Connection Verified**: KeepAlive messages received (2 ONTAP nodes connected)
- **Key Finding**: Updating External Engine IP requires temporarily disabling the FPolicy policy

```
[INFO] fpolicy-server: [+] Connection from ('10.0.x.x', 44107)
[INFO] fpolicy-server: [+] Connection from ('10.0.x.x', 24523)
[INFO] fpolicy-server: [Handshake] Policy=fpolicy_aws | Version=1.2
[INFO] fpolicy-server: [KeepAlive] Received — connection healthy
```

### Step F3: File Operation → Datadog Arrival

- **Result**: ✅ Success
- **Test Operation**: SMB file create via smbclient
- **End-to-End Latency**: ~6–8 seconds

```bash
smbclient //10.0.x.x/smb_test -U 'FPOLSMB\Administrator%<password>' \
  -c 'put /etc/hostname fpolicy_e2e_test.txt'
```

**ECS Logs**:
```
[Event] create fpolicy_e2e_test.txt
[SQS] Sent: fpolicy_e2e_test.txt (create)
```

**Lambda Logs**:
```
FPolicy handler invoked: source=unknown
Extracted 1 FPolicy event(s)
Processing complete: {"statusCode": 200, "body": {"shipped": 1}}
```

**Datadog Confirmation**: 7 logs arrived with `source:fsxn-fpolicy`

### Step F4: Structured Attributes Verification

| Field | Value | Status |
|-------|-------|--------|
| source | fsxn-fpolicy | ✅ |
| file_path | e2e_write_test.txt | ✅ |
| @attributes.operation_type | create | ✅ |
| client_ip | 10.0.x.x | ✅ |
| volume_name | vol1 | ✅ |
| timestamp | 2026-05-17T14:43:51+00:00 | ✅ |

### Issues Discovered and Resolutions

| # | Issue | Root Cause | Resolution |
|---|-------|-----------|------------|
| 1 | Fargate task pull failure | ECR image was arm64-only | Rebuild with `--platform linux/amd64` |
| 2 | SQS → Lambda not connected | Only EventBridge rule existed, no SQS mapping | Added SQS support to Lambda + event source mapping |
| 3 | fsxadmin account locked | Too many password attempts | Reset via `aws fsx update-file-system` |
| 4 | SMB password must change | First-login forced change | Set password via ONTAP CLI `set-password` |
| 5 | rename/delete not captured | FPolicy async mode behavior | Future: test with sync mode |

### FPolicy Full-Path Verification Summary

| Step | Name | Result | Latency |
|------|------|--------|---------|
| F1 | Fargate Deployment | ✅ Success | — |
| F2 | ONTAP Connection | ✅ Success | — |
| F3 | File Op → Datadog | ✅ Success | ~6-8s |
| F4 | Structured Attributes | ✅ Success | — |

**FPolicy Full-Path Overall Judgment**: ✅ PASS (create event full-path verified)

### Screenshots

![FPolicy Log List — Datadog Log Explorer](../screenshots/datadog-fpolicy-full-path.png)

![FPolicy Event Detail](../screenshots/datadog-fpolicy-detail.png)


---

### Step F5: Fargate Task Restart Resilience Test

- **Result**: ✅ Success
- **Test Procedure**:
  1. Start Fargate → Task IP: 10.0.x.x → ONTAP connection confirmed → Event flow confirmed
  2. Stop Fargate (scale to 0) → Task stopped
  3. Restart Fargate (scale to 1) → New task IP: 10.0.x.x
  4. Update ONTAP External Engine IP → Reconnection confirmed
  5. File operation → Event flow resumed

**Detailed Results**:

| Step | Result | Notes |
|------|--------|-------|
| Initial start → connection | ✅ | IP: 10.0.x.x, connected in ~20s |
| Event flow (pre-restart) | ✅ | pre_restart_test.txt → SQS → Datadog |
| Task stop | ✅ | Stopped in ~30s |
| Task restart | ✅ | New IP: 10.0.x.x |
| ONTAP reconnection | ✅ | Reconnected ~20s after Engine IP update |
| Event flow (post-restart) | ✅ | post_restart_test.txt → SQS → Datadog |
| Lambda retry | ✅ | Initial connection error → retry succeeded |

**Key Findings**:
- Fargate task IP changes on restart (10.0.x.x → 10.0.x.x)
- ONTAP External Engine IP update is mandatory (automated via script)
- Lambda retry logic correctly handles transient connection errors
- Full recovery from restart: ~2 minutes (task start 45s + Engine update + connection 20s)
