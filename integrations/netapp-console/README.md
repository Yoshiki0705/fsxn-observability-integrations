# NetApp Console Integration

🌐 [日本語](#概要) | [English](#overview)

---

## 概要

NetApp Console（BlueXP / System Manager）を活用した FSx for ONTAP の GUI 管理パターン集です。

CLI に不慣れな運用部門向けに、ブラウザベースの GUI 操作で以下を実現します:

- 監査ログの設定・管理
- Qtree クォータ（容量制限）の設定
- ボリューム・共有フォルダの管理
- パフォーマンス監視

## ツール比較

| ツール | 種類 | 費用 | 主な用途 |
|--------|------|------|---------|
| **[ONTAP System Manager](system-manager/)** | ONTAP 組み込み Web UI | **無料** | 日常的なストレージ管理 |
| NetApp BlueXP | SaaS | 基本無料 | マルチクラウド管理・DR |
| NetApp Console | SaaS ポータル | 無料 | ライセンス管理・サポート |

## 推奨パターン

```
┌─────────────────────────────────────────────────────────────┐
│ 運用部門の日常業務                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Windows エクスプローラー → ファイル操作（読み書き）            │
│  ONTAP System Manager   → ストレージ管理（GUI）              │
│  CloudWatch / SNS       → 容量アラート（ボリュームレベル）     │
│  EMS Webhook + Lambda   → クォータアラート（Qtree レベル）    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## ディレクトリ構造

```
netapp-console/
├── README.md                    # このファイル
├── system-manager/              # ONTAP System Manager 操作ガイド
│   ├── README.md                # System Manager 概要
│   ├── docs/
│   │   ├── ja/                  # 日本語ドキュメント
│   │   │   ├── audit-log-setup.md      # 監査ログ設定手順
│   │   │   ├── quota-setup.md          # クォータ設定手順
│   │   │   └── access-guide.md         # アクセス方法
│   │   └── en/                  # 英語ドキュメント
│   │       ├── audit-log-setup.md
│   │       ├── quota-setup.md
│   │       └── access-guide.md
│   ├── screenshots/             # 操作スクリーンショット
│   │   ├── 01-login.png
│   │   ├── 02-dashboard.png
│   │   ├── 03-audit-settings.png
│   │   └── ...
│   ├── scripts/                 # 検証・自動化スクリプト
│   └── tests/                   # テスト
└── bluexp/                      # (将来) BlueXP 統合
```

---

## Overview

GUI management patterns for FSx for ONTAP using NetApp Console (BlueXP / System Manager).

For operations teams unfamiliar with CLI, these browser-based GUI operations enable:

- Audit log configuration and management
- Qtree quota (capacity limit) configuration
- Volume and share management
- Performance monitoring

## Recommended Pattern

| Task | Tool | Notes |
|------|------|-------|
| File operations (read/write) | Windows Explorer | Existing workflow |
| Storage management (GUI) | ONTAP System Manager | Free, built-in |
| Volume capacity alerts | CloudWatch + SNS | AWS native |
| Qtree quota alerts | EMS Webhook + Lambda | Real-time, per-Qtree |

## References

- [ONTAP System Manager Guide](system-manager/)
- [AWS Docs — FSx for ONTAP Management](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-resources-ontap-apps.html)
- [NetApp Docs — System Manager](https://docs.netapp.com/us-en/ontap/concept_administration_overview.html)

## Start Here

1. Read [Part 14: System Manager Reality Check](https://dev.to/yoshikifujiwara/series/39759) (dev.to article)
2. Capture evidence using [`evidence/README.md`](system-manager/evidence/README.md)
3. Validate System Manager access via NetApp Console
4. Validate FSA and audit configuration
5. Validate EMS webhook path
6. Review Splunk searches in [`integrations/splunk-serverless/searches/`](../splunk-serverless/searches/)
