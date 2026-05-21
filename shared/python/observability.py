"""Shared observability utilities for FSx ONTAP Lambda handlers.

Provides standardized structured logging, custom metrics, and distributed
tracing using AWS Lambda Powertools. All Lambda handlers in this project
should import from this module for consistent observability.

Usage:
    from shared.python.observability import logger, metrics, tracer

    @tracer.capture_lambda_handler
    @metrics.log_metrics(capture_cold_start_metric=True)
    def lambda_handler(event, context):
        logger.info("Processing event", extra={"record_count": len(records)})
        metrics.add_metric(name="RecordsParsed", unit="Count", value=len(records))
        ...

Dependencies:
    pip install aws-lambda-powertools[tracer]
    # Or include in Lambda Layer

Environment Variables (set in CloudFormation):
    POWERTOOLS_SERVICE_NAME: Service name for structured logs (e.g., "fsxn-datadog-shipper")
    POWERTOOLS_METRICS_NAMESPACE: CloudWatch namespace (default: "FSxNObservability")
    POWERTOOLS_LOG_LEVEL: Log level (default: "INFO")
    POWERTOOLS_TRACER_CAPTURE_RESPONSE: Whether to capture response in traces (default: "false")
"""

from __future__ import annotations

import os

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit

# --- Shared instances ---
# These are module-level singletons, reused across invocations within
# the same Lambda execution context (warm start).

logger = Logger(
    service=os.environ.get("POWERTOOLS_SERVICE_NAME", "fsxn-observability"),
    log_uncaught_exceptions=True,
)

metrics = Metrics(
    namespace=os.environ.get("POWERTOOLS_METRICS_NAMESPACE", "FSxNObservability"),
)

tracer = Tracer(
    service=os.environ.get("POWERTOOLS_SERVICE_NAME", "fsxn-observability"),
)

# --- Standard metric names ---
# Use these constants for consistent metric naming across all handlers.

METRIC_RECORDS_PARSED = "RecordsParsed"
METRIC_RECORDS_SHIPPED = "RecordsShipped"
METRIC_DELIVERY_FAILURES = "DeliveryFailures"
METRIC_CHECKPOINT_AGE_SECONDS = "CheckpointAgeSeconds"
METRIC_DLQ_REPLAY_REQUESTED = "DLQReplayRequested"
METRIC_DUPLICATE_DELIVERY = "DuplicateDeliveryEstimated"
METRIC_POISON_PILL_FILES = "PoisonPillFiles"
METRIC_BATCH_SIZE_BYTES = "BatchSizeBytes"
METRIC_DELIVERY_LATENCY_MS = "DeliveryLatencyMs"

# Re-export MetricUnit for convenience
__all__ = [
    "logger",
    "metrics",
    "tracer",
    "MetricUnit",
    "METRIC_RECORDS_PARSED",
    "METRIC_RECORDS_SHIPPED",
    "METRIC_DELIVERY_FAILURES",
    "METRIC_CHECKPOINT_AGE_SECONDS",
    "METRIC_DLQ_REPLAY_REQUESTED",
    "METRIC_DUPLICATE_DELIVERY",
    "METRIC_POISON_PILL_FILES",
    "METRIC_BATCH_SIZE_BYTES",
    "METRIC_DELIVERY_LATENCY_MS",
]
