"""FPolicy → OTel Collector OTLP log forwarder.

Subscribes to EventBridge custom bus events (source: fpolicy.fsxn),
formats FPolicy file operation events into OTLP Log Data Model,
and forwards to the configured OTel Collector endpoint.

Architecture: ONTAP → TCP:9898 → ECS Fargate → SQS → EventBridge → This Lambda → OTel Collector
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Optional

import urllib3

# ─── Configuration ─────────────────────────────────────────────────────────

OTLP_ENDPOINT = os.environ.get("OTLP_ENDPOINT", "http://localhost:4318")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "fsxn-fpolicy")

# ─── Constants ──────────────────────────────────────────────────────────────

MAX_RETRIES = 3
BASE_INTERVAL = 2

# FPolicy field mapping to OTLP attributes
FPOLICY_FIELD_MAPPING = {
    "operation": "operation",
    "file_path": "file_path",
    "user": "user",
    "client_ip": "client_ip",
}

# ─── Logger ────────────────────────────────────────────────────────────────

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# HTTP client
http = urllib3.PoolManager(
    num_pools=4,
    maxsize=10,
    retries=urllib3.Retry(total=0),
)


# ─── OTLP payload construction ────────────────────────────────────────────


def _timestamp_to_unix_nano(timestamp: Optional[str]) -> str:
    """Convert ISO 8601 timestamp to Unix nanoseconds string.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        Unix nanoseconds as string. Falls back to current time.
    """
    if not timestamp:
        return str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))

    try:
        ts = timestamp.strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp() * 1_000_000_000))
    except (ValueError, AttributeError):
        return str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))


def build_fpolicy_otlp_payload(event_detail: dict[str, Any]) -> dict[str, Any]:
    """Build OTLP Log Data Model payload from a FPolicy event.

    Args:
        event_detail: EventBridge event detail dict with FPolicy fields.

    Returns:
        OTLP payload dict with resourceLogs structure.
    """
    timestamp = event_detail.get("timestamp", event_detail.get("time", ""))
    time_unix_nano = _timestamp_to_unix_nano(timestamp)

    # Build attributes from FPolicy fields
    attributes: list[dict[str, Any]] = []
    for source_field, otlp_key in FPOLICY_FIELD_MAPPING.items():
        value = event_detail.get(source_field)
        if value is not None and str(value) != "":
            attributes.append({
                "key": otlp_key,
                "value": {"stringValue": str(value)},
            })

    # Add any additional fields as attributes
    for key in ("volume", "svm", "protocol", "event_id"):
        value = event_detail.get(key)
        if value is not None and str(value) != "":
            attributes.append({
                "key": key,
                "value": {"stringValue": str(value)},
            })

    # Determine severity (file operations are INFO by default)
    severity_number = 9
    severity_text = "INFO"

    # Build logRecord
    log_record: dict[str, Any] = {
        "timeUnixNano": time_unix_nano,
        "severityNumber": severity_number,
        "severityText": severity_text,
        "body": {
            "stringValue": json.dumps(event_detail, default=str),
        },
        "attributes": attributes,
    }

    # Build full OTLP payload
    payload: dict[str, Any] = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": SERVICE_NAME}},
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {
                            "name": "fsxn-fpolicy-shipper",
                            "version": "1.0.0",
                        },
                        "logRecords": [log_record],
                    }
                ],
            }
        ]
    }

    return payload


# ─── OTLP delivery ────────────────────────────────────────────────────────


def _send_otlp_payload(payload: dict[str, Any]) -> bool:
    """Send OTLP payload to the configured endpoint with retry.

    Args:
        payload: OTLP JSON payload dict.

    Returns:
        True if successfully sent, False otherwise.
    """
    url = f"{OTLP_ENDPOINT}/v1/logs"
    headers = {"Content-Type": "application/json"}
    json_body = json.dumps(payload).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST",
                url,
                body=json_body,
                headers=headers,
                timeout=30.0,
            )

            if response.status < 300:
                logger.debug("FPolicy OTLP payload sent successfully (attempt %d)", attempt + 1)
                return True

            if response.status == 429:
                retry_after = int(
                    response.headers.get("Retry-After", BASE_INTERVAL * (2 ** attempt))
                )
                logger.warning("OTLP rate limited, retrying in %ds", retry_after)
                time.sleep(retry_after)
                continue

            if response.status >= 500:
                wait_time = BASE_INTERVAL * (2 ** attempt) + random.uniform(0, 1)
                logger.warning("OTLP server error %d, retrying in %.1fs", response.status, wait_time)
                time.sleep(wait_time)
                continue

            logger.error("OTLP error %d: %s", response.status,
                         response.data.decode("utf-8", errors="replace")[:500])
            return False

        except urllib3.exceptions.HTTPError as e:
            wait_time = BASE_INTERVAL * (2 ** attempt) + random.uniform(0, 1)
            logger.warning("HTTP error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, str(e))
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)

    return False


# ─── Lambda handler ────────────────────────────────────────────────────────


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle FPolicy event from EventBridge custom bus.

    Expects EventBridge events with source "fpolicy.fsxn" containing
    file operation details in the "detail" field.

    Args:
        event: EventBridge event with FPolicy file operation details.
        context: Lambda context object.

    Returns:
        Response dict with statusCode and processing summary.
    """
    logger.info("FPolicy event received: %s", json.dumps(event, default=str)[:500])

    try:
        # Extract event detail (EventBridge format)
        detail = event.get("detail", event)

        # Validate minimum required fields
        operation = detail.get("operation", "unknown")
        file_path = detail.get("file_path", "unknown")

        logger.info(
            "FPolicy event: operation=%s file_path=%s user=%s client_ip=%s",
            operation,
            file_path,
            detail.get("user", "unknown"),
            detail.get("client_ip", "unknown"),
        )

        # Build OTLP payload
        payload = build_fpolicy_otlp_payload(detail)

        # Forward to OTel Collector
        success = _send_otlp_payload(payload)

        if success:
            return {
                "statusCode": 200,
                "body": {
                    "status": "ok",
                    "operation": operation,
                    "file_path": file_path,
                    "otlp_delivered": True,
                },
            }
        else:
            return {
                "statusCode": 502,
                "body": {
                    "status": "error",
                    "message": "OTLP delivery failed after retries",
                    "operation": operation,
                    "file_path": file_path,
                },
            }

    except Exception as e:
        logger.error("Unexpected error processing FPolicy event: %s", str(e))
        return {
            "statusCode": 500,
            "body": {"status": "error", "message": str(e)},
        }
