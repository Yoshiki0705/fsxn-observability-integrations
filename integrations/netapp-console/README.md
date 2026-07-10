# NetApp Console<!-- allow:naming --> Integration

🌐 [日本語](#概要) | [English](#overview)

---

## 概要

NetApp Console<!-- allow:naming -->（BlueXP<!-- allow:naming --> / System Manager）を活用した FSx for ONTAP の GUI 管理パターン集です。

CLI に不慣れな運用部門向けに、ブラウザベースの GUI 操作で以下を実現します:

- 監査ログの設定・管理
- Qtree クォータ（容量制限）の設定
- ボリューム・共有フォルダの管理
- パフォーマンス監視

## ツール比較

| ツール | 種類 | 費用 | 主な用途 |
|--------|------|------|---------|
| **[ONTAP System Manager](system-manager/)** | ONTAP 組み込み Web UI | **無料** | 日常的なストレージ管理 |
| NetApp BlueXP<!-- allow:naming --> | SaaS | 基本無料 | マルチクラウド管理・DR |
| NetApp Console<!-- allow:naming --> | SaaS ポータル | 無料 | ライセンス管理・サポート |

> 🔍 **ランサムウェア対策・インシデント対応をお探しの場合**: NetApp Console<!-- allow:naming --> / BlueXP<!-- allow:naming --> には、DII（Data Infrastructure Insights、旧 Cloud Insights）Storage Workload Security という専用モジュールがあり、ユーザー別 ML ベースラインによる異常検知とストレージ層でのユーザー/IP 自動遮断を提供します。本リポジトリでは、この着想を AWS ネイティブに再現した [自動インシデント対応ガイド](../../docs/ja/automated-response-guide.md) を用意しています。DII を導入していない、または既存の SIEM/Observability（Datadog、Splunk、Elastic 等）から検知を発生させたい場合の選択肢として、ONTAP REST API による SMB ユーザーブロック・NFS IP ブロック・Snapshot・セッション切断を、任意の検知ソースから SNS 経由でトリガーできます。DII との比較表・FAQ も同ガイドに記載しています。

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
└── bluexp/                      # (将来) BlueXP<!-- allow:naming --> 統合
```

---

## Overview

GUI management patterns for FSx for ONTAP using NetApp Console<!-- allow:naming --> (BlueXP<!-- allow:naming --> / System Manager).

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

> 🔍 **Looking for ransomware / incident response?** NetApp Console<!-- allow:naming --> / BlueXP<!-- allow:naming --> offers a dedicated module, DII (Data Infrastructure Insights, formerly Cloud Insights) Storage Workload Security, which detects anomalies via per-user ML baselines and automatically blocks users/IPs at the storage layer. This repository provides an AWS-native take on the same idea in the [Automated Incident Response Guide](../../docs/en/automated-response-guide.md) — useful if you don't run DII, or want detection to originate from your existing SIEM/observability stack (Datadog, Splunk, Elastic, etc.). It implements SMB user blocking, NFS IP blocking, snapshots, and session disconnect via ONTAP REST API, triggerable from any detection source via SNS. See the guide for a side-by-side comparison table and FAQ against DII.

## References

- [ONTAP System Manager Guide](system-manager/)
- [Automated Incident Response Guide](../../docs/en/automated-response-guide.md) — ransomware / storage-layer blocking, DII comparison and FAQ
- [AWS Docs — FSx for ONTAP Management](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-resources-ontap-apps.html)
- [NetApp Docs — System Manager](https://docs.netapp.com/us-en/ontap/concept_administration_overview.html)

## Start Here

1. Read [Part 14: System Manager Reality Check](https://dev.to/yoshikifujiwara/series/39759) (dev.to article)
2. Capture evidence using [`evidence/README.md`](system-manager/evidence/README.md)
3. Validate System Manager access via NetApp Console<!-- allow:naming -->
4. Validate FSA and audit configuration
5. Validate EMS webhook path
6. Review Splunk searches in [`integrations/splunk-serverless/searches/`](../splunk-serverless/searches/)
7. If evaluating ransomware/incident-response coverage beyond day-to-day GUI management, continue to the [Automated Incident Response Guide](../../docs/en/automated-response-guide.md) ([日本語版](../../docs/ja/automated-response-guide.md))
