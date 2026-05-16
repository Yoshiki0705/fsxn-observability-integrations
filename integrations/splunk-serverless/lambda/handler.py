"""FSxN audit log shipper for Splunk via HTTP Event Collector (HEC).

Serverless alternative to the EC2-based syslog-ng + Universal Forwarder pattern.
Ships audit logs directly to Splunk HEC endpoint from Lambda.
"""

import gzip
import json
import logging
import os
import time
from typing import Any

import boto3
import urllib3

# Configuration
HEC_ENDPOINT = os.environ.get("SPLUNK_HEC_ENDPOINT", "")
API_KEY_SECRET_ARN = os.environ["API_KEY_SECRET_ARN"]
S3_ACCESS_POINT_ARN = os.environ["S3_ACCESS_POINT_ARN"]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
SPLUNK_INDEX = os.environ.get("SPLUNK_INDEX", "fsxn_audit")
SPLUNK_SOURCETYPE = os.environ.get("SPLUNK_SOURCETYPE", "fsxn:ontap:audit")
SPLUNK_SOURCE = os.environ.get("SPLUNK_SOURCE", "fsxn-observability")

# HEC has no hard batch size limit, but recommended chunking for reliability
MAX_BATCH_EVENTS = 500
MAX_RETRIES = 3

# Disable SSL verification for self-signed certs (common in Splunk deployments)
VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() == "true"

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")
http = urllib3.PoolManager(
    num_pools=4,
    maxsize=10,
    cert_reqs="CERT_REQUIRED" if VERIFY_SSL else "CERT_NONE",
)

_hec_token_cache: str | None = None


def get_hec_token() -> str:
    """Retrieve Splunk HEC token from Secrets Manager."""
    global _hec_token_cache
    if _hec_token_cache is None:
        response = secrets_client.get_secret_value(SecretId=API_KEY_SECRET_ARN)
        secret = response["SecretString"]
        try:
            parsed = json.loads(secret)
            _hec_token_cache = parsed.get(
                "hec_token", parsed.get("SPLUNK_HEC_TOKEN", secret)
            )
        except (json.JSONDecodeError, AttributeError):
            _hec_token_cache = secret
    return _hec_token_cache


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for FSxN audit log shipping to Splunk HEC."""
    logger.info("Processing event")

    hec_token = get_hec_token()
    records = _extract_s3_records(event)

    total_logs = 0
    total_shipped = 0
    errors = []

    for record in records:
        bucket = record["bucket"]
        key = record["key"]

        try:
            data = s3_client.get_object(Bucket=S3_ACCESS_POINT_ARN, Key=key)
            raw = data["Body"].read()

            logs = _parse_logs(raw, key)
            total_logs += len(logs)

            hec_events = _format_for_splunk(logs, key)
            shipped = _ship_to_splunk(hec_events, hec_token)
            total_shipped += shipped

        except Exception as e:
            logger.error("Failed to process %s/%s: %s", bucket, key, str(e))
            errors.append({"bucket": bucket, "key": key, "error": str(e)})

    return {
        "statusCode": 200 if not errors else 207,
        "body": {
            "total_logs": total_logs,
            "total_shipped": total_shipped,
            "errors": errors,
        },
    }


def _extract_s3_records(event: dict[str, Any]) -> list[dict[str, str]]:
    """Extract S3 bucket/key pairs from event."""
    records = []
    if "Records" in event:
        for r in event["Records"]:
            s3 = r.get("s3", {})
            records.append({
                "bucket": s3.get("bucket", {}).get("name", ""),
                "key": s3.get("object", {}).get("key", ""),
            })
    elif "detail" in event:
        d = event["detail"]
        records.append({
            "bucket": d.get("bucket", {}).get("name", ""),
            "key": d.get("object", {}).get("key", ""),
        })
    return [r for r in records if r["bucket"] and r["key"]]


def _parse_logs(data: bytes, key: str) -> list[dict[str, Any]]:
    """Parse audit logs."""
    if key.endswith(".gz"):
        data = gzip.decompress(data)
    text = data.decode("utf-8", errors="replace")

    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"message": line})
    return events


def _format_for_splunk(
    logs: list[dict[str, Any]], source_key: str
) -> list[dict[str, Any]]:
    """Format logs for Splunk HEC /services/collector/event endpoint.

    Each event is a JSON object with: time, host, source, sourcetype, index, event.
    """
    hec_events = []
    for log in logs:
        # Extract timestamp (Splunk expects epoch seconds)
        timestamp = log.get("timestamp", log.get("Timestamp", ""))
        epoch_time = _to_epoch(timestamp) if timestamp else None

        hec_event: dict[str, Any] = {
            "source": SPLUNK_SOURCE,
            "sourcetype": SPLUNK_SOURCETYPE,
            "index": SPLUNK_INDEX,
            "host": log.get("SVMName", log.get("svm", "fsxn-ontap")),
            "event": {
                "event_type": log.get("EventID", log.get("event_type", "unknown")),
                "user": log.get("UserName", log.get("user", "")),
                "client_ip": log.get("ClientIP", log.get("client_ip", "")),
                "operation": log.get("Operation", log.get("operation", "")),
                "path": log.get("ObjectName", log.get("path", "")),
                "result": log.get("Result", log.get("result", "")),
                "svm": log.get("SVMName", log.get("svm", "")),
                "s3_key": source_key,
                "raw": log,
            },
        }
        if epoch_time:
            hec_event["time"] = epoch_time

        hec_events.append(hec_event)

    return hec_events


def _to_epoch(timestamp: str) -> float | None:
    """Convert ISO timestamp to epoch seconds."""
    from datetime import datetime, timezone

    try:
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        dt = datetime.fromisoformat(timestamp)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return None


def _ship_to_splunk(events: list[dict[str, Any]], hec_token: str) -> int:
    """Ship events to Splunk HEC in batches."""
    if not events:
        return 0

    shipped = 0
    for i in range(0, len(events), MAX_BATCH_EVENTS):
        batch = events[i : i + MAX_BATCH_EVENTS]
        if _send_batch(batch, hec_token):
            shipped += len(batch)
        else:
            logger.error("Failed to ship batch of %d events", len(batch))

    return shipped


def _send_batch(batch: list[dict[str, Any]], hec_token: str) -> bool:
    """Send batch to Splunk HEC with retry.

    HEC accepts newline-delimited JSON events (not a JSON array).
    """
    # HEC format: one JSON object per line (not an array)
    payload = "\n".join(json.dumps(event) for event in batch)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Splunk {hec_token}",
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST",
                f"{HEC_ENDPOINT}/services/collector/event",
                body=payload.encode("utf-8"),
                headers=headers,
                timeout=30.0,
            )

            if response.status == 200:
                return True

            # Parse HEC response for error details
            try:
                resp_body = json.loads(response.data.decode("utf-8"))
                code = resp_body.get("code", -1)
            except (json.JSONDecodeError, UnicodeDecodeError):
                code = -1

            if response.status == 429 or response.status >= 500:
                wait = 2 ** (attempt + 1)
                logger.warning("Splunk HEC %d (code=%d), retry in %ds",
                               response.status, code, wait)
                time.sleep(wait)
                continue

            logger.error("Splunk HEC error %d (code=%d): %s",
                         response.status, code,
                         response.data.decode("utf-8", errors="replace")[:300])
            return False

        except urllib3.exceptions.HTTPError as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                logger.error("HTTP error: %s", str(e))

    return False
