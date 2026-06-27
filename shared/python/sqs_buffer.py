"""SQS buffering utilities for FSx for ONTAP observability pipeline.

Provides two components:
1. SQSProducer: Used by the poller Lambda to send file keys to the buffer queue
2. process_sqs_batch: Used by the shipper Lambda to process SQS batches with
   partial batch failure reporting

Architecture:
    Poller Lambda (reads S3 AP, sends keys to SQS)
        -> SQS Buffer Queue (backpressure, retry)
            -> Shipper Lambda (reads from SQS, ships to vendor)

Benefits over direct delivery:
- Backpressure: SQS absorbs spikes when vendor API is slow/down
- Retry: SQS automatically retries failed messages (maxReceiveCount)
- Concurrency: Multiple shipper Lambda instances process in parallel
- Visibility: Queue depth and age metrics for operational monitoring
- Partial failure: ReportBatchItemFailures returns only failed messages to queue

Usage (Poller Lambda):
    from sqs_buffer import SQSProducer

    producer = SQSProducer(queue_url=os.environ["BUFFER_QUEUE_URL"])

    for key in new_keys:
        producer.send(key=key, etag=etag, metadata={"svm": svm_name})

Usage (Shipper Lambda):
    from sqs_buffer import process_sqs_batch

    def lambda_handler(event, context):
        return process_sqs_batch(event, ship_single_file)

    def ship_single_file(key: str, etag: str, metadata: dict) -> None:
        # Read from S3 AP, format, ship to vendor
        # Raise on failure (message returns to queue)
        ...
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

import boto3

logger = logging.getLogger(__name__)


class SQSProducer:
    """Sends audit log file references to the SQS buffer queue.

    Each message contains the S3 key, ETag, and optional metadata.
    The shipper Lambda reads these messages and processes the files.
    """

    def __init__(
        self,
        queue_url: str,
        sqs_client: Any | None = None,
    ) -> None:
        """Initialize the SQS producer.

        Args:
            queue_url: SQS Queue URL for the buffer queue.
            sqs_client: Optional pre-configured SQS client (for testing).
        """
        self.queue_url = queue_url
        self._client = sqs_client or boto3.client("sqs")

    def send(self, key: str, etag: str, metadata: dict[str, str] | None = None) -> str:
        """Send a single file reference to the buffer queue.

        Args:
            key: S3 object key.
            etag: S3 object ETag (for deduplication).
            metadata: Optional metadata (svm, prefix, etc.).

        Returns:
            SQS MessageId.
        """
        body = {
            "key": key,
            "etag": etag,
            "metadata": metadata or {},
        }

        params: dict[str, Any] = {
            "QueueUrl": self.queue_url,
            "MessageBody": json.dumps(body),
        }

        response = self._client.send_message(**params)
        logger.debug("Sent to SQS: key=%s, MessageId=%s", key, response["MessageId"])
        return response["MessageId"]

    def send_batch(
        self, items: list[dict[str, Any]], batch_size: int = 10
    ) -> list[str]:
        """Send multiple file references in batches of 10 (SQS limit).

        Args:
            items: List of dicts with 'key', 'etag', and optional 'metadata'.
            batch_size: Max messages per SendMessageBatch call (max 10).

        Returns:
            List of failed message keys (empty if all succeeded).
        """
        failed_keys: list[str] = []

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            entries = []
            for idx, item in enumerate(batch):
                body = {
                    "key": item["key"],
                    "etag": item.get("etag", ""),
                    "metadata": item.get("metadata", {}),
                }
                entry: dict[str, Any] = {
                    "Id": str(idx),
                    "MessageBody": json.dumps(body),
                }
                entries.append(entry)

            response = self._client.send_message_batch(
                QueueUrl=self.queue_url,
                Entries=entries,
            )

            for failed in response.get("Failed", []):
                failed_idx = int(failed["Id"])
                failed_keys.append(batch[failed_idx]["key"])
                logger.error(
                    "Failed to send: key=%s, code=%s",
                    batch[failed_idx]["key"],
                    failed.get("Code", "Unknown"),
                )

        return failed_keys


def process_sqs_batch(
    event: dict[str, Any],
    processor_fn: Callable[[str, str, dict[str, str]], None],
) -> dict[str, Any]:
    """Process an SQS batch event with partial failure reporting.

    This function iterates over SQS records, parses the message body,
    and calls processor_fn for each file. Failed items are reported
    back to SQS for retry (ReportBatchItemFailures).

    Args:
        event: Lambda event from SQS trigger.
        processor_fn: Callable(key, etag, metadata) that processes a single file.
            Must raise an exception on failure.

    Returns:
        Response dict with batchItemFailures for partial failure reporting.
        Lambda must have FunctionResponseTypes: [ReportBatchItemFailures]
        in the EventSourceMapping.

    Example:
        def lambda_handler(event, context):
            return process_sqs_batch(event, ship_single_file)

        def ship_single_file(key: str, etag: str, metadata: dict) -> None:
            data = s3_client.get_object(Bucket=S3_AP_ARN, Key=key)
            logs = parse(data["Body"].read())
            ship_to_vendor(logs)
    """
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = record["messageId"]

        try:
            body = json.loads(record["body"])
            key = body["key"]
            etag = body.get("etag", "")
            metadata = body.get("metadata", {})

            logger.info("Processing: key=%s, messageId=%s", key, message_id)
            processor_fn(key, etag, metadata)
            logger.info("Success: key=%s", key)

        except Exception as e:
            logger.error(
                "Failed: messageId=%s, error=%s", message_id, str(e)
            )
            batch_item_failures.append(
                {"itemIdentifier": message_id}
            )

    return {"batchItemFailures": batch_item_failures}
