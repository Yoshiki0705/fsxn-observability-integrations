"""Dashboard Importer Lambda for FSxN Management Console.

CloudFormation Custom Resource handler that imports Grafana dashboards
into Amazon Managed Grafana (AMG) via the HTTP API. Configures an AMP
data source and imports all dashboard JSON files from an S3 bucket.

Environment Variables:
    AMG_API_KEY_SECRET_ARN: Secrets Manager ARN for the AMG API key.
    AMG_WORKSPACE_URL: AMG workspace URL (e.g., https://g-xxxx.grafana-workspace.region.amazonaws.com).
    DASHBOARD_BUCKET_NAME: S3 bucket containing dashboard JSON files.
    DASHBOARD_S3_PREFIX: S3 prefix for dashboard files (default: 'dashboards/').
    AMP_WORKSPACE_ID: Amazon Managed Prometheus workspace ID.
    AWS_REGION: AWS region (set automatically by Lambda runtime).
"""

import json
import logging
import os
import time
from typing import Any

import boto3
import urllib3

# ─── Logger setup ──────────────────────────────────────────────────────────

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Configuration from environment ────────────────────────────────────────

AMG_API_KEY_SECRET_ARN = os.environ.get("AMG_API_KEY_SECRET_ARN", "")
AMG_WORKSPACE_URL = os.environ.get("AMG_WORKSPACE_URL", "").rstrip("/")
DASHBOARD_BUCKET_NAME = os.environ.get("DASHBOARD_BUCKET_NAME", "")
DASHBOARD_S3_PREFIX = os.environ.get("DASHBOARD_S3_PREFIX", "dashboards/")
AMP_WORKSPACE_ID = os.environ.get("AMP_WORKSPACE_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# ─── Constants ──────────────────────────────────────────────────────────────

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2
CFN_SUCCESS = "SUCCESS"
CFN_FAILED = "FAILED"
HTTP_TOO_MANY_REQUESTS = 429

# ─── Clients ───────────────────────────────────────────────────────────────

_http = urllib3.PoolManager()
_s3_client = boto3.client("s3")
_secrets_client = boto3.client("secretsmanager")


def send_cfn_response(
    event: dict[str, Any],
    context: Any,
    status: str,
    data: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    """Send response to CloudFormation Custom Resource.

    Args:
        event: CloudFormation Custom Resource event.
        context: Lambda context object.
        status: Response status ('SUCCESS' or 'FAILED').
        data: Optional data to return as Custom Resource outputs.
        reason: Optional reason string for failures.
    """
    response_body = {
        "Status": status,
        "Reason": reason or f"See CloudWatch Log Stream: {context.log_stream_name}",
        "PhysicalResourceId": event.get(
            "PhysicalResourceId", context.log_stream_name
        ),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": data or {},
    }

    response_url = event["ResponseURL"]
    encoded_body = json.dumps(response_body).encode("utf-8")

    logger.info(
        "Sending CloudFormation response",
        extra={"status": status, "physical_resource_id": response_body["PhysicalResourceId"]},
    )

    try:
        _http.request(
            "PUT",
            response_url,
            body=encoded_body,
            headers={"Content-Type": ""},
        )
    except Exception as exc:
        logger.error(
            "Failed to send CloudFormation response",
            extra={"error": str(exc)},
        )


def get_amg_api_key() -> str:
    """Retrieve AMG API key from Secrets Manager.

    Returns:
        The API key string.

    Raises:
        RuntimeError: If the secret cannot be retrieved.
    """
    try:
        response = _secrets_client.get_secret_value(SecretId=AMG_API_KEY_SECRET_ARN)
        return response["SecretString"]
    except Exception as exc:
        raise RuntimeError(
            f"Failed to retrieve AMG API key from Secrets Manager: {exc}"
        ) from exc


def amg_api_request(
    method: str,
    path: str,
    api_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an HTTP request to the AMG API with retry on 429.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: API path (e.g., '/api/datasources').
        api_key: AMG API key for authorization.
        body: Optional request body (will be JSON-encoded).

    Returns:
        Parsed JSON response body.

    Raises:
        RuntimeError: If the request fails after all retries.
    """
    url = f"{AMG_WORKSPACE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    encoded_body = json.dumps(body).encode("utf-8") if body else None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = _http.request(
                method,
                url,
                body=encoded_body,
                headers=headers,
            )

            if response.status == HTTP_TOO_MANY_REQUESTS:
                if attempt < MAX_RETRIES:
                    wait_time = BACKOFF_BASE_SECONDS * (2 ** attempt)
                    logger.warning(
                        "Rate limited by AMG API, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "wait_seconds": wait_time,
                            "path": path,
                        },
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(
                        f"AMG API rate limit exceeded after {MAX_RETRIES} retries: "
                        f"{method} {path}"
                    )

            response_data = json.loads(response.data.decode("utf-8")) if response.data else {}

            if response.status >= 400:
                raise RuntimeError(
                    f"AMG API error: {method} {path} returned {response.status}: "
                    f"{response_data.get('message', response.data.decode('utf-8', errors='replace'))}"
                )

            return response_data

        except urllib3.exceptions.HTTPError as exc:
            if attempt < MAX_RETRIES:
                wait_time = BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "HTTP error calling AMG API, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "wait_seconds": wait_time,
                        "path": path,
                        "error": str(exc),
                    },
                )
                time.sleep(wait_time)
                continue
            raise RuntimeError(
                f"AMG API request failed after {MAX_RETRIES} retries: "
                f"{method} {path}: {exc}"
            ) from exc

    # Should not reach here, but satisfy type checker
    raise RuntimeError(f"AMG API request failed: {method} {path}")


def configure_amp_datasource(api_key: str) -> dict[str, Any]:
    """Configure AMP as a data source in AMG.

    Creates or updates the Prometheus data source pointing to the
    AMP workspace. Uses sigV4 authentication for secure access.

    Args:
        api_key: AMG API key.

    Returns:
        API response from datasource creation.
    """
    amp_endpoint = (
        f"https://aps-workspaces.{AWS_REGION}.amazonaws.com/workspaces/"
        f"{AMP_WORKSPACE_ID}"
    )

    datasource_payload = {
        "name": "Amazon Managed Prometheus",
        "type": "prometheus",
        "access": "proxy",
        "url": amp_endpoint,
        "isDefault": True,
        "jsonData": {
            "httpMethod": "POST",
            "sigV4Auth": True,
            "sigV4AuthType": "default",
            "sigV4Region": AWS_REGION,
        },
    }

    logger.info(
        "Configuring AMP data source in AMG",
        extra={
            "amp_workspace_id": AMP_WORKSPACE_ID,
            "amp_endpoint": amp_endpoint,
        },
    )

    try:
        response = amg_api_request("POST", "/api/datasources", api_key, datasource_payload)
        logger.info("AMP data source created successfully")
        return response
    except RuntimeError as exc:
        # If datasource already exists, try to update it
        if "already exists" in str(exc).lower() or "409" in str(exc):
            logger.info("AMP data source already exists, updating")
            # Get existing datasource ID by name
            datasources = amg_api_request("GET", "/api/datasources", api_key)
            for ds in datasources if isinstance(datasources, list) else []:
                if ds.get("name") == "Amazon Managed Prometheus":
                    ds_id = ds["id"]
                    datasource_payload["id"] = ds_id
                    return amg_api_request(
                        "PUT", f"/api/datasources/{ds_id}", api_key, datasource_payload
                    )
        raise


def list_dashboard_files() -> list[str]:
    """List all .json files in the dashboard S3 bucket/prefix.

    Returns:
        List of S3 object keys for dashboard JSON files.
    """
    keys: list[str] = []
    paginator = _s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=DASHBOARD_BUCKET_NAME, Prefix=DASHBOARD_S3_PREFIX
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                keys.append(key)

    logger.info(
        "Listed dashboard files from S3",
        extra={
            "bucket": DASHBOARD_BUCKET_NAME,
            "prefix": DASHBOARD_S3_PREFIX,
            "file_count": len(keys),
        },
    )

    return keys


def read_dashboard_json(key: str) -> dict[str, Any]:
    """Read and parse a dashboard JSON file from S3.

    Args:
        key: S3 object key for the dashboard JSON file.

    Returns:
        Parsed dashboard JSON as a dictionary.

    Raises:
        RuntimeError: If the file cannot be read or parsed.
    """
    try:
        response = _s3_client.get_object(Bucket=DASHBOARD_BUCKET_NAME, Key=key)
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to read dashboard JSON from "
            f"s3://{DASHBOARD_BUCKET_NAME}/{key}: {exc}"
        ) from exc


def import_dashboard(api_key: str, dashboard_json: dict[str, Any]) -> dict[str, Any]:
    """Import a single dashboard into AMG.

    Uses POST /api/dashboards/db with overwrite=true for idempotent
    import. The dashboard UID ensures the same dashboard is updated
    rather than duplicated on re-deploy.

    Args:
        api_key: AMG API key.
        dashboard_json: Dashboard model JSON.

    Returns:
        API response from dashboard import.
    """
    payload = {
        "dashboard": dashboard_json,
        "overwrite": True,
        "folderId": 0,
    }

    # Remove 'id' to allow overwrite by UID
    if "id" in payload["dashboard"]:
        del payload["dashboard"]["id"]

    return amg_api_request("POST", "/api/dashboards/db", api_key, payload)


def handle_create_update(event: dict[str, Any], context: Any) -> None:
    """Handle Create and Update requests for the Custom Resource.

    Steps:
        1. Read AMG API key from Secrets Manager.
        2. Configure AMP data source in AMG.
        3. List dashboard JSON files from S3.
        4. Import each dashboard into AMG.
        5. Return panel embed URLs as Custom Resource output.

    Args:
        event: CloudFormation Custom Resource event.
        context: Lambda context object.
    """
    # Step 1: Get AMG API key
    api_key = get_amg_api_key()

    # Step 2: Configure AMP data source
    configure_amp_datasource(api_key)

    # Step 3: List dashboard files
    dashboard_keys = list_dashboard_files()

    if not dashboard_keys:
        logger.warning("No dashboard JSON files found in S3")
        send_cfn_response(event, context, CFN_SUCCESS, data={
            "Message": "No dashboard files found",
            "ImportedCount": "0",
        })
        return

    # Step 4: Import each dashboard
    success_count = 0
    failure_count = 0
    embed_urls: dict[str, str] = {}
    errors: list[str] = []

    for key in dashboard_keys:
        dashboard_name = key.rsplit("/", 1)[-1].replace(".json", "")
        try:
            dashboard_json = read_dashboard_json(key)
            result = import_dashboard(api_key, dashboard_json)

            # Extract dashboard URL for embed
            dashboard_url = result.get("url", "")
            if dashboard_url:
                full_url = f"{AMG_WORKSPACE_URL}{dashboard_url}"
                embed_urls[dashboard_name] = full_url

            success_count += 1
            logger.info(
                "Dashboard imported successfully",
                extra={"dashboard": dashboard_name, "url": dashboard_url},
            )

        except Exception as exc:
            failure_count += 1
            error_msg = f"{dashboard_name}: {exc}"
            errors.append(error_msg)
            logger.error(
                "Failed to import dashboard",
                extra={"dashboard": dashboard_name, "error": str(exc)},
            )

    # Step 5: Log summary and send response
    logger.info(
        "Dashboard import completed",
        extra={
            "success_count": success_count,
            "failure_count": failure_count,
            "total": len(dashboard_keys),
        },
    )

    # Build output data (CloudFormation limits output to 4096 bytes)
    output_data: dict[str, str] = {
        "ImportedCount": str(success_count),
        "FailedCount": str(failure_count),
        "TotalCount": str(len(dashboard_keys)),
    }

    # Add embed URLs (truncate if too many to fit in CFn output)
    for name, url in list(embed_urls.items())[:10]:
        safe_key = name.replace("-", "").replace("_", "")[:20]
        output_data[f"Url{safe_key}"] = url

    if failure_count > 0 and success_count == 0:
        # All imports failed — report as FAILED
        send_cfn_response(
            event,
            context,
            CFN_FAILED,
            data=output_data,
            reason=f"All {failure_count} dashboard imports failed. First error: {errors[0]}",
        )
    else:
        # At least some succeeded — report SUCCESS (partial failures are acceptable)
        send_cfn_response(event, context, CFN_SUCCESS, data=output_data)


def handle_delete(event: dict[str, Any], context: Any) -> None:
    """Handle Delete request for the Custom Resource.

    No-op: dashboards remain in AMG for manual cleanup.
    Sends SUCCESS response to allow stack deletion to proceed.

    Args:
        event: CloudFormation Custom Resource event.
        context: Lambda context object.
    """
    logger.info("Delete request received — no-op (dashboards remain in AMG)")
    send_cfn_response(event, context, CFN_SUCCESS, data={
        "Message": "Delete is a no-op. Dashboards remain in AMG.",
    })


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """Lambda entry point for CloudFormation Custom Resource.

    Routes to the appropriate handler based on the RequestType
    (Create, Update, or Delete).

    Args:
        event: CloudFormation Custom Resource event containing:
            - RequestType: 'Create', 'Update', or 'Delete'
            - ResponseURL: Pre-signed URL for sending response
            - StackId, RequestId, LogicalResourceId: CFn identifiers
        context: Lambda context object.
    """
    request_type = event.get("RequestType", "")
    logger.info(
        "Dashboard importer invoked",
        extra={
            "request_type": request_type,
            "stack_id": event.get("StackId", ""),
            "logical_resource_id": event.get("LogicalResourceId", ""),
        },
    )

    try:
        if request_type in ("Create", "Update"):
            handle_create_update(event, context)
        elif request_type == "Delete":
            handle_delete(event, context)
        else:
            send_cfn_response(
                event,
                context,
                CFN_FAILED,
                reason=f"Unsupported RequestType: {request_type}",
            )

    except Exception as exc:
        logger.exception(
            "Unhandled exception in dashboard importer",
            extra={"request_type": request_type, "error": str(exc)},
        )
        send_cfn_response(
            event,
            context,
            CFN_FAILED,
            reason=f"Unhandled error: {type(exc).__name__}: {exc}",
        )
