# 運用ガイド — Grafana Cloud 統合

## 推奨 CloudWatch アラーム

パイプラインが配信するログだけでなく、パイプライン自体を監視してください:

| アラーム | メトリクス / ソース | 閾値 | アクション |
|-------|----------------|-----------|--------|
| Scheduler DLQ 深度 | SQS `ApproximateNumberOfMessagesVisible` | > 0 | スケジュール実行の失敗を調査 |
| Lambda Errors | Lambda `Errors` | > 0 | CloudWatch Logs でスタックトレースを確認 |
| Lambda Throttles | Lambda `Throttles` | > 0 | Reserved Concurrency / バックログを確認 |
| Lambda Duration | Lambda `Duration` p95 | > 240000 ms (4 分) | 5 分でタイムアウトのリスク; MAX_KEYS_PER_RUN を削減 |
| Lambda DLQ 深度 | SQS `ApproximateNumberOfMessagesVisible` (Lambda DLQ) | > 0 | リトライ後の処理失敗 |
| チェックポイント経過時間 | カスタムメトリクス（下記参照） | > 想定ローテーション間隔 | ポーラーがスタックまたはサイレント障害の可能性 |
| Grafana 送信失敗 | カスタムメトリクス（下記参照） | > 0 | OTLP Gateway が到達不能またはスロットリング中 |

## カスタムメトリクス（オプション）

より深い可視性のために、Lambda からカスタム CloudWatch メトリクスを発行します:

```python
import boto3

cloudwatch = boto3.client("cloudwatch")

def emit_metric(name: str, value: float, unit: str = "Count") -> None:
    cloudwatch.put_metric_data(
        Namespace="FSxONTAP/Grafana",
        MetricData=[{
            "MetricName": name,
            "Value": value,
            "Unit": unit,
        }],
    )

# Examples:
# emit_metric("FilesProcessed", len(processed_keys))
# emit_metric("GrafanaSendFailures", failure_count)
# emit_metric("CheckpointAge", seconds_since_last_update, "Seconds")
```

## Poison-Pill ファイルの処理

Quickstart では、パースまたは配信の失敗時にチェックポイントの進行を停止し、次回実行で安全にリトライできるようにしています。

本番環境では、Poison-Pill ポリシーを定義してください:

- 同じオブジェクトを最大 N 回リトライ（DynamoDB でオブジェクトキー + ETag ごとにリトライ回数を追跡）
- N 回失敗後、失敗したオブジェクトのメタデータを隔離テーブルに移動
- オブジェクトがリトライ閾値を超えた場合にオペレーターにアラート
- オペレーターの明示的な承認後、オプションで Poison-Pill を超えてチェックポイントを進行
- 後の調査のために隔離されたキーをログに記録

Poison-Pill ポリシーがない場合、1 つの破損または不正な監査ログファイルが、ハイウォーターマークチェックポイント使用時に後続のすべてのファイルをブロックする可能性があります。

## Scheduler リトライポリシーの根拠

Quickstart では以下を使用:
- **MaximumRetryAttempts: 2** — 永続的な障害を迅速に表面化
- **MaximumEventAgeInSeconds: 3600** — 無制限のリトライストームを回避

以下の場合にのみこれらの値を増加:
- Grafana エンドポイントに 1 時間を超える既知のメンテナンスウィンドウがある
- 定義済みの重複処理戦略がある（冪等配信）
- リトライされたイベントが既にチェックポイント済みのファイルを処理する可能性を受容（StartAfter により安全）

## 障害パステストカバレッジ

テストスイートはチェックポイントの安全性をカバーしています:

1. 2 つのキーがリストされ、最初は成功、2 番目の配信が失敗 → チェックポイントは最初のキーのみに留まる
2. Grafana が失敗を返す → Lambda が例外を発生 → チェックポイントは進行しない
3. 空ファイル（パース可能なレコード 0 件）→ 成功として扱い、チェックポイントは進行
4. 障害後の Scheduler 再実行 → 失敗したキーがチェックポイントからリトライされる
5. Reserved Concurrency が重複実行を防止（CloudFormation アサーション）


## ポーラーチューニング

Quickstart のデフォルトから開始:

| パラメータ | デフォルト | 目的 |
|-----------|---------|---------|
| `ScheduleExpression` | `rate(5 minutes)` | ポーリング間隔 |
| `MAX_KEYS_PER_RUN` | 100 | 1 回の実行で処理する最大ファイル数 |
| `SAFETY_THRESHOLD_MS` | 30000 | 残り 30 秒未満で処理を停止 |
| `LambdaTimeout` | 300 (5 分) | Lambda 実行タイムアウト |

### MAX_KEYS_PER_RUN を増加するタイミング

以下を確認した後にのみ増加:

- Lambda p95 Duration がスケジュール間隔を十分に下回っている
- Grafana OTLP 送信レイテンシが安定（429 スロットリングなし）
- FSx S3 Access Point 読み取りスループットが飽和していない
- Scheduler DLQ 深度が 0 のまま
- チェックポイント経過時間が想定される監査ローテーション間隔内

### ScheduleExpression 間隔を短縮するタイミング

以下の場合に短縮（例: `rate(1 minute)`）:

- ほぼリアルタイムの監査可視性が必要
- 監査ログファイルが小さく頻繁
- 1 回あたりの Lambda 実行時間が一貫して 30 秒未満

### 警告サイン

| シグナル | 意味 | アクション |
|--------|---------|--------|
| Lambda Duration p95 > 4 分 | タイムアウトのリスク | MAX_KEYS_PER_RUN を削減 |
| Scheduler DLQ メッセージ > 0 | 実行が失敗 | Lambda エラー、Grafana エンドポイントを確認 |
| チェックポイントが進行しない | ポーラーがスタック | Poison-Pill ファイルまたは認証失敗を確認 |
| Lambda Throttles > 0 | 同時実行数が枯渇 | ReservedConcurrency=1 では想定内; バックログを確認 |


## FSx 監査ポーリング検証チェックリスト

監査ログポーラーを本番環境にデプロイする前に検証:

- [ ] 監査ログファイル名が単調増加（辞書順が時系列順と一致）
- [ ] 監査ログローテーション間隔が既知で文書化済み
- [ ] 遅延到着ファイルが想定されない、またはルックバックウィンドウが設定済み
- [ ] 平均ファイルサイズが計測済み（ファイルあたりの Lambda 実行時間に影響）
- [ ] FSx プロビジョンドスループットがポーリング読み取り負荷に十分
- [ ] Lambda p95 Duration がスケジュール間隔を下回っている
- [ ] S3 Access Point ファイルシステムユーザーが監査ログパスの読み取り権限を持つ
- [ ] S3 Access Point リソースポリシーが Lambda 実行ロールを許可
- [ ] `StartAfter` チェックポイント動作がキー命名パターンで検証済み
- [ ] Scheduler DLQ アラームが設定済み

> **重要な理由**: `StartAfter` ハイウォーターマークチェックポイントは、監査ログキーが単調増加かつ不変であることを前提としています。ファイルが辞書順以外で到着したり上書きされる可能性がある場合は、代わりに DynamoDB オブジェクトレジャーを使用してください。

## オーナーシップマトリクス

エンタープライズデプロイメントでは、チーム間の運用オーナーシップを明確化:

| 領域 | 推奨オーナー |
|------|-------------------|
| FSx 監査ログ設定 | ストレージチーム |
| S3 Access Point ポリシー | ストレージ / プラットフォーム |
| Lambda デプロイと更新 | プラットフォームチーム |
| Grafana ダッシュボードとクエリ | Observability チーム |
| Grafana アラートルーティングとコンタクトポイント | SRE / セキュリティオペレーション |
| EMS Webhook セキュリティ | セキュリティ / プラットフォーム |
| Scheduler DLQ リプレイ | SRE / プラットフォーム |
| トークンローテーション（Grafana、Webhook） | セキュリティ / プラットフォーム |
| Poison-Pill 調査 | ストレージ / プラットフォーム |
| コスト監視（Lambda、Grafana 取り込み） | FinOps / プラットフォーム |

## Loki ラベルカーディナリティガイダンス

高カーディナリティフィールドを Loki ラベルに昇格**しないでください**。ログ本文または構造化メタデータに保持し、クエリ時に `| json` で抽出してください。

**ラベルにしてはいけないフィールド:**
- `UserName` — 無制限のユーザー数
- `ObjectName` / `fsxn.path` — 無制限のファイルパス
- `client.address` — 無制限の IP アドレス
- `event_id` — イベントごとに一意

**ラベルとして安全なフィールド（低カーディナリティ）:**
- `service_name` — 固定セット（`fsxn-audit`、`fsxn-ems`、`fsxn-fpolicy`）
- `severity` — 小さなセット（`alert`、`warning`、`info`）
- `operation` — 有界セット（`create`、`read`、`write`、`delete`、`rename`）

> Loki はラベルをインデックス化し、ログ内容はインデックス化しません。高カーディナリティラベルはインデックス肥大化、クエリ低速化、ストレージコスト増加を引き起こします。`{UserName="admin"}` ではなく `| json | UserName="admin"` を使用してください。

ラベルは `service_name` のような安定したルーティングディメンションに使用し、調査用フィールドはログ本文または構造化メタデータに保持してください。

## 証跡境界（コンプライアンス）

規制環境では、証跡境界を明確に文書化:

| 証跡 | 保存場所 | 保持期間 |
|----------|----------|-----------|
| 監査ログの正本 | FSx for ONTAP 監査ボリューム | ONTAP 保持ポリシーにより制御 |
| 分析とアラート | Grafana Cloud Loki | Grafana Cloud 保持ティアにより制御 |
| 失敗した実行の証跡 | Scheduler DLQ (SQS) | 14 日間（SQS 最大保持期間） |
| 処理進捗 | SSM Parameter Store チェックポイント | 無期限（削除されるまで） |
| Lambda 実行の証跡 | CloudWatch Logs | 設定可能（デフォルト: 30 日） |
| 配信セマンティクス | At-least-once | 重複の可能性あり; 重複排除はアプリ側 |

**重要な原則**: Grafana Cloud は分析、可視化、アラートの送信先であり、記録システムではありません。ONTAP ボリューム上の FSx 監査ファイルが権威あるソースです。このパイプラインは運用可視性のためにコピーを配信するものであり、元の監査証跡を置き換えるものではありません。


## セキュリティシグナルチューニング

各セキュリティユースケースに適切なイベントソースを選択:

| シグナルタイプ | ソース | ユースケース | ボリューム |
|-------------|--------|----------|--------|
| ストレージシステムアラート | EMS | ランサムウェア（ARP）、クォータ、ハードウェア | 低（高信頼度） |
| ユーザー/ファイルアクセス調査 | 監査ログ | 誰が何にいつアクセスしたか | 中〜高 |
| ほぼリアルタイムのファイル操作 | FPolicy | ファイル作成/削除/リネームの検出 | 高（スコープを慎重に） |

**ガイダンス**:
- 高信頼度のストレージシステムアラート（ランサムウェア、クォータ、ディスク障害）には EMS を使用
- ユーザー/ファイルアクセス調査とコンプライアンスには監査ログを使用
- レイテンシが重要なほぼリアルタイムのファイル操作検出には FPolicy を使用
- イベントボリュームを制御するため、FPolicy のスコープをボリューム/共有/パスで限定
- フィルタリングなしですべてのファイル操作をアラートルールに送信しない — LogQL フィルターでノイズを削減

## 適用マトリクス

この統合パターンは FSx for ONTAP 向けに設計されています。他の ONTAP 環境の場合:

| 環境 | S3 Access Point 読み取りパス | 推奨パターン |
|-------------|--------------------------|---------------------|
| FSx for ONTAP | あり（FSx 付属 S3 Access Point） | Lambda Scheduler ポーリング（本プロジェクト） |
| オンプレミス ONTAP | FSx S3 Access Point なし | OTel Collector / VM ベースシッパーまたはログエクスポート |
| Cloud Volumes ONTAP | クラウドプロバイダーごとに利用可能なアクセス方法を確認 | S3 スタイルのアクセスパスが明示的に利用可能でない限り Collector / VM ベースシッパー |
| ハイブリッド（FSx + オンプレミス） | 混在 — ソースアダプターを分離 | OTLP に正規化し、Collector で集約 |

> S3 Access Point 読み取りパスは FSx for ONTAP 固有です。オンプレミス ONTAP と Cloud Volumes ONTAP には FSx S3 Access Point がありません。ハイブリッド環境では、環境ごとに個別のソースアダプターを持つ OTel Collector（Part 5）を集約レイヤーとして使用してください。

## トラブルシューティング境界マトリクス

問題調査時は、まず責任レイヤーを特定:

| 症状 | 最初に確認 | 想定オーナー |
|---------|-------------|--------------|
| S3 AP 経由で監査ファイルが見えない | ONTAP 監査設定、S3 AP 権限、ファイルシステムユーザー | NetApp / ストレージ |
| Lambda で GetObject の `AccessDenied` | IAM ポリシー、S3 AP リソースポリシー、ファイルシステムユーザーマッピング | AWS / ストレージ |
| Scheduler DLQ メッセージ > 0 | Scheduler ログ、Lambda 実行エラー | プラットフォーム / SRE |
| CloudWatch の Lambda エラー | Lambda コード、Grafana エンドポイント、認証情報 | プラットフォーム / Observability |
| Grafana クエリが空を返す | OTLP 配信成功、ラベルマッピング、テナント設定 | Observability |
| EMS イベントが到着しない | ONTAP Webhook 送信先設定、API Gateway ログ | NetApp / セキュリティ / プラットフォーム |
| FPolicy イベントが遅延 | SQS バックログ、ブリッジ Lambda エラー、ECS タスクヘルス | プラットフォーム / NetApp |
| チェックポイントが進行しない | Poison-Pill ファイル、認証失敗、Grafana 5xx | プラットフォーム（Poison-Pill 処理を参照） |


## FPolicy 運用モードガイダンス

FPolicy は mandatory（必須）モードまたは non-mandatory（非必須）モードで動作できます。ユースケースに応じて選択:

| モード | 外部エンジン利用不可時の動作 | ユースケース |
|------|-------------------------------------------|----------|
| **Non-mandatory** | 通知なしでファイル操作が続行 | Observability 専用パイプライン（本プロジェクト） |
| **Mandatory** | エンジンが応答するまでファイル操作がブロック | アクセス制御 / DLP 強制 |

**Observability パイプラインへの推奨事項**:
- **Non-mandatory** モードを使用 — パイプラインは可視性のためであり、アクセス制御ではない
- イベントボリュームを削減するため、監視対象操作のスコープを限定（例: create + delete + rename のみ）
- 可能な場合はボリュームまたは共有パスでスコープを限定
- 配信ヘルスのため SQS バックログとブリッジ Lambda エラーを監視
- FPolicy イベントは at-least-once シグナルとして扱う（エンジン再接続時に重複の可能性）
- ECS Fargate タスクが再起動した場合、ONTAP External Engine IP を更新

**ボリューム制御**: FPolicy はビジーなファイル共有で非常に高いイベントボリュームを生成する可能性があります。Observability 用途では、すべての操作（open、read、write、close）ではなく、セキュリティ関連の操作（create、delete、rename）に焦点を当ててください。ONTAP FPolicy ポリシーレベルでフィルタリングし、Lambda ではフィルタリングしないでください。


## OTLP マッピング

Lambda はパースされた監査/EMS/FPolicy レコードを以下のマッピングで OTLP ログレコードに変換します:

| ソースフィールド | OTLP 配置場所 | 根拠 |
|-------------|---------------|-----------|
| `"fsxn-audit"` / `"fsxn-ems"` / `"fsxn-fpolicy"` | `resource.attributes["service.name"]` | Loki/Grafana サービス識別; `service_name` インデックスラベルになる |
| シグナルタイプ | `resource.attributes["fsxn.signal_type"]` | リソースレベルで audit / ems / fpolicy を区別 |
| SVM 名 | `resource.attributes["fsxn.svm.name"]` | ソース SVM の識別 |
| イベントタイムスタンプ | `log_record.time_unix_nano` | 元のイベント時刻 |
| ONTAP イベント名（EMS） | `log_record.attributes["event_name"]` | クエリ時フィルタリング |
| 監査操作 | `log_record.attributes["Operation"]` | クエリ時フィルタリング |
| ユーザー名 | `log_record.attributes["UserName"]` | クエリ時フィルタリング（ラベルではない） |
| オブジェクトパス | `log_record.attributes["ObjectName"]` | クエリ時フィルタリング（ラベルではない） |
| 生イベントペイロード | `log_record.body` | 調査用にソースペイロードを保持 |
| 重大度 | `log_record.severity_text` | EMS 重大度マッピング |

### 属性命名ポリシー

- 該当する場合は OTel 標準属性を使用: `service.name`、`deployment.environment.name`、`cloud.region`
- 完全忠実度のため ONTAP ネイティブフィールドを `log_record.body` に保持
- 安定した `fsxn.*` 名前空間の下に正規化カスタム属性を追加:
  - `fsxn.signal_type` — audit / ems / fpolicy
  - `fsxn.svm.name` — ソース SVM
  - `fsxn.volume.name` — ソースボリューム（利用可能な場合）
  - `fsxn.operation` — 正規化された操作タイプ
  - `fsxn.result` — success / failure

ソースネイティブフィールドと正規化フィールドの両方が存在する場合、フォレンジック忠実度のために元のフィールドをログ本文に保持し、クロスバックエンドクエリのために正規化 `fsxn.*` 属性を追加してください。

この名前空間アプローチにより、将来 OpenTelemetry Semantic Conventions がストレージドメイン属性を追加した場合の前方互換性が確保されます。

## Alloy への段階的移行

Lambda は既に OTLP 形式のログペイロードを出力しています。直接送信から Grafana Alloy への移行手順:

1. Alloy をデプロイ（ECS Fargate または EC2）し、`otelcol.receiver.otlp` コンポーネントを設定
2. Lambda の `LOKI_ENDPOINT` を Alloy の OTLP レシーバーに変更（`http://<alloy>:4318/v1/logs`）
3. Alloy プロセッサを追加: `otelcol.processor.batch`、`otelcol.processor.attributes`、`otelcol.processor.transform`
4. Alloy から Grafana Cloud OTLP エンドポイントへ `otelcol.exporter.otlphttp` でエクスポート
5. オプションで別のバックエンド用の 2 番目のエクスポーターを追加（Datadog、S3 アーカイブなど）

Alloy レイヤーの利点:
- **バッチ処理**: 複数の Lambda 実行を効率的なバッチに集約
- **永続キュー付きリトライ**: データを失わずに Grafana Cloud の障害を乗り越える
- **変換/墨消し**: 送信前に PII を削除またはメタデータで強化
- **マルチバックエンドルーティング**: 単一パイプラインから複数の送信先にファンアウト
- **リソース検出**: クラウドメタデータ（リージョン、アカウントなど）を自動追加

Lambda は標準 OTLP ペイロードを生成するため、Lambda コードの変更は不要です — 送信先 URL のみ変更します。

Lambda はソース固有のパースと OTLP 出力に集中させてください。エンリッチメント、墨消し、ルーティング、バックエンドファンアウトなどの横断的パイプライン関心事は Alloy または OpenTelemetry Collector に移動してください。

## テレメトリパイプライン SLO 例

これらはパイプライン内部の SLO であり、アプリケーションユーザー向けの SLO ではありません。監査、EMS、FPolicy シグナルが想定される運用境界内で Grafana に到着するかどうかを測定します。

本番環境では、パイプライン自体の SLO を定義:

| SLO | 目標 | 計測方法 |
|-----|--------|-------------|
| 鮮度 | 監査ファイルの 99% が 2× スケジュール間隔以内に Grafana で確認可能 | チェックポイント経過時間カスタムメトリクス |
| 完全性 | 処理済みファイルの 99.9% が配信成功 | Grafana 送信失敗率 |
| リプレイ可能性 | Scheduler DLQ イベントの 100% が 1 営業日以内にレビュー | DLQ 経過時間アラーム |
| 安全性 | クリーンアップスクリプトによる本番監査ファイルの削除 0 件 | クリーンアップスクリプトのガード |
| 可用性 | スケジュール実行の 99% 以上でパイプラインがファイルを処理 | Scheduler DLQ 深度 = 0 |

これらは初期目標です。組織の監査コンプライアンス要件と運用キャパシティに基づいて調整してください。


## 単一ポーラーを超えたスケーリング

単一同時実行ポーラー（ReservedConcurrentExecutions=1）は、Quickstart および低〜中ボリュームワークロードに適しています。より高いボリュームでは、単に MAX_KEYS_PER_RUN を増やすのではなく、再設計してください:

| アプローチ | 使用タイミング | トレードオフ |
|----------|-------------|-----------|
| MAX_KEYS_PER_RUN の増加 | 中程度のボリューム、単一プレフィックス | シンプルだが Lambda タイムアウトに制約 |
| プレフィックスパーティショニング | 複数の SVM または監査パス | 安定したプレフィックスレイアウトが必要 |
| DynamoDB オブジェクトレジャー | 並行ワーカーが必要 | 複雑度は高いが重複排除が可能 |
| SQS ファンアウト | 高ボリューム、オブジェクトごとの分離 | リーダーがリスト → SQS → 複数シッパー |
| Alloy / Collector | マルチバックエンドまたはエンリッチメントが必要 | コンピュートコストがかかるがパイプラインの柔軟性 |

**スケール設計の原則**:
- 監査ログレイアウトがサポートする場合、安定したプレフィックスでパーティション（例: SVM ごとのプレフィックス）
- 並行処理のため SSM ハイウォーターマークを DynamoDB オブジェクトレジャーに置き換え
- SQS を使用してオブジェクト処理を複数のシッパー Lambda にファンアウト
- オブジェクトキー + ETag / LastModified による冪等性を追加（条件付き DynamoDB 書き込み）
- FSx S3 Access Point 読み取りスループットを監視 — FSx プロビジョンドスループットに制約される
- MAX_KEYS_PER_RUN を無制限に増やすのではなく、バックプレッシャーを適用（ポーリングレートの削減または一時停止）
- パイプライン関心事（バッチ処理、リトライ、変換）が Lambda の能力を超えた場合は Alloy / Collector を検討

## ミッションクリティカルワークロード補遺

このパイプラインは高可用性メカニズム**ではありません**。以下を提供することで HA / DR 設計を補完します:

- ファイルアクセスと管理アクティビティの監査証跡
- ONTAP 側イベント（ランサムウェア、クォータ、ハードウェア）の EMS アラート可視性
- FPolicy ベースのほぼリアルタイムファイル操作可視性
- ログ配信ヘルスの DLQ とチェックポイント証跡
- 運用対応のための Grafana ダッシュボードとアラート

EC2 上の FSx for ONTAP を使用する SAP、Oracle、SQL Server、JP1、HULFT、VDI、またはエンタープライズファイルサービスワークロードでは、この Observability レイヤーをワークロード固有の HA / DR パターンと組み合わせてください。このパイプラインは RTO/RPO に影響しません — より迅速なインシデント調査と監査コンプライアンスをサポートする運用証跡とアラートを提供します。
