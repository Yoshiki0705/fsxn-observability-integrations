#!/usr/bin/env bash
# validate-configs.sh — Validate all OTel Collector config files
#
# Uses the otel-collector-contrib Docker image to validate YAML syntax
# and component references. Note: ${env:...} variables will cause
# expected errors when secrets are not available.
#
# Usage:
#   cd integrations/otel-collector
#   bash scripts/validate-configs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COLLECTOR_IMAGE="otel/opentelemetry-collector-contrib:0.152.0"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

CONFIGS=$(find "${PROJECT_DIR}" -maxdepth 1 -name "otel-collector-config*.yaml" | sort)
TOTAL=0
VALID=0

for config in ${CONFIGS}; do
    TOTAL=$((TOTAL + 1))
    BASENAME=$(basename "${config}")
    log_info "Validating: ${BASENAME}"

    OUTPUT=$(docker run --rm \
        -v "${PROJECT_DIR}:/config" \
        "${COLLECTOR_IMAGE}" \
        validate --config "/config/${BASENAME}" 2>&1) || true

    if echo "${OUTPUT}" | grep -q "Error:"; then
        # Check if it's only env var resolution errors (expected)
        if echo "${OUTPUT}" | grep -q "at least one endpoint must be specified\|env:"; then
            log_warn "  ${BASENAME}: env var resolution errors (expected in CI)"
            VALID=$((VALID + 1))
        else
            log_error "  ${BASENAME}: VALIDATION FAILED"
            echo "${OUTPUT}" | head -5
        fi
    else
        log_info "  ${BASENAME}: VALID"
        VALID=$((VALID + 1))
    fi
done

echo ""
log_info "Results: ${VALID}/${TOTAL} configs valid"
if [[ ${VALID} -eq ${TOTAL} ]]; then
    exit 0
else
    exit 1
fi
