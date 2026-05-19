# 18.4 最終確認 — 全成果物の確認チェックリスト

## 概要

Splunk Serverless E2E 検証の全成果物が揃っていることを確認する最終チェックリスト。全項目が PASS であることを確認してから検証完了とする。

## 前提条件

- Task 1〜18.3 が完了済み
- 全テストが PASS 済み

## 最終確認チェックリスト

### Lambda ハンドラーコード

- [ ] Lambda handler code exists and tests pass
  - ファイル: `integrations/splunk-serverless/lambda/handler.py`
  - テスト: `python -m pytest integrations/splunk-serverless/tests/ -k "handler" -v`

```bash
# 存在確認
ls -la integrations/splunk-serverless/lambda/handler.py

# テスト実行
python -m pytest integrations/splunk-serverless/tests/test_handler.py -v
```

### EMS ハンドラーコード

- [ ] EMS handler code exists and tests pass
  - ファイル: `integrations/splunk-serverless/lambda/ems_handler.py`
  - テスト: `python -m pytest integrations/splunk-serverless/tests/test_ems_handler.py -v`

```bash
# 存在確認
ls -la integrations/splunk-serverless/lambda/ems_handler.py

# テスト実行
python -m pytest integrations/splunk-serverless/tests/test_ems_handler.py -v
```

### Firehose 変換コード

- [ ] Firehose transform code exists and tests pass
  - ファイル: `integrations/splunk-serverless/lambda/firehose_transform.py`
  - テスト: `python -m pytest integrations/splunk-serverless/tests/test_firehose_transform.py -v`

```bash
# 存在確認
ls -la integrations/splunk-serverless/lambda/firehose_transform.py

# テスト実行
python -m pytest integrations/splunk-serverless/tests/test_firehose_transform.py -v
```

### CloudFormation テンプレート

- [ ] template.yaml passes cfn-lint
  - ファイル: `integrations/splunk-serverless/template.yaml`

```bash
# 存在確認
ls -la integrations/splunk-serverless/template.yaml

# cfn-lint 実行
cfn-lint integrations/splunk-serverless/template.yaml
```

- [ ] template-firehose.yaml passes cfn-lint
  - ファイル: `integrations/splunk-serverless/template-firehose.yaml`

```bash
# 存在確認
ls -la integrations/splunk-serverless/template-firehose.yaml

# cfn-lint 実行
cfn-lint integrations/splunk-serverless/template-firehose.yaml
```

### セットアップガイド（バイリンガル）

- [ ] Setup guide (ja) exists
  - ファイル: `integrations/splunk-serverless/docs/ja/setup-guide.md`

- [ ] Setup guide (en) exists
  - ファイル: `integrations/splunk-serverless/docs/en/setup-guide.md`

```bash
# 存在確認
ls -la integrations/splunk-serverless/docs/ja/setup-guide.md
ls -la integrations/splunk-serverless/docs/en/setup-guide.md

# 構造一致確認
python3 scripts/verification/bilingual_comparator.py \
  --ja integrations/splunk-serverless/docs/ja/setup-guide.md \
  --en integrations/splunk-serverless/docs/en/setup-guide.md
```

### EC2 比較ドキュメント（バイリンガル）

- [ ] EC2 comparison (ja) exists
  - ファイル: `docs/ja/ec2-comparison.md`

- [ ] EC2 comparison (en) exists
  - ファイル: `docs/en/ec2-comparison.md`

```bash
# 存在確認
ls -la docs/ja/ec2-comparison.md
ls -la docs/en/ec2-comparison.md

# 構造一致確認
python3 scripts/verification/bilingual_comparator.py \
  --ja docs/ja/ec2-comparison.md \
  --en docs/en/ec2-comparison.md
```

### スクリーンショット

- [ ] docs/screenshots/splunk/ has required screenshots
  - 必須: 3ファイル以上（PNG 形式、500KB 以下、命名規約準拠）

```bash
# ファイル一覧
ls -la docs/screenshots/splunk/*.png

# 検証ツール実行
python3 scripts/verification/splunk_screenshot_validator.py docs/screenshots/splunk/
```

### 検証結果ドキュメント

- [ ] verification-results-splunk.md is complete
  - ファイル: `docs/ja/verification-results-splunk.md`
  - プレースホルダーが残っていないこと

```bash
# 存在確認
ls -la docs/ja/verification-results-splunk.md

# プレースホルダー残存チェック
grep -c "TODO\|TBD" docs/ja/verification-results-splunk.md
# 期待値: 0
```

## 一括確認スクリプト

以下のスクリプトで全項目を一括確認:

```bash
#!/bin/bash
set -euo pipefail

echo "=== Splunk Serverless E2E — Final Checklist ==="
echo ""

PASS=0
FAIL=0

check() {
  local desc="$1"
  local file="$2"
  if [ -f "$file" ]; then
    echo "  [PASS] $desc"
    ((PASS++))
  else
    echo "  [FAIL] $desc — $file not found"
    ((FAIL++))
  fi
}

echo "[Code]"
check "Lambda handler" "integrations/splunk-serverless/lambda/handler.py"
check "EMS handler" "integrations/splunk-serverless/lambda/ems_handler.py"
check "Firehose transform" "integrations/splunk-serverless/lambda/firehose_transform.py"

echo ""
echo "[Templates]"
check "template.yaml" "integrations/splunk-serverless/template.yaml"
check "template-firehose.yaml" "integrations/splunk-serverless/template-firehose.yaml"

echo ""
echo "[Setup Guides]"
check "Setup guide (ja)" "integrations/splunk-serverless/docs/ja/setup-guide.md"
check "Setup guide (en)" "integrations/splunk-serverless/docs/en/setup-guide.md"

echo ""
echo "[EC2 Comparison]"
check "EC2 comparison (ja)" "docs/ja/ec2-comparison.md"
check "EC2 comparison (en)" "docs/en/ec2-comparison.md"

echo ""
echo "[Screenshots]"
PNG_COUNT=$(find docs/screenshots/splunk/ -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
if [ "$PNG_COUNT" -ge 3 ]; then
  echo "  [PASS] Screenshots: $PNG_COUNT files found (>= 3 required)"
  ((PASS++))
else
  echo "  [FAIL] Screenshots: $PNG_COUNT files found (>= 3 required)"
  ((FAIL++))
fi

echo ""
echo "[Verification Results]"
check "verification-results-splunk.md" "docs/ja/verification-results-splunk.md"

echo ""
echo "=== Summary ==="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "  Result: ALL PASS"
  exit 0
else
  echo "  Result: $FAIL item(s) FAILED"
  exit 1
fi
```

## PASS/FAIL 判定基準

| 判定 | 条件 |
|------|------|
| **PASS** | 全11項目が PASS（全ファイルが存在し、テストが通り、cfn-lint が通り、スクリーンショットが3枚以上、検証結果が完成） |
| **FAIL** | 1項目でも FAIL がある |

## 不足がある場合の対応

| 不足項目 | 対応タスク |
|---------|-----------|
| Lambda handler | Task 2.1〜2.4 |
| EMS handler | Task 4.1 |
| Firehose transform | Task 6.1 |
| template.yaml | Task 7.1 |
| template-firehose.yaml | Task 7.2 |
| Setup guide (ja/en) | Task 10.1 |
| EC2 comparison (ja/en) | Task 10.2 |
| Screenshots | Task 16.1〜17.3 |
| verification-results | Task 18.3 |

## 関連タスク

- Task 13: 最終チェックポイント（テスト）
- Task 18.1: セットアップガイド日英対応確認
- Task 18.2: スクリーンショット検証
- Task 18.3: 検証結果ドキュメントの生成
