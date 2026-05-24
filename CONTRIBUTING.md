# Contributing

Thank you for your interest in contributing to FSx for ONTAP Observability Integrations.

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/Yoshiki0705/fsxn-observability-integrations/issues) for bug reports and feature requests
- Include your environment details (AWS region, vendor, Lambda runtime)
- For security issues, email directly instead of opening a public issue

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes following the code style below
4. Run tests: `python -m pytest integrations/<vendor>/tests/ -v`
5. Validate templates: `cfn-lint integrations/<vendor>/template.yaml`
6. Submit a PR with a clear description

### Priority Contribution Areas

- Additional vendor integrations (Axiom, Mezmo, Coralogix, Chronosphere)
- Terraform equivalents of CloudFormation templates
- CDK constructs
- Localization (Korean, Chinese, Portuguese)
- Benchmark data from different FSx for ONTAP configurations
- Bug fixes and documentation improvements

## Code Style

### Python (Lambda functions)

- Python 3.12, PEP 8
- Type hints required
- Google-style docstrings
- Use `urllib3` for HTTP (included in Lambda runtime), not `requests`
- Secrets from Secrets Manager, never environment variables

### CloudFormation (YAML)

- 2-space indent
- PascalCase resource logical IDs
- Always include: IAM least-privilege, DLQ, CloudWatch Alarms

### Documentation

- Bilingual: Japanese (primary) + English
- Same heading structure in both languages
- Code examples identical across languages

## Adding a New Vendor Integration

1. Create directory: `mkdir -p integrations/<vendor>/{lambda,docs/{ja,en},tests,scripts}`
2. Copy reference: use `integrations/grafana/` as the template
3. Implement `lambda/handler.py` with vendor-specific API formatting
4. Create `template.yaml`, `template-ems.yaml`, `template-fpolicy.yaml`
5. Write bilingual docs: `docs/ja/setup-guide.md` and `docs/en/setup-guide.md`
6. Add pytest tests with mocked API responses
7. Create `scripts/deploy.sh` and `scripts/cleanup.sh`
8. Update root `README.md` vendor table
9. Run the full test suite before submitting

## Testing

- All Lambda handler logic must have unit tests
- Mock all AWS service calls (boto3) and HTTP calls (urllib3)
- Use `conftest.py` for shared fixtures
- Tests must be deterministic (no real API calls)

```bash
# Run all tests
python -m pytest integrations/*/tests/ -v

# Run specific vendor
python -m pytest integrations/datadog/tests/ -v

# Validate CloudFormation
pip install cfn-lint
cfn-lint integrations/*/template.yaml
```

## Commit Convention

```
feat: add Axiom integration
fix: handle empty EVTX files in log parser
docs: update Datadog setup guide
test: add batch splitting edge case tests
chore: update cfn-lint to v1.x
```

Conventional Commits format. English only. Keep subject under 72 characters.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
