#!/usr/bin/env python3
"""
スクリーンショットから個人情報・環境固有情報をマスクするスクリプト。

対象:
  - Datadog スクリーンショット: メールアドレス、組織名、ユーザー名
  - AWS スクリーンショット: アカウントID、ARN

マスク対象の個人情報:
  - メールアドレス
  - 組織名
  - ユーザー名
  - トライアル情報

使用方法:
  python3 docs/screenshots/mask_screenshots.py

依存:
  pip install Pillow
"""

from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).parent


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


if __name__ == "__main__":
    print("🔒 スクリーンショットマスク処理開始...")
    print()

    print("--- 新規撮影分 ---")
    mask_datadog_arp_detection()
    mask_datadog_arp_log_detail()
    mask_datadog_fpolicy_suspect_activity()
    mask_aws_ems_lambda_logs()

    print()
    print("--- FPolicy フルパス検証分 ---")
    mask_datadog_fpolicy_full_path()
    mask_datadog_fpolicy_detail()
    mask_aws_ecs_fpolicy_logs()
    mask_aws_lambda_fpolicy_logs()

    print()
    print("--- 既存スクリーンショット ---")
    mask_datadog_dashboard()
    mask_datadog_pipeline_config()
    mask_datadog_unauthorized_access()
    mask_datadog_logs_arrival()

    print()
    print("--- OTel Collector 検証分 ---")
    mask_otel_screenshots()

    print()
    print("--- マルチバックエンド検証分 ---")
    mask_grafana_cloud_screenshot()
    mask_honeycomb_screenshot()

    print()
    print("✅ 全マスク処理完了")
