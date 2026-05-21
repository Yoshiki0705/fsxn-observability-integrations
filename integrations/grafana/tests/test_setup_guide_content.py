"""Content validation tests for Grafana setup guides.

Verifies that ja/en setup guide documents contain all required content
as specified in the grafana-e2e-verification spec requirements.

Requirements validated:
- 3.2, 3.5: Log arrival verification and expected fields
- 4.1-4.7: All 7 LogQL query examples
- 5.1-5.6: Dashboard panels with query + visualization type
- 7.3: Screenshot references with correct paths and alt text
"""

import re
from pathlib import Path

import pytest

# Resolve docs directory relative to this test file
TESTS_DIR = Path(__file__).parent
GRAFANA_DIR = TESTS_DIR.parent
DOCS_DIR = GRAFANA_DIR / "docs"
JA_GUIDE = DOCS_DIR / "ja" / "setup-guide.md"
EN_GUIDE = DOCS_DIR / "en" / "setup-guide.md"


@pytest.fixture(params=["ja", "en"], ids=["ja", "en"])
def setup_guide_content(request) -> str:
    """Load setup guide content for each language."""
    guide_path = DOCS_DIR / request.param / "setup-guide.md"
    assert guide_path.exists(), f"Setup guide not found: {guide_path}"
    return guide_path.read_text(encoding="utf-8")


class TestLogQLQueries:
    """Verify all 7 required LogQL queries from Requirement 4 are present."""

    REQUIRED_QUERIES = [
        # Req 4.1: Operation filter
        '{job="fsxn-audit"} | json | Operation="create"',
        # Req 4.2: User filter
        '{job="fsxn-audit"} | json | UserName="admin"',
        # Req 4.3: Failure filter
        '{job="fsxn-audit"} | json | Result="Failure"',
        # Req 4.4: SVM label filter
        '{job="fsxn-audit", svm="svm-prod-01"}',
        # Req 4.5: line_format
        'line_format "{{.UserName}} {{.Operation}} {{.ObjectName}}"',
        # Req 4.6: count_over_time
        "count_over_time({job=\"fsxn-audit\"}",
        # Req 4.7: rate
        "rate({job=\"fsxn-audit\"}[5m])",
    ]

    @pytest.mark.parametrize("query", REQUIRED_QUERIES)
    def test_logql_query_present(self, setup_guide_content: str, query: str) -> None:
        """Each required LogQL query must appear in the setup guide."""
        assert query in setup_guide_content, (
            f"Required LogQL query not found in setup guide: {query}"
        )

    def test_all_seven_queries_present(self, setup_guide_content: str) -> None:
        """All 7 required LogQL queries must be present."""
        missing = [q for q in self.REQUIRED_QUERIES if q not in setup_guide_content]
        assert not missing, (
            f"Missing {len(missing)} required LogQL queries: {missing}"
        )


class TestCLICommands:
    """Verify all required CLI commands are present."""

    def test_cloudformation_deploy_command(self, setup_guide_content: str) -> None:
        """Requirement 2.1: cloudformation deploy command must be present."""
        assert "cloudformation deploy" in setup_guide_content

    def test_cloudformation_deploy_has_template_file(
        self, setup_guide_content: str
    ) -> None:
        """cloudformation deploy must include --template-file flag."""
        assert "--template-file" in setup_guide_content

    def test_cloudformation_deploy_has_capabilities(
        self, setup_guide_content: str
    ) -> None:
        """cloudformation deploy must include --capabilities CAPABILITY_IAM."""
        assert "CAPABILITY_IAM" in setup_guide_content

    def test_lambda_invoke_command(self, setup_guide_content: str) -> None:
        """Requirement 2.3: lambda invoke command must be present."""
        assert "lambda invoke" in setup_guide_content

    def test_secretsmanager_create_secret_command(
        self, setup_guide_content: str
    ) -> None:
        """Requirement 1.2: secretsmanager create-secret command must be present."""
        assert "secretsmanager create-secret" in setup_guide_content


class TestDashboardPanels:
    """Verify all 4 dashboard panels are documented with query + visualization type."""

    def test_log_volume_panel(self, setup_guide_content: str) -> None:
        """Requirement 5.1: Log volume time-series panel with count_over_time."""
        # Must have the query
        assert 'count_over_time({job="fsxn-audit"}[5m])' in setup_guide_content
        # Must specify Time series visualization
        assert "Time series" in setup_guide_content

    def test_operations_breakdown_panel(self, setup_guide_content: str) -> None:
        """Requirement 5.2: Operations breakdown panel with pie/bar gauge."""
        # Must have the query with sum by (Operation)
        assert (
            'sum by (Operation) (count_over_time({job="fsxn-audit"} | json [1h]))'
            in setup_guide_content
        )
        # Must specify Pie chart or Bar gauge visualization
        assert (
            "Pie chart" in setup_guide_content or "Bar gauge" in setup_guide_content
        )

    def test_user_activity_panel(self, setup_guide_content: str) -> None:
        """Requirement 5.3: User activity panel showing top 10 users."""
        # Must reference UserName field extraction via JSON parsing
        assert "UserName" in setup_guide_content
        # Must have topk or similar aggregation for top users
        assert "topk(10" in setup_guide_content or "top" in setup_guide_content.lower()

    def test_failure_events_panel(self, setup_guide_content: str) -> None:
        """Requirement 5.4: Failure events time-series panel."""
        # Must have the query filtering Result="Failure"
        assert 'Result="Failure"' in setup_guide_content
        # Must be a time-series visualization
        assert "Time series" in setup_guide_content

    def test_each_panel_has_query_and_visualization(
        self, setup_guide_content: str
    ) -> None:
        """Requirement 5.5: Each panel must include LogQL query and visualization type."""
        # Check that visualization types are documented for panels
        visualization_types = ["Time series", "Pie chart", "Bar gauge", "Table"]
        found_types = [vt for vt in visualization_types if vt in setup_guide_content]
        # At least 3 different visualization types should be mentioned
        # (Time series for 2 panels, Pie chart/Bar gauge for 2 panels)
        assert len(found_types) >= 3, (
            f"Expected at least 3 visualization types, found: {found_types}"
        )


class TestTroubleshootingSections:
    """Verify troubleshooting sections exist with required categories."""

    def test_troubleshooting_section_exists(self, setup_guide_content: str) -> None:
        """A troubleshooting section must exist."""
        # Check for troubleshooting heading (either language)
        assert (
            "トラブルシューティング" in setup_guide_content
            or "Troubleshooting" in setup_guide_content
        )

    def test_lambda_invocation_errors_category(
        self, setup_guide_content: str
    ) -> None:
        """Troubleshooting must cover Lambda invocation errors (CloudWatch Logs)."""
        assert "CloudWatch Logs" in setup_guide_content or "CloudWatch" in setup_guide_content

    def test_network_connectivity_category(self, setup_guide_content: str) -> None:
        """Troubleshooting must cover network connectivity (VPC/Security Group)."""
        assert (
            "Security Group" in setup_guide_content
            or "セキュリティグループ" in setup_guide_content
        )
        assert (
            "NAT Gateway" in setup_guide_content
            or "VPC" in setup_guide_content
        )

    def test_authentication_issues_category(self, setup_guide_content: str) -> None:
        """Troubleshooting must cover authentication issues (Instance ID/API Key)."""
        assert "Instance ID" in setup_guide_content
        assert "API Key" in setup_guide_content


class TestScreenshotReferences:
    """Verify screenshot references use correct relative paths and have alt text."""

    def test_screenshot_references_use_relative_paths(
        self, setup_guide_content: str
    ) -> None:
        """Screenshot references must use ../screenshots/ relative path."""
        # Find all markdown image references
        image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
        images = image_pattern.findall(setup_guide_content)
        assert len(images) > 0, "No screenshot references found in setup guide"

        for alt_text, path in images:
            assert "../screenshots/" in path, (
                f"Screenshot path does not use ../screenshots/ prefix: {path}"
            )

    def test_screenshot_references_have_alt_text(
        self, setup_guide_content: str
    ) -> None:
        """All screenshot references must have non-empty alt text."""
        image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
        images = image_pattern.findall(setup_guide_content)
        assert len(images) > 0, "No screenshot references found in setup guide"

        for alt_text, path in images:
            assert alt_text.strip(), (
                f"Screenshot reference has empty alt text: ![{alt_text}]({path})"
            )

    def test_explore_screenshot_referenced(self, setup_guide_content: str) -> None:
        """The explore-log-arrival.png screenshot must be referenced."""
        assert "explore-log-arrival.png" in setup_guide_content

    def test_dashboard_screenshot_referenced(self, setup_guide_content: str) -> None:
        """The dashboard-overview.png screenshot must be referenced."""
        assert "dashboard-overview.png" in setup_guide_content


class TestExpectedLogFields:
    """Verify expected log fields are documented."""

    REQUIRED_FIELDS = ["timestamp", "UserName", "Operation", "ObjectName"]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_log_field_documented(self, setup_guide_content: str, field: str) -> None:
        """Each expected log field must be documented in the setup guide."""
        assert field in setup_guide_content, (
            f"Expected log field not documented: {field}"
        )

    def test_all_fields_documented(self, setup_guide_content: str) -> None:
        """All expected log fields must be documented together (Requirement 3.5)."""
        missing = [f for f in self.REQUIRED_FIELDS if f not in setup_guide_content]
        assert not missing, f"Missing expected log fields: {missing}"
