# PoC 成功基準 — Grafana Cloud 統合

🌐 **日本語**（このページ） | [English](../en/poc-checklist.md)

ステークホルダーへの報告前に、Proof of Concept デプロイメントを検証するためのチェックリストです。

## 機能検証

- [ ] 監査ログポーラー Lambda のデプロイ成功
- [ ] 最初の監査ログファイルが Grafana Explore で確認可能（`{service_name="fsxn-audit"}`）
- [ ] EMS テストイベントが確認可能（`{service_name="fsxn-ems"}`）
- [ ] FPolicy テストイベントが確認可能（`{service_name="fsxn-fpolicy"}`）
- [ ] 全 4 パネルがデータを表示するダッシュボードの作成完了
- [ ] アラートルールのプロビジョニング完了（ランサムウェア、クォータ、アクセス失敗）

## 信頼性検証

- [ ] Scheduler DLQ アラームの設定とテスト完了
- [ ] チェックポイント障害パステストの合格（配信失敗 → チェックポイントが進まない）
- [ ] Reserved Concurrency による重複実行の防止
- [ ] 処理境界値（MAX_KEYS_PER_RUN、SAFETY_THRESHOLD_MS）の検証完了

## セキュリティ検証

- [ ] 本番環境向け Webhook 認証モードの選択（SHARED_SECRET 推奨）
- [ ] Grafana 認証情報を Secrets Manager に保存（環境変数ではない）
- [ ] API Gateway アクセスログの有効化
- [ ] CloudFormation パラメータや Lambda コードにハードコードされたシークレットがない

## 運用準備

- [ ] クリーンアップスクリプトのテスト完了（`scripts/cleanup.sh --all`）
- [ ] デプロイスクリプトのテスト完了（`scripts/deploy.sh`）
- [ ] 環境に合わせたポーラーチューニングパラメータの文書化
- [ ] 監査ログローテーション間隔の計測
- [ ] FSx S3 Access Point 読み取りスループットの検証

## Go/No-Go 判断

| 基準 | ステータス | 備考 |
|-----------|--------|-------|
| スケジュール間隔内にログが Grafana に到着 | | |
| テストイベントでアラートが発火 | | |
| DLQ リプレイ手順の文書化 | | |
| 本番環境ギャップを顧客が受容 | | |
| コスト見積もりのレビュー完了（Lambda + Grafana 取り込み） | | |
| Webhook 認証モードの合意 | | |

## 最初の成功パス

初回デプロイの場合:

1. 監査ログポーラー**のみ**をデプロイ（`template.yaml`）
2. 初期検証のため `MAX_KEYS_PER_RUN=1` に設定
3. 既知のテスト監査ファイルを 1 つ処理
4. Grafana Explore で `{service_name="fsxn-audit"}` を確認
5. ダッシュボードを作成
6. 監査パスが動作した後にのみ EMS と FPolicy を追加

これにより変数を最小化し、複雑さを追加する前に明確な成功シグナルを得られます。


## PoC ワークストリーム分割

マルチチーム展開の場合、ドメインごとにタスクを割り当て:

### NetApp / ONTAP 側
- [ ] ターゲット SVM で監査ログを有効化
- [ ] 監査ログフォーマットの設定（EVTX または XML）
- [ ] 監査ログローテーション間隔の文書化
- [ ] EMS Webhook 送信先の設定（EMS パス使用時）
- [ ] FPolicy サーバー接続性の検証（FPolicy パス使用時）
- [ ] S3 Access Point ファイルシステム ID に読み取り権限があることを検証
- [ ] テスト監査ファイルが S3 Access Point 経由で確認可能であることを確認

### AWS 側
- [ ] Lambda / Scheduler / DLQ のデプロイ（CloudFormation）
- [ ] IAM ポリシーと S3 Access Point リソースポリシーの検証
- [ ] チェックポイント進行の検証（SSM Parameter Store）
- [ ] Scheduler DLQ アラームの設定
- [ ] DLQ リプレイ手順のテスト

### Grafana 側
- [ ] OTLP 取り込みの検証（Explore でログが確認可能）
- [ ] 4 パネルのダッシュボード作成
- [ ] アラートルールの作成（ランサムウェア、クォータ、アクセス失敗）
- [ ] コンタクトポイントと通知ポリシーの設定
- [ ] ラベルマッピングの検証（`service_name` インデックスラベル）

## 成果指標

PoC の価値を示すために以下の KPI を追跡:

| 指標 | 目標 | 計測方法 |
|--------|--------|----------------|
| Grafana で最初の監査ログが表示されるまでの時間 | デプロイから 30 分以内 | 最初のログエントリのタイムスタンプ |
| 検証済み LogQL クエリ数 | 5 以上 | 記事内の Verified Query Matrix |
| アラートルール作成の成功 | 3/3 ルール | `create-alerts.sh` の終了コード |
| ポーラー平均実行時間 | スケジュール間隔の 60% 未満 | CloudWatch Lambda Duration p95 |
| Scheduler DLQ カウント | 0 | SQS メトリクス |
| セキュリティオーナーの承認 | サインオフ済み | Webhook 認証モードの合意 |
| 顧客サインオフ | 文書化済み | At-least-once セマンティクスの受容 |
