# CI Policy and Quality Gates

🌐 [日本語](../ja/ci-policy.md) | **English** (this page)

## Current CI Jobs

| Job | Tool | Blocking | Purpose |
|-----|------|----------|---------|
| lint-and-test | npm, pytest, cfn-lint | Yes | Code quality and template validation |
| cfn-guard | CloudFormation Guard | No (continue-on-error) | Policy-as-code for CloudFormation |
| security-scan | Trivy, custom checks | Yes | Vulnerability and secret detection |
| markdown-links | markdown-link-check | No (continue-on-error) | Documentation link integrity |
| actionlint | actionlint | No (continue-on-error) | GitHub Actions workflow syntax |

## Current Enforcement Status

| Check | Current Mode | Target Mode |
|---|---|---|
| cfn-lint | Blocking | Blocking |
| cfn-guard | Non-blocking | Blocking on main after rule tuning |
| markdown-link-check | Non-blocking | Blocking with external-link ignore rules |
| actionlint | Non-blocking | Blocking |
| Trivy | Blocking for high/critical findings | Blocking |

## cfn-guard Adoption Roadmap

```
Phase 1 (current): continue-on-error: true
  - Observe rule violations
  - Identify false positives

Phase 2: Adjust rules
  - Suppress known false positives
  - Add integration-specific rule files

Phase 3: Blocking on main
  - Remove continue-on-error for main branch pushes
  - PRs must pass cfn-guard

Phase 4: Release gate
  - Release tags require full cfn-guard pass
  - No exceptions without documented waiver
```

## cfn-guard Rule Organization

Rules are organized by scope to reduce false positives:

```
guard/rules/
├── lambda-security.guard       # Common Lambda best practices
├── secrets-management.guard    # Secrets Manager and NoEcho rules
├── audit-poller.guard          # (planned) Scheduler + checkpoint patterns
├── webhook-handler.guard       # (planned) API Gateway + sync invocation
└── eventbridge-handler.guard   # (planned) EventBridge + SQS patterns
```

Not all Lambda functions require a DLQ directly:
- **Audit poller**: Uses Scheduler DLQ (not Lambda DLQ)
- **EMS webhook**: Synchronous API Gateway invocation; failure response + alarm is primary
- **FPolicy handler**: SQS source-side DLQ handles failures

## Security Scan Coverage

### Trivy (filesystem scan)
- Dependency vulnerability detection (Python, Node.js)
- IaC misconfiguration detection
- Secret pattern detection

### Custom Security Checks
- `.kiro/` directory not tracked in git
- `docs/blog/` directory not tracked in git
- `.env` file not tracked in git
- No personal file paths (PEM keys, user directories)

### Token Pattern Handling
This repository contains many example token patterns (Datadog API keys, Splunk HEC tokens, Grafana API tokens). To avoid false positives:
- All example tokens use clearly fake values (e.g., `dd-api-key-placeholder`)
- Real tokens are stored in AWS Secrets Manager only
- CI checks for patterns that look like real tokens (length, prefix, entropy)

## Markdown Link Check

External links may produce flaky failures due to rate limiting or temporary outages. The `.markdown-link-check.json` configuration:
- Retries on HTTP 429 (rate limited) up to 3 times
- Ignores `dev.to` links (frequent 403 for automated checks)
- Uses 20-second timeout
- Runs as non-blocking (continue-on-error)

If a link check fails in CI:
1. Check if the link is actually broken (manual verification)
2. If flaky: add to `ignorePatterns` in `.markdown-link-check.json`
3. If broken: fix the link in the source document

## Related Documents

- [Security Review Checklist](security-review-checklist.md)
- [Governance and Compliance](governance-and-compliance.md)
