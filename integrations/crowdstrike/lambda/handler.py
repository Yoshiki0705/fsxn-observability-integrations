"""FSx for ONTAP audit log shipper for CrowdStrike Falcon LogScale.

Ships audit logs to LogScale via HEC (HTTP Event Collector) compatible endpoint.
LogScale supports Splunk HEC format natively at /api/v1/ingest/hec.

Reference: https://library.humio.com/logscale-api/log-shippers-hec.html
"""

import gzip
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any

import boto3
import urllib3

# ─── Configuration ──────────────────────────────────────────────────────────

LOGSCALE_URL = os.environ.get("LOGSCALE_URL", "https://cloud.us.humio.com")
INGEST_TOKEN_SECRET_ARN = os.environ.get("INGEST_TOKEN_SECRET_ARN", "")
S3_ACCESS_POINT_ARN = os.environ.get("S3_ACCESS_POINT_ARN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
SOURCE = os.environ.get("SOURCE", "fsxn-ontap")
SOURCETYPE = os.environ.get("SOURCETYPE", "fsxn:audit")
INDEX = os.environ.get("INDEX", "fsxn_audit")
HEC_PATH = "/api/v1/ingest/hec"

MAX_BATCH_SIZE_BYTES = 5 * 1024 * 1024
MAX_RETRIES = 3

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")
http = urllib3.PoolManager(num_pools=4, maxsize=10, retries=urllib3.Retry(total=0))

_token_cache = None


def get_ingest_token() -> str:
    """Retrieve LogScale ingest token from Secrets Manager."""
    global _token_cache
    if _token_cache is None:
        response = secrets_client.get_secret_value(SecretId=INGEST_TOKEN_SECRET_ARN)
        secret = response["SecretString"]
        try:
            parsed = json.loads(secret)
            _token_cache = parsed.get("ingest_token", parsed.get("token", secret))
        except (json.JSONDecodeError, AttributeError):
            _token_cache = secret
    return _token_cache


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for shipping audit logs to CrowdStrike LogScale."""
    logger.info("Processing event: %s", json.dumps(event, default=str))

    token = get_ingest_token()
    records = _extract_s3_records(event)

    total_logs = 0
    total_shipped = 0
    errors: list[dict[str, str]] = []

    for record in records:
        bucket = record["bucket"]
        key = record["key"]
        logger.info("Processing: s3://%s/%s", bucket, key)

        try:
            data = s3_client.get_object(Bucket=S3_ACCESS_POINT_ARN, Key=key)["Body"].read()
            logs = _parse_audit_logs(data, key)
            total_logs += len(logs)

            hec_events = _format_for_logscale(logs, key)
            shipped = _ship_to_logscale(hec_events, token)
            total_shipped += shipped
        except Exception as e:
            logger.error("Failed: %s/%s: %s", bucket, key, str(e))
            errors.append({"bucket": bucket, "key": key, "error": str(e)})

    result = {
        "statusCode": 200 if not errors else 207,
        "body": {"total_logs": total_logs, "total_shipped": total_shipped, "errors": errors},
    }
    logger.info("Complete: %s", json.dumps(result))
    return result


def _extract_s3_records(event: dict[str, Any]) -> list[dict[str, str]]:
    """Extract S3 bucket/key pairs from event."""
    records = []
    if "Records" in event:
        for record in event["Records"]:
            s3_info = record.get("s3", {})
            records.append({
                "bucket": s3_info.get("bucket", {}).get("name", ""),
                "key": s3_info.get("object", {}).get("key", ""),
            })
    elif "detail" in event:
        detail = event["detail"]
        records.append({
            "bucket": detail.get("bucket", {}).get("name", ""),
            "key": detail.get("object", {}).get("key", ""),
        })
    return [r for r in records if r["bucket"] and r["key"]]


def _parse_audit_logs(data: bytes, key: str) -> list[dict[str, Any]]:
    """Parse FSx ONTAP audit logs (XML, JSON, or EVTX)."""
    if key.endswith(".xml") or (not key.endswith(".evtx") and data.strip()[:5] == b"<?xml"):
        return _parse_xml(data.decode("utf-8", errors="replace"))
    elif key.endswith(".json") or key.endswith(".json.gz"):
        if key.endswith(".gz"):
            data = gzip.decompress(data)
        return _parse_json(data.decode("utf-8"))
    elif data.startswith(b"ElfFile\x00"):
        logger.warning("EVTX format — limited parsing (timestamp only)")
        return [{"event_type": "audit", "source": SOURCE, "message": "EVTX record"}]
    else:
        text = data.decode("utf-8", errors="replace").strip()
        if text.startswith("<"):
            return _parse_xml(text)
        return _parse_json(text)


def _parse_xml(data: str) -> list[dict[str, Any]]:
    """Parse ONTAP XML audit logs with full field extraction."""
    import xml.etree.ElementTree as ET

    events = []
    try:
        if not data.strip().startswith("<?xml"):
            data = f"<AuditEvents>{data}</AuditEvents>"
        else:
            lines = data.strip().split("\n")
            if lines[0].startswith("<?xml"):
                data = f"<AuditEvents>{''.join(lines[1:])}</AuditEvents>"

        root = ET.fromstring(data)
        for event_elem in root.iter("Event"):
            event = {}
            for child in event_elem.iter():
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "Data" and "Name" in child.attrib:
                    if child.text and child.text.strip():
                        event[child.attrib["Name"]] = child.text.strip()
                elif child.text and child.text.strip():
                    event[tag] = child.text.strip()
                for attr_name, attr_value in child.attrib.items():
                    if attr_name != "Name":
                        event[f"{tag}_{attr_name}"] = attr_value
            events.append(_normalize(event))
    except ET.ParseError as e:
        logger.warning("XML parse error: %s", e)

    return events


def _parse_json(data: str) -> list[dict[str, Any]]:
    """Parse JSON audit logs."""
    events = []
    data = data.strip()
    if data.startswith("["):
        try:
            return [_normalize(e) for e in json.loads(data)]
        except json.JSONDecodeError:
            pass
    for line in data.split("\n"):
        line = line.strip()
        if line:
            try:
                events.append(_normalize(json.loads(line)))
            except json.JSONDecodeError:
                continue
    return events


def _normalize(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize to common schema."""
    return {
        "timestamp": event.get("TimeCreated_SystemTime", event.get("timestamp", "")),
        "event_type": event.get("EventID", event.get("event_type", "unknown")),
        "source": SOURCE,
        "svm": event.get("Computer", event.get("SVMName", event.get("svm", ""))),
        "user": event.get("SubjectUserName", event.get("UserName", event.get("user", ""))),
        "client_ip": event.get("IpAddress", event.get("ClientIP", event.get("client_ip", ""))),
        "operation": event.get("ObjectType", event.get("Operation", event.get("operation", ""))),
        "path": event.get("ObjectName", event.get("path", "")),
        "result": event.get("Keywords", event.get("Result", event.get("result", ""))),
    }


def _format_for_logscale(logs: list[dict[str, Any]], source_key: str) -> list[dict[str, Any]]:
    """Format logs as HEC events for LogScale.

    Per LogScale HEC docs, top-level `time` must be epoch seconds (float).
    This is translated to @timestamp on ingestion. If omitted, LogScale
    uses ingest time instead of event time.
    """
    formatted = []
    for log in logs:
        epoch_time = _iso_to_epoch(log.get("timestamp", ""))
        event: dict[str, Any] = {
            "event": log,
            "source": SOURCE,
            "sourcetype": SOURCETYPE,
            "index": INDEX,
        }
        if epoch_time is not None:
            event["time"] = epoch_time
        event["fields"] = {"s3_key": source_key, "svm": log.get("svm", "")}
        formatted.append(event)
    return formatted


def _iso_to_epoch(iso_str: str) -> float | None:
    """Convert ISO 8601 timestamp to epoch seconds for HEC time field.

    Returns None if parsing fails (LogScale will use ingest time).
    """
    if not iso_str:
        return None
    try:
        # Handle both 'Z' suffix and '+00:00' timezone formats
        iso_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return None


def _ship_to_logscale(events: list[dict[str, Any]], token: str) -> int:
    """Ship HEC events to LogScale with retry."""
    if not events:
        return 0

    payload = "\n".join(json.dumps(e) for e in events).encode("utf-8")
    url = f"{LOGSCALE_URL.rstrip('/')}{HEC_PATH}"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = http.request("POST", url, body=payload, headers=headers, timeout=30.0)
            if resp.status < 300:
                return len(events)
            if resp.status == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status >= 500:
                time.sleep(2 ** (attempt + 1) + random.uniform(0, 1))
                continue
            logger.error("LogScale error %d: %s", resp.status, resp.data.decode()[:500])
            return 0
        except urllib3.exceptions.HTTPError as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            logger.warning("HTTP error (attempt %d): %s", attempt + 1, e)

    raise RuntimeError(f"Failed to ship to LogScale after {MAX_RETRIES} retries")
