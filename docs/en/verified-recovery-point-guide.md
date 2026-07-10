# Verified-Clean Recovery Point Guide — Closing the CSF 2.0 RC.RP Gap

🌐 [日本語](../ja/verified-recovery-point-guide.md) | **English** (this page)

## Executive Summary

The [Cyber Resilience Capability Map](cyber-resilience-capability-map.md#recover-rc) is explicit about a gap this repository did not previously address: a protective snapshot existing is a **Protect**-phase artifact, not evidence that the snapshot is actually clean and restorable. NIST CSF 2.0's **RC.RP** (Incident Recovery Plan Execution) subcategory is only credible once a recovery point has been tested and confirmed free of compromise — not merely confirmed to exist.

This guide implements that missing verification step using AWS-native services only:

1. **FlexClone** the candidate snapshot into a read/write clone (ONTAP REST API) — never touches the production volume or the original snapshot.
2. **Attach a VPC-scoped S3 Access Point** to the clone (AWS FSx API) — exposes the clone's files via the S3 API without mounting NFS/SMB, so verification has no network path to the production data plane.
3. **Scan the clone's file listing** (S3 `ListObjectsV2` through the access point) for ransomware-associated file extensions — a fast pre-filter, not a substitute for ONTAP ARP's entropy analysis.
4. **Record a clean/suspicious/error verdict** in DynamoDB (and optionally notify via SNS), then **always tear down** the S3 Access Point and FlexClone regardless of outcome.

> **Scope note**: This closes the RC.RP verification gap specifically — it does not replace ONTAP ARP (which detects ransomware *during* the attack, against the live volume) or the [Automated Response Guide](automated-response-guide.md)'s Respond-phase blocking. It answers a different, later question: *"is this specific snapshot, that we are about to promote to a restore point, actually clean?"*

**Key capabilities:**
- FlexClone-based verification with zero impact on production volumes (copy-on-write, read-only workload against the clone)
- VPC-scoped S3 Access Point — the clone's contents are never internet-reachable
- Fast extension-based pre-filter for ransomware indicators
- Guaranteed cleanup via Step Functions `Catch` — no orphaned clones or access points, even on failure
- DynamoDB ledger of every verification run, doubling as CSF 2.0 RC.RP evidence for audits

**When to run this:**
- After the [Automated Response Guide](automated-response-guide.md)'s `create_snapshot` action fires, before relying on that snapshot as your recovery point
- On a schedule against your regular protective/scheduled snapshots, as a periodic recovery-readiness check
- Manually, before a planned DR test or compliance audit that requires evidence of a *tested* recovery point

> **Customer-facing positioning note**: When positioning this guide to a customer evaluating FSx for ONTAP for ransomware resilience, the accurate one-sentence framing is: "an automated pre-filter that flags obviously-compromised snapshots before a human wastes a restore cycle on one, not a certification that a snapshot is malware-free." Do not represent the "clean" verdict as equivalent to a full forensic clearance in a customer conversation or RFP response — the Resilience-maturity and Threat-intelligence notes elsewhere in this guide spell out exactly why that framing would overstate the capability. The accurate, still-compelling claim is the automation and evidence trail itself: this closes a documented gap (no verified-clean recovery point workflow existed before) using AWS-native services, with a DynamoDB audit trail — that's a legitimate differentiator without needing to oversell the scan's depth.

---

## Architecture

```
+-------------------------------------------------------------------+
| Step Functions: Verified-Clean Recovery Point Workflow            |
+-------------------------------------------------------------------+
|                                                                   |
|  CreateFlexClone (ONTAP REST API)                                 |
|       |                                                           |
|       v                                                           |
|  AttachAccessPoint (AWS FSx API, VPC-scoped)                      |
|       |                                                           |
|       v                                                           |
|  ScanForIndicators (S3 ListObjectsV2 via access point)             |
|       |                                                           |
|       v                                                           |
|  RecordVerdict (DynamoDB + optional SNS)                          |
|       |                                                           |
|       v                                                           |
|  Cleanup (detach S3 AP + delete FlexClone)  <-- ALWAYS runs        |
|                                                                   |
|  (any step failure) --> CleanupAfterError --> RecordErrorVerdict   |
|                          --> Fail                                  |
+-------------------------------------------------------------------+
```

The key design choice: **cleanup runs on every path**, success or failure. The Step Functions `Catch` block routes any error straight to the same cleanup Lambda used on the happy path, so a mid-workflow failure never leaves a FlexClone volume or S3 Access Point behind consuming storage or presenting an unnecessary access surface.

> **Diagram description (text alternative)**: The Step Functions state machine runs five states in sequence — `CreateFlexClone` (ONTAP REST API) → `AttachAccessPoint` (AWS FSx API, VPC-scoped) → `ScanForIndicators` (S3 `ListObjectsV2` via the access point) → `RecordVerdict` (DynamoDB, optional SNS) → `Cleanup` (detaches the S3 Access Point and deletes the FlexClone; this state always runs). If any of the first three states fails, control transfers to `CleanupAfterError`, which invokes the same `Cleanup` Lambda, then `RecordErrorVerdict` writes the failure to the ledger before the execution ends in a `Fail` state. The diagram above is ASCII art; this paragraph is the complete textual equivalent for screen-reader users.

---

## How Verification Works

### Step 1: FlexClone Creation

A [FlexClone](https://aws.amazon.com/fsx/netapp-ontap/features/) is a point-in-time, writable copy that shares data blocks with its parent volume via copy-on-write — creation is near-instant and consumes no additional storage until something writes to the clone (which this workflow never does; it only reads).

```
POST /api/storage/volumes
{
  "name": "verify_vol_data_20260710_143022",
  "svm": {"name": "svm-prod-01"},
  "clone": {
    "parent_volume": {"name": "vol_data"},
    "parent_snapshot": {"name": "incident_response_20260708_143022"},
    "is_flexclone": true
  }
}
```

This returns an async job; the Lambda polls `GET /api/cluster/jobs/{uuid}` until `state: success`, then resolves the clone's ONTAP volume UUID for later cleanup.

> **Concurrency note**: `clone_name` is derived from `verify_{volume_name}_{timestamp}`, where `timestamp` has 1-second resolution (`%Y%m%d_%H%M%S`). Two Step Functions executions started against the *same* `volume_name` within the same second — e.g., a scheduled run and a manually-triggered one firing together — will attempt to create two ONTAP volumes with an identical name, and the second `POST /storage/volumes` call will fail with a naming conflict rather than proceeding. The workflow has no execution-level locking (no DynamoDB conditional write, no Step Functions `name` deduplication) to prevent this. In practice this is a narrow window and an infrequent trigger pattern, but if you invoke this workflow from multiple independent triggers (e.g., both a schedule and a SOAR playbook) against the same volume, consider adding a distinguishing suffix (a short random token or the invoking execution's own ID) to avoid a same-second collision.

### Step 2: S3 Access Point Attachment

The clone is exposed via a [VPC-scoped S3 Access Point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-vpc.html) — not internet-origin — so requests must traverse an Interface VPC Endpoint in the bound VPC:

```python
fsx.create_and_attach_s3_access_point(
    Name="verify-vol-data-20260710-143022",
    Type="ONTAP",
    OntapConfiguration={
        "VolumeId": fsvol_id,  # resolved via DescribeVolumes, NOT the ONTAP UUID
        "FileSystemIdentity": {"Type": "UNIX", "UnixUser": {"Name": "root"}},
    },
    S3AccessPoint={"VpcConfiguration": {"VpcId": vpc_id}},
)
```

> **Resolving fsvol-id from the ONTAP UUID**: AWS FSx discovers volumes created via ONTAP REST API asynchronously — there is no direct API to map an ONTAP volume UUID to the corresponding `fsvol-xxxx` ID. This workflow polls `DescribeVolumes` filtered by `file-system-id`, matching on the clone's `Name`, until FSx reports it `AVAILABLE`.

The access point transitions `CREATING` → `AVAILABLE` (or `FAILED`/`MISCONFIGURED` on error) — the Lambda polls `DescribeS3AccessPointAttachments` until a terminal state.

### Step 3: Ransomware Indicator Scan

The scan lists the clone's objects through the access point (`ListObjectsV2`) and flags file extensions commonly appended by ransomware families (`.encrypted`, `.locked`, `.crypt`, `.wcry`, `.locky`, and others). A snapshot is flagged **suspicious** only when both:

- The suspicious object count is ≥ `SuspiciousMinCount` (default 20 — avoids false positives on small volumes with a couple of legitimately-named files)
- The suspicious ratio is ≥ `SuspiciousRatioThreshold` (default 5%)

> **Resilience-maturity note**: This is deliberately a coarse, fast pre-filter — not a replacement for [ONTAP ARP](arp-incident-response-guide.md)'s file-content entropy analysis, which runs against the live volume during an active attack. This scan answers a narrower, later question: does *this specific snapshot* look like it captured a volume dominated by ransomware-renamed files? A "clean" verdict here is evidence for RC.RP; it is not a general-purpose malware scan, and it does not inspect file *contents* (see the [Content-Level PII Classification Scanner](content-classification-scanner.md) for a complementary content-scanning capability aimed at a different problem — data classification, not ransomware detection).

> **Threat-intelligence note**: `SUSPICIOUS_EXTENSIONS` is a fixed list of extensions historically associated with named ransomware families (`.locky`, `.wcry`, `.cerber`, and similar). This is a known-signature approach and inherits a known-signature blind spot: ransomware operators that append a random or victim-specific extension (a pattern observed increasingly in current campaigns, precisely to evade extension-based detection like this) will not match any entry in the list, and a snapshot encrypted by such a variant can still receive a "clean" verdict from this scan alone. This list is not automatically kept current with emerging ransomware families — review and extend `SUSPICIOUS_EXTENSIONS` periodically against current threat intelligence (e.g., your SIEM vendor's threat feed or a maintained public list) rather than treating the shipped list as exhaustive. This is a second, independent reason (beyond the ones already noted above) that a "clean" verdict here is a pre-filter, not a guarantee — [ONTAP ARP](arp-incident-response-guide.md)'s entropy-based detection does not depend on recognizing a specific extension and is a meaningful complement for exactly this blind spot.

### Step 4: Verdict Recording

Every run — clean, suspicious, or error — is written to a DynamoDB ledger table (`snapshot_key` = `{svm}/{volume}/{snapshot}`, sort key `started_at`), giving you a queryable, timestamped history of which recovery points have been verified and what the outcome was. This table is the artifact you point to as RC.RP evidence in an audit.

### Step 5: Guaranteed Cleanup

The cleanup Lambda is idempotent-ish by design: a missing `access_point_name` or `volume_uuid` (e.g., cleanup running after an early failure, before those resources existed) is treated as a no-op, not an error. Both the S3 Access Point detach and FlexClone deletion tolerate "already gone" (404 / `NotFound`) responses.

> **API contract note**: The contract between Step Functions states is an implicit, untyped dict merge rather than a versioned schema — each Lambda receives the full accumulated JSON payload from prior states (via `"ResultPath": "$"` in the state machine definition) and returns `dict(event)` updated with its own new keys, so downstream states silently depend on upstream key names never changing. This works well for a five-state, single-purpose workflow where all states are maintained together, but it means there is no schema validation catching a typo'd key name or a renamed field at deploy time — a mismatch would only surface at runtime as a missing key, likely inside `RecordVerdict` or `Cleanup` reading `event.get(...)` with a silent default rather than a clear error. If you extend this workflow (e.g., inserting the Content-Level PII Classification Scanner as an additional state per that guide's Restore-testing note), keep the same implicit-passthrough convention rather than introducing a differently-shaped payload, or the inserted state's output may silently drop keys later states depend on.

---

## Comparison: Snapshot Exists vs Verified-Clean Recovery Point

| Aspect | Snapshot Exists (Respond phase) | Verified-Clean Recovery Point (this workflow) |
|--------|----------------------------------|------------------------------------------------|
| CSF 2.0 function | Protect (the snapshot itself) | Recover — RC.RP specifically |
| What it proves | A point-in-time copy was captured | The copy was inspected and does not show ransomware indicators |
| Production impact | None (snapshot creation is near-instant) | None (FlexClone is copy-on-write; scan is read-only against the clone) |
| Confidence for a restore decision | Low — a snapshot taken *during* an attack can itself contain encrypted files | Higher — an automated go/no-go signal before a human commits to a restore |
| Automation in this repo | ✅ Full ([Automated Response Guide](automated-response-guide.md)) | ✅ Full (this guide) |

> **Recovery-sufficiency note**: Treat a "clean" verdict from this workflow as a *necessary*, not *sufficient*, condition before restoring. It rules out the coarse, obvious case (a volume dominated by ransomware-renamed files) fast and cheaply. It does not verify application-level data integrity, verify the snapshot restores cleanly end-to-end, or replace a full DR test. Schedule periodic full restore tests separately; use this workflow as the automated first gate that runs on every candidate snapshot, not as the last word on recoverability.

> **DR-runbook sequencing note**: This is distinct from the Recovery-sufficiency note above — that one addresses the technical sufficiency of a "clean" verdict; this one addresses where this workflow fits into a broader DR plan's operational sequencing. Where does this step sit relative to your other DR runbook steps (failover decision, stakeholder notification, application restart order)? A sensible placement is: incident detected → protective snapshot taken (Respond) → **this verification runs** → only if "clean," the snapshot is presented to whoever makes the restore-or-failover decision, alongside (not instead of) your existing DR decision criteria (RTO/RPO targets, business-impact assessment). If your DR runbook currently treats "a snapshot exists" as sufficient to initiate restore, update that runbook to gate on this workflow's verdict — but do so as a documented change to your DR plan and communicate it to whoever executes that runbook during an actual incident, not as an implicit assumption buried in this guide.

---

## Prerequisites

### ONTAP Version

- **FlexClone REST API** (`clone.is_flexclone`): Available from ONTAP 9.8+
- **Volume creation/deletion REST API**: Available from ONTAP 9.6+

> **Patch-management note**: This guide lists the *minimum* ONTAP version each API requires, not a *recommended* version to run. Treat this workflow the same as any other component touching your ONTAP management endpoint: track [NetApp Security Advisories](https://security.netapp.com/) for the ONTAP version you run, and patch on your organization's normal cadence — a verification workflow that itself calls the ONTAP REST API over credentials with `secretsmanager:GetSecretValue` access is not exempt from the same patch-management discipline you'd apply to any other ONTAP API consumer. Separately, the Lambda runtime (`python3.12`) and its `boto3`/`botocore`/`urllib3` dependencies (see the CloudFormation template's inline `ZipFile` code) are not pinned to specific versions in this stack — Lambda resolves the latest available `python3.12` managed runtime and its bundled SDK versions at deploy time, so track AWS's Lambda runtime deprecation schedule and re-deploy periodically rather than assuming a one-time deployment stays current indefinitely.

> **Security note — must-fix before production**: The `CreateFlexClone` and `Cleanup` Lambdas (the two that call the ONTAP REST API directly) construct their `urllib3.PoolManager` with `cert_reqs="CERT_NONE"` — TLS certificate verification is disabled unconditionally in this stack's inline Lambda code, meaning any TLS certificate (including a self-signed one presented by an on-path attacker) is accepted without validation for `secretsmanager`-sourced ONTAP admin credentials sent over that connection. The standalone `restore_verification.py` library this stack's logic is based on *does* support a `ca_cert_path` parameter to enable proper verification, but the CloudFormation template's inline `ZipFile` code does not expose or use that option — it hardcodes `CERT_NONE`. This is acceptable for a PoC in an isolated lab VPC; it is not acceptable for a production deployment carrying real ONTAP admin credentials over the wire. Before production use, either (a) provide the FSx for ONTAP management endpoint's CA certificate to the Lambda (via a Lambda Layer, an environment variable pointing to a bundled cert, or Secrets Manager) and change `cert_reqs` to `"CERT_REQUIRED"` with `ca_certs` set accordingly, or (b) confirm your compensating network control (e.g., the Lambda reaching the ONTAP management IP only through a private, non-transited VPC subnet) makes on-path TLS interception infeasible in your environment, and document that decision explicitly rather than leaving it as an unstated default.

### AWS Permissions

The Lambda execution role requires:

```
# ONTAP REST API (via Secrets Manager credentials)
- secretsmanager:GetSecretValue

# FSx S3 Access Point lifecycle (no resource-level permissions supported
# for these actions as of this writing)
- fsx:CreateAndAttachS3AccessPoint
- fsx:DetachAndDeleteS3AccessPoint
- fsx:DescribeS3AccessPointAttachments
- fsx:DescribeVolumes

# S3 Access Point object read (scanning) + policy management
- s3:ListBucket / s3:GetObject  (scoped to arn:aws:s3:*:*:accesspoint/*)
- s3:PutAccessPointPolicy / s3:GetAccessPointPolicy

# Verdict ledger
- dynamodb:PutItem / dynamodb:UpdateItem  (scoped to the ledger table)
```

### Network Access

Which Lambdas run inside the VPC depends on what each one calls, not on a uniform "verification workflow" rule:

| Lambda | Calls | Runs inside VPC? | Why |
|--------|-------|-------------------|-----|
| `CreateFlexClone` | ONTAP REST API directly (volume create) | ✅ Yes | Needs the management-IP route via `SubnetIds`/`SecurityGroupId` |
| `AttachAccessPoint` | FSx control-plane API only (`CreateAndAttachS3AccessPoint`, `DescribeVolumes`) — never touches ONTAP directly | ❌ No | The FSx API is a public AWS API reachable without a VPC; running it outside the VPC avoids needing an FSx Interface Endpoint just for this step |
| `ScanForIndicators` | `ListObjectsV2` against the **VPC-scoped** S3 Access Point created in the previous step | ✅ Yes | This is the critical one: a VPC-scoped access point has no route from outside the VPC it's bound to (see Security Considerations below) — a Lambda outside the VPC cannot reach it, full stop |
| `RecordVerdict` | DynamoDB + SNS only | ❌ No | Neither API requires VPC access |
| `Cleanup` | Both the ONTAP REST API directly (volume delete) **and** the FSx control-plane API (`DetachAndDeleteS3AccessPoint`) | ✅ Yes | Needs the management-IP route for the ONTAP call; the FSx API call from inside the VPC requires the FSx Interface Endpoint |

> **Critical: VPC Endpoints**. `CreateFlexClone`/`Cleanup` need Secrets Manager + STS reachable from the VPC (for ONTAP credentials); `Cleanup` additionally needs the **FSx Interface Endpoint** (for `DetachAndDeleteS3AccessPoint`); `ScanForIndicators` needs the **S3 Gateway Endpoint** bound to your route tables (`RouteTableIds` parameter) — without it, the scan step cannot reach the VPC-scoped access point at all, and the workflow will fail at that state every time, not intermittently. Each of these four endpoints has its own `CreateXxxEndpoint` parameter (`CreateSecretsManagerEndpoint`/`CreateStsEndpoint`/`CreateFsxEndpoint`/`CreateS3GatewayEndpoint`, all default `true`) — set the ones your VPC already has to `false` rather than treating this as an all-or-nothing choice. See "Before You Deploy" immediately below for how to check what your VPC already has before choosing these four values.

---

## Before You Deploy: Check Existing VPC Endpoints

This is the single most common deployment failure for this stack, and it fails in a way that is easy to misdiagnose on a first read of the error: CloudFormation rejects a **second** Interface VPC Endpoint for a service that already has one in the same VPC with `PrivateDnsEnabled: true`, because both endpoints would try to register the same private DNS domain (e.g., `secretsmanager.<region>.amazonaws.com`) inside the VPC. The error message names the conflicting DNS domain, not the resource that already registered it, so it's easy to spend time looking in the wrong place.

**Run this before choosing your `CreateXxxEndpoint` parameter values:**

```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<your-vpc-id>" \
  --query "VpcEndpoints[].{Service:ServiceName,Type:VpcEndpointType,State:State}" \
  --output table
```

Match what you see against this table:

| If output shows... | Set this parameter to... |
|---------------------|---------------------------|
| `com.amazonaws.<region>.secretsmanager` (Interface) | `CreateSecretsManagerEndpoint=false` |
| `com.amazonaws.<region>.sts` (Interface) | `CreateStsEndpoint=false` |
| `com.amazonaws.<region>.fsx` (Interface) | `CreateFsxEndpoint=false` |
| `com.amazonaws.<region>.s3` (Gateway) **and** it's already associated with the same route tables you're passing as `RouteTableIds` | `CreateS3GatewayEndpoint=false` |
| None of the above present | Leave all four at their `true` default |

If you're deploying this stack into the same VPC as [`automated-response.yaml`](automated-response-guide.md), that stack does not create any VPC Endpoints of its own — it relies on whatever your VPC already had before either stack was deployed. So the check above still applies in full; do not assume `automated-response.yaml` having been deployed first means any of these four endpoints already exist.

> **Route53-private-hosted-zone note**: Some organizations run FSx for ONTAP and other AWS services inside a VPC that is itself a "spoke" attached to a shared-services VPC via Transit Gateway, VPC peering, or a Virtual Private Gateway, with Interface VPC Endpoints created centrally in that shared-services VPC and their private hosted zones associated (via `AssociateVPCWithHostedZone`) to every spoke VPC that needs to resolve them. If your VPC is a spoke in this kind of topology, `describe-vpc-endpoints` run against the spoke VPC will show **no** endpoints even though `secretsmanager.<region>.amazonaws.com` (for example) already resolves inside that VPC via the shared-services VPC's endpoint — because the endpoint resource itself lives in a different VPC, while only its Route 53 private hosted zone association reaches yours. In this topology, creating this stack's own Interface Endpoint with `PrivateDnsEnabled: true` fails with the same DNS-domain-conflict error, but `describe-vpc-endpoints` alone won't have warned you. If `describe-vpc-endpoints` shows nothing but you suspect a shared-services topology, additionally check `aws route53 list-hosted-zones-by-vpc --vpc-id <your-vpc-id> --vpc-region <region>` for a private hosted zone matching the AWS service domain (e.g., `secretsmanager.<region>.amazonaws.com.`) before assuming `CreateXxxEndpoint=true` is safe — a matching zone means the service already resolves privately in your VPC via a centrally-managed endpoint, and this stack's own endpoint attempt for that service will fail the same way a literal duplicate would. This is not a hypothetical: it is the exact failure mode this project's own verification deployment hit against a shared-services VPC with FSx-, Secrets Manager-, SSM-, and SNS-related private hosted zones already associated from outside the VPC.

**If you deploy anyway and hit the conflict**: the stack rolls back automatically (`ROLLBACK_COMPLETE`), and CloudFormation does not let you retry a `deploy`/`create-stack` against a stack in that state — you must delete it first:

```bash
# Confirm the failure and see which resource conflicted
aws cloudformation describe-stack-events \
  --stack-name fsxn-restore-verification \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED'].{Resource:LogicalResourceId,Reason:ResourceStatusReason}" \
  --output table

# Delete the rolled-back stack (safe — it never reached a working state,
# so there is no verification history in the ledger table to lose)
aws cloudformation delete-stack --stack-name fsxn-restore-verification
aws cloudformation wait stack-delete-complete --stack-name fsxn-restore-verification

# Re-deploy with the correct CreateXxxEndpoint values per the table above
```

---

## Deployment

### One Stack Deploy

```bash
aws cloudformation deploy \
  --template-file shared/templates/restore-verification.yaml \
  --stack-name fsxn-restore-verification \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=<secret-arn> \
    FileSystemId=<fs-id> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    RouteTableIds=<route-table-1>,<route-table-2> \
    NotificationTopicArn=<optional-sns-topic-arn> \
    CreateSecretsManagerEndpoint=<true-or-false> \
    CreateStsEndpoint=<true-or-false> \
    CreateFsxEndpoint=<true-or-false> \
    CreateS3GatewayEndpoint=<true-or-false> \
  --capabilities CAPABILITY_NAMED_IAM
```

Set the four `CreateXxxEndpoint` values per the table in [Before You Deploy](#before-you-deploy-check-existing-vpc-endpoints) above — do not deploy with the defaults unchanged without first running the `describe-vpc-endpoints` check.

The stack creates:
- Step Functions state machine (`{stack-name}-workflow`)
- 5 Lambda functions (create-clone, attach-ap, scan, record-verdict, cleanup)
- DynamoDB ledger table (`{stack-name}-ledger`)
- CloudWatch Logs for the state machine (365-day retention) and each Lambda (90-day, except record-verdict at 365-day since it doubles as compliance evidence)
- Whichever of the Secrets Manager/STS/FSx (Interface) and S3 Gateway VPC Endpoints you left at `true` — see [Network Access](#network-access) above for which Lambda needs which endpoint, and [Before You Deploy](#before-you-deploy-check-existing-vpc-endpoints) for choosing each one independently

> **Change-management note**: For a change-advisory process, note what this deployment does and doesn't touch: it creates new, additive resources (a new Step Functions state machine, new Lambdas, a new DynamoDB table, and whichever VPC Endpoints you opted into) — it does not modify the FSx for ONTAP file system, existing ONTAP volumes, or any pre-existing VPC networking. The blast radius of a bad deploy is contained to these new resources; a `cloudformation delete-stack` rollback removes them without touching production storage. The one shared-state risk worth flagging in a change ticket: if any `CreateXxxEndpoint` parameter is left `true` for a service the target VPC already has an Interface Endpoint for (e.g., from `automated-response.yaml`'s VPC, or a centrally-managed shared-services VPC — see the Route53-private-hosted-zone note above), this deploy fails on a duplicate-endpoint DNS conflict and rolls back the whole stack rather than silently reusing the existing one. Run the [Before You Deploy](#before-you-deploy-check-existing-vpc-endpoints) check as part of the change ticket's pre-deployment validation, not as an afterthought if the first attempt fails.

> **Resource-tagging note**: Only `VerificationLedgerTable` carries the `Project`/`Purpose` tag pair in this stack's CloudFormation template — the five Lambda functions and the Step Functions state machine have no `Tags` property at all. If your organization relies on cost-allocation tags or resource-group tags to attribute spend or enforce tagging policy (e.g., AWS Config's `required-tags` rule, or a Service Control Policy denying untagged resource creation), this stack as shipped will either fail that enforcement or silently escape cost attribution for its Lambda/Step Functions spend, even though the DynamoDB table is correctly tagged. Add equivalent `Tags` blocks to the Lambda `AWS::Lambda::Function` resources and the `AWS::StepFunctions::StateMachine` resource before deploying into an account with tagging governance enforced.

> **Stack-update note**: No resource in this template sets `DeletionPolicy` or `UpdateReplacePolicy` (beyond the DynamoDB table's own delete-protection gap noted above) — a CloudFormation stack **update** that happens to replace `VerificationLedgerTable` (e.g., a change to `KeySchema` or `AttributeDefinitions`, which forces replacement rather than an in-place update) would delete the old table and its full verification history by default, not just a stack **deletion**. This is a narrower but easy-to-miss risk than the already-documented `delete-stack` case: a well-intentioned template change during routine maintenance can trigger the same data loss. Before making any change to this stack's DynamoDB table definition, run `aws cloudformation create-change-set` first and check whether the table shows `Replacement: True` in the change set output — if it does, export the table's contents first or add `DeletionPolicy: Retain` to `VerificationLedgerTable` so an update-triggered replacement leaves the old table orphaned-but-intact rather than deleted.

### Starting a Verification Run

```bash
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn output> \
  --input '{
    "svm_name": "svm-prod-01",
    "volume_name": "vol_data",
    "snapshot_name": "incident_response_20260708_143022",
    "vpc_id": "vpc-0123456789abcdef0"
  }'
```

Chain this after the [Automated Response Guide](automated-response-guide.md)'s `create_snapshot` action by having your SOAR playbook or Step Functions fan-out (see that guide's FAQ) invoke this state machine with the newly created snapshot's name once containment completes.

> **Capacity-planning note**: This workflow does not set `ReservedConcurrentExecutions` or `MaxConcurrency` anywhere — each Step Functions execution runs its own five Lambda invocations against the account/Region's shared unreserved concurrency pool. On a large fleet where many snapshots are verified around the same time (e.g., a scheduled sweep across hundreds of volumes, or a mass-incident scenario triggering many `create_snapshot` actions at once), a burst of concurrent executions competes for that same pool with every other Lambda function in the account, including `automated-response.yaml`'s response handlers. Size your expected concurrent verification count against your account's Lambda concurrency limit before scheduling this against a large fleet, and consider a `MaxConcurrency` cap on whatever mechanism fans out executions (EventBridge Scheduler, Step Functions `Map` state, or your SOAR tool) rather than relying on the account-wide limit as an implicit throttle.

### Querying the Ledger

```bash
aws dynamodb query \
  --table-name fsxn-restore-verification-ledger \
  --key-condition-expression "snapshot_key = :sk" \
  --expression-attribute-values '{":sk": {"S": "svm-prod-01/vol_data/incident_response_20260708_143022"}}'
```

---

## Configuration Reference

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `SuspiciousRatioThreshold` | 0.05 | Fraction of scanned objects with ransomware-associated extensions required to flag "suspicious" |
| `SuspiciousMinCount` | 20 | Absolute floor on suspicious object count (avoids false positives on small volumes) |
| `StepTimeoutSeconds` | 180 | Timeout for each Step Functions Lambda task |
| `UnixUser` | root | UNIX identity used by the verification S3 Access Point for file system access checks |
| `LambdaMemorySize` | 512 MB | Memory for all 5 verification Lambdas |

> **Cost note**: The recurring cost drivers per verification run are Lambda invocation time (5 short-lived functions, typically seconds each), DynamoDB on-demand writes (2-3 `PutItem`/`UpdateItem` calls per run against a `PAY_PER_REQUEST` table), and — if `CreateVpcEndpoints=true` — the hourly cost of the Interface VPC Endpoints (Secrets Manager, STS, FSx) plus their per-GB data-processing charge; the S3 Gateway Endpoint itself has no hourly charge. None of these are metered per-scan-object the way [Amazon Comprehend pricing](https://aws.amazon.com/comprehend/pricing/) is for the companion PII scanner — cost here scales with *run frequency*, not volume size, so scheduling this workflow hourly against every snapshot on a large fleet is a meaningfully different cost profile than running it once per incident. Reuse Interface VPC Endpoints across this stack and `automated-response.yaml` in the same VPC (`CreateVpcEndpoints=false`) rather than paying for duplicates.

> **Sustainability note**: This is a fundamentally lightweight workload from a compute-carbon perspective — five short-lived Lambda invocations per run, each doing I/O-bound work (an ONTAP REST call, an S3 list, a DynamoDB write) rather than sustained CPU-bound computation, and no persistent compute (no EC2, no always-on container) idling between runs. The same observation as the cost note above applies here in different units: *run frequency* is the lever that matters for energy consumption, not volume size, since `ScanForIndicators` only lists object keys (`ListObjectsV2`) rather than reading file contents. Scheduling this hourly against every snapshot on a large fleet multiplies invocation count (and therefore energy draw) linearly with schedule frequency — if a periodic recovery-readiness check is the goal rather than post-incident verification, a daily or weekly cadence against representative volumes is likely to meet that goal with meaningfully less aggregate energy use than an hourly sweep of an entire fleet.

---

## Security Considerations

- **No production data path**: The FlexClone shares blocks with its parent via copy-on-write, but the S3 Access Point only exposes the *clone*, not the parent volume. Deleting the clone at cleanup does not affect the parent volume or the original snapshot.
- **VPC-scoped access point**: The access point is bound to the VPC at creation time and cannot be reached from outside it. This is a stronger guarantee than an internet-origin access point restricted only by policy — see [AWS's network-origin comparison](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html). This is also why `ScanForIndicators` (the Lambda that lists the access point's objects) *must* run inside the bound VPC with a route to S3 (the S3 Gateway Endpoint this stack creates) — there is no policy-only way to reach a VPC-scoped access point from outside its VPC, unlike an internet-origin one.

> **Data-residency note**: Every resource this workflow creates — the FlexClone (same Region as the parent FSx for ONTAP file system, by definition), the S3 Access Point, the DynamoDB ledger table, and the Lambda functions themselves — stays within the single AWS Region you deploy this stack into. There is no cross-Region data movement anywhere in this workflow, which is a relevant point to confirm affirmatively for a data-residency questionnaire rather than leaving it as an inference. If your organization operates this workflow across multiple Regions (one stack per Region, per the [Multi-Account Deployment](multi-account-deployment.md) pattern referenced in the Cyber Resilience Capability Map), each Region's ledger is independent — there is no built-in cross-Region replication or aggregation of verification history, so a residency-driven multi-Region deployment also means a per-Region evidence trail unless you build your own aggregation layer.
- **Least privilege for `fsx:*S3AccessPoint*` actions**: These actions do not currently support resource-level permissions or condition keys as fine-grained as other FSx actions; the IAM policy in this stack scopes them to `Resource: '*'` with a documented rationale. Revisit this if AWS adds resource-level support.

> **IAM-design note**: `VerificationLambdaRole` is a single shared role attached to all five Lambdas (see the CloudFormation template), rather than five distinct roles scoped to each function's actual needs — `ScanForIndicators` (which only needs `s3:ListBucket`/`s3:GetObject`) can technically assume the same broad `Resource: '*'` `fsx:*S3AccessPoint*` permissions that `AttachAccessPoint`/`Cleanup` actually use, even though it never calls those APIs. This is a common, reasonable tradeoff for a single-purpose stack (fewer roles to audit, no cross-role `iam:PassRole` complexity), but it does mean a compromised `ScanForIndicators` execution environment has more IAM reach than its own code requires. If your organization's IAM standard requires role-per-function least privilege even within a single workflow, split `VerificationLambdaRole` into per-Lambda roles scoped to exactly the policy statements each function's code path calls.
- **Verdict ledger as evidence, not a substitute for governance**: The DynamoDB ledger supplies auditable evidence (who verified what, when, with what result) that a CSF 2.0 Govern program can consume — see the [Cyber Resilience Capability Map](cyber-resilience-capability-map.md#govern-gv)'s Govern-function discussion for why this repo does not attempt to automate the governance program itself.
- **The ledger table has no delete protection by default**: `VerificationLedgerTable` is created with Point-in-Time Recovery enabled but without `DeletionProtectionEnabled` or an explicit `DeletionPolicy: Retain`. If this table is your primary evidence of periodic restore testing (see the cyber-insurance evidence note below), add `DeletionProtectionEnabled: true` and consider a `DeletionPolicy: Retain` override before relying on it for audit purposes — an accidental `aws cloudformation delete-stack` should not be able to erase your evidence history.

> **Encryption-at-rest note**: `VerificationLedgerTable`'s `SSESpecification` enables encryption with `SSEEnabled: true` but does not set `SSEType`/`KMSMasterKeyId`, which means it encrypts with the AWS-owned DynamoDB key rather than a customer-managed KMS key. This is a reasonable default for most workloads and meets "encrypted at rest," but if your organization's key-management policy requires customer-managed KMS keys (for independent rotation control, cross-account key policies, or a specific compliance mapping), add `SSEType: KMS` and `KMSMasterKeyId: <your-key-arn>` explicitly — the current template does not expose this as a parameter. The same applies to the state machine's and Lambdas' CloudWatch Log Groups, which are also encrypted with the AWS-owned CloudWatch Logs key by default (no `KmsKeyId` set on any `AWS::Logs::LogGroup` resource in this stack).

> **Audit-trail-completeness note**: The `VerificationStateMachine`'s `LoggingConfiguration` sets `Level: ALL` and `IncludeExecutionData: true`, which is exactly what you want for full observability — but "full observability" here also means the complete input/output payload of every state (including `svm_name`, `volume_name`, `snapshot_name`, and any `reason`/`error` text) is written to CloudWatch Logs on every execution, not just the DynamoDB ledger's curated fields. If `volume_name` or `snapshot_name` values in your environment ever embed sensitive context (an incident ticket number, a customer name in a snapshot label), that context now also lives in CloudWatch Logs with this stack's log-group retention (365 days) rather than only in the ledger table you might otherwise assume is the single source of truth. Review your snapshot- and volume-naming conventions with this in mind, or set `IncludeExecutionData: false` if the full payload in logs is more exposure than you want, accepting the corresponding loss of debugging detail.

> **Cyber-insurance evidence note**: Underwriting checklists for cyber insurance increasingly ask for evidence of *tested* backups, not just backup existence — "periodic restore verification" is called out explicitly in several 2026 underwriting guides. The DynamoDB ledger this workflow produces (timestamped `snapshot_key`, verdict, and `reason` per run) is a reasonable evidence artifact for that question, but it wasn't designed with an insurer's evidence format in mind: there is no built-in export to PDF/CSV for a renewal questionnaire, and (as noted above) no delete protection guarding the evidence itself. If you plan to cite this ledger during underwriting or renewal, export a snapshot of the relevant `dynamodb query` output alongside your other control evidence, and enable the delete protection above first.

> **Audit-evidence note**: If this workflow is cited as a control in an internal audit or SOX control matrix (e.g., a control asserting "recovery points are verified before restoration"), the auditor's test of operating effectiveness will typically want to see: (1) evidence the control actually *ran* on a sample of periods, not just that it *exists* — the DynamoDB ledger's `started_at`/`completed_at` timestamps support this; (2) evidence someone with appropriate authority *reviewed* a "suspicious" or "error" verdict and took action, which this workflow does not itself produce — an SNS notification firing is evidence an alert was *sent*, not evidence anyone *acted* on it; (3) segregation of duties between whoever can modify this stack's IAM permissions/code (effectively controlling what "clean" means) and whoever relies on its verdict to authorize a restore. If a SOX control depends on this workflow, pair the automated verdict with a manual attestation step (a ticket, an approval workflow) that captures human review and action, and retain that attestation alongside the DynamoDB record as the actual audit evidence — the ledger alone documents that a scan ran, not that anyone exercised judgment on its result.

---

## Testing

The `restore_verification.py` module has 23 unit tests covering:

| Category | What's Verified |
|----------|-----------------|
| FlexClone create/delete | Success, job failure, clone-lookup failure, already-deleted (404) |
| S3 Access Point attach/detach | Success, fsvol resolution timeout, MISCONFIGURED state, ClientError handling, not-found on detach |
| Ransomware indicator scan | Clean volume, suspicious volume, empty volume, case-insensitive extension matching |
| Full orchestration | Clean verdict, suspicious verdict, below-min-count false-positive avoidance, error path with cleanup, error-after-clone-created cleanup, result serialization capping |

```bash
python3 -m pytest shared/python/tests/test_restore_verification.py -v
# 23 passed in 0.11s
```

> **Test-coverage note**: All 23 tests run against mocked `boto3` clients and mocked ONTAP HTTP responses — none of them exercise a real FSx for ONTAP file system or a real S3 Access Point. This keeps the suite fast and CI-safe (no AWS credentials or live infrastructure required), but it also means these tests cannot catch drift between the mocked API contracts and the real ONTAP REST API/AWS FSx API behavior. Treat `pytest` passing as necessary but not sufficient evidence the workflow works end-to-end — validate against a real (non-production) FSx for ONTAP file system before relying on this in production, and re-validate after any ONTAP or AWS SDK version bump that touches the FlexClone or S3 Access Point APIs.

> **License note**: This workflow's runtime dependencies are `boto3`, `botocore`, and `urllib3` — all bundled with the Lambda `python3.12` managed runtime rather than vendored into this repo, so there is no `requirements.txt` or lockfile in this stack to license-scan directly. All three are [Apache License 2.0](https://github.com/boto/boto3/blob/develop/LICENSE), which is permissive and imposes no copyleft obligations, so this is a low-friction dependency set from a license-compliance standpoint. If your organization runs automated license scanning (e.g., an SBOM generator or a tool like `pip-licenses`) as part of its supply-chain review, note that scanning the inline CloudFormation `ZipFile` code directly won't surface these dependencies the way a `requirements.txt`-based deployment would — you'd need to scan against the Lambda managed runtime's own published dependency manifest instead, or migrate to the pinned-dependency deployment approach mentioned in the Patch-management note above, which would also make this scanning straightforward.

> **Operational-triage note**: If paged for a failed verification run, start here: (1) check the Step Functions execution history for the `StateMachineExecutionArn` — the failing state name tells you which of the five Lambdas failed; (2) check that Lambda's CloudWatch Logs (`/aws/lambda/{stack-name}-{create-clone|attach-ap|scan|record-verdict|cleanup}`) for the actual exception; (3) query the DynamoDB ledger for the `snapshot_key` in question — an `error` verdict with a `reason` field is often enough to triage without touching logs at all. A failed run does not require immediate remediation at 2am: the workflow's own `Cleanup`/`CleanupAfterError` states already guarantee no orphaned FlexClone or S3 Access Point is left behind (see Architecture above), so this is a "investigate when convenient" alert, not a "stop the bleeding" one — unless the same `snapshot_key` fails repeatedly, which may indicate an ONTAP-side or IAM-side problem worth escalating sooner.

> **Failure-injection note**: The Testing section above validates the happy path and several mocked failure modes, but the claim that "cleanup runs on every path" (see Architecture) is best validated by actually injecting failures against a real (non-production) deployment rather than trusting the Step Functions `Catch` topology alone. Worthwhile experiments: (1) kill the `ScanForIndicators` Lambda mid-execution (e.g., a temporary IAM deny on `s3:ListBucket`) and confirm the FlexClone is actually deleted afterward, not just that the state machine reports success; (2) inject an ONTAP API timeout during `Cleanup` itself (the one Lambda with no downstream catch of its own) and confirm you can detect and manually remediate an orphaned clone when cleanup-of-cleanup has no safety net; (3) verify what happens if `RecordVerdict` succeeds but the subsequent `Cleanup` step's own Lambda invocation fails to even start (a Step Functions-level fault, not an application error) — confirm your CloudWatch alarms would actually catch that gap. None of this requires production data; a throwaway SVM/volume with a synthetic snapshot is sufficient.

> **Retry-policy note**: Every state in this workflow's `DefinitionString` defines a `Catch` block but none defines a `Retry` block — a transient failure (an ONTAP management endpoint momentarily unreachable, a brief Secrets Manager or DynamoDB throttle, a one-off network blip inside the VPC) routes straight to `CleanupAfterError`/`RecordErrorVerdict` on the first attempt rather than retrying with backoff first. This means a workflow that would have succeeded on a second attempt instead records a permanent "error" verdict and triggers a full clone-and-cleanup cycle for what was, in fact, a recoverable blip. If your environment sees occasional transient ONTAP API or AWS API errors, consider adding a `Retry` block (e.g., `ErrorEquals: ["States.Timeout", "States.TaskFailed"]` with a short `IntervalSeconds`/`MaxAttempts`/`BackoffRate`) to the Lambda-calling states before falling through to `Catch` — this is a standard Step Functions pattern this workflow does not currently use.

> **SNS-delivery note**: Both `RecordVerdict` and `RecordErrorVerdict`'s SNS `publish` calls are wrapped in a bare `try`/`except Exception` that only logs a warning on failure (`logger.warning("Verdict notification failed: %s", e)`) — the DynamoDB `put_item` before it always succeeds or raises, but a failed SNS publish (a deleted topic, a permissions change, throttling) is swallowed silently from the caller's perspective. The Step Functions execution still reports success, and the DynamoDB ledger still has the correct verdict, but the notification you were relying on to learn about a "suspicious" result may simply never have arrived — and nothing in this workflow's own CloudWatch metrics distinguishes "no PII found, no notification needed" from "notification attempted and failed." If SNS delivery is part of your incident-response trigger chain, add a CloudWatch Alarm on this Lambda's own log pattern (`"notification failed"`) rather than assuming a lack of alerts means a lack of suspicious verdicts.

---

## Related Documents

- [Cyber Resilience Capability Map](cyber-resilience-capability-map.md#recover-rc) — the Recover-function discussion this guide implements a fix for
- [Automated Response Guide](automated-response-guide.md) — the Respond-phase blocking and protective snapshot creation that typically precedes running this workflow
- [ARP Incident Response Guide](arp-incident-response-guide.md) — the live-volume entropy detection this workflow's scan complements but does not replace
- [Content-Level PII Classification Scanner](content-classification-scanner.md) — a related content-scanning capability for the CSF 2.0 Identify function (data classification), built on the same FlexClone + S3 Access Point pattern
- [Governance & Compliance](governance-and-compliance.md) — where the verdict ledger fits as Govern-function evidence
- [Compliance Evidence Pack](compliance-evidence-pack.md) — audit-trail evidence artifact templates

## FAQ

**Q: Does a "clean" verdict guarantee the snapshot is safe to restore?**
A: No — see the Recovery-sufficiency note above. It's a fast, automated pre-filter based on file-extension patterns, not a full malware scan or application-level integrity check. Treat it as a necessary first gate, not the final word.

**Q: Why FlexClone instead of just scanning the production volume directly?**
A: Scanning the live volume would compete with production I/O and risk interacting with an active attack. A FlexClone is an isolated, point-in-time, read/write copy that shares blocks via copy-on-write — verification runs against it with zero production impact, and it's deleted afterward.

**Q: Why an S3 Access Point instead of mounting the clone via NFS/SMB?**
A: Mounting requires network-level access to the SVM's data LIF and a running NFS/SMB client in the verification environment. An S3 Access Point lets a stateless Lambda list and read files via the S3 API with no mount step, and (when VPC-scoped) with no path to the production data plane beyond the read-only access point itself.

**Q: What happens if the workflow fails partway through — is the clone left behind?**
A: No. The Step Functions `Catch` blocks route every failure mode to the same `Cleanup` Lambda used on the success path. The cleanup Lambda tolerates partial state (e.g., a clone was created but the access point attach failed) and cleans up whatever exists.

**Q: Can I run this against snapshots other than the ones created by the Automated Response module?**
A: Yes. `verify_snapshot()` / the Step Functions input only need `svm_name`, `volume_name`, and `snapshot_name` — any existing ONTAP snapshot works, including scheduled Snapshot Policy snapshots unrelated to an incident.

**Q: A customer/user reports "the verification never finishes" — what's the first thing to check, before escalating?**
A: Check the Step Functions execution's current state in the console or via `describe-execution` first — "never finishes" almost always means it's stuck in a specific state, not silently hung everywhere. If it's stuck in `AttachAccessPoint` or `ScanForIndicators`, the most common cause is a VPC networking gap (see Network Access above — e.g., the S3 Gateway Endpoint missing for `ScanForIndicators`, which fails deterministically every time, not intermittently). If it's stuck in `CreateFlexClone`, check whether the ONTAP volume/SVM name in the request actually exists and whether the ONTAP job it's polling shows progress via `GET /api/cluster/jobs/{uuid}` directly against the management endpoint. Each Lambda has a `StepTimeoutSeconds` bound (default 180s), so a true hang should surface as a Step Functions `States.Timeout` error within that window rather than running indefinitely — if you see an execution that's been "running" for much longer than `StepTimeoutSeconds` × 5, that itself is worth escalating as an anomaly, since it suggests the timeout mechanism itself isn't functioning as expected.

**Q: We're migrating an existing FSx for ONTAP fleet to this verification workflow — where do we start?**
A: Deploy this stack against one volume first, and run `verify_snapshot()` manually against an existing scheduled snapshot before wiring it into any automated trigger — this confirms the ONTAP permissions, VPC networking, and FSx S3 Access Point support actually work against your specific environment (ONTAP version, VPC configuration) before you depend on it. Existing snapshots created before this workflow existed work without any special handling; there's no metadata or tagging this workflow requires a snapshot to have retroactively. Once validated on one volume, expand to your full fleet using the same [Multi-Account Deployment](multi-account-deployment.md) StackSets pattern referenced in the Cyber Resilience Capability Map, rather than manually deploying per-volume or per-account.

**Q: A "suspicious" verdict was recorded in the DynamoDB ledger, but no one received an SNS notification — is that expected?**
A: Check CloudWatch Logs for the `RecordVerdict` Lambda for a `"Verdict notification failed"` warning before assuming the notification pipeline is broken end-to-end. The SNS `publish` call is wrapped in a try/except that logs and continues rather than failing the workflow (see the SNS-delivery note under Security Considerations above) — this is intentional, so a notification-delivery problem never blocks the verdict from being recorded, but it also means notification failures are silent unless you're watching for that specific log line. If you rely on this notification as an incident-response trigger, add a CloudWatch Alarm on that log pattern rather than treating "no alert received" as equivalent to "nothing suspicious happened."

**Q: We changed the DynamoDB table's key schema and now the old verification history is gone — what happened?**
A: A CloudFormation stack update that changes `VerificationLedgerTable`'s `KeySchema` or `AttributeDefinitions` forces DynamoDB table replacement rather than an in-place update, and this template does not set `DeletionPolicy: Retain` on that table (see the Stack-update note under Deployment above) — CloudFormation deleted the old table as part of applying the replacement. This is recoverable only if Point-in-Time Recovery was enabled and you restore within its retention window; going forward, run `aws cloudformation create-change-set` before any schema-affecting update and check for `Replacement: True` in the output.
