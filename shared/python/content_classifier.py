"""Content-level PII discovery for FSx for ONTAP volumes (CSF 2.0 Identify).

Closes the gap documented in the DII Capability Map: this repository's
[Data Classification Guide](../../docs/en/data-classification.md) defines a
schema-level classification (which *fields* — UserName, ObjectName — are
PII), but did not scan file *contents* the way NetApp's data classification
service does for the CSF 2.0 Identify function. This module adds that
content-level scan using AWS-native services only.

Architecture (same isolation pattern as restore_verification.py):
    1. Read files through a (typically FlexClone-backed) S3 Access Point —
       never scans the live production volume directly.
    2. For each text-bearing file under a size ceiling, extract plain text
       and call Amazon Comprehend's DetectPiiEntities in language-appropriate,
       size-bounded chunks (DetectPiiEntities has both a UTF-8 byte-size limit
       and a supported-language list — see _chunk_text).
    3. Aggregate findings per file: which PII entity types were found, at
       what confidence, without persisting the PII values themselves — only
       entity type, offset, and confidence score are recorded.
    4. Produce a per-volume classification report summarizing PII density
       by entity type and by file, for the Identify-function output this
       repo's Data Classification Guide does not currently provide.

This module does NOT attempt content classification beyond PII detection
(e.g., trade secrets, intellectual property) — Comprehend's managed PII
entity types are the scope. It also does not redact or modify files; it is
read-only, discovery-only, matching the CSF 2.0 Identify function's scope
(inventory and understanding, not remediation).

Usage:
    from content_classifier import ContentClassifier

    classifier = ContentClassifier(region="ap-northeast-1")
    report = classifier.classify_access_point(
        access_point_arn="arn:aws:s3:...:accesspoint/verify-vol-data",
        language_code="en",
        max_files=500,
    )
    # report.pii_density_by_type -> {"EMAIL": 42, "SSN": 3, ...}

Reference:
    Amazon Comprehend DetectPiiEntities: https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html
    Supported languages: https://docs.aws.amazon.com/comprehend/latest/dg/supported-languages.html
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Amazon Comprehend DetectPiiEntities: max input size is 100 KB (102400
# bytes) of UTF-8 text per call. Chunk below that with margin for multi-byte
# character boundaries.
COMPREHEND_MAX_BYTES = 100_000
CHUNK_SAFETY_MARGIN_BYTES = 2_000
CHUNK_TARGET_BYTES = COMPREHEND_MAX_BYTES - CHUNK_SAFETY_MARGIN_BYTES

# File extensions treated as scannable plain/structured text. Binary
# formats (images, archives, most Office formats without extraction) are
# skipped — this module does not implement document-format parsing.
SCANNABLE_EXTENSIONS = frozenset({
    ".txt", ".csv", ".tsv", ".json", ".xml", ".log", ".md",
    ".yaml", ".yml", ".ini", ".conf", ".sql", ".html", ".htm",
})

# Skip files above this size to bound Comprehend API call volume and cost
# per file. Large files are sampled (first N bytes) rather than skipped
# entirely — see classify_object's sampling behavior.
DEFAULT_MAX_FILE_BYTES = 5_000_000  # 5 MB
DEFAULT_SAMPLE_BYTES = 500_000  # 500 KB — read only the head of large files

# Amazon Comprehend DetectPiiEntities supported languages as of this
# writing. Verify against AWS docs if adding a new language_code.
COMPREHEND_SUPPORTED_LANGUAGES = frozenset({
    "en", "es", "fr", "de", "it", "pt", "ar", "hi", "ja", "ko", "zh", "zh-TW",
})


class ContentClassifierError(Exception):
    """Raised when a step in the content classification workflow fails."""

    def __init__(self, message: str, step: str = "") -> None:
        super().__init__(message)
        self.step = step


@dataclass
class FileFinding:
    """PII entities found in a single file."""

    key: str
    size_bytes: int
    sampled: bool  # True if only a leading portion of the file was scanned
    entity_counts: dict[str, int] = field(default_factory=dict)
    highest_confidence_by_type: dict[str, float] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "size_bytes": self.size_bytes,
            "sampled": self.sampled,
            "entity_counts": self.entity_counts,
            "highest_confidence_by_type": {
                k: round(v, 4) for k, v in self.highest_confidence_by_type.items()
            },
            "error": self.error,
        }


@dataclass
class ClassificationReport:
    """Aggregate PII discovery result for a volume/access point."""

    access_point_arn: str
    language_code: str
    files_scanned: int = 0
    files_skipped_unscannable: int = 0
    files_sampled_too_large: int = 0
    files_with_pii: int = 0
    pii_density_by_type: dict[str, int] = field(default_factory=dict)
    findings: list[FileFinding] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self, max_findings: int = 100) -> dict[str, Any]:
        return {
            "access_point_arn": self.access_point_arn,
            "language_code": self.language_code,
            "files_scanned": self.files_scanned,
            "files_skipped_unscannable": self.files_skipped_unscannable,
            "files_sampled_too_large": self.files_sampled_too_large,
            "files_with_pii": self.files_with_pii,
            "pii_density_by_type": self.pii_density_by_type,
            "findings": [f.to_dict() for f in self.findings[:max_findings]],
            "finding_count": len(self.findings),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


def _chunk_text(text: str, target_bytes: int = CHUNK_TARGET_BYTES) -> list[str]:
    """Split text into UTF-8 byte-bounded chunks, breaking on line boundaries
    where possible so entities aren't split across a chunk boundary more
    than necessary.

    Comprehend's DetectPiiEntities enforces a UTF-8 byte-size ceiling per
    call (not a character-count ceiling), so this chunks by encoded byte
    length rather than len(text).
    """
    if not text:
        return []

    chunks: list[str] = []
    current_lines: list[str] = []
    current_bytes = 0

    for line in text.splitlines(keepends=True):
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > target_bytes:
            # A single line exceeds the chunk size on its own — hard-split
            # it by byte length. Rare (e.g., minified JSON on one line).
            if current_lines:
                chunks.append("".join(current_lines))
                current_lines, current_bytes = [], 0
            encoded = line.encode("utf-8")
            for i in range(0, len(encoded), target_bytes):
                chunks.append(encoded[i:i + target_bytes].decode("utf-8", errors="ignore"))
            continue

        if current_bytes + line_bytes > target_bytes and current_lines:
            chunks.append("".join(current_lines))
            current_lines, current_bytes = [], 0

        current_lines.append(line)
        current_bytes += line_bytes

    if current_lines:
        chunks.append("".join(current_lines))

    return chunks


class ContentClassifier:
    """Scans files exposed via an S3 Access Point for PII content.

    Args:
        region: AWS region for the s3/comprehend boto3 clients.
        s3_client: Optional pre-configured boto3 s3 client (for testing).
        comprehend_client: Optional pre-configured boto3 comprehend client
            (for testing).
        max_file_bytes: Files larger than this are sampled, not skipped —
            see sample_bytes.
        sample_bytes: For files exceeding max_file_bytes, only the first
            this-many bytes are read and scanned (a range GetObject read).
    """

    def __init__(
        self,
        region: str | None = None,
        s3_client: Any | None = None,
        comprehend_client: Any | None = None,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        sample_bytes: int = DEFAULT_SAMPLE_BYTES,
    ) -> None:
        self._s3 = s3_client or boto3.client("s3", region_name=region)
        self._comprehend = comprehend_client or boto3.client("comprehend", region_name=region)
        self.max_file_bytes = max_file_bytes
        self.sample_bytes = sample_bytes

    # ------------------------------------------------------------------
    # Per-file classification
    # ------------------------------------------------------------------

    def classify_object(
        self, access_point_arn: str, key: str, size_bytes: int, language_code: str = "en"
    ) -> FileFinding:
        """Read and scan a single object for PII entities.

        Args:
            access_point_arn: ARN of the S3 Access Point to read from.
            key: Object key.
            size_bytes: Object size, as reported by ListObjectsV2 (avoids an
                extra HeadObject call).
            language_code: Comprehend language code for DetectPiiEntities.

        Returns:
            FileFinding with aggregated entity counts and confidence scores.
            On a read or Comprehend error, returns a FileFinding with the
            `error` field set rather than raising, so a single bad file
            doesn't abort a whole-volume scan.
        """
        sampled = size_bytes > self.max_file_bytes
        finding = FileFinding(key=key, size_bytes=size_bytes, sampled=sampled)

        try:
            if sampled:
                resp = self._s3.get_object(
                    Bucket=access_point_arn, Key=key, Range=f"bytes=0-{self.sample_bytes - 1}"
                )
            else:
                resp = self._s3.get_object(Bucket=access_point_arn, Key=key)
            raw = resp["Body"].read()
        except ClientError as e:
            finding.error = f"read_failed: {e}"
            return finding

        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001 - defensive, decode() rarely raises with errors="ignore"
            finding.error = f"decode_failed: {e}"
            return finding

        if not text.strip():
            return finding

        for chunk in _chunk_text(text):
            if not chunk.strip():
                continue
            try:
                resp = self._comprehend.detect_pii_entities(
                    Text=chunk, LanguageCode=language_code
                )
            except ClientError as e:
                finding.error = f"comprehend_failed: {e}"
                continue

            for entity in resp.get("Entities", []):
                entity_type = entity.get("Type", "UNKNOWN")
                score = entity.get("Score", 0.0)
                finding.entity_counts[entity_type] = finding.entity_counts.get(entity_type, 0) + 1
                finding.highest_confidence_by_type[entity_type] = max(
                    finding.highest_confidence_by_type.get(entity_type, 0.0), score
                )

        return finding

    # ------------------------------------------------------------------
    # Volume-level orchestration
    # ------------------------------------------------------------------

    def classify_access_point(
        self,
        access_point_arn: str,
        language_code: str = "en",
        max_files: int = 1000,
    ) -> ClassificationReport:
        """Scan every scannable object exposed via an S3 Access Point.

        Args:
            access_point_arn: ARN of the S3 Access Point (typically attached
                to a FlexClone via restore_verification.py, so this never
                touches the production volume directly).
            language_code: Comprehend language code. Must be one of
                COMPREHEND_SUPPORTED_LANGUAGES.
            max_files: Cap on the number of files scanned per run, to bound
                cost and runtime on large volumes. Files beyond this cap are
                not scanned (not counted as skipped-too-large).

        Returns:
            ClassificationReport with per-file findings and aggregate PII
            density by entity type.
        """
        if language_code not in COMPREHEND_SUPPORTED_LANGUAGES:
            raise ContentClassifierError(
                f"Unsupported language_code '{language_code}' — must be one of "
                f"{sorted(COMPREHEND_SUPPORTED_LANGUAGES)}",
                step="validate_language",
            )

        report = ClassificationReport(
            access_point_arn=access_point_arn,
            language_code=language_code,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        scanned_count = 0
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=access_point_arn, MaxKeys=1000):
            for obj in page.get("Contents", []):
                if scanned_count >= max_files:
                    break

                key = obj["Key"]
                size_bytes = obj.get("Size", 0)
                lower_key = key.lower()

                if not any(lower_key.endswith(ext) for ext in SCANNABLE_EXTENSIONS):
                    report.files_skipped_unscannable += 1
                    continue

                if size_bytes == 0:
                    continue

                finding = self.classify_object(access_point_arn, key, size_bytes, language_code)
                scanned_count += 1
                report.files_scanned += 1

                if finding.sampled:
                    report.files_sampled_too_large += 1
                if finding.entity_counts:
                    report.files_with_pii += 1
                    report.findings.append(finding)
                    for entity_type, count in finding.entity_counts.items():
                        report.pii_density_by_type[entity_type] = (
                            report.pii_density_by_type.get(entity_type, 0) + count
                        )
                elif finding.error:
                    report.findings.append(finding)

            if scanned_count >= max_files:
                break

        report.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Content classification complete: %d files scanned, %d with PII, "
            "%d unscannable extensions skipped",
            report.files_scanned, report.files_with_pii, report.files_skipped_unscannable,
        )
        return report
