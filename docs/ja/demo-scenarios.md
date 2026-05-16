# デモシナリオ集

## 概要

各ベンダー統合のデモ手順と想定シナリオです。実際のデモ実施時に使用してください。

---

## シナリオ 1: 不正アクセス検知 (Datadog)

### ストーリー
社内の機密ファイルに対して、権限のないユーザーからのアクセス試行を検知し、Datadog でリアルタイムにアラートを発報する。

### 手順

1. **準備**: Datadog 統合をデプロイ済み
2. **操作**: FSx ONTAP マウントポイントで権限のないファイルにアクセス
   ```bash
   # 権限のないユーザーで機密ファイルにアクセス試行
   sudo -u testuser cat /mnt/fsxn/confidential/secret-report.pdf
   # → Permission denied (監査ログに Failure として記録)
   ```
3. **確認**: Datadog Logs で確認
   - 検索: `source:fsxn @attributes.result:Failure`
   - ダッシュボードで失敗アクセスの急増を確認
4. **アラート**: Datadog Monitor で閾値超過時に Slack/PagerDuty 通知

### 期待される結果
- 30秒以内に Datadog Logs にイベント到着
- `@attributes.user`, `@attributes.path`, `@attributes.client_ip` で追跡可能

---

## シナリオ 2: ランサムウェア検知 (Splunk + EMS)

### ストーリー
ARP/AI がランサムウェアの疑いのある活動を検知し、EMS イベント経由で Splunk にアラートを送信する。

### 手順

1. **準備**: Splunk 統合 + EMS Webhook 設定済み
2. **シミュレーション**: 大量のファイルリネーム操作を実行
   ```bash
   # ランサムウェアを模倣した大量リネーム（テスト環境のみ）
   for f in /mnt/fsxn/test-data/*.txt; do
     mv "$f" "${f}.encrypted"
   done
   ```
3. **ARP 検知**: ONTAP ARP/AI が異常を検知
   - EMS イベント `arw.volume.state` が発行される
   - 自動スナップショット `Anti_ransomware_backup_*` が作成される
4. **Splunk 確認**:
   - 検索: `index=fsxn_audit sourcetype=fsxn:ontap:audit event_type=arw*`
   - アラート: 「ARP Detection」ダッシュボードで確認

### 期待される結果
- ARP 検知から 1 分以内に Splunk にアラート到着
- Splunk ダッシュボードで攻撃タイムラインを可視化

---

## シナリオ 3: クォータ閾値超過アラート (New Relic + EMS)

### ストーリー
ユーザーのストレージ使用量がソフトクォータを超過し、管理者に New Relic 経由で通知する。

### 手順

1. **準備**: New Relic 統合 + EMS CloudWatch 連携設定済み
2. **操作**: 大容量ファイルを書き込んでクォータ超過
   ```bash
   # テスト用大容量ファイル作成
   dd if=/dev/zero of=/mnt/fsxn/user-data/large-file.bin bs=1M count=500
   ```
3. **EMS 発行**: `wafl.quota.softlimit.exceeded` イベント
4. **New Relic 確認**:
   - Logs UI で `source:fsxn-ontap` フィルタ
   - NRQL: `SELECT count(*) FROM Log WHERE source='fsxn-ontap' AND event_type LIKE 'wafl.quota%' SINCE 1 hour ago`

### 期待される結果
- クォータ超過から 2 分以内に New Relic にログ到着
- New Relic Alert Condition で自動通知

---

## シナリオ 4: マルチベンダー同時配信 (OTel Collector)

### ストーリー
OTel Collector を使って、同一の監査ログを Grafana Cloud と Honeycomb に同時配信する。

### 手順

1. **準備**: OTel Collector 統合デプロイ + Collector 設定
   ```yaml
   # otel-collector-config.yaml
   exporters:
     loki:
       endpoint: https://logs-prod.grafana.net/loki/api/v1/push
     otlphttp/honeycomb:
       endpoint: https://api.honeycomb.io
       headers:
         x-honeycomb-team: ${HONEYCOMB_KEY}
   service:
     pipelines:
       logs:
         exporters: [loki, otlphttp/honeycomb]
   ```
2. **操作**: FSx ONTAP でファイル操作
3. **確認**:
   - Grafana: Explore → Loki → `{job="fsxn-audit"}`
   - Honeycomb: Dataset `fsxn-audit` → Query

### 期待される結果
- 両ベンダーに同一イベントが到着
- ベンダー切り替え時にコード変更不要

---

## シナリオ 5: コンプライアンス監査レポート (Elastic)

### ストーリー
四半期ごとのコンプライアンス監査のため、特定期間のファイルアクセスログを Elasticsearch で集計・レポート生成する。

### 手順

1. **準備**: Elastic 統合デプロイ済み
2. **データ蓄積**: 通常運用で監査ログが日次インデックスに蓄積
3. **レポート生成**: Kibana で可視化
   ```
   GET fsxn-audit-2026.01.*/_search
   {
     "query": {"bool": {"must": [
       {"term": {"fsxn.svm": "svm-prod-01"}},
       {"range": {"@timestamp": {"gte": "2026-01-01", "lte": "2026-03-31"}}}
     ]}},
     "aggs": {
       "by_user": {"terms": {"field": "user.name.keyword"}},
       "by_operation": {"terms": {"field": "fsxn.operation.keyword"}}
     }
   }
   ```
4. **ダッシュボード**: Kibana Dashboard でアクセスパターン可視化

---

## シナリオ 6: FPolicy リアルタイムファイル監視 (Dynatrace)

### ストーリー
特定の拡張子（.exe, .bat, .ps1）のファイルが作成された場合、即座に Dynatrace にアラートを送信する。

### 手順

1. **準備**: FPolicy + Dynatrace 統合設定済み
2. **FPolicy 設定**:
   ```bash
   fpolicy policy event create -vserver svm-prod-01 \
     -event-name suspicious-files \
     -protocol cifs \
     -file-operations create \
     -filters-on-extension exe,bat,ps1,vbs
   ```
3. **操作**: 疑わしいファイルを作成
   ```bash
   echo "test" > /mnt/fsxn/shared/malware.exe
   ```
4. **Dynatrace 確認**: Problems → Custom events

---

## デモ環境セットアップチェックリスト

- [ ] FSx ONTAP ファイルシステム稼働中
- [ ] 監査ログ有効化済み
- [ ] S3 バケット + Access Point デプロイ済み
- [ ] 対象ベンダー統合スタックデプロイ済み
- [ ] テスト用ファイル/ディレクトリ準備
- [ ] ベンダー側ダッシュボード/アラート設定済み
- [ ] スクリーンショット撮影ツール準備

## スクリーンショット撮影ポイント

各デモで以下のスクリーンショットを撮影:

1. **Lambda CloudWatch Logs**: 正常処理のログ
2. **ベンダー UI**: ログ到着確認画面
3. **ダッシュボード**: 可視化されたデータ
4. **アラート**: 通知が発報された画面
5. **アーキテクチャ図**: 実際のリソース構成
