# PoC Success Criteria — Grafana Cloud Integration

🌐 [日本語](../ja/poc-checklist.md) | **English** (this page)

Use this checklist to validate a Proof of Concept deployment before presenting results to stakeholders.

## Functional Validation

- [ ] Audit log poller Lambda deployed successfully
- [ ] First audit log file visible in Grafana Explore (`{service_name="fsxn-audit"}`)
- [ ] EMS test event visible (`{service_name="fsxn-ems"}`)
- [ ] FPolicy test event visible (`{service_name="fsxn-fpolicy"}`)
- [ ] Dashboard created with all 4 panels rendering data
- [ ] Alert rules provisioned (ransomware, quota, failed access)

## Reliability Validation

- [ ] Scheduler DLQ alarm configured and tested
- [ ] Checkpoint failure-path test passed (delivery failure → checkpoint does not advance)
- [ ] Reserved concurrency prevents overlapping execution
- [ ] Processing bounds (MAX_KEYS_PER_RUN, SAFETY_THRESHOLD_MS) validated

## Security Validation

- [ ] Webhook auth mode selected for production (SHARED_SECRET recommended)
- [ ] Grafana credentials stored in Secrets Manager (not environment variables)
- [ ] API Gateway access logging enabled
- [ ] No hardcoded secrets in CloudFormation parameters or Lambda code

## Operational Readiness

- [ ] Cleanup script tested (`scripts/cleanup.sh --all`)
- [ ] Deploy script tested (`scripts/deploy.sh`)
- [ ] Poller tuning parameters documented for the environment
- [ ] Audit log rotation interval measured
- [ ] FSx S3 Access Point read throughput validated

## Go/No-Go Decision

| Criterion | Status | Notes |
|-----------|--------|-------|
| Logs arrive in Grafana within schedule interval | | |
| Alerts fire on test events | | |
| DLQ replay procedure documented | | |
| Production gaps accepted by organization | | |
| Cost estimate reviewed (Lambda + Grafana ingest) | | |
| Webhook auth mode agreed | | |

## First Success Path

If this is your first deployment:

1. Deploy **only** the audit log poller (`template.yaml`)
2. Set `MAX_KEYS_PER_RUN=1` for initial validation
3. Process one known test audit file
4. Confirm `{service_name="fsxn-audit"}` in Grafana Explore
5. Create the dashboard
6. Add EMS and FPolicy only after the audit path works

This minimizes variables and gives you a clear success signal before adding complexity.


## PoC Workstream Split

For multi-team deployments, assign tasks by domain:

### NetApp / ONTAP Side
- [ ] Enable audit logging on target SVM
- [ ] Configure audit log format (EVTX or XML)
- [ ] Document audit log rotation interval
- [ ] Configure EMS webhook destination (if using EMS path)
- [ ] Validate FPolicy server connectivity (if using FPolicy path)
- [ ] Validate S3 Access Point file-system identity has read permission
- [ ] Confirm test audit file is visible through S3 Access Point

### AWS Side
- [ ] Deploy Lambda / Scheduler / DLQ (CloudFormation)
- [ ] Validate IAM policy and S3 Access Point resource policy
- [ ] Validate checkpoint advancement (SSM Parameter Store)
- [ ] Configure Scheduler DLQ alarm
- [ ] Test DLQ replay procedure

### Grafana Side
- [ ] Validate OTLP ingestion (logs visible in Explore)
- [ ] Create dashboard with 4 panels
- [ ] Create alert rules (ransomware, quota, failed access)
- [ ] Configure contact points and notification policies
- [ ] Validate label mapping (`service_name` index label)

## Outcome Metrics

Track these KPIs to demonstrate PoC value:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Time to first audit log in Grafana | < 30 min from deploy | Timestamp of first log entry |
| Number of verified LogQL queries | ≥ 5 | Verified Query Matrix in article |
| Alert rule creation success | 3/3 rules | `create-alerts.sh` exit code |
| Mean poller duration | < 60% of schedule interval | CloudWatch Lambda Duration p95 |
| Scheduler DLQ count | 0 | SQS metric |
| Security owner approval | Signed off | Webhook auth mode agreed |
| Organization sign-off | Documented | At-least-once semantics accepted |
