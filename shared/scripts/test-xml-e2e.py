#!/usr/bin/env python3
"""Cross-vendor E2E test: XML audit log parse → vendor API delivery.

This script validates the full pipeline for XML format audit logs:
1. Reads sample XML audit log (shared/test-data/sample_audit_logs.xml)
2. Parses using the shared log parser (same code path as production Lambda)
3. Ships to the vendor's API endpoint
4. Reports success/failure

Usage:
  # Datadog
  python3 shared/scripts/test-xml-e2e.py --vendor datadog

  # Splunk
  python3 shared/scripts/test-xml-e2e.py --vendor splunk

  # New Relic
  python3 shared/scripts/test-xml-e2e.py --vendor new-relic

  # All vendors (ships to whichever have credentials configured)
  python3 shared/scripts/test-xml-e2e.py --vendor all

  # Parse only (no delivery)
  python3 shared/scripts/test-xml-e2e.py --dry-run

Environment variables (set in .env or export):
  DD_API_KEY, DD_SITE          - Datadog
  SPLUNK_HEC_TOKEN, SPLUNK_URL - Splunk
  NR_LICENSE_KEY               - New Relic
  GRAFANA_USER, GRAFANA_TOKEN, GRAFANA_OTLP_ENDPOINT - Grafana Cloud
  ELASTIC_API_KEY, ELASTIC_URL - Elastic
  DT_API_TOKEN, DT_ENV_URL    - Dynatrace
  SUMO_HTTP_URL                - Sumo Logic
  HONEYCOMB_API_KEY            - Honeycomb

Prerequisites:
  pip install urllib3
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import urllib3

urllib3.disable_warnings()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "shared" / "lambda-layers" / "log-parser" / "python"))

SAMPLE_XML_PATH = PROJECT_ROOT / "shared" / "test-data" / "sample_audit_logs.xml"


def load_env():
    """Load .env file if it exists."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def generate_fresh_xml() -> str:
    """Generate XML with current timestamps (within vendor acceptance window)."""
    now = datetime.now(timezone.utc)
    template = SAMPLE_XML_PATH.read_text()
    counter = [0]

    def replace_time(match):
        counter[0] += 1
        offset = counter[0] * 30
        ts = now.replace(second=max(0, now.second - min(offset, 59)))
        return f'SystemTime="{ts.strftime("%Y-%m-%dT%H:%M:%S.000000Z")}"'

    return re.sub(r'SystemTime="[^"]*"', replace_time, template)


def parse_xml(xml_data: str) -> list:
    """Parse XML using the shared log parser."""
    from fsxn_log_parser.parser import parse_xml_log
    return parse_xml_log(xml_data)


def test_datadog(events: list) -> dict:
    """Ship to Datadog Logs API v2."""
    api_key = os.environ.get("DD_API_KEY", "")
    site = os.environ.get("DD_SITE", "datadoghq.com")
    if not api_key:
        return {"status": "SKIP", "reason": "DD_API_KEY not set"}

    dd_logs = [{
        "ddsource": "fsxn", "service": "ontap-audit",
        "ddtags": "source:fsxn,service:ontap-audit,env:test,format:xml",
        "hostname": e.get("svm", "test-svm"),
        "message": json.dumps(e, default=str),
        "date": e.get("timestamp"),
        "attributes": {"event_type": e.get("event_type"), "user": e.get("user"),
                       "client_ip": e.get("client_ip"), "operation": e.get("operation"),
                       "path": e.get("path"), "result": e.get("result"),
                       "svm": e.get("svm"), "log_format": "xml"},
    } for e in events]

    http = urllib3.PoolManager()
    resp = http.request("POST", f"https://http-intake.logs.{site}/api/v2/logs",
                        body=json.dumps(dd_logs).encode(),
                        headers={"Content-Type": "application/json", "DD-API-KEY": api_key}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(dd_logs)}


def test_splunk(events: list) -> dict:
    """Ship to Splunk HEC."""
    token = os.environ.get("SPLUNK_HEC_TOKEN", "")
    url = os.environ.get("SPLUNK_URL", "")
    if not token or not url:
        return {"status": "SKIP", "reason": "SPLUNK_HEC_TOKEN/URL not set"}

    payload = "\n".join(json.dumps({"event": e, "sourcetype": "fsxn:audit:xml",
                                    "source": "fsxn-xml-e2e", "index": "fsxn_audit"}) for e in events)
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    resp = http.request("POST", url, body=payload.encode(),
                        headers={"Authorization": f"Splunk {token}", "Content-Type": "application/json"}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_new_relic(events: list) -> dict:
    """Ship to New Relic Log API."""
    key = os.environ.get("NR_LICENSE_KEY", "")
    if not key:
        return {"status": "SKIP", "reason": "NR_LICENSE_KEY not set"}

    nr_payload = [{"common": {"attributes": {"logtype": "fsxn-audit-xml"}},
                   "logs": [{"timestamp": int(time.time() * 1000), "message": json.dumps(e, default=str),
                             "attributes": {"event_type": e.get("event_type"), "user": e.get("user"),
                                            "path": e.get("path"), "svm": e.get("svm"), "log_format": "xml"}}
                            for e in events]}]
    http = urllib3.PoolManager()
    resp = http.request("POST", "https://log-api.newrelic.com/log/v1", body=json.dumps(nr_payload).encode(),
                        headers={"Content-Type": "application/json", "Api-Key": key}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_grafana(events: list) -> dict:
    """Ship to Grafana Cloud Loki."""
    import base64
    user = os.environ.get("GRAFANA_USER", "")
    token = os.environ.get("GRAFANA_TOKEN", "")
    endpoint = os.environ.get("GRAFANA_OTLP_ENDPOINT", "")
    if not all([user, token, endpoint]):
        return {"status": "SKIP", "reason": "GRAFANA credentials not set"}

    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    streams = [{"stream": {"source": "fsxn", "format": "xml"},
                "values": [[str(int(time.time() * 1e9)), json.dumps(e, default=str)] for e in events]}]
    http = urllib3.PoolManager()
    resp = http.request("POST", f"{endpoint}/loki/api/v1/push", body=json.dumps({"streams": streams}).encode(),
                        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_elastic(events: list) -> dict:
    """Ship to Elastic Bulk API."""
    key = os.environ.get("ELASTIC_API_KEY", "")
    url = os.environ.get("ELASTIC_URL", "")
    if not key or not url:
        return {"status": "SKIP", "reason": "ELASTIC credentials not set"}

    bulk = "".join(json.dumps({"index": {"_index": "fsxn-audit-xml"}}) + "\n" +
                   json.dumps({**e, "log_format": "xml"}) + "\n" for e in events)
    http = urllib3.PoolManager(cert_reqs="CERT_NONE")
    resp = http.request("POST", f"{url}/_bulk", body=bulk.encode(),
                        headers={"Content-Type": "application/x-ndjson", "Authorization": f"ApiKey {key}"}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_dynatrace(events: list) -> dict:
    """Ship to Dynatrace Log Ingest API v2."""
    token = os.environ.get("DT_API_TOKEN", "")
    url = os.environ.get("DT_ENV_URL", "")
    if not token or not url:
        return {"status": "SKIP", "reason": "DT credentials not set"}

    dt_logs = [{"content": json.dumps(e, default=str), "log.source": "fsxn-audit-xml",
                "severity": "info" if "Success" in e.get("result", "") else "warn"} for e in events]
    http = urllib3.PoolManager()
    resp = http.request("POST", f"{url}/api/v2/logs/ingest", body=json.dumps(dt_logs).encode(),
                        headers={"Content-Type": "application/json; charset=utf-8",
                                 "Authorization": f"Api-Token {token}"}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_sumo_logic(events: list) -> dict:
    """Ship to Sumo Logic HTTP Source."""
    url = os.environ.get("SUMO_HTTP_URL", "")
    if not url:
        return {"status": "SKIP", "reason": "SUMO_HTTP_URL not set"}

    payload = "\n".join(json.dumps(e, default=str) for e in events)
    http = urllib3.PoolManager()
    resp = http.request("POST", url, body=payload.encode(),
                        headers={"Content-Type": "application/json", "X-Sumo-Category": "fsxn/audit/xml"}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_honeycomb(events: list) -> dict:
    """Ship to Honeycomb Events API."""
    key = os.environ.get("HONEYCOMB_API_KEY", "")
    if not key:
        return {"status": "SKIP", "reason": "HONEYCOMB_API_KEY not set"}

    hc = [{"data": {**e, "log_format": "xml"}, "time": e.get("timestamp", "")} for e in events]
    http = urllib3.PoolManager()
    resp = http.request("POST", "https://api.honeycomb.io/1/batch/fsxn-audit", body=json.dumps(hc).encode(),
                        headers={"Content-Type": "application/json", "X-Honeycomb-Team": key}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


def test_crowdstrike(events: list) -> dict:
    """Ship to CrowdStrike Falcon LogScale via HEC."""
    token = os.environ.get("CROWDSTRIKE_INGEST_TOKEN", "")
    url = os.environ.get("CROWDSTRIKE_LOGSCALE_URL", "")
    if not token or not url:
        return {"status": "SKIP", "reason": "CROWDSTRIKE_INGEST_TOKEN/LOGSCALE_URL not set"}

    hec_events = "\n".join(json.dumps({
        "event": e, "source": "fsxn-ontap", "sourcetype": "fsxn:audit:xml", "index": "fsxn_audit",
        "time": e.get("timestamp", ""), "fields": {"log_format": "xml", "svm": e.get("svm", "")}
    }) for e in events)

    http = urllib3.PoolManager()
    resp = http.request("POST", f"{url.rstrip('/')}/api/v1/ingest/hec", body=hec_events.encode(),
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, timeout=30.0)
    return {"status": "OK" if resp.status < 300 else "FAIL", "http_status": resp.status, "events_sent": len(events)}


VENDORS = {"datadog": test_datadog, "splunk": test_splunk, "new-relic": test_new_relic,
           "grafana": test_grafana, "elastic": test_elastic, "dynatrace": test_dynatrace,
           "sumo-logic": test_sumo_logic, "honeycomb": test_honeycomb, "crowdstrike": test_crowdstrike}


def main():
    ap = argparse.ArgumentParser(description="XML audit log E2E test for all vendors")
    ap.add_argument("--vendor", default="all", choices=list(VENDORS.keys()) + ["all"])
    ap.add_argument("--dry-run", action="store_true", help="Parse only, don't ship")
    args = ap.parse_args()

    load_env()
    print("=" * 60)
    print("FSx for ONTAP XML Audit Log — Cross-Vendor E2E Test")
    print("=" * 60)
    print()
    print("[1/3] Generating XML with current timestamps...")
    xml_data = generate_fresh_xml()
    print(f"      Source: {SAMPLE_XML_PATH.relative_to(PROJECT_ROOT)}")
    print()
    print("[2/3] Parsing XML...")
    events = parse_xml(xml_data)
    print(f"      Parsed: {len(events)} events")
    for e in events:
        print(f"        EventID={e.get('event_type')}, user={e.get('user')}, "
              f"path={e.get('path', '')[:40]}..., result={e.get('result')}")
    print()

    if args.dry_run:
        print("[3/3] DRY RUN — skipping delivery")
        print(json.dumps(events[0], indent=2, default=str))
        return 0

    targets = VENDORS.keys() if args.vendor == "all" else [args.vendor]
    print(f"[3/3] Shipping to: {', '.join(targets)}")
    print()
    results = {}
    for v in targets:
        r = VENDORS[v](events)
        results[v] = r
        icon = {"OK": "\u2705", "FAIL": "\u274c", "SKIP": "\u23ed\ufe0f"}.get(r["status"], "?")
        line = f"  {icon} {v:12} {r['status']}"
        if r.get("http_status"):
            line += f" (HTTP {r['http_status']}, {r.get('events_sent', 0)} events)"
        if r.get("reason"):
            line += f" [{r['reason']}]"
        print(line)

    print()
    ok = sum(1 for r in results.values() if r["status"] == "OK")
    skip = sum(1 for r in results.values() if r["status"] == "SKIP")
    fail = sum(1 for r in results.values() if r["status"] == "FAIL")
    print(f"Summary: {ok} OK, {skip} skipped, {fail} failed")
    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
