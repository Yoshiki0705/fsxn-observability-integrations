"""Auto-remediation Lambda — Creates ONTAP Snapshot for evidence preservation.

Triggered by Datadog Workflow when mass file deletion is confirmed by SOC analyst.
Creates a timestamped snapshot with audit metadata for forensic investigation.

Features:
    - 15-minute cooldown to prevent Snapshot storms during sustained attacks
    - Audit trail via CloudWatch Logs (correlation ID for traceability)
    - TLS-ready: configure CA_CERT_PATH for production certificate validation

Environment Variables:
    ONTAP_MGMT_IP: FSx for ONTAP management endpoint IP
    ONTAP_CREDENTIALS_SECRET_ARN: Secrets Manager ARN for ONTAP admin credentials
    DEFAULT_VOLUME: Default volume name (if not provided in event)
    DEFAULT_SVM: Default SVM name (if not provided in event)
    COOLDOWN_MINUTES: Minutes between remediation snapshots (default: 15)
    CA_CERT_PATH: Path to ONTAP CA certificate (default: None = CERT_NONE)
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Any

import urllib3
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# TLS configuration: Use CA cert in production, CERT_NONE for PoC
_ca_cert_path = os.environ.get("CA_CERT_PATH")
if _ca_cert_path and os.path.exists(_ca_cert_path):
    http = urllib3.PoolManager(ca_certs=_ca_cert_path)
    logger.info("TLS: Using CA certificate from %s", _ca_cert_path)
else:
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    if not _ca_cert_path:
        logger.warning("TLS: CERT_NONE (set CA_CERT_PATH for production)")

COOLDOWN_MINUTES = int(os.environ.get("COOLDOWN_MINUTES", "15"))


def _check_cooldown(
    mgmt_ip: str, vol_uuid: str, headers: dict
) -> tuple[bool, str]:
    """Check if a remediation snapshot was created within the cooldown period.

    Returns:
        Tuple of (should_skip: bool, reason: str)
    """
    resp = http.request(
        "GET",
        f"https://{mgmt_ip}/api/storage/volumes/{vol_uuid}/snapshots"
        f"?name=remediation_*&order_by=create_time+desc&max_records=1",
        headers=headers,
    )

    if resp.status != 200:
        # If we can't check, proceed with creation (fail-open for remediation)
        return False, "snapshot list unavailable"

    records = json.loads(resp.data).get("records", [])
    if not records:
        return False, "no prior remediation snapshots"

    last_create_time = records[0].get("create_time", "")
    if not last_create_time:
        return False, "no create_time on last snapshot"

    try:
        # ONTAP returns ISO format: 2026-06-14T21:55:30+00:00
        last_dt = datetime.fromisoformat(last_create_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed_minutes = (now - last_dt).total_seconds() / 60

        if elapsed_minutes < COOLDOWN_MINUTES:
            return True, (
                f"cooldown active — last snapshot {records[0].get('name', '?')} "
                f"created {elapsed_minutes:.1f} min ago (limit: {COOLDOWN_MINUTES}m)"
            )
    except (ValueError, TypeError) as e:
        logger.warning("Could not parse snapshot time: %s", e)

    return False, "cooldown expired"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Create protective snapshot on ONTAP volume with cooldown protection.

    Args:
        event: Invocation payload from Datadog Workflow.
            Required: volume_name, svm_name
            Optional: reason, user

    Returns:
        Dict with snapshot details or error information.
    """
    volume_name = event.get("volume_name", os.environ.get("DEFAULT_VOLUME", ""))
    svm_name = event.get("svm_name", os.environ.get("DEFAULT_SVM", ""))
    reason = event.get("reason", "automated-remediation")
    user = event.get("user", "unknown")

    # Correlation ID for audit trail
    request_id = getattr(context, "aws_request_id", "local")
    logger.info(
        "Remediation request: volume=%s svm=%s reason=%s user=%s request_id=%s",
        volume_name, svm_name, reason, user, request_id,
    )

    if not volume_name or not svm_name:
        logger.error("Missing required parameters: volume_name and svm_name")
        return {"statusCode": 400, "body": "volume_name and svm_name required"}

    # Get ONTAP credentials from Secrets Manager
    sm = boto3.client("secretsmanager")
    secret_arn = os.environ["ONTAP_CREDENTIALS_SECRET_ARN"]
    secret = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    username = secret["username"]
    password = secret["password"]
    mgmt_ip = os.environ["ONTAP_MGMT_IP"]

    # Authenticate to ONTAP REST API
    auth_header = urllib3.util.make_headers(basic_auth=f"{username}:{password}")
    base_headers = {**auth_header, "Accept": "application/json"}

    # Step 1: Find volume UUID
    vol_resp = http.request(
        "GET",
        f"https://{mgmt_ip}/api/storage/volumes"
        f"?name={volume_name}&svm.name={svm_name}&fields=uuid",
        headers=base_headers,
    )

    if vol_resp.status != 200:
        logger.error("Volume lookup failed: HTTP %d", vol_resp.status)
        return {"statusCode": 500, "body": f"Volume lookup failed: {vol_resp.status}"}

    volumes = json.loads(vol_resp.data).get("records", [])
    if not volumes:
        logger.error("Volume %s not found in SVM %s", volume_name, svm_name)
        return {
            "statusCode": 404,
            "body": f"Volume {volume_name} not found in SVM {svm_name}",
        }

    vol_uuid = volumes[0]["uuid"]

    # Step 2: Check cooldown (prevent Snapshot storm)
    should_skip, cooldown_reason = _check_cooldown(mgmt_ip, vol_uuid, base_headers)
    if should_skip:
        logger.info("Snapshot skipped: %s", cooldown_reason)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "skipped",
                "reason": cooldown_reason,
                "volume": volume_name,
                "svm": svm_name,
            }),
        }

    # Step 3: Create snapshot
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_reason = reason[:20].replace(" ", "_").replace("\\", "")
    snap_name = f"remediation_{timestamp}_{safe_reason}"

    logger.info("Creating snapshot: %s (cooldown check: %s)", snap_name, cooldown_reason)

    snap_body = json.dumps({
        "name": snap_name,
        "comment": (
            f"Auto-remediation: {reason} | user: {user} | "
            f"request_id: {request_id}"
        ),
    })

    snap_resp = http.request(
        "POST",
        f"https://{mgmt_ip}/api/storage/volumes/{vol_uuid}/snapshots",
        body=snap_body.encode(),
        headers={**base_headers, "Content-Type": "application/json"},
    )

    if snap_resp.status in (201, 202):
        logger.info("Snapshot created: %s on %s/%s", snap_name, svm_name, volume_name)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "snapshot_name": snap_name,
                "volume": volume_name,
                "svm": svm_name,
                "reason": reason,
                "user": user,
                "status": "created",
                "request_id": request_id,
            }),
        }

    error_msg = snap_resp.data.decode()[:200]
    logger.error("Snapshot failed: HTTP %d — %s", snap_resp.status, error_msg)
    return {"statusCode": 500, "body": f"Snapshot failed: {snap_resp.status}"}
