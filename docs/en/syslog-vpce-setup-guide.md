# Syslog VPC Endpoint Setup Guide — FSx for ONTAP Admin Audit Logs → CloudWatch Logs

> **Time required**: ~15 minutes (CloudFormation deploy + ONTAP configuration)
> **Prerequisite**: Running FSx for ONTAP file system
> **Template**: `shared/templates/syslog-vpce-cloudwatch.yaml`

---

## Overview

Ship FSx for ONTAP management activity audit logs (ONTAP CLI/API operations) directly to CloudWatch Logs — no EC2 syslog server required.

```
FSx for ONTAP (ONTAP log-forwarding)
    │ Syslog (TCP port 6514 or 1514)
    ▼
VPC Endpoint (com.amazonaws.{region}.syslog-logs)
    │ AWS PrivateLink
    ▼
CloudWatch Logs (/syslog/fsxn-admin-audit)
```

---

## Prerequisites

| Parameter | How to find | Example |
|-----------|-------------|---------|
| VPC ID | FSx Console → File system → Network | `vpc-0ae01826f906191af` |
| Subnet ID | Same AZ as FSx | `subnet-0e36804c7fbc819a6` |
| VPC CIDR | VPC Console → Target VPC | `10.0.0.0/16` |
| FSx Management IP | FSx Console → Management endpoint | `10.0.3.72` |

---

## Step 1: Deploy CloudFormation Stack

```bash
aws cloudformation deploy \
  --template-file shared/templates/syslog-vpce-cloudwatch.yaml \
  --stack-name fsxn-syslog-vpce-admin-audit \
  --parameter-overrides \
    VpcId=<YOUR_VPC_ID> \
    SubnetIds=<YOUR_SUBNET_ID> \
    VpcCidr=<YOUR_VPC_CIDR> \
    LogGroupName=/syslog/fsxn-admin-audit \
    LogRetentionDays=90 \
  --region ap-northeast-1 \
  --no-fail-on-empty-changeset
```

Then retrieve the VPC Endpoint ENI IP:

```bash
VPCE_ID=$(aws cloudformation describe-stacks \
  --stack-name fsxn-syslog-vpce-admin-audit \
  --query "Stacks[0].Outputs[?OutputKey=='VpcEndpointId'].OutputValue" \
  --output text --region ap-northeast-1)

ENI_ID=$(aws ec2 describe-vpc-endpoints --vpc-endpoint-ids $VPCE_ID \
  --query 'VpcEndpoints[0].NetworkInterfaceIds[0]' \
  --output text --region ap-northeast-1)

VPCE_IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID \
  --query 'NetworkInterfaces[0].PrivateIpAddress' \
  --output text --region ap-northeast-1)

echo "VPC Endpoint IP: $VPCE_IP"
```

---

## Step 2: Create Syslog Configuration

```bash
python3 shared/scripts/create-syslog-configuration.py \
  --vpce-id $VPCE_ID \
  --log-group-arn "arn:aws:logs:ap-northeast-1:$(aws sts get-caller-identity --query Account --output text):log-group:/syslog/fsxn-admin-audit" \
  --region ap-northeast-1
```

> **Note**: As of June 2026, AWS CLI/boto3 does not have `put-syslog-configuration`. This script uses raw SigV4 signing. Alternatively, use the AWS Console: CloudWatch → Logs → Syslog configurations → Create.

---

## Step 3: Configure ONTAP Log-Forwarding

> **CLI command naming**: ONTAP 9.11.1+ uses `security audit log-forwarding` (replacing the older `cluster log-forwarding`). Both refer to the same feature.

### Option A: REST API (recommended for automation)

```bash
curl -sk -u fsxadmin:<PASSWORD> \
  -X POST "https://<FSx-Management-IP>/api/security/audit/destinations?force=true" \
  -H "Content-Type: application/json" \
  -d '{
    "address": "'$VPCE_IP'",
    "port": 6514,
    "protocol": "tcp_encrypted",
    "facility": "local7"
  }'
```

### Option B: SSH + ONTAP CLI

```bash
ssh fsxadmin@<FSx-Management-IP>

FsxId*> security audit log-forwarding create \
  -destination <VPCE_IP> \
  -port 6514 \
  -protocol tcp-encrypted \
  -facility local7

FsxId*> security audit log-forwarding show
```

### Protocol Options

| Protocol | Port | ONTAP parameter | Recommendation |
|----------|------|-----------------|----------------|
| TCP+TLS | 6514 | `tcp-encrypted` | **Production (recommended)** |
| TCP Plaintext | 1514 | `tcp-unencrypted` | Validation fallback only |

> **Production security hardening**:
> - Restrict Security Group source to FSx subnet CIDR (not full VPC CIDR)
> - Use Secrets Manager for credentials (not inline `curl -u`)
> - Always use `tcp-encrypted` (port 6514) in production

---

## Step 4: Verify

```bash
# Generate admin activity
curl -sk -u fsxadmin:<PASSWORD> \
  https://<FSx-Management-IP>/api/storage/volumes?fields=name --max-time 10 > /dev/null

# Check CloudWatch Logs (wait ~10 seconds)
aws logs get-log-events \
  --log-group-name /syslog/fsxn-admin-audit \
  --log-stream-name "${VPCE_ID}_Syslog_ap-northeast-1" \
  --limit 5 --region ap-northeast-1
```

![CloudWatch Logs — Admin Audit Events](../screenshots/syslog-vpce/02-cloudwatch-log-events-ontap-audit.png)

---

## Operational Monitoring

Monitor the syslog pipeline health:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "FSx-ONTAP-SyslogDropped" \
  --metric-name SyslogMessagesDropped \
  --namespace AWS/Logs \
  --statistic Sum --period 300 --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --evaluation-periods 1 \
  --dimensions Name=LogGroupName,Value=/syslog/fsxn-admin-audit \
  --alarm-actions <SNS_TOPIC_ARN> \
  --region ap-northeast-1
```

| Metric | Meaning | Alert threshold |
|--------|---------|-----------------|
| `SyslogMessagesDropped` | Messages dropped due to delivery failure | > 0 (5 min) |
| `IncomingLogEvents` | Received log events | < 1 (1 hour) = no logs arriving |

---

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| No log stream created | Syslog Configuration missing | Run Step 2 |
| ONTAP "Cannot contact destination" | SG blocking traffic | Add VPC CIDR → port 6514 to VPCE SG |
| "User is not authorized" | fsxadmin locked | `aws fsx update-file-system --ontap-configuration '{"FsxAdminPassword":"<new>"}'` |
| Logs delayed > 1 min | Network routing | Verify VPCE ENI is in same AZ as FSx |

---

## Cleanup

```bash
# 1. Remove ONTAP forwarding destination
curl -sk -u fsxadmin:<PASSWORD> \
  -X DELETE "https://<FSx-Management-IP>/api/security/audit/destinations/<VPCE_IP>/6514"

# 2. Delete CloudFormation stack
aws cloudformation delete-stack --stack-name fsxn-syslog-vpce-admin-audit --region ap-northeast-1

# 3. Delete retained log group (optional)
aws logs delete-log-group --log-group-name /syslog/fsxn-admin-audit --region ap-northeast-1
```

---

## Related Documents

- [Architecture Evolution — Syslog VPCE](architecture-evolution-syslog-vpce.md)
- [Event Sources Guide](event-sources.md)
- [AWS Docs: Syslog ingestion](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_Syslog.html)
- [NetApp: ONTAP audit destinations](https://docs.netapp.com/us-en/ontap/system-admin/forward-command-history-log-file-destination-task.html)
