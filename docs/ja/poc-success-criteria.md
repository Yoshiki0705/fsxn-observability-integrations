# PoC 成功基準

FSx for ONTAP オブザーバビリティ統合すべてに共通する成功基準です。各検証段階の完了条件を明確に定義するために使用してください。

## 最低限の成功 (レベル 1)

パイプラインがエンドツーエンドで動作することを証明する最低条件:

- [ ] S3 Access Point から監査ログファイルを 1 件読み取れる
- [ ] オブザーバビリティバックエンドにログレコードが 1 件到達し、検索可能である
- [ ] SSM チェックポイントが配信成功後にのみ更新される
- [ ] DLQ が空のままである（配信失敗なし）
- [ ] デプロイスクリプト (`aws cloudformation deploy`) がエラーなく完了する
- [ ] クリーンアップスクリプト (`aws cloudformation delete-stack`) がすべてのリソースを正常に削除する

### 検証コマンド

```bash
# Confirm checkpoint advanced
aws ssm get-parameter \
  --name /fsxn/observability/checkpoint \
  --query 'Parameter.Value' --output text

# Confirm DLQ is empty
aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages'

# Query backend (example: Datadog)
# source:fsxn earliest:-15m
```

## 運用上の成功 (レベル 2)

パイプラインが監視可能かつ運用可能であることを証明する条件:

- [ ] Lambda エラーとスロットルが監視されている（CloudWatch Alarm 設定済み）
- [ ] DLQ 深度アラームが設定・テスト済みである
- [ ] チェックポイント経過時間メトリクスが利用可能である（滞留検知）
- [ ] リプレイ手順が文書化・テスト済みである（手動 DLQ ドレイン）
- [ ] シークレットローテーション動作がテスト済みである（次回コールドスタート時に新トークンを取得）
- [ ] 想定ログ量に対するコスト見積もりが作成されている
- [ ] ダッシュボードにログ量、配信レイテンシ、エラー率が表示されている

### 追跡すべき主要メトリクス

| メトリクス | ソース | アラート閾値 |
|-----------|--------|------------|
| Lambda Errors | CloudWatch | 連続 2 期間で > 0 |
| DLQ Depth | SQS ApproximateNumberOfMessages | > 0 |
| Checkpoint Age | カスタムメトリクスまたは Scheduler 失敗 | > ポーリング間隔の 2 倍 |
| Delivery Latency | カスタムメトリクス（ファイルタイムスタンプ → バックエンド検索可能） | > 5 分 |

## 本番準備ゲート (レベル 3)

本番デプロイ前の完了基準:

- [ ] Webhook 認証が有効化されている（API キー、IAM、または WAF）
- [ ] 配信保証レベルが選定・文書化されている（at-least-once vs exactly-once）
- [ ] DynamoDB オブジェクト台帳の要否が決定されている（exactly-once に必要）
- [ ] OTel Collector / Grafana Alloy への移行判断が完了している
- [ ] 保持期間とコンプライアンス要件がセキュリティチームに承認されている
- [ ] セキュリティレビューチェックリストが完了している
- [ ] ガバナンスおよびコンプライアンスレビューが完了している
- [ ] 想定ピーク量での負荷テストに合格している
- [ ] ランブックが以下をカバーしている: 配信失敗、チェックポイントリセット、トークンローテーション、DLQ リプレイ

### 本番準備レビュー質問事項

1. 想定される 1 日あたりのログ量は？（GB/日）
2. 許容される配信レイテンシは？（秒/分）
3. 選択したバックエンドへの越境データ転送は許容されるか？
4. パイプラインの運用責任者は誰か？（監視、エスカレーション、保守）
5. トークンローテーションのスケジュールは？
6. DLQ リプレイ手順はセキュリティ部門に承認されているか？

## EMS / FPolicy 追加基準

EMS Webhook または FPolicy イベントパスを含む統合向けの追加基準:

### EMS Webhook
- [ ] API Gateway エンドポイントが保護されている（未認証の公開アクセスなし）
- [ ] ONTAP EMS 宛先が設定され、イベントを送信している
- [ ] 少なくとも 1 件の EMS イベント（例: `arw.volume.state`）がバックエンドに到達している
- [ ] Webhook レイテンシが 30 秒未満である（ONTAP → バックエンド検索可能）

### FPolicy
- [ ] ECS Fargate タスクが稼働し、ONTAP KeepAlive メッセージを受信している
- [ ] 少なくとも 1 件のファイル操作イベントが SQS → Lambda 経由でバックエンドに到達している
- [ ] Fargate タスク再起動後に ONTAP External Engine IP が更新されている
- [ ] FPolicy レイテンシが 30 秒未満である（ファイル操作 → バックエンド検索可能）

## マルチバックエンド基準 (OTel Collector / Alloy)

OTel Collector または Grafana Alloy デプロイ向けの基準:

- [ ] 単一の Lambda が OTLP を Collector/Alloy に送信している
- [ ] Collector/Alloy が設定されたすべてのバックエンドに同時にルーティングしている
- [ ] 各バックエンドが同一のログレコードを受信している（パリティチェック）
- [ ] Collector のヘルスエンドポイントが監視されている
- [ ] 永続キューが信頼性のために設定されている
- [ ] Memory Limiter が高負荷時の OOM を防止している

## 関連ドキュメント

- [ガバナンスとコンプライアンス](governance-and-compliance.md)
- [セキュリティレビューチェックリスト](security-review-checklist.md)
- [配信保証パターン](delivery-guarantees.md)
- [運用ガイド](operational-guide.md)
- [本番準備レベル (README)](../../README.md#production-readiness-levels--本番準備レベル)
