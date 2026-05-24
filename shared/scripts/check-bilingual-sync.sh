#!/bin/bash
# Check bilingual documentation sync between ja/ and en/ directories.
# Reports files that exist in one language but not the other,
# and files where the heading structure differs significantly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

echo "=== Bilingual Documentation Sync Check ==="
echo ""

# Check docs/ja vs docs/en
check_directory_pair() {
  local ja_dir="$1"
  local en_dir="$2"
  local label="$3"

  if [ ! -d "$ja_dir" ] && [ ! -d "$en_dir" ]; then
    return
  fi

  echo "--- ${label} ---"

  # Files in ja/ but not in en/
  if [ -d "$ja_dir" ]; then
    for ja_file in "$ja_dir"/*.md; do
      [ -f "$ja_file" ] || continue
      local basename
      basename=$(basename "$ja_file")
      if [ ! -f "$en_dir/$basename" ]; then
        echo -e "  ${RED}MISSING EN${NC}: $en_dir/$basename (exists in ja/)"
        ERRORS=$((ERRORS + 1))
      fi
    done
  fi

  # Files in en/ but not in ja/
  if [ -d "$en_dir" ]; then
    for en_file in "$en_dir"/*.md; do
      [ -f "$en_file" ] || continue
      local basename
      basename=$(basename "$en_file")
      if [ ! -f "$ja_dir/$basename" ]; then
        echo -e "  ${YELLOW}MISSING JA${NC}: $ja_dir/$basename (exists in en/)"
        WARNINGS=$((WARNINGS + 1))
      fi
    done
  fi

  # Heading structure comparison for files that exist in both
  if [ -d "$ja_dir" ] && [ -d "$en_dir" ]; then
    for ja_file in "$ja_dir"/*.md; do
      [ -f "$ja_file" ] || continue
      local basename
      basename=$(basename "$ja_file")
      local en_file="$en_dir/$basename"
      [ -f "$en_file" ] || continue

      local ja_headings
      ja_headings=$(grep -c "^#" "$ja_file" 2>/dev/null || echo 0)
      local en_headings
      en_headings=$(grep -c "^#" "$en_file" 2>/dev/null || echo 0)

      local diff=$((ja_headings - en_headings))
      if [ ${diff#-} -gt 3 ]; then
        echo -e "  ${YELLOW}STRUCTURE DIFF${NC}: $basename (ja: ${ja_headings} headings, en: ${en_headings} headings)"
        WARNINGS=$((WARNINGS + 1))
      fi
    done
  fi

  echo ""
}

# Check main docs directory
check_directory_pair \
  "$PROJECT_ROOT/docs/ja" \
  "$PROJECT_ROOT/docs/en" \
  "docs/"

# Check each vendor's docs
for vendor_dir in "$PROJECT_ROOT"/integrations/*/; do
  [ -d "$vendor_dir" ] || continue
  local_vendor=$(basename "$vendor_dir")
  check_directory_pair \
    "$vendor_dir/docs/ja" \
    "$vendor_dir/docs/en" \
    "integrations/${local_vendor}/docs/"
done

# Summary
echo "=== Summary ==="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
  echo -e "${GREEN}All bilingual docs are in sync.${NC}"
  exit 0
elif [ $ERRORS -eq 0 ]; then
  echo -e "${YELLOW}${WARNINGS} warning(s) found (missing ja/ files or structure differences).${NC}"
  exit 0
else
  echo -e "${RED}${ERRORS} error(s) found (missing en/ files).${NC}"
  echo -e "${YELLOW}${WARNINGS} warning(s) found.${NC}"
  echo ""
  echo "Japanese is the primary language. Missing English files should be created."
  exit 1
fi
