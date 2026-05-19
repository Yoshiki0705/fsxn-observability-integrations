#!/bin/bash
set -euo pipefail

# FSxN Observability Integration - Test Runner
# Usage: ./test.sh [vendor] [--unit|--integration|--all]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

VENDOR="${1:-all}"
TEST_TYPE="${2:---all}"

run_python_tests() {
  local vendor_dir="$1"
  echo "🐍 Running Python tests for ${vendor_dir}..."
  if [[ -d "${PROJECT_ROOT}/integrations/${vendor_dir}/tests" ]]; then
    cd "${PROJECT_ROOT}/integrations/${vendor_dir}"
    python -m pytest tests/ -v --tb=short
    cd "${PROJECT_ROOT}"
  else
    echo "   No Python tests found"
  fi
}

run_ts_tests() {
  echo "📘 Running TypeScript tests..."
  cd "${PROJECT_ROOT}"
  if [[ -f "node_modules/.bin/jest" ]] && [[ -d "node_modules/ts-jest" ]]; then
    npx jest --passWithNoTests
  else
    echo "   ⏭️  Skipping TypeScript tests (ts-jest not installed). Run 'npm install' first."
  fi
}

if [[ "$VENDOR" == "all" ]]; then
  echo "🧪 Running all tests..."
  run_ts_tests
  for dir in "${PROJECT_ROOT}"/integrations/*/; do
    vendor_name=$(basename "$dir")
    run_python_tests "$vendor_name"
  done
else
  run_python_tests "$VENDOR"
fi

echo ""
echo "✅ All tests passed"
