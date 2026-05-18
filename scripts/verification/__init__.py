"""E2E verification package.

Provides tools for end-to-end verification of vendor integrations
(Datadog, New Relic), including bilingual document comparison,
results rendering, and screenshot validation.
"""

from scripts.verification.models import (
    AlertConditionConfig,
    BilingualComparisonResult,
    BilingualDifference,
    DemoScenarioTimeline,
    Heading,
    Issue,
    LogAttributeValidation,
    MarkdownStructure,
    NewRelicVerificationEnvironment,
    NRQLQueryResult,
    Table,
    VerificationEnvironment,
    VerificationReport,
    VerificationStep,
    VerifierInfo,
)

__all__ = [
    "AlertConditionConfig",
    "BilingualComparisonResult",
    "BilingualDifference",
    "DemoScenarioTimeline",
    "Heading",
    "Issue",
    "LogAttributeValidation",
    "MarkdownStructure",
    "NewRelicVerificationEnvironment",
    "NRQLQueryResult",
    "Table",
    "VerificationEnvironment",
    "VerificationReport",
    "VerificationStep",
    "VerifierInfo",
]
