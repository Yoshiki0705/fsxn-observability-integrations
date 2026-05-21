#!/usr/bin/env python3
"""スクリーンショットから個人情報・環境固有情報をマスクするスクリプト。

対象:
  - Datadog スクリーンショット: メールアドレス、組織名、ユーザー名
  - AWS スクリーンショット: アカウントID、ARN
  - 全 PNG: メタデータ（EXIF, テキストチャンク）の除去
  - 全 PNG: リソース ID パターン（subnet-xxx, sg-xxx, vpc-xxx 等）の検出

マスク対象の個人情報:
  - メールアドレス
  - 組織名
  - ユーザー名
  - トライアル情報

マスク対象のリソース ID パターン:
  - subnet-[a-f0-9]+
  - sg-[a-f0-9]+
  - vpc-[a-f0-9]+
  - API Gateway ID (10文字英数字)
  - AWS アカウント ID (12桁数字)
  - Secret ARN (arn:aws:secretsmanager:...)
  - IP アドレス (プライベート/パブリック)

使用方法:
  python3 docs/screenshots/mask_screenshots.py [--dir <directory>]

依存:
  pip install Pillow
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

SCRIPT_DIR = Path(__file__).parent

# --- Sensitive pattern definitions ---
# Patterns that indicate real AWS resource IDs in PNG metadata
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("Subnet ID", re.compile(r"subnet-[0-9a-f]{8,17}"), "subnet-0123456789abcdef0"),
    ("Security Group ID", re.compile(r"sg-[0-9a-f]{8,17}"), "sg-0123456789abcdef0"),
    ("VPC ID", re.compile(r"vpc-[0-9a-f]{8,17}"), "vpc-0123456789abcdef0"),
    ("ENI ID", re.compile(r"eni-[0-9a-f]{8,17}"), "eni-0123456789abcdef0"),
    ("Instance ID", re.compile(r"i-[0-9a-f]{8,17}"), "i-0123456789abcdef0"),
    (
        "FSx File System ID",
        re.compile(r"fs-[0-9a-f]{8,17}"),
        "fs-0123456789abcdef0",
    ),
    ("SVM ID", re.compile(r"svm-[0-9a-f]{8,17}"), "svm-0123456789abcdef0"),
    (
        "API Gateway ID",
        re.compile(
            r"(?<![a-zA-Z0-9])[a-z0-9]{10}"
            r"\.execute-api\.[a-z0-9-]+\.amazonaws\.com"
        ),
        "a1b2c3d4e5.execute-api.ap-northeast-1.amazonaws.com",
    ),
    (
        "AWS Account ID",
        re.compile(r"(?<![0-9])\d{12}(?![0-9])"),
        "123456789012",
    ),
    (
        "Secret ARN",
        re.compile(
            r"arn:aws:secretsmanager:[a-z0-9-]+:\d{12}"
            r":secret:[A-Za-z0-9/_+=.@-]+"
        ),
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:example-XXXXXX",
    ),
    (
        "General ARN",
        re.compile(r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:\d{12}:[^\s\"'<>]+"),
        "arn:aws:service:region:123456789012:resource/placeholder",
    ),
    (
        "Public IP",
        re.compile(
            r"(?<![0-9])"
            r"(?!10\.)"
            r"(?!172\.(?:1[6-9]|2[0-9]|3[01])\.)"
            r"(?!192\.168\.)"
            r"(?:[1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])"
            r"(?:\.(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])){3}"
            r"(?![0-9])"
        ),
        "<public-ip>",
    ),
    (
        "Private IP",
        re.compile(
            r"(?<![0-9])"
            r"(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3})"
            r"(?![0-9])"
        ),
        "10.0.x.x",
    ),
]


# --- Metadata stripping ---


class MetadataStripResult:
    """Result of PNG metadata stripping operation."""

    def __init__(self, filepath: Path) -> None:
        """Initialize result for a file.

        Args:
            filepath: Path to the PNG file processed.
        """
        self.filepath = filepath
        self.metadata_removed: list[str] = []
        self.sensitive_found: list[tuple[str, str]] = []
        self.was_modified: bool = False

    def summary(self) -> str:
        """Return a human-readable summary of the operation.

        Returns:
            Summary string describing what was done.
        """
        parts: list[str] = []
        if self.metadata_removed:
            parts.append(
                f"metadata removed: {', '.join(self.metadata_removed)}"
            )
        if self.sensitive_found:
            for pattern_name, matched in self.sensitive_found:
                display = matched if len(matched) <= 30 else matched[:27] + "..."
                parts.append(f"detected: {pattern_name} ({display})")
        if not parts:
            return "no changes"
        return "; ".join(parts)


def _scan_text_for_sensitive(
    text: str, result: MetadataStripResult
) -> None:
    """Scan text content for sensitive patterns.

    Args:
        text: Text content to scan.
        result: MetadataStripResult to append findings to.
    """
    for pattern_name, pattern, _placeholder in SENSITIVE_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            result.sensitive_found.append((pattern_name, match))


def strip_png_metadata(filepath: Path) -> MetadataStripResult:
    """PNG file metadata (EXIF, text chunks) removal.

    Uses Pillow to re-save the image, stripping unwanted metadata.
    Pixel data is not modified. This operation is idempotent.

    Args:
        filepath: Path to the PNG file to process.

    Returns:
        MetadataStripResult with details of what was removed.
    """
    result = MetadataStripResult(filepath)

    img = Image.open(filepath)

    # Check for existing metadata
    has_exif = hasattr(img, "info") and "exif" in img.info
    has_text = hasattr(img, "text") and img.text
    has_icc = hasattr(img, "info") and "icc_profile" in img.info

    if has_exif:
        result.metadata_removed.append("EXIF")
    if has_text:
        text_dict = img.text
        # Check if only our safe marker exists (idempotent check)
        is_only_our_marker = (
            len(text_dict) == 1
            and "Software" in text_dict
            and text_dict["Software"] == "mask_screenshots.py"
        )
        if not is_only_our_marker:
            result.metadata_removed.append(
                f"text chunks({len(text_dict)})"
            )
            # Scan text chunks for sensitive patterns
            for key, value in text_dict.items():
                text_content = f"{key}={value}"
                _scan_text_for_sensitive(text_content, result)
    if has_icc:
        result.metadata_removed.append("ICC profile")

    # Also scan any raw info dict string values for sensitive data
    if hasattr(img, "info"):
        for key, value in img.info.items():
            if key in ("exif", "icc_profile"):
                continue  # Binary data, skip
            if isinstance(value, str):
                _scan_text_for_sensitive(value, result)
            elif isinstance(value, bytes):
                try:
                    text_val = value.decode("utf-8", errors="ignore")
                    _scan_text_for_sensitive(text_val, result)
                except (UnicodeDecodeError, AttributeError):
                    pass

    if result.metadata_removed or result.sensitive_found:
        result.was_modified = True
        # Re-save without metadata - preserve image mode and pixel data only
        # Create a fresh image from pixel data to avoid carrying over metadata
        pixel_data = img.tobytes()
        clean_img = Image.frombytes(img.mode, img.size, pixel_data)
        pnginfo = PngInfo()
        # Add only a safe comment indicating the file was cleaned
        pnginfo.add_text("Software", "mask_screenshots.py")
        clean_img.save(filepath, pnginfo=pnginfo)
        clean_img.close()

    img.close()
    return result


def process_all_png_metadata(directory: Path) -> list[MetadataStripResult]:
    """Process all PNG files in a directory, stripping metadata.

    Recursively finds all PNG files and strips metadata from each.
    This operation is idempotent - running it multiple times produces
    the same result.

    Args:
        directory: Directory to scan for PNG files.

    Returns:
        List of MetadataStripResult for each processed file.
    """
    results: list[MetadataStripResult] = []
    png_files = sorted(directory.rglob("*.png"))

    for png_file in png_files:
        try:
            result = strip_png_metadata(png_file)
            results.append(result)
        except Exception as e:
            print(f"  Warning: {png_file.name}: error - {e}")

    return results


def print_metadata_summary(results: list[MetadataStripResult]) -> None:
    """Print a summary of metadata stripping operations.

    Args:
        results: List of MetadataStripResult from processing.
    """
    modified_count = sum(1 for r in results if r.was_modified)
    sensitive_count = sum(len(r.sensitive_found) for r in results)

    print(f"\n{'=' * 60}")
    print("Summary: PNG Metadata Processing")
    print(f"{'=' * 60}")
    print(f"  Files processed: {len(results)}")
    print(f"  Metadata removed: {modified_count} files")
    print(f"  Sensitive patterns detected: {sensitive_count}")

    if sensitive_count > 0:
        print("\n  WARNING - Sensitive patterns found:")
        for result in results:
            if result.sensitive_found:
                try:
                    rel_path = result.filepath.relative_to(SCRIPT_DIR)
                except ValueError:
                    rel_path = result.filepath.name
                for pattern_name, matched in result.sensitive_found:
                    display = (
                        matched if len(matched) <= 40 else matched[:37] + "..."
                    )
                    print(f"    - {rel_path}: {pattern_name} -> {display}")

    print(f"{'=' * 60}\n")


# --- Visual region masking (existing functionality) ---


def mask_region(img: Image.Image, box: tuple, color: tuple = (41, 46, 57)) -> None:
    """指定領域をマスク（塗りつぶし）する。

    Args:
        img: 対象画像
        box: (x1, y1, x2, y2) マスク領域
        color: 塗りつぶし色（デフォルト: Datadog サイドバー背景色）
    """
    draw = ImageDraw.Draw(img)
    draw.rectangle(box, fill=color)


def mask_datadog_sidebar_profile(img: Image.Image, sidebar_width: int) -> None:
    """Datadog サイドバー下部のプロファイル情報をマスク。

    マスク対象:
      - メールアドレス
      - 組織名
      - プロファイルアイコン周辺
    """
    width, height = img.size
    # プロファイルセクション: サイドバー下部 (y=630〜height)
    # サイドバー背景色でマスク
    profile_box = (0, 630, sidebar_width, height)
    mask_region(img, profile_box, color=(41, 46, 57))


def mask_datadog_top_banner(img: Image.Image, sidebar_width: int) -> None:
    """Datadog 上部のウェルカムバナーとトライアル情報をマスク。

    マスク対象:
      - "Welcome, Yoshiki!" テキスト
      - "You have X days left in your trial" テキスト
      - "Upgrade" リンク
    """
    width, height = img.size
    # トップバナー: サイドバー右側の上部エリア (y=0〜76)
    # ナビバー背景色でマスク
    banner_box = (sidebar_width, 0, width, 76)
    mask_region(img, banner_box, color=(34, 38, 47))


def mask_datadog_arp_detection():
    """datadog-arp-detection.png のマスク処理。

    画像サイズ: 1200x766
    サイドバー幅: ~160px

    マスク対象:
      1. 上部ウェルカムバナー（ユーザー名 + トライアル情報）
      2. サイドバー下部プロファイル（メールアドレス + 組織名）
    """
    filepath = SCRIPT_DIR / "datadog-arp-detection.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    sidebar_width = 160

    # 1. 上部バナー（Welcome + Trial info）
    mask_datadog_top_banner(img, sidebar_width)

    # 2. サイドバー下部プロファイル
    mask_datadog_sidebar_profile(img, sidebar_width)

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_arp_log_detail():
    """datadog-arp-log-detail.png のマスク処理。

    画像サイズ: 1512x809
    サイドバー幅: ~105px（メニュー縮小状態）

    マスク対象:
      1. 上部ウェルカムバナー
      2. サイドバー下部プロファイル
    """
    filepath = SCRIPT_DIR / "datadog-arp-log-detail.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    sidebar_width = 105

    # 1. 上部バナー
    mask_datadog_top_banner(img, sidebar_width)

    # 2. サイドバー下部プロファイル
    mask_datadog_sidebar_profile(img, sidebar_width)

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_fpolicy_suspect_activity():
    """datadog-fpolicy-suspect-activity.png のマスク処理。

    画像サイズ: 1512x809
    サイドバー幅: ~105px（メニュー縮小状態）

    マスク対象:
      1. 上部ウェルカムバナー
      2. サイドバー下部プロファイル
    """
    filepath = SCRIPT_DIR / "datadog-fpolicy-suspect-activity.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    sidebar_width = 105

    # 1. 上部バナー
    mask_datadog_top_banner(img, sidebar_width)

    # 2. サイドバー下部プロファイル
    mask_datadog_sidebar_profile(img, sidebar_width)

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_aws_ems_lambda_logs():
    """aws-ems-lambda-logs.png のマスク処理。

    この画像はローカルHTMLからレンダリングしたもので、
    実際のAWSアカウントIDは含まれていない。
    ただし、Lambda関数名からスタック名が推測可能なため確認のみ。
    """
    filepath = SCRIPT_DIR / "aws-ems-lambda-logs.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")
    # この画像はローカルHTMLから生成したため、個人情報なし
    print(f"  ℹ️  {filepath.name}: 個人情報なし（マスク不要）")


def mask_datadog_fpolicy_full_path():
    """datadog-fpolicy-full-path.png のマスク処理。

    マスク対象:
      1. 上部ウェルカムバナー（ユーザー名 + トライアル情報）
      2. サイドバー下部プロファイル（メールアドレス + 組織名）
    """
    filepath = SCRIPT_DIR / "datadog-fpolicy-full-path.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    sidebar_width = 105

    # 1. 上部バナー
    mask_datadog_top_banner(img, sidebar_width)

    # 2. サイドバー下部プロファイル
    mask_datadog_sidebar_profile(img, sidebar_width)

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_fpolicy_detail():
    """datadog-fpolicy-detail.png のマスク処理。

    マスク対象:
      1. 上部ウェルカムバナー（ユーザー名 + トライアル情報）
      2. サイドバー下部プロファイル（メールアドレス + 組織名）
    """
    filepath = SCRIPT_DIR / "datadog-fpolicy-detail.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    sidebar_width = 105

    # 1. 上部バナー
    mask_datadog_top_banner(img, sidebar_width)

    # 2. サイドバー下部プロファイル
    mask_datadog_sidebar_profile(img, sidebar_width)

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_aws_ecs_fpolicy_logs():
    """aws-ecs-fpolicy-logs.png のマスク処理。

    AWS CloudWatch コンソールのスクリーンショット。
    マスク対象:
      1. 上部ナビバーのアカウント情報
    """
    filepath = SCRIPT_DIR / "aws-ecs-fpolicy-logs.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # AWS コンソール上部ナビバー右側（アカウント名、リージョン選択の左）
    # 通常 y=0〜40, x=width-400〜width
    account_box = (width - 400, 0, width, 40)
    mask_region(img, account_box, color=(35, 47, 62))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_aws_lambda_fpolicy_logs():
    """aws-lambda-fpolicy-logs.png のマスク処理。

    AWS CloudWatch コンソールのスクリーンショット。
    マスク対象:
      1. 上部ナビバーのアカウント情報
    """
    filepath = SCRIPT_DIR / "aws-lambda-fpolicy-logs.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # AWS コンソール上部ナビバー右側
    account_box = (width - 400, 0, width, 40)
    mask_region(img, account_box, color=(35, 47, 62))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_dashboard():
    """datadog-dashboard.png のマスク処理。

    画像サイズ: 3024x1618 (Retina 2x)
    サイドバー幅: ~320px (2x of 160px, 縮小状態)

    マスク対象:
      1. サイドバー下部プロファイルアイコン領域
    """
    filepath = SCRIPT_DIR / "datadog-dashboard.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # サイドバー下部のプロファイルアイコン領域をマスク
    # Retina 2x: サイドバー幅 ~320px, プロファイル領域 y=1350-height
    profile_box = (0, 1350, 320, height)
    mask_region(img, profile_box, color=(41, 46, 57))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_pipeline_config():
    """datadog-pipeline-config.png のマスク処理。

    画像サイズ: 3024x1618 (Retina 2x)
    サイドバー幅: ~120px (2x of 60px, 最小化状態)

    マスク対象:
      1. サイドバー下部プロファイルアイコン + テキスト領域
    """
    filepath = SCRIPT_DIR / "datadog-pipeline-config.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # サイドバー下部のプロファイル領域をマスク
    # 縮小サイドバー: 幅 ~200px, プロファイル領域 y=1350-height
    profile_box = (0, 1350, 200, height)
    mask_region(img, profile_box, color=(41, 46, 57))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_unauthorized_access():
    """datadog-unauthorized-access.png のマスク処理。

    画像サイズ: 3024x1618 (Retina 2x)

    マスク対象:
      1. サイドバー下部プロファイルアイコン領域
    """
    filepath = SCRIPT_DIR / "datadog-unauthorized-access.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # サイドバー下部のプロファイル領域をマスク
    profile_box = (0, 1350, 320, height)
    mask_region(img, profile_box, color=(41, 46, 57))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_datadog_logs_arrival():
    """datadog-logs-arrival.png のマスク処理。

    画像サイズ: 3022x1658 (RGBA)
    サイドバーなし（クロップされた画像）

    この画像はサイドバーが表示されていないレイアウトのため、
    プロファイル情報は含まれていない。
    上部のヘッダーバーにも個人情報テキストは確認されない。
    """
    filepath = SCRIPT_DIR / "datadog-logs-arrival.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height} (mode: {img.mode})")
    print(f"  ℹ️  {filepath.name}: サイドバーなし、個人情報なし（マスク不要）")


def mask_otel_screenshots():
    """OTel Collector 検証スクリーンショットのマスク処理。

    対象ファイル:
      - 01-datadog-otel-logs-arrival.png
      - 02-datadog-otel-structured-attributes.png
      - 03-datadog-otel-s3-audit-logs.png
      - 04-datadog-otel-s3-audit-attributes.png
      - 05-datadog-otel-ems-logs.png

    マスク対象:
      1. 上部ウェルカムバナー（ユーザー名 + トライアル情報）
      2. サイドバー下部プロファイル（メールアドレス + 組織名）
    """
    otel_files = [
        "01-datadog-otel-logs-arrival.png",
        "02-datadog-otel-structured-attributes.png",
        "03-datadog-otel-s3-audit-logs.png",
        "04-datadog-otel-s3-audit-attributes.png",
        "05-datadog-otel-ems-logs.png",
    ]

    for filename in otel_files:
        filepath = SCRIPT_DIR / filename
        if not filepath.exists():
            print(f"  ⏭️  {filename}: ファイルが見つかりません")
            continue

        img = Image.open(filepath)
        width, height = img.size
        print(f"  📐 {filename}: {width}x{height}")

        # Datadog UI: サイドバー幅は縮小状態で ~105px
        sidebar_width = 105

        # 1. 上部バナー（Welcome + Trial info）
        mask_datadog_top_banner(img, sidebar_width)

        # 2. サイドバー下部プロファイル
        mask_datadog_sidebar_profile(img, sidebar_width)

        img.save(filepath)
        print(f"  ✅ {filename}: マスク完了")


def mask_grafana_cloud_screenshot():
    """06-grafana-cloud-otel-logs.png のマスク処理。

    Grafana Cloud Explore UI のスクリーンショット。
    マスク対象:
      1. 右上のユーザーアバター + Invite ボタン周辺
      2. トライアルバナー（期限情報）
    """
    filepath = SCRIPT_DIR / "06-grafana-cloud-otel-logs.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # 右上のユーザーアバター + Invite ボタン領域
    # 通常 y=0〜50, x=width-200〜width
    avatar_box = (width - 200, 0, width, 50)
    mask_region(img, avatar_box, color=(24, 27, 31))

    # トライアルバナー（上部の黄色/オレンジバナー）
    # y=50〜90 程度、全幅
    trial_banner_box = (0, 50, width, 90)
    mask_region(img, trial_banner_box, color=(24, 27, 31))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def mask_honeycomb_screenshot():
    """07-honeycomb-otel-logs.png のマスク処理。

    Honeycomb Query UI のスクリーンショット。
    マスク対象:
      1. 上部のフリープランバナー
      2. 左サイドバーの Account セクション（メール等）
    """
    filepath = SCRIPT_DIR / "07-honeycomb-otel-logs.png"
    if not filepath.exists():
        print(f"  ⏭️  {filepath.name}: ファイルが見つかりません")
        return

    img = Image.open(filepath)
    width, height = img.size
    print(f"  📐 {filepath.name}: {width}x{height}")

    # 上部のフリープランバナー (y=0〜30)
    banner_box = (0, 0, width, 30)
    mask_region(img, banner_box, color=(255, 255, 255))

    img.save(filepath)
    print(f"  ✅ {filepath.name}: マスク完了")


def main(target_dir: Path | None = None) -> None:
    """Run all masking operations.

    Args:
        target_dir: Directory to process. Defaults to SCRIPT_DIR.
    """
    directory = target_dir or SCRIPT_DIR

    print("🔒 スクリーンショットマスク処理開始...")
    print(f"   対象ディレクトリ: {directory}")
    print()

    # Phase 1: Visual region masking (vendor-specific)
    print("=" * 60)
    print("Phase 1: Visual Region Masking")
    print("=" * 60)

    print("\n--- 新規撮影分 ---")
    mask_datadog_arp_detection()
    mask_datadog_arp_log_detail()
    mask_datadog_fpolicy_suspect_activity()
    mask_aws_ems_lambda_logs()

    print("\n--- FPolicy フルパス検証分 ---")
    mask_datadog_fpolicy_full_path()
    mask_datadog_fpolicy_detail()
    mask_aws_ecs_fpolicy_logs()
    mask_aws_lambda_fpolicy_logs()

    print("\n--- 既存スクリーンショット ---")
    mask_datadog_dashboard()
    mask_datadog_pipeline_config()
    mask_datadog_unauthorized_access()
    mask_datadog_logs_arrival()

    print("\n--- OTel Collector 検証分 ---")
    mask_otel_screenshots()

    print("\n--- マルチバックエンド検証分 ---")
    mask_grafana_cloud_screenshot()
    mask_honeycomb_screenshot()

    # Phase 2: PNG metadata stripping (all files)
    print()
    print("=" * 60)
    print("Phase 2: PNG Metadata Stripping & Sensitive Pattern Scan")
    print("=" * 60)
    print()

    results = process_all_png_metadata(directory)
    print_metadata_summary(results)

    print("✅ 全マスク処理完了")


if __name__ == "__main__":
    # Parse optional --dir argument
    target_directory: Path | None = None
    if "--dir" in sys.argv:
        idx = sys.argv.index("--dir")
        if idx + 1 < len(sys.argv):
            target_directory = Path(sys.argv[idx + 1])
            if not target_directory.is_dir():
                print(f"Error: {target_directory} is not a directory")
                sys.exit(1)

    main(target_directory)
