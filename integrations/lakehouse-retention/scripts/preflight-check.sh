#!/usr/bin/env bash
# preflight-check.sh — Pre-deployment checks for the lakehouse retention pipeline.
#
# Checks for the Lake Formation gotcha found during E2E verification: if AWS
# Lake Formation is enabled anywhere in this AWS account (even for an
# unrelated Glue database), the Firehose delivery role's IAM policy alone is
# NOT sufficient for Firehose's DataFormatConversionConfiguration to reach
# the Glue Data Catalog. template.yaml already includes the required
# AWS::LakeFormation::PrincipalPermissions resources, but this script surfaces
# the check up front so a failed deployment isn't the first sign of it.
#
# Usage:
#   bash scripts/preflight-check.sh [--region ap-northeast-1]
#
# Exit codes (BSD sysexits.h-compatible, matching this repo's other preflight
# scripts):
#   0  - all checks passed
#   78 - configuration issue found (Lake Formation admin access needed, etc.)
#   75 - temporary failure (could not reach AWS API)
#   2  - usage error

set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
SKIP="${PREFLIGHT_SKIP:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)
      REGION="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${SKIP}" == "true" ]]; then
  echo "[SKIP] PREFLIGHT_SKIP=true — skipping all checks (CI/CD mode)."
  exit 0
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }

echo "Region: ${REGION}"
echo ""

# --- Check 1: AWS CLI reachability ---
if ! aws sts get-caller-identity --region "${REGION}" > /dev/null 2>&1; then
  fail "Could not call AWS STS. Check your AWS credentials/region and try again."
  exit 75
fi
pass "AWS credentials are valid."

# --- Check 2: Lake Formation status ---
echo ""
echo "Checking whether AWS Lake Formation is enabled in this account..."
LF_ADMINS_JSON=$(aws lakeformation get-data-lake-settings --region "${REGION}" \
  --query "DataLakeSettings.DataLakeAdmins" --output json 2>/dev/null || echo "[]")
LF_ADMIN_COUNT=$(echo "${LF_ADMINS_JSON}" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ "${LF_ADMIN_COUNT}" -gt 0 ]]; then
  warn "Lake Formation is active in this account (${LF_ADMIN_COUNT} data lake admin(s) configured)."
  warn "template.yaml already includes AWS::LakeFormation::PrincipalPermissions grants for the"
  warn "Firehose delivery role, so deployment should still succeed. However:"
  warn "  - If the principal deploying this stack is NOT a Lake Formation admin, creating"
  warn "    AWS::LakeFormation::PrincipalPermissions resources may itself require elevated"
  warn "    permissions. Ask a Lake Formation admin to run this deployment, or to grant"
  warn "    the deploying principal 'lakeformation:GrantPermissions' first."
  warn "  - If you fork this template and REMOVE the LakeFormation::PrincipalPermissions"
  warn "    resources, the Firehose delivery stream will fail with:"
  warn "    'Insufficient Lake Formation permission(s): Required Describe on <table>'"
  echo ""
  echo "Current data lake admins:"
  echo "${LF_ADMINS_JSON}" | python3 -m json.tool 2>/dev/null || echo "${LF_ADMINS_JSON}"
else
  pass "Lake Formation does not appear to have any data lake admins configured (or the"
  pass "calling principal cannot see them). Deployment should not hit the Lake Formation"
  pass "permission gotcha, but this is not a guarantee — Lake Formation catalog settings"
  pass "can still be scoped per-database. If deployment fails with a 'Lake Formation"
  pass "permission' error despite this check passing, see docs/en/lakehouse-long-term-retention.md."
fi

# --- Check 3: bucket name availability (best-effort) ---
echo ""
echo "Reminder: RetentionBucketName and AthenaResultsBucketName must be globally"
echo "unique S3 bucket names that do not already exist anywhere in AWS. This script"
echo "does not check name availability automatically (pass your intended names to"
echo "'aws s3api head-bucket --bucket <name>' yourself — a 404 means the name is free,"
echo "any other response means it's taken or you don't have access to check)."

echo ""
pass "Pre-flight checks complete."
exit 0
