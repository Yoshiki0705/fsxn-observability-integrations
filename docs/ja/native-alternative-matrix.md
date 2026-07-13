# AWS ネイティブ代替マトリクス — System Manager / Workload Factory / DII

🌐 **日本語**（このページ） | [English](../en/native-alternative-matrix.md)

## 目的

本ドキュメントは、ONTAP System Manager、NetApp Workload Factory、DII Storage Workload Security の主要機能を、本リポジトリの AWS ネイティブ実装にマッピングしたものです。目的: FSx for ONTAP の本番運用・監視・セキュリティが、専有の管理コンソールなしで達成可能であることを示す。

> **位置づけに関する補足**: これは「競合比較」ではありません。各ツールは異なるコンテキストに適しています。本マトリクスは、AWS ネイティブ運用を選択済みのチームが機能カバレッジを確認するため、および選択肢を評価中のチームが追加ライセンスなしで何が利用可能かを理解するためのものです。

---

## ONTAP System Manager — 機能カバレッジ

| System Manager 機能 | AWS ネイティブ同等 | 本リポジトリ | 状態 |
|-------------------|------------------|-----------|:----:|
| **性能: IOPS** | CloudWatch `DataReadOperations` + `DataWriteOperations` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **性能: スループット** | CloudWatch `DataReadBytes` + `DataWriteBytes` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **性能: レイテンシ** | CloudWatch `DataReadLatency` + `DataWriteLatency`（詳細メトリクス） | `fsxn-monitoring-dashboard.yaml` | ⚠️ 詳細メトリクス有効化が必要 |
| **性能: ネットワーク利用率** | CloudWatch `NetworkThroughputUtilization` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **容量: ストレージ使用量** | CloudWatch `StorageUsed` + `StorageCapacityUtilization` | `fsxn-monitoring-dashboard.yaml` | ✅ |
| **容量: アラート** | CloudWatch Alarm on `StorageCapacityUtilization` | `fsxn-monitoring-dashboard.yaml`（閾値アラーム） | ✅ |
| **Qtree: クォータ管理** | ONTAP REST API `/storage/quota/rules` | CLI スクリプト / 手動 | ⚠️ API経由の管理、GUIなし |
| **Qtree: クォータ監視** | Lambda → ONTAP REST API → CloudWatch Custom Metric | `qtree-quota-monitor.yaml` | ✅ |
| **Qtree: クォータアラート** | CloudWatch Alarm on `QtreeQuotaUsedPercent` | `qtree-quota-monitor.yaml` | ✅ |
| **ボリューム: 作成/削除/リサイズ** | FSx コンソール + ONTAP REST API | CloudFormation テンプレート + スクリプト | ✅ |
| **Snapshot: 作成/スケジュール** | FSx Backup + ONTAP REST API | `ontap_response.py` + FSx ネイティブ | ✅ |
| **Snapshot: リストア** | FSx コンソール + ONTAP REST API | `restore-verification.yaml`（リストア前検証） | ✅ |
| **NFS エクスポート管理** | ONTAP REST API | `ontap_response.py`（export-policy rules） | ✅ |
| **SMB 共有管理** | ONTAP REST API | `ontap_response.py`（name-mapping） | ✅ |
| **EMS イベントビューア** | CloudWatch Logs（syslog VPC EP） | `syslog-vpce-cloudwatch.yaml` | ✅ |
| **ARP ステータス** | EMS → Observability パイプライン | 9 ベンダー統合 + EMS webhook | ✅ |
| **SnapMirror 管理** | FSx コンソール + ONTAP REST API | ドキュメント（手動手順） | ⚠️ 自動化なし |
| **QoS ポリシー** | ONTAP REST API | — | ❌ 対象外 |
| **ネットワーク (LIF/DNS)** | FSx コンソール + ONTAP REST API | — | ❌ インフラ管理 |
| **FPolicy 設定** | ONTAP REST API | FPolicy サーバー (Fargate) + スクリプト | ✅ |
| **監査設定** | ONTAP CLI/REST API | セットアップスクリプト + docs | ✅ |

---

## Workload Factory — 機能カバレッジ

| Workload Factory 機能 | AWS ネイティブ同等 | 本リポジトリ | 状態 |
|---------------------|------------------|-----------|:----:|
| **ファイルシステム作成ウィザード** | FSx コンソール / CloudFormation | `demo-ad-environment.yaml` + テンプレート群 | ✅ |
| **コスト最適化推奨** | AWS Cost Explorer + CloudWatch メトリクス | — | ❌ 将来対応 |
| **FabricPool 階層化推奨** | CloudWatch 容量メトリクス + ONTAP tiering API | ドキュメント（手動ガイダンス） | ⚠️ |
| **バックアップ管理** | FSx Backup（AWS マネージド） | AWS ネイティブ（テンプレート不要） | ✅ |
| **レプリケーション設定** | FSx コンソール + SnapMirror API | ドキュメント（手動手順） | ⚠️ |
| **セキュリティ姿勢スキャン** | AWS Security Hub + cfn-guard | `guard/rules/` + CI | ✅ |
| **GenAI データ準備** | Bedrock Knowledge Bases + S3 AP | S3AP Patterns リポジトリ | ✅ |
| **データ移行** | AWS DataSync | — | ❌ 対象外 |
| **コンプライアンステンプレート** | CloudFormation + cfn-guard | `compliance-evidence-pack.md` | ✅ |

---

## DII Storage Workload Security — 機能カバレッジ

| DII 機能 | AWS ネイティブ同等 | 本リポジトリ | 状態 |
|---------|------------------|-----------|:----:|
| **ML ベースライン異常検知** | ONTAP ARP/AI（内蔵）+ SIEM ML | EMS → Datadog/9 ベンダー | ✅ |
| **ユーザー自動ブロック** | ONTAP REST API（name-mapping deny） | `ontap_response.py` + `automated-response.yaml` | ✅ E2E検証済み |
| **IP 自動ブロック** | ONTAP REST API（export-policy）+ VPC NACL | `ontap_response.py` + `automated-response.yaml` | ✅ E2E検証済み |
| **保護 Snapshot** | ONTAP REST API | `ontap_response.py` `create_snapshot` | ✅ E2E検証済み |
| **セッション切断** | ONTAP REST API（CIFS sessions） | `ontap_response.py` `disconnect_smb_sessions` | ✅ E2E検証済み |
| **Forensics ダッシュボード** | Datadog カスタムダッシュボード | `datadog-forensics-dashboard.png` | ✅ 作成済み |
| **ユーザーアクティビティタイムライン** | Datadog Timeseries ウィジェット | Forensics ダッシュボード | ✅ |
| **ファイルアクセス監査証跡** | 監査ログ → Datadog Log Explorer | パイプライン + Forensics ダッシュボード | ✅ |
| **影響ボリューム可視化** | Datadog TopList ウィジェット | Forensics ダッシュボード | ✅ |
| **アラート重要度分布** | Datadog ウィジェット | Forensics ダッシュボード | ✅ |
| **復旧ポイント検証** | Step Functions（FlexClone + S3 AP + Scan） | `restore-verification.yaml` | ✅ E2E検証済み |
| **自動解除（TTL）** | EventBridge Scheduler | `automated-response-ttl.yaml` | ✅ |
| **マルチ SVM 封じ込め** | Step Functions fan-out / multi-SVM CLI | `automated-response-multi-svm-cli.sh` | ✅ |

---

## サマリ: カバレッジ状況

| プロダクト | マッピング機能数 | ✅ 対応済み | ⚠️ 部分対応 | ❌ 対象外 |
|----------|:-------------:|:---------:|:---------:|:--------:|
| System Manager | 18 | 14 | 2 | 2 |
| Workload Factory | 9 | 5 | 2 | 2 |
| DII SWS | 13 | 13 | 0 | 0 |

**重要な洞察**: セキュリティ/インシデント対応機能（DII 相当）は **100% カバー**。運用監視（System Manager 相当）は **78% カバー** — 残りのギャップは QoS 管理と SnapMirror 自動化であり、FSx コンソールまたは専用の IaC ツールの方が適しているインフラ管理タスクです。

---

## デプロイクイックリファレンス

| 機能 | テンプレート | デプロイ順序 |
|------|-----------|:---------:|
| 性能＆容量 | `fsxn-monitoring-dashboard.yaml` | いつでも |
| Qtree クォータ監視 | `qtree-quota-monitor.yaml` | VPC EP 存在後 |
| インシデント対応 | `automated-response.yaml` | Tier 2 |
| 復旧検証 | `restore-verification.yaml` | Tier 2 の後 |
| フォレンジクス | Datadog API（ダッシュボード JSON） | ログパイプライン後 |

---

## 関連ドキュメント

- [デプロイメントガイド](deployment-guide.md) — 全スタックのデプロイパスと VPC Endpoint 管理
- [サイバーレジリエンス機能マップ](cyber-resilience-capability-map.md) — NIST CSF 2.0 マッピング
- [自動応答ガイド](automated-response-guide.md) — DII 相当の封じ込めアクション
- [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) — Step Functions 検証ワークフロー
