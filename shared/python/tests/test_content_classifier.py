"""Unit tests for content_classifier module.

Tests cover:
- Text chunking under Comprehend's byte-size ceiling
- Per-file PII classification (clean, PII found, read/decode/comprehend errors)
- File sampling for oversized files
- Volume-level orchestration (scannable-extension filtering, max_files cap,
  aggregate density counts)
- Language code validation
"""

import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).parent.parent))

from content_classifier import (
    ContentClassifier,
    ContentClassifierError,
    COMPREHEND_MAX_BYTES,
    _chunk_text,
)


def _streaming_body(data: bytes) -> MagicMock:
    body = MagicMock()
    body.read.return_value = data
    return body


@pytest.fixture
def s3_client():
    return MagicMock()


@pytest.fixture
def comprehend_client():
    return MagicMock()


@pytest.fixture
def classifier(s3_client, comprehend_client):
    return ContentClassifier(s3_client=s3_client, comprehend_client=comprehend_client)


# ==========================================================================
# Text chunking
# ==========================================================================


class TestChunkText:
    def test_empty_text(self):
        assert _chunk_text("") == []

    def test_small_text_single_chunk(self):
        text = "line1\nline2\nline3\n"
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_large_text_splits_into_multiple_chunks(self):
        # Build text well over the target chunk size using repeated lines.
        line = "x" * 1000 + "\n"
        text = line * 200  # ~200KB, well over the ~98KB target
        chunks = _chunk_text(text, target_bytes=50_000)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 50_000 + 1001  # allow one line's slack

    def test_reassembled_chunks_preserve_content(self):
        line = "abc123\n"
        text = line * 50
        chunks = _chunk_text(text, target_bytes=100)
        assert "".join(chunks) == text

    def test_single_line_exceeding_target_is_hard_split(self):
        text = "a" * 500  # one line, no newline, exceeds target
        chunks = _chunk_text(text, target_bytes=100)
        assert len(chunks) == 5
        assert "".join(chunks) == text

    def test_default_target_is_below_comprehend_limit(self):
        from content_classifier import CHUNK_TARGET_BYTES
        assert CHUNK_TARGET_BYTES < COMPREHEND_MAX_BYTES


# ==========================================================================
# Per-file classification
# ==========================================================================


class TestClassifyObject:
    def test_no_pii_found(self, classifier, s3_client, comprehend_client):
        s3_client.get_object.return_value = {"Body": _streaming_body(b"hello world, nothing sensitive here")}
        comprehend_client.detect_pii_entities.return_value = {"Entities": []}

        finding = classifier.classify_object(
            "arn:aws:s3:::ap/test", "notes.txt", size_bytes=100
        )

        assert finding.entity_counts == {}
        assert finding.error == ""
        assert finding.sampled is False

    def test_pii_found_aggregates_counts_and_confidence(self, classifier, s3_client, comprehend_client):
        s3_client.get_object.return_value = {
            "Body": _streaming_body(b"Contact jdoe@example.com or call 555-1234")
        }
        comprehend_client.detect_pii_entities.return_value = {
            "Entities": [
                {"Type": "EMAIL", "Score": 0.99, "BeginOffset": 8, "EndOffset": 24},
                {"Type": "PHONE", "Score": 0.85, "BeginOffset": 33, "EndOffset": 41},
            ]
        }

        finding = classifier.classify_object("arn:aws:s3:::ap/test", "contacts.txt", size_bytes=42)

        assert finding.entity_counts == {"EMAIL": 1, "PHONE": 1}
        assert finding.highest_confidence_by_type["EMAIL"] == 0.99
        assert finding.highest_confidence_by_type["PHONE"] == 0.85

    def test_multiple_chunks_aggregate_across_calls(self, classifier, s3_client, comprehend_client, monkeypatch):
        s3_client.get_object.return_value = {"Body": _streaming_body(b"chunk data")}
        monkeypatch.setattr(
            "content_classifier._chunk_text", lambda text, target_bytes=0: ["chunk1", "chunk2"]
        )
        comprehend_client.detect_pii_entities.side_effect = [
            {"Entities": [{"Type": "EMAIL", "Score": 0.9}]},
            {"Entities": [{"Type": "EMAIL", "Score": 0.95}, {"Type": "SSN", "Score": 0.99}]},
        ]

        finding = classifier.classify_object("arn:aws:s3:::ap/test", "big.txt", size_bytes=1000)

        assert finding.entity_counts == {"EMAIL": 2, "SSN": 1}
        assert finding.highest_confidence_by_type["EMAIL"] == 0.95  # max across both calls
        assert comprehend_client.detect_pii_entities.call_count == 2

    def test_read_failure_sets_error_does_not_raise(self, classifier, s3_client):
        s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
        )

        finding = classifier.classify_object("arn:aws:s3:::ap/test", "missing.txt", size_bytes=10)

        assert finding.error.startswith("read_failed")
        assert finding.entity_counts == {}

    def test_comprehend_failure_sets_error_continues(self, classifier, s3_client, comprehend_client):
        s3_client.get_object.return_value = {"Body": _streaming_body(b"some text content here")}
        comprehend_client.detect_pii_entities.side_effect = ClientError(
            {"Error": {"Code": "TextSizeLimitExceededException", "Message": "too big"}},
            "DetectPiiEntities",
        )

        finding = classifier.classify_object("arn:aws:s3:::ap/test", "notes.txt", size_bytes=100)

        assert finding.error.startswith("comprehend_failed")

    def test_empty_file_skips_comprehend_call(self, classifier, s3_client, comprehend_client):
        s3_client.get_object.return_value = {"Body": _streaming_body(b"   \n\n  ")}

        finding = classifier.classify_object("arn:aws:s3:::ap/test", "empty.txt", size_bytes=10)

        comprehend_client.detect_pii_entities.assert_not_called()
        assert finding.entity_counts == {}

    def test_oversized_file_uses_range_read(self, s3_client, comprehend_client):
        classifier = ContentClassifier(
            s3_client=s3_client,
            comprehend_client=comprehend_client,
            max_file_bytes=1000,
            sample_bytes=500,
        )
        s3_client.get_object.return_value = {"Body": _streaming_body(b"partial content")}
        comprehend_client.detect_pii_entities.return_value = {"Entities": []}

        finding = classifier.classify_object("arn:aws:s3:::ap/test", "huge.csv", size_bytes=10_000)

        assert finding.sampled is True
        call_kwargs = s3_client.get_object.call_args[1]
        assert call_kwargs["Range"] == "bytes=0-499"

    def test_to_dict_rounds_confidence(self, classifier, s3_client, comprehend_client):
        s3_client.get_object.return_value = {"Body": _streaming_body(b"data")}
        comprehend_client.detect_pii_entities.return_value = {
            "Entities": [{"Type": "EMAIL", "Score": 0.987654321}]
        }
        finding = classifier.classify_object("arn:aws:s3:::ap/test", "f.txt", size_bytes=4)
        d = finding.to_dict()
        assert d["highest_confidence_by_type"]["EMAIL"] == 0.9877


# ==========================================================================
# Volume-level orchestration
# ==========================================================================


class TestClassifyAccessPoint:
    def test_invalid_language_code_raises(self, classifier):
        with pytest.raises(ContentClassifierError, match="Unsupported language_code"):
            classifier.classify_access_point("arn:aws:s3:::ap/test", language_code="xx")

    def test_skips_unscannable_extensions(self, classifier, s3_client):
        s3_client.get_paginator.return_value.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "photo.jpg", "Size": 1000},
                    {"Key": "archive.zip", "Size": 2000},
                    {"Key": "binary.exe", "Size": 3000},
                ]
            }
        ]

        report = classifier.classify_access_point("arn:aws:s3:::ap/test")

        assert report.files_scanned == 0
        assert report.files_skipped_unscannable == 3

    def test_skips_zero_byte_files(self, classifier, s3_client):
        s3_client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "empty.txt", "Size": 0}]}
        ]

        report = classifier.classify_access_point("arn:aws:s3:::ap/test")

        assert report.files_scanned == 0

    def test_scans_and_aggregates_pii_density(self, classifier, s3_client, comprehend_client):
        s3_client.get_paginator.return_value.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "a.txt", "Size": 50},
                    {"Key": "b.csv", "Size": 60},
                ]
            }
        ]
        s3_client.get_object.side_effect = [
            {"Body": _streaming_body(b"email: jdoe@example.com")},
            {"Body": _streaming_body(b"email: jane@example.com and ssn 123-45-6789")},
        ]
        comprehend_client.detect_pii_entities.side_effect = [
            {"Entities": [{"Type": "EMAIL", "Score": 0.9}]},
            {"Entities": [{"Type": "EMAIL", "Score": 0.9}, {"Type": "SSN", "Score": 0.95}]},
        ]

        report = classifier.classify_access_point("arn:aws:s3:::ap/test")

        assert report.files_scanned == 2
        assert report.files_with_pii == 2
        assert report.pii_density_by_type == {"EMAIL": 2, "SSN": 1}
        assert report.started_at
        assert report.completed_at

    def test_clean_files_not_added_to_findings(self, classifier, s3_client, comprehend_client):
        s3_client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "clean.txt", "Size": 20}]}
        ]
        s3_client.get_object.return_value = {"Body": _streaming_body(b"nothing sensitive")}
        comprehend_client.detect_pii_entities.return_value = {"Entities": []}

        report = classifier.classify_access_point("arn:aws:s3:::ap/test")

        assert report.files_scanned == 1
        assert report.files_with_pii == 0
        assert report.findings == []

    def test_error_files_added_to_findings(self, classifier, s3_client):
        s3_client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "broken.txt", "Size": 20}]}
        ]
        s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject"
        )

        report = classifier.classify_access_point("arn:aws:s3:::ap/test")

        assert len(report.findings) == 1
        assert report.findings[0].error.startswith("read_failed")

    def test_max_files_cap_stops_scanning(self, classifier, s3_client, comprehend_client):
        s3_client.get_paginator.return_value.paginate.return_value = [
            {
                "Contents": [
                    {"Key": f"file{i}.txt", "Size": 10} for i in range(10)
                ]
            }
        ]
        s3_client.get_object.return_value = {"Body": _streaming_body(b"text")}
        comprehend_client.detect_pii_entities.return_value = {"Entities": []}

        report = classifier.classify_access_point("arn:aws:s3:::ap/test", max_files=3)

        assert report.files_scanned == 3

    def test_report_to_dict_caps_findings(self, classifier):
        from content_classifier import ClassificationReport, FileFinding

        report = ClassificationReport(access_point_arn="arn:test", language_code="en")
        report.findings = [
            FileFinding(key=f"f{i}.txt", size_bytes=10, sampled=False, entity_counts={"EMAIL": 1})
            for i in range(150)
        ]
        d = report.to_dict(max_findings=100)
        assert len(d["findings"]) == 100
        assert d["finding_count"] == 150

    def test_sampled_files_tracked_separately(self, s3_client, comprehend_client):
        classifier = ContentClassifier(
            s3_client=s3_client, comprehend_client=comprehend_client, max_file_bytes=100,
        )
        s3_client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "huge.txt", "Size": 100_000}]}
        ]
        s3_client.get_object.return_value = {"Body": _streaming_body(b"sampled content")}
        comprehend_client.detect_pii_entities.return_value = {"Entities": []}

        report = classifier.classify_access_point("arn:aws:s3:::ap/test")

        assert report.files_sampled_too_large == 1
