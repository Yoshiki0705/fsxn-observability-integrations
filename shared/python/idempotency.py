"""Shared idempotency utilities for FSx ONTAP Lambda handlers.

Provides a lightweight idempotency layer using DynamoDB for idempotent
object processing and duplicate suppression of audit log files. This is
the "Level 3" object ledger referenced in the Production Readiness Levels.

Usage:
    from shared.python.idempotency import ObjectLedger

    ledger = ObjectLedger(table_name=os.environ["LEDGER_TABLE_NAME"])

    if ledger.is_processed(object_key):
        logger.info("Already processed, skipping", extra={"key": object_key})
        return

    # ... process the file ...

    ledger.mark_processed(object_key, record_count=len(records))

Dependencies:
    pip install boto3
    # DynamoDB table with partition key "object_key" (String)

Environment Variables:
    LEDGER_TABLE_NAME: DynamoDB table name for the object ledger
    LEDGER_TTL_DAYS: TTL for ledger entries in days (default: 30)
"""

from __future__ import annotations

import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError


class ObjectLedger:
    """DynamoDB-backed object ledger for idempotent object processing and duplicate suppression.

    Tracks which S3 objects (audit log files) have been successfully
    processed and delivered to the observability backend. This does not
    provide end-to-end exactly-once delivery. It provides idempotent
    object processing and duplicate suppression within the configured
    TTL window.

    Attributes:
        table_name: DynamoDB table name.
        ttl_days: Number of days before ledger entries expire.
    """

    def __init__(
        self,
        table_name: str | None = None,
        ttl_days: int | None = None,
    ) -> None:
        """Initialize the object ledger.

        Args:
            table_name: DynamoDB table name. Defaults to LEDGER_TABLE_NAME env var.
            ttl_days: TTL for entries in days. Defaults to LEDGER_TTL_DAYS env var or 30.
        """
        self.table_name = table_name or os.environ.get("LEDGER_TABLE_NAME", "")
        self.ttl_days = ttl_days or int(os.environ.get("LEDGER_TTL_DAYS", "30"))
        self._dynamodb = boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(self.table_name)

    def is_processed(self, object_key: str) -> bool:
        """Check if an object has already been processed.

        Args:
            object_key: S3 object key to check.

        Returns:
            True if the object has been processed, False otherwise.
        """
        try:
            response = self._table.get_item(
                Key={"object_key": object_key},
                ProjectionExpression="object_key",
            )
            return "Item" in response
        except ClientError:
            # If we can't check, assume not processed (at-least-once)
            return False

    def mark_processed(
        self,
        object_key: str,
        record_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark an object as successfully processed.

        Args:
            object_key: S3 object key that was processed.
            record_count: Number of records extracted and shipped.
            metadata: Optional additional metadata to store.
        """
        ttl_epoch = int(time.time()) + (self.ttl_days * 86400)
        item: dict[str, Any] = {
            "object_key": object_key,
            "processed_at": int(time.time()),
            "record_count": record_count,
            "ttl": ttl_epoch,
        }
        if metadata:
            item["metadata"] = metadata

        self._table.put_item(Item=item)

    def get_processing_status(self, object_key: str) -> dict[str, Any] | None:
        """Get full processing status for an object.

        Args:
            object_key: S3 object key to look up.

        Returns:
            Dict with processing details, or None if not found.
        """
        try:
            response = self._table.get_item(Key={"object_key": object_key})
            return response.get("Item")
        except ClientError:
            return None
