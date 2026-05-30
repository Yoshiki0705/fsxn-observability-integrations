# パートナーソリューション概要: FSx for ONTAP Observability Quickstart

## ターゲット顧客

- エンタープライズファイルサービス（NAS 統合、ホームディレクトリ、共有ドライブ）で FSx for ONTAP を利用中のユーザー
- EC2 上の SAP / Oracle / SQL Server / ビジネスクリティカルアプリケーションワークロードで FSx for ONTAP ストレージを使用中のユーザー
- FSx for ONTAP にユーザープロファイルやデータストレージを持つ VDI / EUC 環境
- ファイルアクセスの可視化、ランサムウェア関連アラート、または監査コンプライアンスが必要な顧客
- Grafana Cloud を Observability プラットフォームとして評価中の組織

## 顧客の課題

| 課題 | 本ソリューションによる解決 |
|------|------------------------|
| ファイルアクセスパターンの可視性がない | 監査ログを Grafana に配信し調査可能に |
| ランサムウェア検知のギャップ | EMS ARP アラートを Grafana でアラートルール付きで可視化 |
| 監査コンプライアンス要件 | クエリ可能で保持期間管理されたログストアにファイルアクセス証跡を保存 |
| EC2 ベースのログコレクターの運用負荷 | サーバーレス Lambda パイプライン — EC2 管理不要 |
| ベンダーロックインの懸念 | OTLP ファーストの設計; マルチバックエンド対応の Collector へ段階的移行可能 |
| インシデント調査の遅延 | 監査ログ + EMS + FPolicy を単一ダッシュボードで相関分析 |

## アーキテクチャ

```
FSx for ONTAP audit volume → S3 Access Point → EventBridge Scheduler → Lambda → Grafana Cloud OTLP Gateway
ONTAP EMS → Webhook → API Gateway → Lambda → Grafana Cloud
ONTAP FPolicy → ECS Fargate → SQS → Lambda → Grafana Cloud
```

## PoC スコープ

| 項目 | 期間 | 成果物 |
|------|----------|-------------|
| 監査ログ取り込み | Day 1–2 | Grafana Explore でログが確認可能 |
| EMS アラート取り込み | Day 2–3 | EMS イベントが確認可能、ランサムウェアアラートルールが有効 |
| FPolicy 取り込み（オプション） | Day 3–5 | ファイル操作が確認可能 |
| ダッシュボードとアラート | Day 5–7 | 4 パネルダッシュボード + 3 アラートルール |
| パイプラインヘルスアラーム | Day 7–8 | CloudWatch アラーム設定完了 |
| Go/No-Go レポート | Day 8–10 | PoC 成功基準の評価完了 |

**PoC 総期間**: 1〜2 週間

## 成果物

- [ ] 監査ログポーラーのデプロイと取り込み開始
- [ ] EMS Webhook の設定とアラート配信
- [ ] FPolicy パスのデプロイ（スコープ内の場合）
- [ ] 4 パネルの Grafana ダッシュボード
- [ ] 3 つのアラートルール（ランサムウェア、クォータ、アクセス失敗）
- [ ] パイプラインヘルス CloudWatch アラーム
- [ ] Go/No-Go 推奨を含む PoC 成功レポート

## 本番環境ギャップの評価

PoC 後、本番環境への移行に向けて以下を評価:

| ギャップ | 必要な判断 |
|-----|-----------------|
| Webhook 認証 | SHARED_SECRET / API_KEY / IAM |
| 配信保証レベル | Quickstart（DLQ）vs Medium（SQS バッファ）vs Collector |
| チェックポイントモデル | SSM ハイウォーターマーク vs DynamoDB オブジェクトレジャー |
| Alloy / Collector への移行 | シングルバックエンド直接送信 vs マルチバックエンドパイプライン |
| 保持とコンプライアンス | Grafana Cloud 保持ティア vs S3 アーカイブ |
| FPolicy スコープ | 監視対象のボリューム/操作 |
| スケール時のコスト | 実測ボリュームでコストモデルを検証 |

## 責任分担

| 領域 | パートナー / SI | 顧客 | AWS |
|------|-------------|----------|-----|
| CloudFormation デプロイ | リード | 承認 | サポート |
| ONTAP 監査/EMS/FPolicy 設定 | アドバイス | 実行 | — |
| Grafana Cloud セットアップ | リード | 認証情報提供 | — |
| ダッシュボード / アラート設計 | リード | レビュー | — |
| Webhook セキュリティ設計 | リード | 承認 | サポート |
| 本番環境ハードニング | リード | 承認 + 運用 | サポート |
| 継続的運用 | ハンドオーバー | 所有 | サポート |

## 関連リソース

- [PoC チェックリスト](poc-checklist.md)
- [運用ガイド](operations.md)
- [配信保証パターン](../../../../docs/ja/delivery-guarantees.md)
- [Webhook セキュリティガイド](../../../../docs/ja/webhook-security.md)
- [コストモデル](../../../../docs/ja/cost-model.md)
