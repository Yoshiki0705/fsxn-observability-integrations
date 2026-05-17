# Minimum Test Path

Ship audit events to Datadog with the simplest possible configuration.

## Prerequisites

- FSx for ONTAP file system (audit logging enabled)
- FSx for ONTAP S3 Access Point (attached to the audit volume)
- Datadog account (free trial works)
- Datadog API Key stored in Secrets Manager

## Minimum Configuration

| Setting | Value | Reason |
|---------|-------|--------|
| Lambda VPC | Outside VPC | No NAT Gateway required |
| Scheduler | rate(5 minutes) | Default |
| Audit rotation | 5-minute interval (time-based) | Rotated files appear quickly |
| Datadog site | Your site (e.g., ap1.datadoghq.com) | — |

## Steps

```bash
# 1. Deploy (single command)
aws cloudformation deploy \
  --template-file integrations/datadog/template.yaml \
  --stack-name fsxn-datadog-integration \
  --parameter-overrides \
    FsxS3AccessPointArn=<your-fsx-s3-ap-arn> \
    DatadogApiKeySecretArn=<your-secret-arn> \
    DatadogSite=<your-site> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region <your-region>

# 2. Perform a test file operation on the audited share
#    (create/delete a file via SMB or NFS)

# 3. Wait 5-10 minutes

# 4. Verify in Datadog
#    Search: source:fsxn
```

## Success Criteria

- [ ] `source:fsxn` returns at least one result in Datadog Log Explorer
- [ ] `@attributes.operation` is populated
- [ ] `@attributes.user` is populated

## Not Included in the Minimum Test

- VPC / NAT Gateway configuration
- DLQ replay procedures
- Custom metrics
- Datadog Monitor setup
- Multi-SVM / multi-account

These are production hardening steps covered in the full documentation.

## Next Steps

After confirming log arrival:
1. Review the [field mapping](../../integrations/datadog/docs/en/field-mapping.md)
2. Try [investigation queries](../../integrations/datadog/docs/en/field-mapping.md#datadog-search-queries)
3. Set up Monitors (blog series Part 3)
