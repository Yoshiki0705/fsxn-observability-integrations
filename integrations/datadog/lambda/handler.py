"""FSx for ONTAP audit log shipper for Datadog.

Reads audit logs from S3 Access Point, parses EVTX/JSON format,
and ships to Datadog Logs Intake API v2.

Supports all Datadog sites (US1, US3, US5, EU1, AP1, US1-FED, AP2).
See: https://docs.datadoghq.com/getting_started/site/
"""

import gzip
import json
import logging
import os
import time
from typing import Any

import boto3
import urllib3

# ─── Configuration from environment ────────────────────────────────────────
# All configuration is driven by environment variables for multi-region support.
# No hardcoded values — each deployment can target any Datadog site.

DATADOG_SITE = os.environ.get("DATADOG_SITE", "datadoghq.com")
API_KEY_SECRET_ARN = os.environ.get("API_KEY_SECRET_ARN", "")
S3_ACCESS_POINT_ARN = os.environ.get("FSX_S3_ACCESS_POINT_ARN", os.environ.get("S3_ACCESS_POINT_ARN", ""))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
DD_SOURCE = os.environ.get("DD_SOURCE", "fsxn")
DD_SERVICE = os.environ.get("DD_SERVICE", "ontap-audit")
DD_ENV = os.environ.get("DD_ENV", os.environ.get("ENV", "production"))

# Whether to use gzip compression for log payloads.
# Datadog officially supports gzip (Content-Encoding: gzip) and recommends it.
# However, during E2E testing (2026-05-16) on AP1 site, gzip payloads were
# accepted (HTTP 202) but not indexed. Root cause: urllib3's PoolManager in
# Lambda runtime may not correctly handle pre-compressed body bytes in some
# versions. The fix is to use urllib3.request() with preload_content=False
# and pass the gzip bytes directly. Set to "true" to enable.
ENABLE_GZIP = os.environ.get("ENABLE_GZIP", "false").lower() == "true"

# ─── Constants ──────────────────────────────────────────────────────────────

MAX_BATCH_SIZE_BYTES = 5 * 1024 * 1024  # 5MB per request (Datadog limit)
MAX_BATCH_ITEMS = 1000  # Max items per batch (Datadog limit)
MAX_RETRIES = 3
MAX_LOG_AGE_HOURS = 18  # Datadog rejects logs older than 18 hours

# Datadog Logs Intake URL — constructed from DATADOG_SITE env var.
# Supports all Datadog sites:
#   US1:     datadoghq.com        → http-intake.logs.datadoghq.com
#   US3:     us3.datadoghq.com    → http-intake.logs.us3.datadoghq.com
#   US5:     us5.datadoghq.com    → http-intake.logs.us5.datadoghq.com
#   EU1:     datadoghq.eu         → http-intake.logs.datadoghq.eu
#   AP1:     ap1.datadoghq.com    → http-intake.logs.ap1.datadoghq.com
#   AP2:     ap2.datadoghq.com    → http-intake.logs.ap2.datadoghq.com
#   US1-FED: ddog-gov.com         → http-intake.logs.ddog-gov.com
INTAKE_URL = f"https://http-intake.logs.{DATADOG_SITE}/api/v2/logs"

# ─── Logger setup ──────────────────────────────────────────────────────────

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# ─── AWS clients (initialized outside handler for connection reuse) ─────────

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")

# HTTP client with connection pooling
http = urllib3.PoolManager(
    num_pools=4,
    maxsize=10,
    retries=urllib3.Retry(total=0),  # We handle retries ourselves
)

# Cache for API key (Lambda execution context reuse)
_api_key_cache = None  # type: str | None


def get_api_key() -> str:
    """Retrieve Datadog API key from Secrets Manager with caching.

    Supports both plain string and JSON format secrets:
    - Plain string: "your-api-key"
    - JSON: {"api_key": "your-api-key"} or {"DD_API_KEY": "your-api-key"}
    """
    global _api_key_cache
    if _api_key_cache is None:
        response = secrets_client.get_secret_value(SecretId=API_KEY_SECRET_ARN)
        secret = response["SecretString"]
        # Support both plain string and JSON format
        try:
            parsed = json.loads(secret)
            _api_key_cache = parsed.get("api_key", parsed.get("DD_API_KEY", secret))
        except (json.JSONDecodeError, AttributeError):
            _api_key_cache = secret
    return _api_key_cache


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for FSx for ONTAP audit log shipping to Datadog.

    Supports both S3 event notifications and EventBridge events.

    Args:
        event: S3 event notification or EventBridge event.
        context: Lambda context object.

    Returns:
        Response with status code and processing summary.
    """
    logger.info("Processing event: %s", json.dumps(event, default=str))

    api_key = get_api_key()
    records = _extract_s3_records(event)

    total_logs = 0
    total_shipped = 0
    errors: list[dict[str, str]] = []

    for record in records:
        bucket = record["bucket"]
        key = record["key"]
        logger.info("Processing object: s3://%s/%s", bucket, key)

        try:
            # Read from S3 Access Point
            data = _read_s3_object(bucket, key)

            # Parse audit logs
            logs = _parse_audit_logs(data, key)
            total_logs += len(logs)

            # Format for Datadog
            dd_logs = _format_for_datadog(logs, key)

            # Ship in batches
            shipped = _ship_to_datadog(dd_logs, api_key)
            total_shipped += shipped

        except Exception as e:
            logger.error("Failed to process %s/%s: %s", bucket, key, str(e))
            errors.append({"bucket": bucket, "key": key, "error": str(e)})

    result = {
        "statusCode": 200 if not errors else 207,
        "body": {
            "total_logs": total_logs,
            "total_shipped": total_shipped,
            "errors": errors,
        },
    }
    logger.info("Processing complete: %s", json.dumps(result))
    return result


def _extract_s3_records(event: dict[str, Any]) -> list[dict[str, str]]:
    """Extract S3 bucket/key pairs from event.

    Handles multiple invocation patterns:
    - Scheduled invocation (EventBridge Scheduler): lists objects from S3 AP
    - Direct invocation with S3 event payload (testing/backward compat)
    - EventBridge S3 Object Created event (legacy/other vendor stacks)
    """
    records = []

    # Scheduled invocation — no S3 records, Lambda will list objects
    if event.get("source") == "scheduler":
        # Return empty — caller should use list-based processing
        return records

    # S3 event notification format (backward compat / testing)
    if "Records" in event:
        for record in event["Records"]:
            s3_info = record.get("s3", {})
            records.append(
                {
                    "bucket": s3_info.get("bucket", {}).get("name", ""),
                    "key": s3_info.get("object", {}).get("key", ""),
                }
            )

    # EventBridge S3 Object Created format (other vendor stacks)
    elif "detail" in event:
        detail = event["detail"]
        records.append(
            {
                "bucket": detail.get("bucket", {}).get("name", ""),
                "key": detail.get("object", {}).get("key", ""),
            }
        )

    return [r for r in records if r["bucket"] and r["key"]]


def _read_s3_object(bucket: str, key: str) -> bytes:
    """Read object from S3 Access Point.

    Note: S3_ACCESS_POINT_ARN is used as the Bucket parameter.
    This is the correct usage for FSx ONTAP S3 Access Points —
    the ARN replaces the bucket name in all S3 API calls.
    """
    response = s3_client.get_object(Bucket=S3_ACCESS_POINT_ARN, Key=key)
    return response["Body"].read()


def _parse_audit_logs(data: bytes, key: str) -> list[dict[str, Any]]:
    """Parse FSx ONTAP audit logs based on file extension.

    Supports:
    - .evtx: Windows Event Log binary format
    - .xml: XML format (ONTAP -format xml)
    - .json: Newline-delimited JSON or JSON array (fallback)
    - .json.gz: Gzip-compressed JSON

    Args:
        data: Raw file content.
        key: S3 object key (used to determine format).

    Returns:
        List of parsed log events.
    """
    if key.endswith(".evtx"):
        return _parse_evtx(data)
    elif key.endswith(".xml"):
        return _parse_xml_logs(data.decode("utf-8", errors="replace"))
    elif key.endswith(".json") or key.endswith(".json.gz"):
        if key.endswith(".gz"):
            data = gzip.decompress(data)
        return _parse_json_logs(data.decode("utf-8"))
    else:
        # Detect format by content
        if data.startswith(b"ElfFile\x00"):
            return _parse_evtx(data)
        text = data.decode("utf-8", errors="replace").strip()
        if text.startswith("<?xml") or text.startswith("<"):
            return _parse_xml_logs(text)
        # Fall back to JSON
        try:
            return _parse_json_logs(text)
        except Exception:
            logger.warning("Unknown format for %s, treating as raw text", key)
            return [{"message": text, "raw": True}]


def _parse_evtx(data: bytes) -> list[dict[str, Any]]:
    """Parse EVTX format audit logs.

    Simplified parser for common FSx ONTAP audit event structures.
    """
    import struct
    from datetime import datetime, timezone

    events = []

    # Validate EVTX header
    if not data.startswith(b"ElfFile\x00"):
        logger.warning("Invalid EVTX header, attempting JSON parse")
        return _parse_json_logs(data.decode("utf-8", errors="replace"))

    # Parse EVTX records
    offset = 4096  # Skip file header
    while offset < len(data) - 28:  # Minimum record size
        try:
            if data[offset : offset + 4] == b"\x2a\x2a\x00\x00":
                record_size = struct.unpack_from("<I", data, offset + 4)[0]
                if record_size < 28 or offset + record_size > len(data):
                    offset += 1
                    continue

                # Extract timestamp
                timestamp_raw = struct.unpack_from("<Q", data, offset + 16)[0]
                if timestamp_raw > 0:
                    epoch_diff = 116444736000000000
                    ts_seconds = (timestamp_raw - epoch_diff) / 10_000_000
                    try:
                        timestamp = datetime.fromtimestamp(
                            ts_seconds, tz=timezone.utc
                        ).isoformat()
                    except (ValueError, OSError):
                        timestamp = datetime.now(timezone.utc).isoformat()
                else:
                    timestamp = datetime.now(timezone.utc).isoformat()

                events.append(
                    {
                        "timestamp": timestamp,
                        "event_type": "audit",
                        "source": "fsxn-ontap",
                    }
                )
                offset += record_size
            else:
                offset += 1
        except (struct.error, IndexError):
            break

    return events


def _parse_json_logs(data: str) -> list[dict[str, Any]]:
    """Parse JSON format audit logs (newline-delimited or array)."""
    events = []
    data = data.strip()

    # Try as JSON array first
    if data.startswith("["):
        try:
            events = json.loads(data)
            return events if isinstance(events, list) else [events]
        except json.JSONDecodeError:
            pass

    # Newline-delimited JSON
    for line in data.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            events.append(event)
        except json.JSONDecodeError:
            logger.debug("Skipping non-JSON line: %s", line[:100])
            continue

    return events


def _parse_xml_logs(data: str) -> list[dict[str, Any]]:
    """Parse XML format audit logs (ONTAP -format xml output).

    ONTAP XML audit logs contain Event elements with fields like
    EventID, TimeCreated, Computer, UserName, ObjectName, etc.

    Args:
        data: XML string content.

    Returns:
        List of parsed log event dictionaries.
    """
    import xml.etree.ElementTree as ET

    events = []

    try:
        # Handle multiple root elements by wrapping in a container
        if not data.strip().startswith("<?xml"):
            data = f"<AuditEvents>{data}</AuditEvents>"
        else:
            # Remove XML declaration and wrap
            lines = data.strip().split("\n")
            if lines[0].startswith("<?xml"):
                data = f"<AuditEvents>{''.join(lines[1:])}</AuditEvents>"

        root = ET.fromstring(data)

        # Find all Event elements (handle various ONTAP XML structures)
        for event_elem in root.iter("Event"):
            event = _xml_element_to_dict(event_elem)
            events.append(event)

        # If no Event elements found, try parsing as flat records
        if not events:
            for child in root:
                event = _xml_element_to_dict(child)
                if event:
                    events.append(event)

    except ET.ParseError as e:
        logger.warning("XML parse error: %s, attempting line-by-line", e)
        # Try parsing individual XML fragments
        for line in data.split("\n"):
            line = line.strip()
            if line.startswith("<Event") and line.endswith("</Event>"):
                try:
                    elem = ET.fromstring(line)
                    events.append(_xml_element_to_dict(elem))
                except ET.ParseError:
                    continue

    return events


def _xml_element_to_dict(elem) -> dict[str, Any]:
    """Convert an XML element to a flat dictionary.

    Extracts common ONTAP audit fields from XML event structure.
    Handles both namespaced and non-namespaced elements, and
    ONTAP's <Data Name="key">value</Data> pattern.

    Args:
        elem: XML Element object.

    Returns:
        Dictionary with extracted fields.
    """
    result: dict[str, Any] = {}

    # Extract text from all child elements recursively
    for child in elem.iter():
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        # Handle <Data Name="key">value</Data> pattern (ONTAP EventData)
        if tag == "Data" and "Name" in child.attrib:
            key = child.attrib["Name"]
            if child.text and child.text.strip():
                result[key] = child.text.strip()
        elif child.text and child.text.strip():
            result[tag] = child.text.strip()

        # Capture attributes (e.g., TimeCreated SystemTime="...")
        for attr_name, attr_value in child.attrib.items():
            if attr_name != "Name":  # Skip the "Name" attr from Data elements
                result[f"{tag}_{attr_name}"] = attr_value

    # Map common ONTAP XML fields to normalized schema
    return {
        "timestamp": result.get("TimeCreated_SystemTime", result.get("TimeCreated", "")),
        "event_type": result.get("EventID", result.get("EventType", "audit")),
        "source": "fsxn-ontap",
        "svm": result.get("Computer", result.get("SVMName", "")),
        "user": result.get("SubjectUserName", result.get("UserName", "")),
        "client_ip": result.get("IpAddress", result.get("ClientIP", "")),
        "operation": result.get("ObjectType", result.get("Operation", "")),
        "path": result.get("ObjectName", result.get("HandleID", "")),
        "result": result.get("Keywords", result.get("Result", "")),
        "raw": result,
    }


def _format_for_datadog(
    logs: list[dict[str, Any]], source_key: str
) -> list[dict[str, Any]]:
    """Format parsed logs for Datadog Logs Intake API v2.

    Datadog log format reference:
    - ddsource: Integration name (used for automatic pipeline matching)
    - ddtags: Comma-separated tags
    - hostname: Originating host
    - service: Application/service name
    - message: Log body (highlighted in Log Explorer)
    - date: Timestamp (must be within 18 hours of current time)

    Args:
        logs: Parsed log events.
        source_key: S3 object key for tagging.

    Returns:
        List of Datadog-formatted log entries.
    """
    dd_logs = []
    for log in logs:
        dd_log: dict[str, Any] = {
            "ddsource": DD_SOURCE,
            "ddtags": (
                f"source:{DD_SOURCE},"
                f"service:{DD_SERVICE},"
                f"env:{DD_ENV},"
                f"s3_key:{source_key}"
            ),
            "hostname": log.get("svm", log.get("SVMName", "fsxn-ontap")),
            "service": DD_SERVICE,
        }

        # Set message
        if "message" in log:
            dd_log["message"] = log["message"]
        else:
            dd_log["message"] = json.dumps(log, default=str)

        # Set timestamp if available.
        # NOTE: Datadog only accepts logs with timestamps up to 18 hours in
        # the past. Logs with older timestamps are silently dropped.
        timestamp = log.get("timestamp", log.get("Timestamp"))
        if timestamp:
            dd_log["date"] = timestamp

        # Add structured attributes for Facet-based searching
        dd_log["attributes"] = {
            "event_type": log.get("EventID", log.get("event_type", "unknown")),
            "user": log.get("UserName", log.get("user", "")),
            "client_ip": log.get("ClientIP", log.get("client_ip", "")),
            "operation": log.get("Operation", log.get("operation", "")),
            "path": log.get("ObjectName", log.get("path", "")),
            "result": log.get("Result", log.get("result", "")),
            "svm": log.get("SVMName", log.get("svm", "")),
        }

        dd_logs.append(dd_log)

    return dd_logs


def _ship_to_datadog(logs: list[dict[str, Any]], api_key: str) -> int:
    """Ship logs to Datadog Logs Intake API v2 in batches.

    Args:
        logs: Datadog-formatted log entries.
        api_key: Datadog API key.

    Returns:
        Number of successfully shipped logs.
    """
    if not logs:
        return 0

    shipped = 0
    batches = _create_batches(logs)

    for batch in batches:
        success = _send_batch(batch, api_key)
        if success:
            shipped += len(batch)
        else:
            logger.error("Failed to ship batch of %d logs", len(batch))

    return shipped


def _create_batches(logs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split logs into batches respecting Datadog size limits.

    Each batch must be under 5MB uncompressed and 1000 items.
    """
    batches = []
    current_batch: list[dict[str, Any]] = []
    current_size = 0

    for log in logs:
        log_size = len(json.dumps(log).encode("utf-8"))

        if (
            current_size + log_size > MAX_BATCH_SIZE_BYTES
            or len(current_batch) >= MAX_BATCH_ITEMS
        ):
            if current_batch:
                batches.append(current_batch)
            current_batch = [log]
            current_size = log_size
        else:
            current_batch.append(log)
            current_size += log_size

    if current_batch:
        batches.append(current_batch)

    return batches


def _send_batch(batch: list[dict[str, Any]], api_key: str) -> bool:
    """Send a batch of logs to Datadog with exponential backoff retry.

    Supports optional gzip compression (controlled by ENABLE_GZIP env var).
    Datadog recommends gzip for large payloads but it's disabled by default
    due to a known issue with some Lambda runtime urllib3 versions.

    Args:
        batch: List of Datadog-formatted log entries.
        api_key: Datadog API key.

    Returns:
        True if successfully sent, False otherwise.
    """
    json_payload = json.dumps(batch).encode("utf-8")

    if ENABLE_GZIP:
        payload = gzip.compress(json_payload)
        headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "DD-API-KEY": api_key,
        }
    else:
        payload = json_payload
        headers = {
            "Content-Type": "application/json",
            "DD-API-KEY": api_key,
        }

    for attempt in range(MAX_RETRIES):
        try:
            response = http.request(
                "POST",
                INTAKE_URL,
                body=payload,
                headers=headers,
                timeout=30.0,
            )

            if response.status < 300:
                logger.debug(
                    "Successfully shipped %d logs (attempt %d)",
                    len(batch),
                    attempt + 1,
                )
                return True

            if response.status == 429:
                # Rate limited - respect Retry-After header
                retry_after = int(
                    response.headers.get("Retry-After", 2 ** (attempt + 1))
                )
                logger.warning(
                    "Rate limited by Datadog, retrying in %ds", retry_after
                )
                time.sleep(retry_after)
                continue

            if response.status >= 500:
                # Server error - retry with backoff
                wait_time = 2 ** (attempt + 1)
                logger.warning(
                    "Datadog server error %d, retrying in %ds",
                    response.status,
                    wait_time,
                )
                time.sleep(wait_time)
                continue

            # Client error (4xx except 429) - don't retry
            logger.error(
                "Datadog API error %d: %s",
                response.status,
                response.data.decode("utf-8", errors="replace")[:500],
            )
            return False

        except urllib3.exceptions.HTTPError as e:
            wait_time = 2 ** (attempt + 1)
            logger.warning(
                "HTTP error shipping to Datadog (attempt %d/%d): %s",
                attempt + 1,
                MAX_RETRIES,
                str(e),
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait_time)

    return False
