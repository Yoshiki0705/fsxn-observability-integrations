"""Data models for the Splunk serverless integration.

Defines dataclasses for HEC event formatting, EMS event payloads,
and Firehose transformation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SplunkHecEvent:
    """Splunk HEC event structure for /services/collector/event endpoint.

    Represents a single event to be sent to Splunk via the HTTP Event
    Collector JSON endpoint.

    Attributes:
        time: Event timestamp in epoch seconds. None to use Splunk indexing time.
        host: Hostname or SVM name originating the event.
        source: Data source identifier (e.g., "fsxn-observability").
        sourcetype: Splunk sourcetype for parsing (e.g., "fsxn:ontap:audit").
        index: Target Splunk index (e.g., "fsxn_audit").
        event: Structured event data containing the log payload.
    """

    time: float | None
    host: str
    source: str
    sourcetype: str
    index: str
    event: dict[str, Any]

    def to_hec_json(self) -> dict[str, Any]:
        """Convert to HEC JSON payload format.

        Returns:
            Dictionary suitable for JSON serialization and HEC submission.
        """
        result: dict[str, Any] = {
            "host": self.host,
            "source": self.source,
            "sourcetype": self.sourcetype,
            "index": self.index,
            "event": self.event,
        }
        if self.time is not None:
            result["time"] = self.time
        return result


@dataclass
class EmsEventPayload:
    """ONTAP EMS event payload received via webhook.

    Represents an Event Management System event from ONTAP, typically
    received through the API Gateway HTTP endpoint for ransomware
    detection and other alerting scenarios.

    Attributes:
        message_name: EMS message identifier (e.g., "arw.volume.state").
        message_severity: Severity level (e.g., "alert", "warning").
        message_timestamp: ISO 8601 timestamp of the event.
        parameters: Event-specific parameters and metadata.
    """

    message_name: str
    message_severity: str
    message_timestamp: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_webhook_payload(cls, payload: dict[str, Any]) -> EmsEventPayload:
        """Create from raw webhook JSON payload.

        Args:
            payload: Raw JSON body from the API Gateway event.

        Returns:
            Parsed EmsEventPayload instance.
        """
        return cls(
            message_name=payload.get("message-name", ""),
            message_severity=payload.get("message-severity", ""),
            message_timestamp=payload.get("message-timestamp", ""),
            parameters=payload.get("parameters", {}),
        )


@dataclass
class FirehoseTransformResult:
    """Firehose transformation output record.

    Represents the result of transforming a single Kinesis Data Firehose
    record from FSx for ONTAP audit log format to Splunk HEC event JSON.

    Attributes:
        recordId: Unique identifier for the Firehose record.
        result: Transformation outcome status.
        data: Base64-encoded HEC event JSON string.
    """

    recordId: str
    result: Literal["Ok", "Dropped", "ProcessingFailed"]
    data: str

    def to_firehose_response(self) -> dict[str, str]:
        """Convert to Firehose transformation response format.

        Returns:
            Dictionary matching the Firehose transformation response schema.
        """
        return {
            "recordId": self.recordId,
            "result": self.result,
            "data": self.data,
        }
