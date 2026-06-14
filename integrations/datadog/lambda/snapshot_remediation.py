"""Auto-remediation Lambda — Creates ONTAP Snapshot for evidence preservation.

Triggered by Datadog Workflow when mass file deletion is confirmed by SOC analyst.
Creates a timestamped snapshot with audit metadata for forensic investigation.

Environment Variables:
    ONTAP_MGMT_IP: FSx for ONTAP management endpoint IP
    ONTAP_CREDENTIALS_SECRET_ARN: Secrets Manager ARN for ONTAP admin credentials
    DEFAULT_VOLUME: Default volume name (if not provided in event)
    DEFAULT_SVM: Default SVM name (if not provided in event)
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

http = urllib3.PoolManager(cert_reqs="CERT_NONE")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Create protective snapshot on ONTAP volume.

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

    # Generate descriptive snapshot name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_reason = reason[:20].replace(" ", "_").replace("\\", "")
    snap_name = f"remediation_{timestamp}_{safe_reason}"

    logger.info(
        "Creating snapshot: %s on %s/%s (reason: %s, user: %s)",
        snap_name, svm_name, volume_name, reason, user,
    )

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

    # Step 2: Create snapshot
    snap_body = json.dumps({
        "name": snap_name,
        "comment": f"Auto-remediation: {reason} (user: {user})",
    })

    snap_resp = http.request(
        "POST",
        f"https://{mgmt_ip}/api/storage/volumes/{vol_uuid}/snapshots",
        body=snap_body.encode(),
        headers={**base_headers, "Content-Type": "application/json"},
    )

    if snap_resp.status in (201, 202):
        logger.info("Snapshot created successfully: %s", snap_name)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "snapshot_name": snap_name,
                "volume": volume_name,
                "svm": svm_name,
                "reason": reason,
                "user": user,
                "status": "created",
            }),
        }

    error_msg = snap_resp.data.decode()[:200]
    logger.error("Snapshot creation failed: HTTP %d — %s", snap_resp.status, error_msg)
    return {"statusCode": 500, "body": f"Snapshot failed: {snap_resp.status}"}
