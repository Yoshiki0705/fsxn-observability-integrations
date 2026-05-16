"""Datadog E2E verification package.

Provides tools for end-to-end verification of the Datadog integration,
including bilingual document comparison, results rendering, and
screenshot validation.
"""

from scripts.verification.models import (
    BilingualComparisonResult,
    BilingualDifference,
    Heading,
    Issue,
    MarkdownStructure,
    Table,
    VerificationEnvironment,
    VerificationReport,
    VerificationStep,
    VerifierInfo,
)

__all__ = [
    "BilingualComparisonResult",
    "BilingualDifference",
    "Heading",
    "Issue",
    "MarkdownStructure",
    "Table",
    "VerificationEnvironment",
    "VerificationReport",
    "VerificationStep",
    "VerifierInfo",
]
