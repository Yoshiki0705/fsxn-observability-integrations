# CloudTrail Data Events as an Alternative Trigger for FSx for ONTAP S3 Access Points

🌐 [日本語](../ja/cloudtrail-trigger-alternative.md) | **English** (this page)

## Summary

**CloudTrail data events DO work with FSx for ONTAP S3 Access Points.** This provides an event-driven alternative to the polling pattern used in the primary integration.

However, the polling pattern (EventBridge Scheduler + checkpoint) remains the **recommended primary approach** for this project because:

1. CloudTrail data events add cost ($0.10 per 100,000 events)
2. The polling pattern is simpler to deploy and debug
3. CloudTrail adds 5-15 minutes of delivery latency to EventBridge anyway
4. NetApp Workload Factory's Journal table feature already uses this CloudTrail pattern — no need to duplicate it

## Evidence: CloudTrail Support for FSx for ONTAP S3 AP

### AWS Documentation

CloudTrail supports S3 data events (GetObject, PutObject, DeleteObject, etc.) for standard S3 access points. FSx for ONTAP S3 Access Points appear as standard S3 access points to the AWS control plane, so CloudTrail data events capture operations made through them.

The CloudTrail `resources.ARN` field includes the access point ARN:
```
arn:aws:s3:<region>:<account-id>:accesspoint/<access-point-name>/object/<key>
```

### NetApp Workload Factory Validation

NetApp's Workload Factory product uses exactly this pattern for its **Journal table** feature:
- CloudTrail data events capture S3 API calls on FSx for ONTAP access points
- Events flow through CloudTrail → EventBridge → processing pipeline
- This confirms the pattern works in production

### Journal Table vs Polling: When to Use Which

| Pattern | Source Data | Use Case |
|---------|------------|----------|
| **Journal table / CloudTrail** | S3 Access Point data-plane operations (GetObject, PutObject, etc.) | Track who accessed files through the S3 API |
| **Polling (this project)** | ONTAP-generated audit log files on the FSx volume | Ship ONTAP audit logs to an observability backend |

Use Journal table / CloudTrail data events when you need S3 Access Point data-plane operation history (which Lambda or user called GetObject on which key). Use the polling pattern when your primary source is ONTAP-generated audit log files (SMB/NFS file access events written by ONTAP's audit subsystem) that you want to ship to an observability backend like Grafana, Datadog, or Splunk.

Reference: [NetApp Workload Factory — Journal Table Setup](https://docs.netapp.com/us-en/workload-fsx-ontap/setup-journal-table.html)

## Architecture: CloudTrail → EventBridge → Lambda

```
FSx for ONTAP S3 Access Point
        │
        ▼ (GetObject/PutObject via S3 API)
   CloudTrail Trail
   (S3 data events)
        │
        ▼ (5-15 min latency)
   EventBridge Rule
   (detail-type: "AWS API Call via CloudTrail")
        │
        ▼
   Lambda (log shipper)
        │
        ▼
   Grafana Cloud (OTLP Gateway)
```

## CloudFormation Example

The following snippet shows how to configure CloudTrail data events for an FSx for ONTAP S3 Access Point and route them to a Lambda function via EventBridge:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: >
  CloudTrail data events trigger for FSx for ONTAP S3 Access Point.
  Alternative to EventBridge Scheduler polling pattern.

Parameters:
  S3AccessPointArn:
    Type: String
    Description: ARN of the FSx for ONTAP S3 Access Point
    # Example: arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap

  LogShipperFunctionArn:
    Type: String
    Description: ARN of the log shipper Lambda function

  CloudTrailBucketName:
    Type: String
    Description: S3 bucket for CloudTrail log delivery

Resources:
  # --- CloudTrail Trail with S3 Data Events ---
  AuditTrail:
    Type: AWS::CloudTrail::Trail
    Properties:
      TrailName: fsxn-s3ap-data-events
      IsLogging: true
      S3BucketName: !Ref CloudTrailBucketName
      EnableLogFileValidation: true
      IsMultiRegionTrail: false
      EventSelectors:
        - ReadWriteType: ReadOnly
          IncludeManagementEvents: false
          DataResources:
            - Type: AWS::S3::Object
              Values:
                - !Sub "${S3AccessPointArn}/"

  # --- EventBridge Rule ---
  # Matches CloudTrail S3 data events for GetObject on the access point
  S3DataEventRule:
    Type: AWS::Events::Rule
    Properties:
      Name: fsxn-s3ap-object-access
      Description: Trigger Lambda on S3 GetObject via FSx for ONTAP Access Point
      State: ENABLED
      EventPattern:
        source:
          - aws.s3
        detail-type:
          - "AWS API Call via CloudTrail"
        detail:
          eventSource:
            - s3.amazonaws.com
          eventName:
            - GetObject
            - PutObject
          requestParameters:
            bucketName:
              - !Select [5, !Split [":", !Ref S3AccessPointArn]]
      Targets:
        - Id: LogShipperLambda
          Arn: !Ref LogShipperFunctionArn

  # --- Lambda Permission for EventBridge ---
  LambdaInvokePermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !Ref LogShipperFunctionArn
      Action: lambda:InvokeFunction
      Principal: events.amazonaws.com
      SourceArn: !GetAtt S3DataEventRule.Arn
```

## Cost Comparison

| Approach | Trigger Cost | Latency | Complexity |
|----------|-------------|---------|------------|
| EventBridge Scheduler (polling) | ~$0.00 (1 invocation/5min) | Up to 5 min (configurable) | Low |
| CloudTrail data events | $0.10/100K events + trail storage | 5-15 min (CloudTrail delivery) | Medium |
| S3 Event Notifications | Not supported on FSx for ONTAP S3 AP | — | — |

## When to Use CloudTrail Trigger

Consider the CloudTrail approach when:
- You need an audit trail of **who** accessed files via the S3 API (CloudTrail provides caller identity)
- You already have CloudTrail data events enabled for compliance
- You want event-driven processing without polling (accepting the CloudTrail latency)
- You're building on top of NetApp Workload Factory's Journal table pattern

## When to Use Polling (Recommended Default)

Stick with the EventBridge Scheduler polling pattern when:
- You want the simplest, lowest-cost deployment
- You need predictable, configurable latency (rate(1 minute) to rate(15 minutes))
- You don't need CloudTrail's caller identity metadata
- You want to avoid CloudTrail data event costs at high volume

## NetApp Workload Factory Journal Table Pattern

NetApp's Workload Factory provides a managed version of the CloudTrail-based pattern:
- Automatically deploys CloudTrail trail, EventBridge rules, and processing pipeline
- Captures user access events and object operations on FSx for ONTAP S3 access points
- Stores results in a queryable "Journal table" (DynamoDB)
- Includes CloudWatch log groups for monitoring

If you're already using Workload Factory, consider leveraging the Journal table output as a data source rather than building a parallel CloudTrail pipeline.

## Limitations

1. **Latency**: CloudTrail delivers events to EventBridge with 5-15 minute delay
2. **Cost**: $0.10 per 100,000 data events (can be significant at high volume)
3. **Scope**: Only captures S3 API operations — does not capture NFS/SMB file access
4. **Deduplication**: CloudTrail may deliver duplicate events; Lambda must handle idempotently
5. **Access Point network origin**: The S3 access point must be configured as Internet-origin for CloudTrail to capture events from external callers

## References

- [AWS CloudTrail — Logging S3 Data Events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
- [AWS CloudTrail — Advanced Event Selectors](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/filtering-data-events.html)
- [Amazon S3 — Monitoring and Logging Access Points](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-monitoring-logging.html)
- [NetApp Workload Factory — Journal Table Setup](https://docs.netapp.com/us-en/workload-fsx-ontap/setup-journal-table.html)
- [FSx for ONTAP — Monitoring with CloudTrail](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/logging-using-cloudtrail-win.html)


## Service Feedback Summary

### Observed Customer Need

- Near-real-time audit log shipping from FSx for ONTAP S3 Access Points
- Lower latency than CloudTrail data event delivery (observed 5–15 min in validation)
- Lower operational complexity than polling for higher-volume workloads
- Event-driven trigger without the $0.10/100K events cost of CloudTrail data events

### Current Workaround

- EventBridge Scheduler polling with SSM / DynamoDB checkpoint
- Polling interval configurable (default: 5 minutes)
- Application-side responsibility for list, read, checkpoint, retry

### Trade-off Analysis

| Approach | Latency | Cost | Complexity | Reliability |
|----------|---------|------|-----------|-------------|
| Scheduler polling (this project) | ≤ schedule interval | Lambda only | Medium (app-side checkpoint) | At-least-once with DLQ |
| CloudTrail data events → EventBridge | 5–15 min observed | $0.10/100K events + Lambda | Low (event-driven) | At-least-once |
| Native object notification (hypothetical) | Near-real-time | TBD | Low | TBD |

### Potential Future Improvement

Native object-created style eventing or lower-latency data-plane event delivery for FSx-attached S3 Access Points would simplify operational design for audit log shipping use cases, reducing the need for application-side polling, checkpointing, and overlap prevention logic.
