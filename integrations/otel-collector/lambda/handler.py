"""FSxN audit log shipper via OpenTelemetry Protocol (OTLP).

Vendor-neutral integration that ships logs to any OTLP-compatible backend.
Supports OTLP/HTTP (port 4318) for maximum compatibility.
"""

import gzip
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import boto3
import urllib3

# Configuration
OTLP_ENDPOINT = os.environ.get("OTLP_ENDPOINT", "http://localhost:4318")
OTLP_HEADERS = os.environ.get("OTLP_HEADERS", "")  # key=value,key2=value2
API_KEY_SECRET_ARN = os.environ.get("API_KEY_SECRET_ARN", "")
S3_ACCESS_POINT_ARN = os.environ["S3_ACCESS_POINT_ARN"]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "fsxn-ontap-audit")
RESOURCE_ATTRIBUTES = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")

MAX_BATCH_SIZE = 500
MAX_RETRIES = 3

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")
http = urllib3.PoolManager(num_pools=4, maxsize=10)

_auth_header_cache: dict[str, str] | None = None


def get_auth_headers() -> dict[str, str]:
    """Get authentication headers from Secrets Manager or env var."""
    global _auth_header_cache
    if _auth_header_cache is not None:
        return _auth_header_cache

    headers: dict[str, str] = {}

    # Parse OTLP_HEADERS env var (key=value,key2=value2)
    if OTLP_HEADERS:
        for pair in OTLP_HEADERS.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                headers[k.strip()] = v.strip()

    # If secret ARN is provided, add Authorization header
    if API_KEY_SECRET_ARN:
        response = secrets_client.get_secret_value(SecretId=API_KEY_SECRET_ARN)
        secret = response["SecretString"]
        try:
            parsed = json.loads(secret)
            # Support various key names
            token = parsed.get("api_key", parsed.get("token", parsed.get("bearer", secret)))
        except (json.JSONDecodeError, AttributeError):
            token = secret
        headers["Authorization"] = f"Bearer {token}"

    _auth_header_cache = headers
    return headers


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for OTLP log shipping."""
    logger.info("Processing event")

    auth_headers = get_auth_headers()
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

            otlp_payload = _build_otlp_logs_payload(logs, key)
            shipped = _ship_otlp(otlp_payload, auth_headers)
            total_shipped += shipped

        except Exception as e:
            logger.error("Failed to process %s/%s: %s", bucket, key, str(e))
            errors.append({"bucket": bucket, "key": key, "error": str(e)})

    return {
        "statusCode": 200 if not errors else 207,
        "body": {"total_logs": total_logs, "total_shipped": total_shipped, "errors": errors},
    }


def _extract_s3_records(event: dict[str, Any]) -> list[dict[str, str]]:
    """Extract S3 records from event."""
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


def _build_otlp_logs_payload(
    logs: list[dict[str, Any]], source_key: str
) -> dict[str, Any]:
    """Build OTLP Logs Export request payload (JSON encoding).

    Follows the OpenTelemetry Log Data Model:
    https://opentelemetry.io/docs/specs/otel/logs/data-model/
    """
    # Resource attributes
    resource_attrs = [
        {"key": "service.name", "value": {"stringValue": SERVICE_NAME}},
        {"key": "service.namespace", "value": {"stringValue": "fsxn-observability"}},
        {"key": "cloud.provider", "value": {"stringValue": "aws"}},
        {"key": "cloud.platform", "value": {"stringValue": "aws_fsx"}},
    ]

    # Parse additional resource attributes from env
    if RESOURCE_ATTRIBUTES:
        for pair in RESOURCE_ATTRIBUTES.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                resource_attrs.append(
                    {"key": k.strip(), "value": {"stringValue": v.strip()}}
                )

    # Build log records
    log_records = []
    for log in logs:
        timestamp = log.get("timestamp", log.get("Timestamp", ""))
        time_unix_nano = _iso_to_unix_nano(timestamp) if timestamp else _now_unix_nano()

        body_str = log.get("message", json.dumps(log, default=str))

        attributes = [
            {"key": "event.type", "value": {"stringValue": log.get("EventID", log.get("event_type", "unknown"))}},
            {"key": "user.name", "value": {"stringValue": log.get("UserName", log.get("user", ""))}},
            {"key": "client.address", "value": {"stringValue": log.get("ClientIP", log.get("client_ip", ""))}},
            {"key": "fsxn.operation", "value": {"stringValue": log.get("Operation", log.get("operation", ""))}},
            {"key": "fsxn.path", "value": {"stringValue": log.get("ObjectName", log.get("path", ""))}},
            {"key": "fsxn.result", "value": {"stringValue": log.get("Result", log.get("result", ""))}},
            {"key": "fsxn.svm", "value": {"stringValue": log.get("SVMName", log.get("svm", ""))}},
            {"key": "s3.key", "value": {"stringValue": source_key}},
        ]
        # Remove empty attributes
        attributes = [a for a in attributes if a["value"]["stringValue"]]

        record: dict[str, Any] = {
            "timeUnixNano": str(time_unix_nano),
            "body": {"stringValue": body_str},
            "attributes": attributes,
            "severityNumber": 9,  # INFO
            "severityText": "INFO",
        }

        # Set severity based on result
        result = log.get("Result", log.get("result", "")).lower()
        if "fail" in result or "denied" in result or "error" in result:
            record["severityNumber"] = 13  # WARN
            record["severityText"] = "WARN"

        log_records.append(record)

    return {
        "resourceLogs": [
            {
                "resource": {"attributes": resource_attrs},
                "scopeLogs": [
                    {
                        "scope": {"name": "fsxn-observability", "version": "0.1.0"},
                        "logRecords": log_records,
                    }
                ],
            }
        ]
    }


def _ship_otlp(payload: dict[str, Any], auth_headers: dict[str, str]) -> int:
    """Ship OTLP payload to collector endpoint."""
    log_records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    if not log_records:
        return 0

    shipped = 0
    # Batch if needed
    for i in range(0, len(log_records), MAX_BATCH_SIZE):
        batch_records = log_records[i : i + MAX_BATCH_SIZE]
        batch_payload = {
            "resourceLogs": [
                {
                    "resource": payload["resourceLogs"][0]["resource"],
                    "scopeLogs": [
                        {
                            "scope": payload["resourceLogs"][0]["scopeLogs"][0]["scope"],
                            "logRecords": batch_records,
                        }
                    ],
                }
            ]
        }
        if _send_otlp_batch(batch_payload, auth_headers):
            shipped += len(batch_records)

    return shipped


def _send_otlp_batch(payload: dict[str, Any], auth_headers: dict[str, str]) -> bool:
    """Send OTLP batch with retry."""
    body = gzip.compress(json.dumps(payload).encode("utf-8"))

    headers = {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
    }
    headers.update(auth_headers)

    url = f"{OTLP_ENDPOINT.rstrip('/')}/v1/logs"

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST", url, body=body, headers=headers, timeout=30.0
            )
            if response.status == 200:
                return True
            if response.status == 429 or response.status >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            logger.error("OTLP error %d: %s", response.status,
                         response.data.decode("utf-8", errors="replace")[:300])
            return False
        except urllib3.exceptions.HTTPError as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                logger.error("HTTP error: %s", str(e))

    return False


def _iso_to_unix_nano(timestamp: str) -> int:
    """Convert ISO timestamp to Unix nanoseconds."""
    try:
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        dt = datetime.fromisoformat(timestamp)
        return int(dt.timestamp() * 1_000_000_000)
    except (ValueError, AttributeError):
        return _now_unix_nano()


def _now_unix_nano() -> int:
    """Get current time in Unix nanoseconds."""
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
