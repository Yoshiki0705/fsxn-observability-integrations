# ARP Incident Response Demo Runbook

🌐 [日本語](../ja/demo-arp-incident-response.md) | **English** (this page)

## Purpose

Step-by-step procedure for demonstrating the ARP (Autonomous Ransomware Protection) detection-to-response flow described in the [ARP Incident Response Guide](arp-incident-response-guide.md). This runbook is scoped to the ARP detection chain and its Datadog-side confirmation specifically — for the automated containment actions (SMB/NFS blocking, snapshot creation) that a real or simulated ARP alert can trigger, see the [Automated Response Demo Runbook](demo-automated-response.md)'s Phase 4, which this runbook complements rather than duplicates.

Use this runbook for:
- Live demos (in-person or recorded)
- E2E verification before blog publication
- Internal training

> **Evidence format note — verification status update (2026-07-12)**: Phase 1 (EMS delivery pipeline) and Phase 2 (actual ARP/AI detection) have both been verified end-to-end on ONTAP 9.17.1P7D1. Key findings from verification: (1) `attack simulate` CLI command does NOT exist in ONTAP 9.17.1 — actual file operations (encrypt + delete + rename with new extension) must be used instead; (2) ARP/AI is immediately active with no learning period; (3) ARP correctly detected the ransomware-like pattern (Attack Probability: moderate, Detected By: file_analysis) and auto-created an `Anti_ransomware_attack_backup` snapshot; (4) EMS event `callhome.arw.activity.seen` was emitted with severity=alert. Phase 3 (incident response decision steps) was partially verified (`clear-suspect -false-positive true` works, but `show-suspect-files` does not exist as a CLI command). Full verification results: [`docs/screenshots/group-b-verification-results.md`](../screenshots/group-b-verification-results.md).

---

## Prerequisites

| Item | Requirement |
|------|------------|
| FSx for ONTAP | Running, with ARP enabled on at least one volume (`security anti-ransomware volume show`) |
| ONTAP credentials | Admin SSH access to the management endpoint |
| EMS Webhook stack | Deployed (`fsxn-ems-webhook` or your vendor's equivalent — see [Prerequisites](prerequisites.md)) |
| Observability platform | Datadog (or your configured vendor) receiving EMS/FPolicy events |
| AWS CLI | Configured with appropriate IAM permissions |

---

## Phase 1: Confirm the EMS Detection Pipeline (Previously Verified)

This phase reproduces the pipeline test documented in `docs/en/verification-results-datadog.md`. It confirms the Lambda-to-Datadog delivery path works — it does **not** exercise ONTAP's own ARP detection logic (see Phase 2 for that).

### Step 1.1: Confirm the EMS/FPolicy Stack Is Deployed

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-datadog-ems-fpolicy \
  --query 'Stacks[0].StackStatus' \
  --output text
```

**What to check**: `CREATE_COMPLETE` or `UPDATE_COMPLETE`. If this stack doesn't exist yet, deploy it first — see [EMS Detection Capabilities](ems-detection-capabilities.md) for the template and parameters.

### Step 1.2: Invoke the EMS Lambda With a Synthetic ARP Event

This is the same invocation used in the project's own prior verification — it simulates the JSON payload EMS would deliver for an ARP alert, without needing a real attack or a real `attack simulate` run:

```bash
aws lambda invoke \
  --function-name fsxn-datadog-ems-fpolicy-ems \
  --payload '{"body":"{\"messageName\":\"arw.volume.state\",\"severity\":\"alert\",\"parameters\":{\"volume_name\":\"<test-vol>\",\"state\":\"attack-detected\"}}","requestContext":{}}' \
  --cli-binary-format raw-in-base64-out \
  response.json

cat response.json
```

**What to check**: the response body reports `"shipped": 1` (or similar, depending on your vendor's Lambda). Compare against the previously-verified response documented in `verification-results-datadog.md`: `{"statusCode": 200, "body": {"total_events": 1, "shipped": 1}}`.

### Step 1.3: Confirm Arrival in Datadog (or Your Vendor)

Search in Datadog:

```
source:fsxn-ems @attributes.event_name:arw.volume.state
```

**What to check**: one log entry matching the volume name and severity you sent in Step 1.2, arriving within roughly 30 seconds of the invocation. This is exactly what [`datadog-arp-detection.png`](../screenshots/datadog-arp-detection.png) and [`datadog-arp-log-detail.png`](../screenshots/datadog-arp-log-detail.png) show from the prior verification pass — use those screenshots as a reference for what the result should look like, not as evidence that today's run succeeded.

---

## Phase 2: Exercise ONTAP's Actual ARP Feature (Not Yet Verified)

This phase runs ONTAP's own ARP detection against a real (test) volume, rather than simulating the resulting EMS payload. As of this writing, this project has not executed this phase end-to-end, and no screenshots exist for it.

### Step 2.1: Confirm ARP Is Active on the Target Volume

```bash
ssh admin@<management-ip> "security anti-ransomware volume show -vserver <svm-name> -volume <volume-name>"
```

**What to check**: the target volume's ARP state shows as enabled/active. If it doesn't, enable ARP on the volume before proceeding — see the [AWS documentation on ARP](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/ARP.html) referenced in the main guide.

### Step 2.2: Trigger ARP Detection (TEST ENVIRONMENT ONLY, Disposable Data)

> **Important (ONTAP 9.16.1+ / ARP/AI)**: The `security anti-ransomware volume attack simulate` command does **NOT exist** in ONTAP 9.17.1. To trigger ARP/AI detection, you must perform actual ransomware-like file operations. ARP/AI is immediately active (no learning period) and detects patterns such as: high-entropy data writes + file deletion + never-seen-before file extensions.

Trigger detection using actual file operations from a mounted NFS/SMB client:

```bash
# From a client with NFS or SMB mount on the target volume:
# 1. Create normal files
for i in $(seq 1 15); do
  dd if=/dev/urandom of=/mnt/target-vol/doc_${i}.dat bs=256K count=1 status=none
done

# 2. Encrypt them (simulating ransomware behavior — zip with password + new extension)
cd /mnt/target-vol
for f in doc_*.dat; do
  zip -q -e -P TestPass123 "${f}.ktkt" "$f" && rm -f "$f"
done
```

**What to check**: After 1-5 minutes, verify ARP detected the activity:
```bash
ssh admin@<management-ip> "security anti-ransomware volume show -vserver <svm-name> -volume <volume-name>"
```
Expected: `Attack Probability: moderate` (or higher), `Attack Detected By: file_analysis`.

> **Detection thresholds**: ARP/AI uses `never_seen_before_file_extension_count_notify_threshold: 5` — the extension must be new and distinct. Using the same extension (even on many files) may not trigger detection on its own. Combining encryption + deletion + new extension is the most reliable trigger pattern.

### Step 2.3: Confirm the ARP Snapshot Was Created

```bash
ssh admin@<management-ip> "volume snapshot show -vserver <svm-name> -volume <volume-name> -snapshot Anti_ransomware*"
```

**What to check**: a snapshot with the `Anti_ransomware_backup` prefix appears, with a timestamp close to when the file operations were performed. ARP/AI automatically creates this snapshot when it detects suspicious activity. Example from verified deployment:
```
Anti_ransomware_attack_backup.2026-07-12_0042    30.73MB
```

### Step 2.4: Confirm the Real EMS Event Reaches Datadog

Repeat the Datadog search from Step 1.3:

```
source:fsxn-ems @attributes.event_name:arw.volume.state
```

**What to check**: a new log entry appears, this time triggered by ARP's detection of the actual file operations (not a directly-invoked Lambda payload). The EMS event name is `callhome.arw.activity.seen` (severity=alert). If it does not appear within a few minutes, check the EMS Webhook stack's own Lambda logs (see [EMS Detection Capabilities](ems-detection-capabilities.md)) — the gap could be anywhere in the ONTAP → EMS Webhook → Lambda → vendor chain.

### Step 2.5: Confirm ARP Status via ONTAP CLI

```bash
ssh admin@<management-ip> "security anti-ransomware volume show -vserver <svm-name> -volume <volume-name>"
```

**What to check**: the volume's ARP state reflects the detected attack (e.g., `Attack Probability: moderate`, `Attack Detected By: file_analysis`). Verified output from ONTAP 9.17.1P7D1:
```
Vserver Name: <svm-name>
 Volume Name: <volume-name>
       State: enabled
Attack Probability: moderate
   Attack Timeline: 7/12/2026 00:26:12
 Number of Attacks: 1
Attack Detected By: file_analysis
```

---

## Phase 3: Walk Through the Incident Response Decision Steps

This phase follows [ARP Incident Response Guide § Step 1 through Step 4a/4b](arp-incident-response-guide.md#step-1-initial-response-within-5-minutes-of-detection). It is a decision/documentation exercise more than a technical verification step — there is no single command whose output confirms "the incident response process was followed correctly."

### Step 3.1: Investigate Scope

> **Note**: The `show-suspect-files` subcommand does not exist in ONTAP 9.17.1. Use the REST API to query suspect files, or inspect the ARP attack report:

```bash
# Generate and view the ARP attack report
ssh admin@<management-ip> \
  "security anti-ransomware volume attack generate-report -vserver <svm-name> -volume <volume-name> -dest-path <svm-name>:/<volume-name>/"

# Alternatively, check via REST API:
# GET /api/storage/volumes/<vol-uuid>?fields=anti_ransomware
```

**What to check**: review the suspect file listing / attack report against the [ARP Incident Response Guide § Step 2](arp-incident-response-guide.md#step-2-scope-assessment) Assessment Checklist to determine whether this is a false positive or a real attack.

### Step 3.2: Practice Both Outcomes

For a demo, walk through both branches rather than picking one:

**False positive branch** — see [Step 4a](arp-incident-response-guide.md#step-4a-false-positive):
```bash
ssh admin@<management-ip> "security anti-ransomware volume attack clear-suspect -vserver <svm-name> -volume <volume-name> -false-positive true"
```
**What to check**: the command completes without error, and a follow-up `security anti-ransomware volume show` no longer shows the attack state. The ARP snapshot created in Step 2.3 is automatically deleted as part of this action.

> **Note**: The `-false-positive` parameter is **required** (not optional). Use `true` for false-positive clearance, `false` for confirmed-attack clearance.

**Attack-confirmed branch** — see [Step 4b](arp-incident-response-guide.md#step-4b-attack-confirmed--containment). Rather than repeating those containment commands here, chain into the [Automated Response Demo Runbook](demo-automated-response.md)'s Phase 4, which demonstrates the automated containment path (SMB user block, snapshot, session disconnect) that a confirmed ARP attack should trigger.

---

## Cleanup

```bash
# Remove the ARP snapshot created during Phase 2, if you did not already
# clear it via the false-positive branch in Phase 3
ssh admin@<management-ip> "volume snapshot delete -vserver <svm-name> -volume <volume-name> -snapshot Anti_ransomware_backup.<timestamp>"

# If you deployed the EMS/FPolicy stack solely for this demo, it is shared
# infrastructure with other detection flows — do not delete it without
# confirming no other integration depends on it.
```

---

## Timing Reference

| Phase | Duration | Notes |
|-------|----------|-------|
| Phase 1 (EMS pipeline confirmation) | ~3 min | Invoke + search |
| Phase 2 (ONTAP ARP exercise) | ~5 min | Simulate + confirm snapshot + confirm EMS delivery |
| Phase 3 (Incident response walkthrough) | ~5 min | Scope assessment + both outcome branches |
| **Total** | **~13 min** | Full demo; add [Automated Response Demo Runbook](demo-automated-response.md) Phase 4 (~5 min) if demonstrating the confirmed-attack containment path too |

---

## Related Documents

- [ARP Incident Response Guide](arp-incident-response-guide.md)
- [Automated Response Guide](automated-response-guide.md) — the containment actions a confirmed ARP attack should trigger
- [Automated Response Demo Runbook](demo-automated-response.md) — Phase 4 demonstrates the ARP → auto-containment flow
- [EMS Detection Capabilities](ems-detection-capabilities.md) — the full EMS event catalog, including `arw.volume.state`
- [Security Monitoring Index](security-monitoring-index.md)
