#!/usr/bin/env bash
# test-local-datadog.sh — Local E2E test for OTel Collector → Datadog path
#
# Prerequisites:
#   - Docker installed (Docker Compose optional — script falls back to docker run)
#   - .env.datadog file with DD_API_KEY and DD_SITE configured
#
# Usage:
#   cd integrations/otel-collector
#   bash scripts/test-local-datadog.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose-datadog.yaml"
ENV_FILE="${PROJECT_DIR}/.env.datadog"
PAYLOAD_FILE="${PROJECT_DIR}/tests/test_data/sample_otlp_payload.json"
COLLECTOR_CONFIG="${PROJECT_DIR}/otel-collector-config-datadog.yaml"

# Pinned OTel Collector version (verified working 2026-05-18)
COLLECTOR_IMAGE="otel/opentelemetry-collector-contrib:0.152.0"
CONTAINER_NAME="otel-collector-datadog"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Detect whether docker compose (v2 plugin) is available
USE_COMPOSE=false
if docker compose version &>/dev/null; then
    USE_COMPOSE=true
fi

cleanup() {
    log_info "Stopping OTel Collector..."
    if [[ "${USE_COMPOSE}" == "true" ]]; then
        docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down --remove-orphans 2>/dev/null || true
    else
        docker stop "${CONTAINER_NAME}" 2>/dev/null || true
        docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    fi
}

trap cleanup EXIT

# --- Pre-flight checks ---

if [[ ! -f "${ENV_FILE}" ]]; then
    log_error ".env.datadog not found. Copy .env.datadog.example and configure:"
    log_error "  cp .env.datadog.example .env.datadog"
    exit 1
fi

if [[ ! -f "${PAYLOAD_FILE}" ]]; then
    log_error "Test payload not found: ${PAYLOAD_FILE}"
    exit 1
fi

# --- Step 1: Start OTel Collector with Datadog config ---

log_info "Starting OTel Collector with Datadog exporter..."
log_info "  Image: ${COLLECTOR_IMAGE}"

if [[ "${USE_COMPOSE}" == "true" ]]; then
    log_info "  Method: docker compose"
    docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d
else
    log_warn "  docker compose plugin not available (common with Colima)"
    log_info "  Method: docker run (fallback)"
    # Stop any existing container
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    # Start with docker run
    docker run -d --name "${CONTAINER_NAME}" \
        -p 4318:4318 -p 13133:13133 \
        -v "${COLLECTOR_CONFIG}:/etc/otelcol-contrib/config.yaml" \
        --env-file "${ENV_FILE}" \
        "${COLLECTOR_IMAGE}"
fi

# --- Step 2: Wait for health check ---

log_info "Waiting for health check (max 30s)..."
RETRIES=0
MAX_RETRIES=30
until curl -sf http://localhost:13133/ > /dev/null 2>&1; do
    RETRIES=$((RETRIES + 1))
    if [[ ${RETRIES} -ge ${MAX_RETRIES} ]]; then
        log_error "Health check failed after ${MAX_RETRIES}s"
        if [[ "${USE_COMPOSE}" == "true" ]]; then
            docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs
        else
            docker logs "${CONTAINER_NAME}"
        fi
        exit 1
    fi
    sleep 1
done
log_info "Health check passed"

# --- Step 3: Send sample OTLP payload ---

log_info "Sending OTLP test payload to localhost:4318/v1/logs..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:4318/v1/logs \
    -H "Content-Type: application/json" \
    -d @"${PAYLOAD_FILE}")

if [[ "${HTTP_STATUS}" -ge 200 && "${HTTP_STATUS}" -lt 300 ]]; then
    log_info "OTLP endpoint accepted payload (HTTP ${HTTP_STATUS})"
else
    log_error "OTLP endpoint rejected payload (HTTP ${HTTP_STATUS})"
    exit 1
fi

# --- Step 4: Check collector logs for export activity ---

log_info "Waiting 5s for batch processor to flush..."
sleep 5

log_info "Checking collector logs for export activity..."
if [[ "${USE_COMPOSE}" == "true" ]]; then
    LOGS=$(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs 2>&1)
else
    LOGS=$(docker logs "${CONTAINER_NAME}" 2>&1)
fi

if echo "${LOGS}" | grep -qi "error"; then
    log_warn "Collector logs contain errors:"
    echo "${LOGS}" | grep -i "error" | head -5
    log_warn "This may indicate invalid DD_API_KEY or DD_SITE configuration."
fi

if echo "${LOGS}" | grep -qi "exporting"; then
    log_info "Collector is exporting data"
elif echo "${LOGS}" | grep -qi "sending"; then
    log_info "Collector is sending data"
else
    log_info "Collector logs (last 10 lines):"
    echo "${LOGS}" | tail -10
fi

# --- Summary ---

echo ""
log_info "=== Local Datadog E2E Test Complete ==="
log_info ""
log_info "  OTel Collector started with Datadog exporter"
log_info "  Image: ${COLLECTOR_IMAGE}"
log_info "  Health check passed"
log_info "  OTLP payload accepted (HTTP ${HTTP_STATUS})"
log_info ""
log_info "  Next steps:"
log_info "    1. Check Datadog Logs UI for source:fsxn-audit"
log_info "    2. Verify structured attributes (event.type, user.name, etc.)"
log_info ""
log_info "  Key insight: Lambda handler.py is UNCHANGED."
log_info "  Only the Collector config determines the backend."
log_info "======================================="
