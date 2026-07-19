"""Unit tests for sqs_buffer module.

Tests cover:
- SQSProducer.send() (single message)
- SQSProducer.send_batch() (batched sends, partial batch failures)
- process_sqs_batch() (Lambda Event Source Mapping ReportBatchItemFailures
  contract: successful records are dropped, failed records return their
  messageId in batchItemFailures)

All tests run against a mocked boto3 SQS client -- none of them exercise
a real SQS queue.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqs_buffer import SQSProducer, process_sqs_batch


@pytest.fixture
def sqs_client():
    return MagicMock()


@pytest.fixture
def producer(sqs_client):
    return SQSProducer(
        queue_url="https://sqs.ap-northeast-1.amazonaws.com/123456789012/test-queue",
        sqs_client=sqs_client,
    )


def make_sqs_record(message_id: str, key: str, etag: str = "etag1", metadata: dict | None = None) -> dict:
    """Build a single SQS record matching the Lambda Event Source Mapping shape."""
    return {
        "messageId": message_id,
        "body": json.dumps(
            {"key": key, "etag": etag, "metadata": metadata or {}}
        ),
    }


# ==========================================================================
# SQSProducer.send
# ==========================================================================


class TestSend:
    def test_send_returns_message_id(self, producer, sqs_client):
        sqs_client.send_message.return_value = {"MessageId": "msg-1"}

        message_id = producer.send(key="audit/log1.json", etag="etag-abc")

        assert message_id == "msg-1"
        call_kwargs = sqs_client.send_message.call_args.kwargs
        assert call_kwargs["QueueUrl"] == producer.queue_url
        body = json.loads(call_kwargs["MessageBody"])
        assert body == {"key": "audit/log1.json", "etag": "etag-abc", "metadata": {}}

    def test_send_includes_metadata(self, producer, sqs_client):
        sqs_client.send_message.return_value = {"MessageId": "msg-2"}

        producer.send(key="k1", etag="e1", metadata={"svm": "svm-prod-01"})

        call_kwargs = sqs_client.send_message.call_args.kwargs
        body = json.loads(call_kwargs["MessageBody"])
        assert body["metadata"] == {"svm": "svm-prod-01"}

    def test_send_defaults_metadata_to_empty_dict(self, producer, sqs_client):
        sqs_client.send_message.return_value = {"MessageId": "msg-3"}

        producer.send(key="k1", etag="e1")

        call_kwargs = sqs_client.send_message.call_args.kwargs
        body = json.loads(call_kwargs["MessageBody"])
        assert body["metadata"] == {}


# ==========================================================================
# SQSProducer.send_batch
# ==========================================================================


class TestSendBatch:
    def test_send_batch_all_succeed_returns_no_failures(self, producer, sqs_client):
        sqs_client.send_message_batch.return_value = {"Successful": [], "Failed": []}
        items = [{"key": f"k{i}", "etag": f"e{i}"} for i in range(3)]

        failed = producer.send_batch(items)

        assert failed == []
        sqs_client.send_message_batch.assert_called_once()

    def test_send_batch_reports_partial_failures(self, producer, sqs_client):
        sqs_client.send_message_batch.return_value = {
            "Successful": [{"Id": "0"}],
            "Failed": [{"Id": "1", "Code": "InternalError", "Message": "x"}],
        }
        items = [{"key": "k0", "etag": "e0"}, {"key": "k1", "etag": "e1"}]

        failed = producer.send_batch(items)

        assert failed == ["k1"]

    def test_send_batch_splits_into_chunks_of_batch_size(self, producer, sqs_client):
        sqs_client.send_message_batch.return_value = {"Successful": [], "Failed": []}
        items = [{"key": f"k{i}", "etag": f"e{i}"} for i in range(25)]

        producer.send_batch(items, batch_size=10)

        # 25 items / batch_size 10 -> 3 calls (10, 10, 5)
        assert sqs_client.send_message_batch.call_count == 3
        first_call_entries = sqs_client.send_message_batch.call_args_list[0].kwargs["Entries"]
        assert len(first_call_entries) == 10
        last_call_entries = sqs_client.send_message_batch.call_args_list[2].kwargs["Entries"]
        assert len(last_call_entries) == 5

    def test_send_batch_defaults_missing_etag_and_metadata(self, producer, sqs_client):
        sqs_client.send_message_batch.return_value = {"Successful": [], "Failed": []}
        items = [{"key": "k0"}]

        producer.send_batch(items)

        entries = sqs_client.send_message_batch.call_args.kwargs["Entries"]
        body = json.loads(entries[0]["MessageBody"])
        assert body == {"key": "k0", "etag": "", "metadata": {}}

    def test_send_batch_empty_items_makes_no_calls(self, producer, sqs_client):
        failed = producer.send_batch([])

        assert failed == []
        sqs_client.send_message_batch.assert_not_called()


# ==========================================================================
# process_sqs_batch
# ==========================================================================


class TestProcessSqsBatch:
    def test_all_records_succeed_returns_empty_failures(self):
        event = {
            "Records": [
                make_sqs_record("msg-1", "key1"),
                make_sqs_record("msg-2", "key2"),
            ]
        }
        processor = MagicMock()

        result = process_sqs_batch(event, processor)

        assert result == {"batchItemFailures": []}
        assert processor.call_count == 2

    def test_processor_receives_key_etag_metadata(self):
        event = {
            "Records": [
                make_sqs_record("msg-1", "key1", etag="etag-x", metadata={"svm": "svm01"})
            ]
        }
        processor = MagicMock()

        process_sqs_batch(event, processor)

        processor.assert_called_once_with("key1", "etag-x", {"svm": "svm01"})

    def test_failed_record_reports_message_id(self):
        event = {"Records": [make_sqs_record("msg-1", "key1")]}
        processor = MagicMock(side_effect=RuntimeError("ship failed"))

        result = process_sqs_batch(event, processor)

        assert result == {"batchItemFailures": [{"itemIdentifier": "msg-1"}]}

    def test_partial_batch_failure_only_reports_failed_records(self):
        event = {
            "Records": [
                make_sqs_record("msg-1", "key1"),
                make_sqs_record("msg-2", "key2"),
                make_sqs_record("msg-3", "key3"),
            ]
        }
        # key2 fails, key1 and key3 succeed.
        def processor(key, etag, metadata):
            if key == "key2":
                raise ValueError("boom")

        result = process_sqs_batch(event, processor)

        assert result == {"batchItemFailures": [{"itemIdentifier": "msg-2"}]}

    def test_malformed_json_body_reports_as_failure(self):
        event = {
            "Records": [
                {"messageId": "msg-bad", "body": "not valid json {"}
            ]
        }
        processor = MagicMock()

        result = process_sqs_batch(event, processor)

        assert result == {"batchItemFailures": [{"itemIdentifier": "msg-bad"}]}
        processor.assert_not_called()

    def test_missing_key_field_reports_as_failure(self):
        event = {
            "Records": [
                {"messageId": "msg-nokey", "body": json.dumps({"etag": "e1"})}
            ]
        }
        processor = MagicMock()

        result = process_sqs_batch(event, processor)

        assert result == {"batchItemFailures": [{"itemIdentifier": "msg-nokey"}]}

    def test_empty_records_returns_empty_failures(self):
        result = process_sqs_batch({"Records": []}, MagicMock())

        assert result == {"batchItemFailures": []}

    def test_missing_records_key_returns_empty_failures(self):
        result = process_sqs_batch({}, MagicMock())

        assert result == {"batchItemFailures": []}
