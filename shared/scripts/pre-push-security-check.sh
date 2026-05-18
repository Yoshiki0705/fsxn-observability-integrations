#!/bin/bash
set -euo pipefail

# Pre-Push Security Check
#
# Scans tracked files for sensitive data that should not be in a public repository.
# Run this before pushing to GitHub.
#
# Usage:
#   bash shared/scripts/pre-push-security-check.sh
#
# Exit codes:
#   0 = All checks passed
#   1 = Sensitive data found (DO NOT PUSH)
#
# NOTE: This script contains grep patterns for detection purposes.
# The patterns themselves are not sensitive data — they are used to FIND leaks.

REPO_ROOT="$(git rev-parse --show-toplevel)"
FAILED=0

# Load patterns from environment or use defaults
# These are the REAL values to search for — set via .env or export
ACCOUNT_ID_PATTERN="${SECURITY_CHECK_ACCOUNT_ID:-}"
SECRET_SUFFIX_PATTERN="${SECURITY_CHECK_SECRET_SUFFIX:-}"
RESOURCE_ID_PATTERNS="${SECURITY_CHECK_RESOURCE_IDS:-}"
IP_PATTERNS="${SECURITY_CHECK_IPS:-}"

if [[ -z "${ACCOUNT_ID_PATTERN}" ]]; then
  echo "⚠️  SECURITY_CHECK_ACCOUNT_ID not set. Skipping account ID check."
  echo "   Set it in .env or export SECURITY_CHECK_ACCOUNT_ID=<your-account-id>"
  echo ""
fi

echo "🔒 Pre-Push Security Check"
echo "=========================="
echo ""

# Check 1: AWS Account ID
if [[ -n "${ACCOUNT_ID_PATTERN}" ]]; then
  echo "📋 Check 1: AWS Account ID in tracked files..."
  if git ls-files | xargs grep -l "${ACCOUNT_ID_PATTERN}" 2>/dev/null; then
    echo "   ❌ FAIL: Real AWS account ID found in tracked files"
    echo "   Fix: Replace with 123456789012"
    FAILED=1
  else
    echo "   ✅ PASS"
  fi
  echo ""
fi

# Check 2: Secret ARN suffix
if [[ -n "${SECRET_SUFFIX_PATTERN}" ]]; then
  echo "📋 Check 2: Secret ARN suffix..."
  if git ls-files | xargs grep -l "${SECRET_SUFFIX_PATTERN}" 2>/dev/null; then
    echo "   ❌ FAIL: Real secret ARN suffix found"
    echo "   Fix: Replace with -XXXXXX"
    FAILED=1
  else
    echo "   ✅ PASS"
  fi
  echo ""
fi

# Check 3: Real resource IDs
if [[ -n "${RESOURCE_ID_PATTERNS}" ]]; then
  echo "📋 Check 3: Real AWS resource IDs..."
  if git ls-files | xargs grep -lE "${RESOURCE_ID_PATTERNS}" 2>/dev/null; then
    echo "   ❌ FAIL: Real resource IDs found"
    echo "   Fix: Replace with placeholder IDs (fs-0123456789abcdef0, etc.)"
    FAILED=1
  else
    echo "   ✅ PASS"
  fi
  echo ""
fi

# Check 4: Real IP addresses
if [[ -n "${IP_PATTERNS}" ]]; then
  echo "📋 Check 4: Real IP addresses..."
  if git ls-files | xargs grep -lE "${IP_PATTERNS}" 2>/dev/null; then
    echo "   ❌ FAIL: Real IP addresses found"
    echo "   Fix: Replace with <bastion-ip> or 10.0.x.x"
    FAILED=1
  else
    echo "   ✅ PASS"
  fi
  echo ""
fi

# Check 5: .kiro/ not tracked
echo "📋 Check 5: .kiro/ not in git tracking..."
KIRO_COUNT=$(git ls-files .kiro/ | wc -l | tr -d ' ')
if [ "${KIRO_COUNT}" -gt 0 ]; then
  echo "   ❌ FAIL: .kiro/ files are tracked (${KIRO_COUNT} files)"
  echo "   Fix: git rm --cached .kiro/ && verify .gitignore"
  FAILED=1
else
  echo "   ✅ PASS"
fi
echo ""

# Check 6: docs/blog/ not tracked
echo "📋 Check 6: docs/blog/ not in git tracking..."
BLOG_COUNT=$(git ls-files docs/blog/ | wc -l | tr -d ' ')
if [ "${BLOG_COUNT}" -gt 0 ]; then
  echo "   ❌ FAIL: docs/blog/ files are tracked (${BLOG_COUNT} files)"
  echo "   Fix: git rm --cached docs/blog/ && verify .gitignore"
  FAILED=1
else
  echo "   ✅ PASS"
fi
echo ""

# Check 7: .env not tracked
echo "📋 Check 7: .env not in git tracking..."
if git ls-files | grep -q "^\.env$"; then
  echo "   ❌ FAIL: .env is tracked"
  echo "   Fix: git rm --cached .env"
  FAILED=1
else
  echo "   ✅ PASS"
fi
echo ""

# Check 8: Personal SSH key paths
echo "📋 Check 8: Personal file paths..."
if git ls-files | xargs grep -lE "/Users/[^/]+/(Downloads|Library|Documents)/.*\\.pem" 2>/dev/null; then
  echo "   ❌ FAIL: Personal file paths found"
  echo "   Fix: Replace with environment variable references"
  FAILED=1
else
  echo "   ✅ PASS"
fi
echo ""

# Summary
echo "=========================="
if [ "${FAILED}" -eq 0 ]; then
  echo "✅ All security checks passed. Safe to push."
  exit 0
else
  echo "❌ Security checks FAILED. Fix issues above before pushing."
  exit 1
fi
