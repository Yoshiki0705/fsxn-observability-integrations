# FSx for ONTAP 監査ログの Lakehouse 長期保管パターン

🌐 **日本語** (このページ) | [English](../en/lakehouse-long-term-retention.md)

## TL;DR

Observability ベンダーは通常、FSx for ONTAP の監査ログを数週間〜数ヶ月保持します。コンプライアンス要件で複数年の保管が必要な場合、あるいはログ検索ではなく複数年分のデータを横断する SQL 結合が必要な場合、このガイドは同じ監査ログストリームを Apache Parquet に変換し、通常の Amazon S3 バケットに保管し、Amazon Athena や Snowflake で SQL クエリ可能にする第二の経路を追加します。これは本プロジェクトのベンダーパイプラインの代替ではなく、長期保管・SQL 分析を補完するものです。

**E2E 検証済み**（2026年7月19日、ap-northeast-1）: 合成監査ログ 500 件 → Kinesis Data Firehose（JSON → Parquet 変換）→ S3（Snappy 圧縮 Parquet、日付パーティション）→ Glue Data Catalog（Partition Projection、クローラー不要）→ Amazon Athena。`SELECT COUNT(*)` で正確に 500 件、`GROUP BY operation, result` 集計クエリの結果が入力データの分布と一致。クエリ実行はスキャン量 556 バイト、実行時間 417ms。

## なぜ第二の経路が必要か

本プロジェクトの9ベンダー統合（Datadog、Splunk、Elastic など）は**検索とアラート**のために構築されています — 今この瞬間に問題のログ行を見つけ、数秒以内にアラートを発火させることです。**複数年にわたる SQL 分析**のためには構築されていません。「過去3年間の四半期ごとにSVM別で失敗した削除操作は何件か」という問いは異なる種類の問いであり、多くの Observability プラットフォームの保持期間（標準ティアで30〜90日）とGBあたりの取り込み課金は、この規模の問いには適していません。

| 要件 | Observability ベンダー（本プロジェクトの9統合） | Lakehouse 長期保管（本ガイド） |
|---|---|---|
| 直近1時間の特定エラーを検索 | ✅ 最適 | ⚠️ 動作するが、リアルタイム検索UX向けではない |
| 異常検知から数秒以内にアラート | ✅ 最適 | ❌ リアルタイムアラート向けではない |
| 複数年のコンプライアンス保管 | ⚠️ 可能だが、規模が大きくなるとコストが高くなりやすい | ✅ 最適（S3ストレージ階層は規模が大きいほどコスト効率が良い） |
| 複数年分データへのアドホックSQL結合 | ❌ 多くのプラットフォームは苦手 | ✅ 最適（AthenaやSnowflakeはSQLネイティブ） |
| BIダッシュボード・レポートツール連携 | ⚠️ ベンダー依存 | ✅ 最適（標準SQL/JDBC/ODBC） |

これはベンダー対ベンダーの優劣判断ではなく、問われている質問の性質に応じて選択するものです。多くの本番環境では、同じソースデータから両方の経路を並行運用します。

## アーキテクチャ

```
FSx for ONTAP（監査ログ有効化済み SVM）
        │
        ▼
S3（標準バケット、監査ログJSON — ベンダーパイプラインと同じソース）
        │
        ▼
Kinesis Data Firehose
  • 入力: OpenX JSON デシリアライザー
  • 出力: Parquet（Snappy圧縮）、DataFormatConversionConfiguration 経由
  • バッファ: 64 MB / 300秒（Parquet変換有効時、64 MBがFirehoseの最小強制値）
        │
        ▼
S3（保管バケット）
  audit-logs/year=YYYY/month=MM/day=DD/*.parquet
        │
        ├──────────────────────────┐
        ▼                          ▼
  AWS Glue Data Catalog      Snowflake External Stage
  （Partition Projection、    （Storage Integration、
   クローラー不要）            2段階 IAM トラスト）
        │                          │
        ▼                          ▼
   Amazon Athena              Snowflake External Table
   （従量課金 SQL）            （SQL + Snowflake ガバナンス機能）
```

本ガイドは本プロジェクトのベンダーパイプラインが使う FSx for ONTAP S3 Access Point パターンには触れません。Firehose ストリームは、既に監査ログJSONを受信している**標準 S3 バケット**（ベンダー Lambda が読み取っているのと同じソース）から読み取ります。これは意図的なスコープ境界です — 本ガイドの制約を、本プロジェクトの他の場所で文書化されている FSx for ONTAP S3 AP 固有の制約（S3イベント通知非対応、AD DC 到達性要件など）から独立させています。これらの制約はここには当てはまりません。Firehose ストリームとその後段の S3 イベント通知（下記 Snowflake セクションの Snowpipe 自動取り込みで使用）は、それらをネイティブにサポートするバケットに対して動作するためです。

## Glue テーブルスキーマ

本プロジェクトのベンダー Lambda ハンドラー（`integrations/otel-collector/lambda/handler.py` の `FIELD_MAPPING`、および `integrations/otel-collector/tests/test_data/sample_audit_logs.json`）と同じフィールド名を、一貫性のためそのまま使用しています。

| カラム | 型 | ソースフィールド | 補足 |
|---|---|---|---|
| `timestamp` | string | `Timestamp` | ISO 8601、文字列として保持（必要に応じてクエリ側でキャスト） |
| `eventid` | string | `EventID` | ONTAP 監査イベントID |
| `svmname` | string | `SVMName` | Storage Virtual Machine 名 |
| `username` | string | `UserName` | 匿名・システム操作では空の場合あり |
| `clientip` | string | `ClientIP` | 空の場合あり |
| `operation` | string | `Operation` | 例: `ReadData`、`WriteData`、`Delete` |
| `objectname` | string | `ObjectName` | ファイルパス |
| `result` | string | `Result` | `Success`、`Failure`、`Access Denied` |
| `year` / `month` / `day` | string（パーティション） | Firehose 配信タイムスタンプから導出 | Partition Projection — クローラー不要 |

> **データ分類に関する補足**: `username`・`clientip`・`objectname` は、組織のファイル命名規則やユーザーディレクトリ構成によっては個人情報を含む可能性があります。この Athena/Snowflake テーブルへの広範なクエリアクセスを許可する前に、[データ分類ガイド](data-classification.md) の取り扱いパターンを参照してください。

## パイプラインのデプロイ

```bash
aws cloudformation deploy \
  --template-file integrations/lakehouse-retention/template.yaml \
  --stack-name fsxn-lakehouse-retention \
  --parameter-overrides \
    RetentionBucketName=<グローバルに一意なバケット名> \
    AthenaResultsBucketName=<グローバルに一意な結果バケット名> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region <対象リージョン>
```

### 準備が必要なもの

- [ ] S3バケット・Glueデータベース/テーブル・Kinesis Data Firehose 配信ストリーム・IAMロール・Athena ワークグループを作成できる権限を持つAWSアカウント
- [ ] グローバルに一意なS3バケット名2つ（保管用バケット、Athenaクエリ結果用バケット）
- [ ] アカウントで **AWS Lake Formation** が有効な場合（`aws lakeformation get-data-lake-settings` で確認）: 下記の Lake Formation の落とし穴に備えてください — このテンプレートで最も頻出するデプロイ失敗要因です
- [ ] （任意、Snowflakeパスのみ）`ACCOUNTADMIN` 権限を持つ Snowflake アカウント（Standard エディション以上、トライアルアカウントでも可）

### デプロイ時間の見積もり

| 作業 | 所要時間の目安 |
|---|---|
| CloudFormation スタックデプロイ | 約2〜3分 |
| 最初のParquetファイルがS3に出現するまで | 最初のレコード送信後、`BufferIntervalSeconds`（デフォルト300秒）経過時、または64MBバッファが満杯になった時点のいずれか早い方 |
| Snowflake Storage Integration の2段階トラスト設定 | 約5〜10分（Integration作成 → `DESCRIBE INTEGRATION` → SnowflakeのアカウントID/External IDでIAMロール再デプロイ → 再確認） |

### 検証時に判明した注意点: Lake Formation

アカウントで Lake Formation が有効な場合（他のGlueテーブルで一度でも Lake Formation を使ったことがあるアカウントでは一般的）、Firehose 配信ロールの IAM ポリシーで `glue:GetTable` を許可しているだけでは**不十分**です。Firehose の `DataFormatConversionConfiguration` は同じプリンシパルに対する Lake Formation 権限も別途要求し、なければ配信ストリームの作成が以下のエラーで失敗します。

```
Access was denied when calling Glue. Please ensure that the role specified in the
data format conversion configuration has the necessary permissions. Insufficient
Lake Formation permission(s): Required Describe on audit_logs
```

これは Firehose や Glue のドキュメントからは分かりにくい落とし穴です。IAM 権限と Lake Formation 権限は独立して加算的に評価されるため、片方だけでは、両方に依存するリソースを実際に作成しようとするまで問題が見えません。本テンプレートには既に必要な `AWS::LakeFormation::PrincipalPermissions` リソース（データベースに対する `DESCRIBE`、テーブルに対する `DESCRIBE`/`SELECT`/`ALTER`/`INSERT`、Firehose ロールへの付与）が含まれており、明示的な `DependsOn` 順序付けにより、これらの権限が存在するまで配信ストリームが作成されないようにしています。本テンプレートを自身のユースケース向けにフォークする場合、これらのリソースは残してください — 削除すると Lake Formation 有効アカックでのみサイレントにパイプラインが壊れ、Lake Formation 無効なテスト環境では見逃しやすく、本番環境で予期せず遭遇することになります。

### 検証時に判明したその他2つのCloudFormationの落とし穴

- `AWS::Glue::Table` には明示的な `DependsOn: GlueDatabase` が必要です。これがないと、CloudFormation はデータベースが存在する前にテーブル作成を試みる場合があり（`Database <name> not found`）、`DatabaseName: !Ref GlueDatabaseName`（データベースリソース自体への `!GetAtt`/`!Ref` ではなく単純な文字列参照）からは暗黙の依存関係が推論されないためです。
- `AWS::KinesisFirehose::DeliveryStream` の `ExtendedS3DestinationConfiguration` にある `CloudWatchLoggingOptions.LogStreamName` は `!Ref FirehoseLogStream`（単純な文字列）である必要があり、`!GetAtt FirehoseLogStream.LogStreamName` は使えません。`!GetAtt` を使うと `cfn-lint` の `E1010` 型不一致エラーが発生します。このプロパティは `String` 型を期待しており、`AWS::Logs::LogStream` リソースへの `!Ref` は（多くの他のリソースタイプでは `!Ref` がARNやIDを返すのとは異なり）既にログストリーム名に解決されるためです。

## Athena でのクエリ

```sql
-- 特定日の総レコード数
SELECT COUNT(*) AS total_records
FROM fsxn_audit_lakehouse.audit_logs
WHERE year = '2026' AND month = '07' AND day = '19';

-- Operation/Result の分布（year/month/day によるパーティションプルーニング）
SELECT operation, result, COUNT(*) AS cnt
FROM fsxn_audit_lakehouse.audit_logs
WHERE year = '2026' AND month = '07' AND day = '19'
GROUP BY operation, result
ORDER BY cnt DESC;

-- 日付範囲を横断した、SVM別の失敗・拒否操作
SELECT svmname, operation, COUNT(*) AS cnt
FROM fsxn_audit_lakehouse.audit_logs
WHERE year = '2026' AND month = '07'
  AND result IN ('Failure', 'Access Denied')
GROUP BY svmname, operation
ORDER BY cnt DESC;
```

**検証済みクエリ性能**（500件のテストデータセット、単一Parquetファイル、Snappy圧縮後2,970バイト）: `DataScannedInBytes=556`、`EngineExecutionTimeInMillis=417`。この規模では、これらの数値は本番規模のベンチマークとしては意味を持ちません — パイプラインが正しく動作することを確認するものであり、大量データ時の速度を示すものではありません。Partition Projection により、上記クエリで Athena は `year=2026/month=07/day=19` プレフィックスのみをスキャンし、バケット全体を列挙しません。パーティション数が数千に増える（複数年保管）ほど、この効果は重要になります。

## Snowflake でのクエリ（External Table）

Snowflake 対応は、[fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) の Snowflake 統合で既に確立済みの2段階 Storage Integration トラストパターンを再利用しています — FSx for ONTAP S3 Access Point 向けではなく、通常のS3バケット向けに適応しています。

```bash
# Phase 1: プレースホルダー（自アカウント）トラストポリシーでIAMロールをデプロイ
aws cloudformation deploy \
  --template-file integrations/lakehouse-retention/snowflake-role.yaml \
  --stack-name fsxn-lakehouse-retention-snowflake \
  --parameter-overrides RetentionBucketName=<保管用バケット名> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region <対象リージョン>
```

```sql
-- Snowflake 内（完全なスクリプトは
-- integrations/lakehouse-retention/sql/01_storage_integration_and_stage.sql 参照）
CREATE OR REPLACE STORAGE INTEGRATION fsxn_lakehouse_retention_integration
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = '<snowflake-role.yaml の IAMRoleArn 出力値>'
  STORAGE_ALLOWED_LOCATIONS = ('s3://<保管用バケット名>/audit-logs/');

DESCRIBE INTEGRATION fsxn_lakehouse_retention_integration;
-- STORAGE_AWS_IAM_USER_ARN と STORAGE_AWS_EXTERNAL_ID をコピーし、
-- SnowflakeAccountId/SnowflakeExternalId にこれらの値を設定して
-- snowflake-role.yaml を再デプロイ（Phase 2 トラスト）。

CREATE OR REPLACE STAGE audit_logs_stage
  STORAGE_INTEGRATION = fsxn_lakehouse_retention_integration
  URL = 's3://<保管用バケット名>/audit-logs/'
  FILE_FORMAT = (TYPE = 'PARQUET');

LIST @audit_logs_stage;

CREATE OR REPLACE EXTERNAL TABLE audit_logs_ext (
    "timestamp"  VARCHAR AS (value:"timestamp"::VARCHAR),
    eventid      VARCHAR AS (value:eventid::VARCHAR),
    svmname      VARCHAR AS (value:svmname::VARCHAR),
    username     VARCHAR AS (value:username::VARCHAR),
    clientip     VARCHAR AS (value:clientip::VARCHAR),
    operation    VARCHAR AS (value:operation::VARCHAR),
    objectname   VARCHAR AS (value:objectname::VARCHAR),
    result       VARCHAR AS (value:result::VARCHAR)
)
  LOCATION = @audit_logs_stage
  FILE_FORMAT = (TYPE = 'PARQUET')
  AUTO_REFRESH = FALSE;

ALTER EXTERNAL TABLE audit_logs_ext REFRESH;

SELECT COUNT(*) AS total_records FROM audit_logs_ext;
```

> **本セクションの検証状況: E2E検証済み**（2026年7月20日）。上記Firehoseパイプラインが生成した同じ500件のParquetデータセットを使い、Storage Integrationの2段階トラスト設定が成功し、`LIST @audit_logs_stage` が実際のParquetファイルをS3から返し、`SELECT COUNT(*) FROM audit_logs_ext` は正確に500件を返しました — Athenaの結果と完全に一致します。同じExternal Tableに対する `GROUP BY operation, result` クエリも、上記Athena検証と同じOperation×Result分布に一致する15行を返しました。

### FSx S3 AP 版 Snowflake パスとの構成上の違い

本パイプラインのデータは FSx for ONTAP S3 Access Point ではなく**通常のS3バケット**に着地するため、S3イベント通知によってトリガーされる実際の Snowpipe 自動取り込みが直接動作すると予想されます。`fsxn-lakehouse-integrations` プロジェクトの Snowflake 統合は、まさにこの理由（FSx for ONTAP S3 AP は S3イベント通知非対応）で FSx for ONTAP S3 AP に対して自動取り込みを使えず、FPolicy + Lambda + SNS + Snowpipe REST API、またはスケジュール実行の `COPY INTO` にフォールバックする必要がありました。本ガイドのアーキテクチャは、保管先の標準S3バケットがS3イベント通知をネイティブにサポートするため、この制約を取り除いています（本検証では Snowpipe 自動取り込み自体は実施しておらず、上記External Tableパスを検証しました。ただし自動取り込みが依存するS3イベント通知機能自体は、FSx S3 APとは異なり通常のS3バケットの標準機能です）。

## コスト比較

| コンポーネント | 月額コストの主な要因 | 補足 |
|---|---|---|
| S3ストレージ（保管バケット） | 標準S3料金、90日でS3標準低頻度アクセスへ、365日でS3 Glacier Instant Retrieval へ移行（本テンプレートのライフサイクルポリシー） | Parquet + Snappy圧縮により、生のJSONに比べて保存バイト数が大幅に削減される（参考: 500件のテストで生成されたParquetファイルは2,970バイト、同等の生JSONはおおよそ25倍のサイズ） |
| Kinesis Data Firehose | 取り込みGBあたり + フォーマット変換GBあたりの課金 | クエリ量に関わらず、配信された監査ログデータ量に対して課金 |
| Athena | スキャンTBあたりの課金（本稿執筆時点で$5/TB） | Partition Projection + Parquet列形式によりクエリごとのスキャンバイト数を最小化。本テンプレートのAthenaワークグループに設定した10GBのクエリ上限が、暴走クエリのコストを制限する |
| Snowflake（利用する場合） | Snowflakeコンピュートクレジット（ウェアハウス） + `COPY INTO` を使う場合はSnowflake側の追加ストレージ | External Table はデータをS3に残すため重複ストレージコストを回避。`COPY INTO` はストレージが重複するが、Snowflakeネイティブの性能機能（クラスタリング、Time Travel）が使える |

**同じデータをObservabilityベンダーで複数年保持する場合との比較**: 多くのベンダープラットフォームは「取り込みGB×保持日数」で課金され、保持期間が長くなるほど複雑に積み上がります。S3ストレージコストは同様の形で保持期間と複雑に積み上がるわけではなく（ライフサイクル移行によりさらに時間経過で削減される）、月単位ではなく年単位のコンプライアンス要件では、このコスト構造の違いが決定要因になることが多いです。一方、秒単位のレイテンシでアラートが必要な本当のユースケースでは、ベンダープラットフォームが依然として適切な選択です。本Lakehouse経路はそのレイテンシ向けには設計されていません。

## 関連ドキュメント

- [ベンダー比較](vendor-comparison.md)
- [データ分類ガイド](data-classification.md)
- [パイプライン SLO 定義](pipeline-slo.md)
- [Lakehouse モニタリングパターン](lakehouse-monitoring-patterns.md) — FSx for ONTAP + Lakehouse 統合の運用メトリクス（別の関心事: 監査データそのもののクエリではなく、パイプラインの健全性の監視）
- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — 本ガイドの Snowflake パターンと Athena/Glue IAM 規約の元になった姉妹プロジェクト
