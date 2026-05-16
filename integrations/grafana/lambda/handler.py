"""FSxN audit log shipper for Grafana Cloud (Loki Push API).

Ships audit logs to Grafana Cloud Loki using the /loki/api/v1/push endpoint.
Authentication via Basic Auth (Instance ID + API Key).
"""

import gzip
import json
import logging
import os
import time
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any

import boto3
import urllib3

# Configuration
LOKI_ENDPOINT = os.environ.get("LOKI_ENDPOINT", "")  # https://<instance>.grafana.net
API_KEY_SECRET_ARN = os.environ["API_KEY_SECRET_ARN"]
S3_ACCESS_POINT_ARN = os.environ["S3_ACCESS_POINT_ARN"]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOKI_TENANT_ID = os.environ.get("LOKI_TENANT_ID", "")

# Loki recommended max ~4MB per push request
MAX_BATCH_BYTES = 3 * 1024 * 1024  # 3MB to stay safe
MAX_RETRIES = 3

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")
http = urllib3.PoolManager(num_pools=4, maxsize=10)

_auth_header_cache: str | None = None


def get_auth_header() -> str:
    """Retrieve Grafana Cloud credentials and build Basic Auth header."""
    global _auth_header_cache
    if _auth_header_cache is None:
        response = secrets_client.get_secret_value(SecretId=API_KEY_SECRET_ARN)
        secret = response["SecretString"]
        try:
            parsed = json.loads(secret)
            instance_id = parsed.get("instance_id", parsed.get("user", ""))
            api_key = parsed.get("api_key", parsed.get("password", ""))
            credentials = f"{instance_id}:{api_key}"
        except (json.JSONDecodeError, AttributeError):
            credentials = secret  # Assume pre-formatted "user:pass"
        _auth_header_cache = f"Basic {b64encode(credentials.encode()).decode()}"
    return _auth_header_cache


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for Grafana Loki log shipping."""
    logger.info("Processing event")

    auth_header = get_auth_header()
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

            loki_streams = _format_for_loki(logs, key)
            shipped = _ship_to_loki(loki_streams, auth_header)
            total_shipped += shipped

        except Exception as e:
            logger.error("Failed to process %s/%s: %s", bucket, key, str(e))
            errors.append({"bucket": bucket, "key": key, "error": str(e)})

    return {
        "statusCode": 200 if not errors else 207,
        "body": {"total_logs": total_logs, "total_shipped": total_shipped, "errors": errors},
    }


def _extract_s3_records(event: dict[str, Any]) -> list[dict[str, str]]:
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


def _format_for_loki(
    logs: list[dict[str, Any]], source_key: str
) -> dict[str, Any]:
    """Format logs for Loki Push API.

    Loki expects streams with labels and arrays of [timestamp_ns, log_line] values.
    """
    # Group by SVM for separate streams
    streams_by_svm: dict[str, list[list[str]]] = {}

    for log in logs:
        svm = log.get("SVMName", log.get("svm", "unknown"))
        timestamp = log.get("timestamp", log.get("Timestamp", ""))
        ts_ns = _iso_to_ns(timestamp) if timestamp else str(int(time.time() * 1e9))

        log_line = json.dumps(log, default=str)

        if svm not in streams_by_svm:
            streams_by_svm[svm] = []
        streams_by_svm[svm].append([ts_ns, log_line])

    # Build Loki push payload
    streams = []
    for svm, values in streams_by_svm.items():
        # Sort by timestamp (Loki requires ordered entries)
        values.sort(key=lambda x: x[0])
        streams.append({
            "stream": {
                "job": "fsxn-audit",
                "source": "fsxn-ontap",
                "svm": svm,
                "s3_key": source_key,
            },
            "values": values,
        })

    return {"streams": streams}


def _ship_to_loki(payload: dict[str, Any], auth_header: str) -> int:
    """Ship logs to Loki Push API."""
    total_values = sum(len(s["values"]) for s in payload.get("streams", []))
    if total_values == 0:
        return 0

    if _send_loki_push(payload, auth_header):
        return total_values
    return 0


def _send_loki_push(payload: dict[str, Any], auth_header: str) -> bool:
    """Send push request to Loki with retry."""
    body = gzip.compress(json.dumps(payload).encode("utf-8"))

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Authorization": auth_header,
    }
    if LOKI_TENANT_ID:
        headers["X-Scope-OrgID"] = LOKI_TENANT_ID

    url = f"{LOKI_ENDPOINT.rstrip('/')}/loki/api/v1/push"

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST", url, body=body, headers=headers, timeout=30.0
            )
            if response.status == 204 or response.status == 200:
                return True
            if response.status == 429 or response.status >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            logger.error("Loki error %d: %s", response.status,
                         response.data.decode("utf-8", errors="replace")[:300])
            return False
        except urllib3.exceptions.HTTPError as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                logger.error("HTTP error: %s", str(e))

    return False


def _iso_to_ns(timestamp: str) -> str:
    """Convert ISO timestamp to nanosecond string for Loki."""
    try:
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        dt = datetime.fromisoformat(timestamp)
        return str(int(dt.timestamp() * 1e9))
    except (ValueError, AttributeError):
        return str(int(time.time() * 1e9))
