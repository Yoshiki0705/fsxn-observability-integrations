# コンテンツレベル PII 分類スキャナー — CSF 2.0 Identify のギャップを埋める

🌐 **日本語**（このページ） | [English](../en/content-classification-scanner.md)

## エグゼクティブサマリ

[DII Capability Map](dii-capability-map.md) では、Identify 機能におけるギャップを明確に指摘していました。本リポジトリの [データ分類ガイド](data-classification.md) はスキーマレベルの分類（`UserName`、`ObjectName` といった *フィールド* のどれが PII か）を定義していますが、NetApp のデータ分類ツールが CSF 2.0 の Identify 機能に対して行うような、ファイル *内容* のスキャンは行っていませんでした。

本ガイドは、Amazon Comprehend のマネージド PII エンティティ検出を使い、既存の S3 Access Point 経由でファイルを読み取るスタンドアロンの Lambda 関数として、このコンテンツレベルのスキャンを実装します。

1. **オブジェクト一覧の取得**: 指定した S3 Access Point 経由で `ListObjectsV2` を実行し、スキャン対象のテキスト/構造化データ拡張子（`.txt`、`.csv`、`.json`、`.log` など）にフィルタします。バイナリ形式（Office ドキュメントなど）は対象外です（詳細は[残存する限界](#残存する限界)を参照）。
2. **読み取りとチャンク分割**: 各ファイルの内容を、Amazon Comprehend の 1 回あたりのサイズ上限を下回るバイト境界のセグメントに分割します。
3. **`DetectPiiEntities` の呼び出し**: チャンクごとに呼び出し、エンティティタイプ・件数・確信度スコアをファイル単位で集計します。**PII の値そのものは一切保持しません** — エンティティタイプ/オフセット/確信度のみです。
4. **分類レポートの記録**: DynamoDB に書き込み、PII が検出された場合は任意で SNS 通知を送信します。

> **スコープに関する注記**: これは PII の *発見* ツールであり、マスキング、修復、あるいは汎用的なマルウェア/コンテンツスキャナーではありません。答えるのは「このボリュームに PII らしきコンテンツが含まれているか、おおよそどの程度か」という問いです — これは CSF 2.0 の Identify 機能（資産・データの理解）が対象とする問いであり、Protect、Detect、Respond のいずれでもありません。

**主要機能:**
- Amazon Comprehend `DetectPiiEntities` — [12 言語](https://docs.aws.amazon.com/comprehend/latest/dg/supported-languages.html)に対応したマネージド PII 検出、数十種類のエンティティタイプ（SSN、クレジットカード番号、銀行口座番号、各国の国民 ID 番号など）
- データ最小化を前提とした設計: 検出結果にはエンティティタイプと確信度のみを記録し、マッチしたテキスト自体は一切記録しない
- 既存の任意の FSx for ONTAP S3 Access Point に対して動作 — スタンドアロンでも、[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)の FlexClone ベースの Access Point に連結して本番影響ゼロで実行することも可能
- サイズ超過ファイルは全体スキップではなく先頭数バイトのサンプリング対象となるため、大きなログ/CSV ファイルでも部分的な信号は得られる
- DynamoDB のレポート台帳が、監査時の CSF 2.0 Identify 機能エビデンスとしても機能

**実行タイミング:**
- ユーザー生成コンテンツを含むボリューム（共有、ホームディレクトリ、エクスポート）に対して定期的に実行し、PII が実際にどこにあるかの最新像を維持する
- ランサムウェア検証の直後に、[FlexClone 検証用 Access Point](verified-recovery-point-guide.md) に対して実行し、同じ隔離クローンに対して両方のスキャンを組み合わせる
- 新しい Observability/SIEM の配信先にボリュームを接続する前に、フォレンジックダッシュボードやエクスポートされたログサンプルが何を露出する可能性があるかを確認する

---

## アーキテクチャ

```
+-------------------------------------------------------------------+
| 入力: 既存の任意の S3 Access Point ARN                             |
| (スタンドアロン、または                                            |
|  verified-recovery-point-guide.md の AttachAccessPoint 出力)        |
+-------------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------------+
| Lambda: ScannerFunction                                            |
|                                                                    |
|  ListObjectsV2 (Access Point 経由)                                 |
|       |                                                            |
|       +-> フィルタ: スキャン対象拡張子か？サイズ > 0か？             |
|              |                                                     |
|              v                                                     |
|         GetObject (通常読み取り、サイズ超過時は Range サンプリング)  |
|              |                                                     |
|              v                                                     |
|         100KB 未満の UTF-8 セグメントにチャンク分割                 |
|              |                                                     |
|              v                                                     |
|         Comprehend DetectPiiEntities (チャンクごと)                 |
|              |                                                     |
|              v                                                     |
|         entity_type -> 件数、最大確信度に集計                       |
+-------------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------------+
| DynamoDB: 分類レポート(Access Point ごと、実行ごと)                  |
| SNS: PII 検出時の任意通知                                           |
+-------------------------------------------------------------------+
```

---

## 分類の仕組み

### ファイル選定

読み取るのはスキャン対象拡張子を持つファイルのみです — 本スキャナーはドキュメント形式のパース（Office/PDF のテキスト抽出）は実装していません:

```
.txt  .csv  .tsv  .json  .xml  .log  .md  .yaml  .yml  .ini  .conf  .sql  .html  .htm
```

0 バイトのファイルはスキップされます。`DEFAULT_MAX_FILE_BYTES`（5 MB）を超えるファイルは全体スキップではなく **サンプリング** されます — S3 の Range `GetObject` により先頭 500 KB のみを読み取り、検出結果には `sampled: true` が記録されるため、結果が部分的であることが分かります。

### Comprehend のサイズ上限に対応するチャンク分割

[`DetectPiiEntities`](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html) は 1 回の呼び出しあたり UTF-8 で 100 KB のサイズ上限を設けています。本スキャナーはファイル内容をその上限未満のチャンクに分割し、可能な限り行境界で分割します。これにより、エンティティ（例: メールアドレス）が不必要にチャンク境界で分断されることを避けます:

```python
# 簡略版 — 行境界を考慮した完全な実装は content_classifier.py の
# _chunk_text を参照
for chunk in _chunk_text(file_text, target_bytes=98_000):
    entities = comprehend.detect_pii_entities(Text=chunk, LanguageCode="en")
```

### エンティティの集計 — データ最小化を前提とした設計

各ファイルについて、検出結果には**以下のみ**を記録します:

- エンティティの `Type`（例: `EMAIL`、`SSN`、`CREDIT_DEBIT_NUMBER`、`BANK_ACCOUNT_NUMBER` — [全タイプ一覧](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html)）
- タイプごとの検出件数
- タイプごとに観測された最大の確信度 `Score`

マッチしたテキスト自体（実際のメールアドレスや SSN など）は、**レポート・ログ・DynamoDB のいずれにも一切書き込まれません**。これは [データ分類ガイド](data-classification.md) の疑似匿名化の指針と同じ考え方です — 「このファイルには 0.97 以上の確信度で SSN パターンのマッチが 3 件ある」というレポートは、それ自体が新たな PII の露出面になることなく、修復の優先順位付けに役立ちます。

> **Data Protection Officer/Privacy Engineer の視点**: レポートはエンティティタイプごとに `highest_confidence_by_type` を記録しますが、本スキャナーは低確信度のマッチを自動でフィルタ・フラグ付けすることは**しません** — 確信度 0.31 の `EMAIL` 検出 1 件は、確信度 0.99 の検出 1 件と全く同じ扱いで `files_with_pii` に計上されます。`files_with_pii`/`pii_density_by_type` を規制上の PII 台帳や DPIA（データ保護影響評価）の入力として使う前に、サマリの件数だけでなく生の検出結果内の `highest_confidence_by_type` を確認し、自社の確信度の下限を適用してください — 低確信度のマッチを全て確定 PII として扱えば露出を過大に見せるリスクがあり、全てをノイズとして扱えば過小に見せるリスクがあります。どちらの判断も本スキャナーは代わりに行いません。

### エラーハンドリング — 1 ファイルの失敗がスキャン全体を止めない

読み取り失敗（`AccessDenied`、`NoSuchKey`）、デコード失敗、Comprehend API エラー（`TextSizeLimitExceededException`、スロットリング）は、例外を発生させずにファイル単位の `error` フィールドに記録されます。問題のある 1 ファイルは記録されてスキップされ、ボリューム内の残りのファイルに対するスキャンは継続されます。

---

## 比較: スキーマレベル vs コンテンツレベルの分類

| 観点 | スキーマレベル（データ分類ガイド） | コンテンツレベル（本スキャナー） |
|------|--------------------------------------|-----------------------------------|
| 分類対象 | audit/FPolicy イベントのどの *フィールド* が PII か（`UserName`、`ObjectName`） | ボリューム上のどの *ファイル内容* が PII らしきデータを含むか |
| CSF 2.0 機能 | Identify（メタデータレベルの資産理解） | Identify（データレベルの資産理解） |
| メカニズム | 静的なフィールド分類マトリクス（ドキュメント） | Amazon Comprehend `DetectPiiEntities`（ML 推論） |
| 対応範囲 | 本リポジトリのパイプラインが出力する全イベントフィールド | スキャン対象拡張子に一致するテキスト/構造化データファイルのみ |
| 本リポジトリでの自動化状況 | ✅ 完全対応（リファレンス表） | ✅ 完全対応（本スキャナー） |

> **Compliance の視点（HIPAA/FISC/SOC2）**: 両方を組み合わせて使ってください。スキーマレベルのガイドは、ベンダー RBAC でどの *パイプラインフィールド* を制限すべきかを示します（`user`/`path` を表示するダッシュボードは定義上 PII を表示しています）。本スキャナーは、どの *ボリューム/ファイル* がコンテンツとして PII を含んでいる可能性が高いかを示し、DLP 制御、アクセス制限、あるいはストレージ層での正式なデータ分類ラベル付けをどこに適用すべきかの判断材料になります。いずれも、規制目的でのデータ保護責任者による手動レビューの代替にはなりません — データ分類ガイドのスコープに関する注記を参照してください。

---

## 残存する限界

本スキャナーが**行わないこと**を明確にしておきます:

1. **ドキュメント形式のパースを行わない。** Office ドキュメント（`.docx`、`.xlsx`、`.pdf`）はテキスト抽出されません — 本スキャナーは生のバイトを読み取り UTF-8 でデコードするだけであり、これはプレーンテキスト/構造化形式には有効ですが、バイナリの Office/PDF 形式では無意味な結果（有効な検出なし）になります。これを拡張するには、現時点では含まれていないドキュメントパースライブラリ（Lambda Layer 経由など）が必要です。
2. **拡張子リストは形式ベースだが、コンテンツ検出は多言語対応。** `SCANNABLE_EXTENSIONS` によるフィルタは言語ではなく形式に基づいています。Comprehend 自体は `language_code` により 12 言語をサポートしますが、本スキャナーは 1 回の実行で 1 言語のみを処理します。複数言語が混在するボリュームには、`language_code` を変えた複数回の実行、または言語検出の前処理ステップ（未実装）が必要です。
3. **5 MB を超えるファイルは全体スキャンではなくサンプリング。** デフォルトでは大きなログ/CSV ファイルは先頭 500 KB のみスキャンされます — 大きなファイルの後半に現れる PII は検出されません。データの性質上これが問題になる場合は `DEFAULT_MAX_FILE_BYTES`/`sample_bytes` を増やしてください（Comprehend のコストは増加します）。
4. **コストはファイル数とサイズに比例する。** Comprehend `DetectPiiEntities` は処理したテキスト量に応じて課金されます。スキャン対象ファイルが多い/大きい大規模ボリュームをスキャンすると、相応の Comprehend 費用が発生する可能性があります — `max_files` は、1 回の実行あたりのこの費用を制限するために存在します。
5. **ファイル変更時の自動再スキャンはない。** これはオンデマンド/スケジュール実行のスキャナーであり、イベント駆動ではありません。定期的な再分類が必要な場合は、[自動応答ガイドのデプロイ節](automated-response-guide.md#デプロイ)にある TTL クリーンアップスケジュールと同じパターンで、独自の EventBridge Scheduler ルールを組み合わせてください。
6. **スキャン途中で Lambda がタイムアウトすると、未スキャン分だけでなく実行全体の検出結果が失われる。** 本スキャナーは `ListObjectsV2`/分類ループが完全に終わった後に一度だけ DynamoDB レポートを書き込みます — 途中経過をチェックポイントする仕組みはありません。大きなボリュームのスキャン途中で `LambdaTimeoutSeconds` を超えると、`put_item` の呼び出し前に Lambda が強制終了され、その実行に対するレポートは（部分的なものすら）一切記録されません。想定するファイル数と平均ファイルサイズに応じて `LambdaTimeoutSeconds` と `max_files` を余裕を持って設定し、「スキャンした結果 PII がなかった」のか「スキャンが完了しなかった」のかを見分けるために、DynamoDB テーブルだけでなく CloudWatch Logs も確認してください。

> **Recovery Test Engineer の視点**: 本スキャナーを[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)のワークフローに連結する場合、実行順序が重要です — 同ガイドのワークフローの `Cleanup` ステップは、成功・失敗どちらの経路でも必ず S3 Access Point をデタッチし FlexClone を削除します（同ガイドのアーキテクチャ参照）。本スキャナーの分類処理は、そのワークフローが `Cleanup` に到達する**前**に呼び出してください — そのステートマシンにステートを追加するか、同一実行の `access_point_arn` 出力を使った同期的な後続呼び出しとして実装します。ワークフローが完了した後に呼び出すと、Access Point が既に存在しないため失敗します。

---

## 前提条件

### AWS 権限

Lambda 実行ロールには以下が必要です:

```
# S3 Access Point オブジェクト読み取り
- s3:ListBucket / s3:GetObject (arn:aws:s3:*:*:accesspoint/* にスコープ)

# Amazon Comprehend(リソースレベル権限はサポートされていません —
# DetectPiiEntities はアドレス可能なリソースを持たない
# ステートレスな同期推論 API です)
- comprehend:DetectPiiEntities

# 分類レポート台帳
- dynamodb:PutItem (レポートテーブルにスコープ)
```

### 既存の S3 Access Point

本スキャナーは S3 Access Point を**作成・管理しません** — 既に存在する Access Point の ARN を渡してください。一般的な取得元は 2 つあります:

- 本番または DR ボリュームに対して直接管理している Access Point
- [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)の `AttachAccessPoint` ステップの出力（`access_point_arn`）— ランサムウェア検証に使用した同じ FlexClone をスキャンする場合

> **ネットワーク起点によって `VpcId` の指定が必要かが決まる**: `AttachAccessPoint` が作成するのは [VPC 限定の Access Point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-vpc.html) であり、これは束縛された VPC の外からは一切到達できません — IAM 権限の有無に関わらず、VPC 外の Lambda はそもそもネットワーク経路を持ちません。インターネット起点の Access Point（`VpcConfiguration` を持たない Access Point）は VPC なしでも到達可能です。本スタックがどちらのモードでデプロイされるかを制御する `VpcId` パラメータについては、下記の[デプロイ](#デプロイ)を参照してください。

---

## デプロイ

### デプロイモード1: スタンドアロン（インターネット起点の Access Point）

`VpcConfiguration` を持たない Access Point をスキャンする場合に使用します — VPC Endpoint を作成しないため、よりシンプルで低コストなモードです:

```bash
aws cloudformation deploy \
  --template-file shared/templates/content-classification-scanner.yaml \
  --stack-name fsxn-content-classification \
  --parameter-overrides \
    DefaultLanguageCode=en \
    DefaultMaxFiles=500 \
    NotificationTopicArn=<optional-sns-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

### デプロイモード2: VPC 内（VPC 限定の Access Point）

VPC 限定の Access Point をスキャンする場合に使用します — [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)の `AttachAccessPoint` ステップに連結する場合は必須です。同ステップが作成する Access Point は常に VPC 限定であるためです:

```bash
aws cloudformation deploy \
  --template-file shared/templates/content-classification-scanner.yaml \
  --stack-name fsxn-content-classification \
  --parameter-overrides \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    RouteTableIds=<route-table-1>,<route-table-2> \
    DefaultLanguageCode=en \
    DefaultMaxFiles=500 \
    NotificationTopicArn=<optional-sns-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

`VpcId` を設定すると、スキャナー Lambda（`VpcConfig` が追加される）とスタックのリソース（`CreateVpcEndpoints=false` を明示しない限り、S3/DynamoDB の Gateway Endpoint と Comprehend/SNS の Interface Endpoint が追加される）の両方が変化します。`restore-verification.yaml` の VPC を再利用する場合でも、そのスタック自身が用意するのは Secrets Manager/STS/FSx の Endpoint のみで、この 4 つとは異なるため注意してください。

### スタックが作成するリソース

- Lambda 関数 1 個（`{stack-name}-scanner`）— `VpcId` の有無により `VpcConfig` の有無が変わる
- DynamoDB レポートテーブル（`{stack-name}-reports`）
- CloudWatch Logs（365 日保持 — レポートがコンプライアンスエビデンスも兼ねるため）
- `VpcId` が設定され `CreateVpcEndpoints=true`（デフォルト）の場合: S3 Gateway Endpoint、DynamoDB Gateway Endpoint、Comprehend Interface Endpoint、SNS Interface Endpoint

### スキャナーの呼び出し

```bash
aws lambda invoke \
  --function-name fsxn-content-classification-scanner \
  --payload '{
    "access_point_arn": "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/verify-vol-data-20260710",
    "language_code": "en",
    "max_files": 500
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json
```

### 復旧検証との連結

本番データではなく、ランサムウェア検証に使用した同じ隔離 FlexClone をスキャンするには、[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)の `AttachAccessPoint` Step Functions タスクが出力する `access_point_arn` を使ってこの Lambda を呼び出してください。そのステートマシンにステートを追加するか、同一実行の出力を使った別の後続呼び出しとして実装できます。

> **この連結パターンにはデプロイモード2（VPC 内）が必須です**: `AttachAccessPoint` は常に VPC 限定の Access Point を作成し、本スキャナーはそれに到達するために同じ VPC 内で実行される必要があります — 上記[前提条件](#既存の-s3-access-point)のネットワーク起点に関する注記を参照してください。本スタックをスタンドアロンモード（`VpcId` 未指定）で連結先の FlexClone Access Point に対してデプロイすると、`ListObjectsV2` の呼び出しで毎回確実に失敗します。ネットワーク経路自体が存在しないため、間欠的な失敗ではありません。

---

## 設定リファレンス

| パラメータ | デフォルト | 用途 |
|-----------|-----------|------|
| `DefaultLanguageCode` | en | Amazon Comprehend `DetectPiiEntities` の言語コード（12 言語対応） |
| `DefaultMaxFiles` | 500 | 1 回の実行あたりのスキャン対象ファイル数の上限（コスト/実行時間の制御）。呼び出しペイロードの `max_files` キーで実行ごとに上書き可能 |
| `LambdaMemorySize` | 512 MB | スキャナー Lambda のメモリサイズ |
| `LambdaTimeoutSeconds` | 600 | スキャナー Lambda のタイムアウト — 想定ファイル数に応じて調整 |

---

## セキュリティ考慮事項

- **設計によるデータ最小化**: 検出結果にはマッチした PII テキストが一切含まれません — エンティティタイプ、件数、確信度スコアのみです。上記の[エンティティの集計](#エンティティの集計--データ最小化を前提とした設計)を参照してください。
- **スキャン対象ボリュームへの書き込みアクセスなし**: スキャナーは `s3:GetObject`/`s3:ListBucket` のみを呼び出します — スキャン対象のファイルを変更、マスキング、削除することはできません。
- **レポートテーブルへのアクセスは制限すべき**: レポート自体には PII の値は含まれませんが、PII らしきデータが *どこで*（ファイルパス）*どの程度*見つかったかは含まれます — 機密データの所在に関する一覧と同様のアクセス制限を適用してください。
- **Comprehend はリージョナルな AWS マネージドサービス**: `DetectPiiEntities` に送信されたテキストは、呼び出し先の AWS リージョン内で処理されます。サービス自体のデータ取り扱いに関するコミットメントについては、[Amazon Comprehend のデータプライバシードキュメント](https://docs.aws.amazon.com/comprehend/latest/dg/data-privacy.html)を参照してください。
- **VPC 限定の Access Point は束縛された VPC の外からは経路を持たない**: これは Access Point 自体が持つネットワーク上の性質であり（[AWS のネットワーク起点比較](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)参照）、IAM だけで回避できるものではありません。VPC 限定の Access Point をスキャンする場合は、`VpcId` を設定して本スタックをデプロイし（デプロイモード2）、本スタックが作成する S3 Gateway Endpoint 経由で、スキャナー Lambda が同じ VPC 内から S3 へのルートを持つようにしてください。

---

## テスト

`content_classifier.py` モジュールには 23 のユニットテストがあります:

| カテゴリ | 検証内容 |
|---------|---------|
| テキストチャンク分割 | 空入力、単一チャンク、複数チャンク分割、内容を保持した再結合、上限を超える単一行の強制分割、チャンク目標値が Comprehend の上限未満であること |
| ファイル単位の分類 | PII なし、集計された件数/確信度を伴う PII 検出、複数チャンクにわたる集計、読み取り失敗の処理、Comprehend 失敗の処理、空ファイルのスキップ、サイズ超過ファイルの Range サンプリング、確信度の四捨五入 |
| ボリュームレベルのオーケストレーション | 非対応言語の拒否、スキャン対象外拡張子のフィルタリング、0 バイトファイルのスキップ、PII 密度の集計、クリーンなファイルの検出結果からの除外、エラーファイルの検出結果への含有、`max_files` 上限の適用、レポートシリアライズの上限処理、サンプリングされたファイルの個別トラッキング |

```bash
python3 -m pytest shared/python/tests/test_content_classifier.py -v
# 23 passed in 0.08s
```

> **Observability Engineer の視点**: 本スタックが用意するのは CloudWatch Logs のみです — Lambda のエラー・スロットリング・タイムアウトに対する CloudWatch Alarm はありません。[残存する限界](#残存する限界)項目6で述べた「タイムアウトすると実行全体の結果が失われる」という挙動を踏まえ、この Lambda の `Errors`/`Duration` メトリクスに独自のアラームを追加するか、PII 検出通知用に既に配線されている SNS トピックに失敗も流すようにしてください。そうしないと、静かにタイムアウトしたスキャンが「PII なし」と誤って解釈されてしまいます。

---

## 関連ドキュメント

- [DII Capability Map](dii-capability-map.md) — 本スキャナーが対応する Identify 機能の「残存するギャップ」
- [データ分類ガイド](data-classification.md) — 本スキャナーがコンテンツレベルで補完する、スキーマレベル（フィールド名）の分類
- [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) — 本スキャナーが連結でき、本番への影響ゼロでスキャンできる FlexClone + S3 Access Point パターン
- [自動インシデント対応ガイド](automated-response-guide.md) — 保護 Snapshot が復旧検証ワークフロー経由での自然なスキャン対象となる、封じ込めフェーズのモジュール
- [ガバナンス・コンプライアンス](governance-and-compliance.md) — 分類レポートが Identify 機能のエビデンスとしてどう位置づけられるか

## FAQ

**Q: 本スキャナーはファイルから PII をマスキング・削除しますか？**
A: いいえ。これは発見専用のツールであり、CSF 2.0 の Identify 機能のスコープ（棚卸しと理解、修復ではない）に一致します。マスキングには、本モジュールが意図的に実装していない別の書き込み経路が必要になります。

**Q: FlexClone だけでなく、本番ボリュームを直接スキャンできますか？**
A: できます — 本番ボリュームに直接接続した Access Point を含め、任意の S3 Access Point ARN を渡せます。[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)の FlexClone パターンは、本番への読み取り負荷影響をゼロにしたい場合やランサムウェア検証とスキャンを組み合わせたい場合に推奨されますが、必須ではありません。

**Q: なぜ Office ドキュメントや PDF はスキップされるのですか？**
A: 本モジュールは、ドキュメントパースライブラリへの依存を避けるため、意図的にプレーンテキストと構造化データ形式にスコープを絞っています。ボリュームの内容が Office/PDF 中心の場合は、Amazon Textract やドキュメント抽出用の Lambda Layer を前処理ステップとして検討し、本スキャナーの `classify_object` ロジックに生バイトではなく抽出済みテキストを渡すようにしてください。

**Q: 非常に大きなボリュームで Comprehend のコストが過大にならないようにするには？**
A: `max_files` で 1 回あたりのスキャン範囲を制限し、複数テラバイトのボリューム全体を一度にスキャンするのではなく、代表的なサブセット（例: 特定部門の共有フォルダ）に対して実行することを検討してください。Comprehend の課金は処理したテキスト量に応じるため、コストはファイル数だけでなくスキャンした総コンテンツ量に比例します。

**Q: スタンドアロン（`VpcId` 未指定）でデプロイしたところ、毎回 `ListObjectsV2` で失敗します。なぜですか？**
A: 渡している `access_point_arn` はほぼ確実に VPC 限定です（多くの場合、[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)の `AttachAccessPoint` ステップが出力したものです）。VPC 限定の Access Point は、束縛された VPC の外からはネットワーク経路自体を持ちません — これは IAM 権限に関わらず確定的に失敗するもので、間欠的な問題ではありません。`VpcId`/`SubnetIds`/`SecurityGroupId`/`RouteTableIds` を設定して（デプロイモード2）、スキャナーが Access Point と同じ VPC 内で実行されるように再デプロイしてください。

**Q: PII エンティティの `Score`（確信度）が低い場合、無視してよいですか？**
A: 自動では判断できません — 本スキャナーは確信度の下限を自動適用しません（[エンティティの集計](#エンティティの集計--データ最小化を前提とした設計)の Data Protection Officer/Privacy Engineer の視点を参照）。ファイル・エンティティタイプごとに観測された最大確信度を記録するだけなので、どの確信度を「検出された」PII とみなすかは、規制上の文脈に応じて*利用者側*が判断してください。

**Q: 大きなボリュームをスキャンしたのに DynamoDB の検出件数がゼロです。本当に実行されたのでしょうか？**
A: 「PII が見つからなかった」と結論する前に、その実行の CloudWatch Logs を確認してください。レポートは handler の最後で一度だけ書き込まれるため（[残存する限界](#残存する限界)項目6参照）、大きなスキャンの途中で Lambda がタイムアウトした場合も、DynamoDB 側では本当に何も見つからなかった場合と同じ症状（レポート行がない）になります。両者は Lambda 自身のログ/実行時間メトリクスでのみ区別できます。
