# 検証済みクリーン復旧ポイントガイド — CSF 2.0 RC.RP のギャップを埋める

🌐 **日本語**（このページ） | [English](../en/verified-recovery-point-guide.md)

## エグゼクティブサマリ

[DII Capability Map](dii-capability-map.md) では、本リポジトリがこれまで対応していなかったギャップを明確に指摘していました。保護 Snapshot が存在すること自体は **Protect** フェーズのエビデンスであり、その Snapshot が実際にクリーンで復旧に使えることの証明にはなりません。NIST CSF 2.0 の **RC.RP**（Incident Recovery Plan Execution）サブカテゴリが信頼できると言えるのは、復旧ポイントが実際にテストされ、侵害されていないことが確認された場合のみであり、単にその存在が確認されたことではありません。

本ガイドは、この未対応だった検証ステップを AWS ネイティブサービスのみで実装します。

1. **FlexClone**: 検証対象の Snapshot を読み書き可能なクローンとして複製します（ONTAP REST API）。本番ボリュームや元の Snapshot には一切触れません。
2. **VPC 限定の S3 Access Point** をクローンに接続します（AWS FSx API）。NFS/SMB でマウントせずに S3 API 経由でクローンのファイルを公開するため、検証処理は本番データプレーンへのネットワーク経路を一切持ちません。
3. **クローンのファイル一覧をスキャン**します（S3 Access Point 経由の `ListObjectsV2`）。ランサムウェアに関連するファイル拡張子を検出する高速な事前フィルタであり、ONTAP ARP のエントロピー分析の代替ではありません。
4. **合否判定を DynamoDB に記録**し（任意で SNS 通知も送信）、結果に関わらず S3 Access Point と FlexClone を**常に削除**します。

> **スコープに関する注記**: 本ガイドが埋めるのは RC.RP の検証ギャップに限定されます。ONTAP ARP（攻撃発生中に本番ボリュームに対してランサムウェアを検知する仕組み）や、[自動インシデント対応ガイド](automated-response-guide.md)の Respond フェーズのブロック機能を置き換えるものではありません。本ガイドが答えるのは別の、より後段の問いです — 「復旧ポイントとして採用しようとしている、この特定の Snapshot は、実際にクリーンなのか？」

**主要機能:**
- FlexClone ベースの検証により本番ボリュームへの影響ゼロ（copy-on-write、クローンに対する読み取り専用処理のみ）
- VPC 限定の S3 Access Point — クローンの内容がインターネットから到達可能になることはない
- ランサムウェア痕跡の高速な拡張子ベース事前フィルタ
- Step Functions の `Catch` により、失敗時も含めてクリーンアップを保証 — クローンや Access Point が残置されることはない
- 全検証実行を DynamoDB 台帳に記録し、監査時の CSF 2.0 RC.RP エビデンスとしても機能

**実行タイミング:**
- [自動インシデント対応ガイド](automated-response-guide.md)の `create_snapshot` アクションが発火した後、その Snapshot を復旧ポイントとして信頼する前に
- 定期的な保護 Snapshot / スケジュール Snapshot に対して定期実行し、復旧レディネスの継続チェックとして
- 計画的な DR テストやコンプライアンス監査の前に、手動で「テスト済み」の復旧ポイントであることのエビデンスを取得するために

---

## アーキテクチャ

```
+-------------------------------------------------------------------+
| Step Functions: 検証済みクリーン復旧ポイントワークフロー            |
+-------------------------------------------------------------------+
|                                                                   |
|  CreateFlexClone (ONTAP REST API)                                 |
|       |                                                           |
|       v                                                           |
|  AttachAccessPoint (AWS FSx API, VPC 限定)                        |
|       |                                                           |
|       v                                                           |
|  ScanForIndicators (Access Point 経由の S3 ListObjectsV2)          |
|       |                                                           |
|       v                                                           |
|  RecordVerdict (DynamoDB + 任意で SNS)                             |
|       |                                                           |
|       v                                                           |
|  Cleanup (S3 AP デタッチ + FlexClone 削除)  <-- 必ず実行            |
|                                                                   |
|  (いずれかのステップで失敗) --> CleanupAfterError                  |
|                              --> RecordErrorVerdict --> Fail       |
+-------------------------------------------------------------------+
```

設計上の重要な選択: **クリーンアップは成功・失敗どちらの経路でも必ず実行されます**。Step Functions の `Catch` ブロックは、どのエラーも正常系と同じ Cleanup Lambda に直接ルーティングします。そのため、ワークフローの途中で失敗しても、FlexClone ボリュームや S3 Access Point がストレージを消費したり不要なアクセス面を残したりすることはありません。

---

## 検証の仕組み

### ステップ1: FlexClone の作成

[FlexClone](https://aws.amazon.com/fsx/netapp-ontap/features/) は、親ボリュームと copy-on-write でデータブロックを共有する、その時点の書き込み可能なコピーです。作成はほぼ即時で、クローンへの書き込みが発生するまで追加のストレージを消費しません（本ワークフローはクローンへの読み取りのみを行うため、追加ストレージは発生しません）。

```
POST /api/storage/volumes
{
  "name": "verify_vol_data_20260710_143022",
  "svm": {"name": "svm-prod-01"},
  "clone": {
    "parent_volume": {"name": "vol_data"},
    "parent_snapshot": {"name": "incident_response_20260708_143022"},
    "is_flexclone": true
  }
}
```

これは非同期ジョブを返します。Lambda は `GET /api/cluster/jobs/{uuid}` を `state: success` になるまでポーリングし、その後クリーンアップ用にクローンの ONTAP ボリューム UUID を解決します。

### ステップ2: S3 Access Point の接続

クローンは [VPC 限定の S3 Access Point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-vpc.html) 経由で公開されます（インターネット起点ではありません）。そのため、リクエストは接続先 VPC 内の Interface VPC Endpoint を経由する必要があります:

```python
fsx.create_and_attach_s3_access_point(
    Name="verify-vol-data-20260710-143022",
    Type="ONTAP",
    OntapConfiguration={
        "VolumeId": fsvol_id,  # DescribeVolumes で解決(ONTAP UUID ではない)
        "FileSystemIdentity": {"Type": "UNIX", "UnixUser": {"Name": "root"}},
    },
    S3AccessPoint={"VpcConfiguration": {"VpcId": vpc_id}},
)
```

> **ONTAP UUID から fsvol-id への解決について**: AWS FSx は ONTAP REST API 経由で作成されたボリュームを非同期に検出します。ONTAP ボリューム UUID を対応する `fsvol-xxxx` ID に直接マッピングする API は存在しません。本ワークフローは `file-system-id` でフィルタした `DescribeVolumes` をポーリングし、クローンの `Name` が一致してかつ FSx 側で `AVAILABLE` と報告されるまで待機します。

Access Point は `CREATING` → `AVAILABLE`（エラー時は `FAILED`/`MISCONFIGURED`）と遷移します。Lambda は `DescribeS3AccessPointAttachments` を終了状態になるまでポーリングします。

### ステップ3: ランサムウェア痕跡スキャン

スキャンは Access Point 経由でクローンのオブジェクトを一覧化し（`ListObjectsV2`）、ランサムウェアファミリーが付与することの多いファイル拡張子（`.encrypted`、`.locked`、`.crypt`、`.wcry`、`.locky` など）を検出します。Snapshot が **suspicious（疑わしい）** と判定されるのは、以下の両方を満たす場合のみです。

- 疑わしいオブジェクト数が `SuspiciousMinCount`（デフォルト 20）以上 — 少数のファイルが偶然この拡張子を持つ小規模ボリュームでの誤検知を回避
- 疑わしい比率が `SuspiciousRatioThreshold`（デフォルト 5%）以上

> **レジリエンス成熟度の視点**: これは意図的に粗く高速な事前フィルタであり、攻撃発生中に本番ボリュームに対して動作する [ONTAP ARP](arp-incident-response-guide.md) のファイル内容エントロピー分析の代替ではありません。本スキャンが答えるのは、より狭く、より後段の問いです — 「この特定の Snapshot は、ランサムウェアによってリネームされたファイルが多数を占めるボリュームを捉えているように見えるか」。ここでの「clean」判定は RC.RP のエビデンスにはなりますが、汎用的なマルウェアスキャンではなく、ファイルの *内容* は検査しません（データ分類を目的とした補完的な内容スキャン機能については、[コンテンツレベル PII 分類スキャナー](content-classification-scanner.md)を参照してください — こちらはランサムウェア検知ではなく別の課題に対応するものです）。

### ステップ4: 判定結果の記録

clean、suspicious、error のいずれであっても、全ての実行結果は DynamoDB 台帳テーブル（パーティションキー `snapshot_key` = `{svm}/{volume}/{snapshot}`、ソートキー `started_at`）に記録されます。これにより、どの復旧ポイントがいつ検証され、どのような結果だったかをクエリ可能な履歴として保持できます。このテーブルが、監査時に RC.RP のエビデンスとして提示するアーティファクトになります。

### ステップ5: クリーンアップの保証

Cleanup Lambda は設計上べき等的に振る舞います。`access_point_name` や `volume_uuid` が欠落している場合（例: 早期の失敗によりクリーンアップ実行時にまだそれらのリソースが存在しない場合）は no-op として扱われ、エラーにはなりません。S3 Access Point のデタッチと FlexClone の削除は、いずれも「既に削除済み」（404 / `NotFound`）の応答を許容します。

---

## 比較: Snapshot の存在 vs 検証済みクリーン復旧ポイント

| 観点 | Snapshot が存在する（Respond フェーズ） | 検証済みクリーン復旧ポイント（本ワークフロー） |
|------|------------------------------------------|--------------------------------------------------|
| CSF 2.0 機能 | Protect（Snapshot 自体） | Recover — 具体的には RC.RP |
| 何を証明するか | 時点コピーが取得されたこと | そのコピーが検査され、ランサムウェアの痕跡が見られないこと |
| 本番への影響 | なし（Snapshot 作成はほぼ即時） | なし（FlexClone は copy-on-write、スキャンはクローンへの読み取り専用） |
| リストア判断への確度 | 低い — 攻撃 *中* に取得した Snapshot 自体に暗号化済みファイルが含まれる可能性がある | より高い — 人間がリストアを決断する前の自動 go/no-go 信号 |
| 本リポジトリでの自動化状況 | ✅ 完全対応（[自動インシデント対応ガイド](automated-response-guide.md)） | ✅ 完全対応（本ガイド） |

> **Recovery/BC-DR の視点**: 本ワークフローの「clean」判定は、リストア前の *必要条件* であって *十分条件* ではないものとして扱ってください。粗く分かりやすいケース（ランサムウェアによってリネームされたファイルが多数を占めるボリューム）を、高速かつ低コストに除外するものです。アプリケーションレベルのデータ整合性の検証や、Snapshot がエンドツーエンドでクリーンにリストアできることの検証、あるいは完全な DR テストの代替にはなりません。定期的な完全リストアテストは別途スケジュールし、本ワークフローは全ての検証対象 Snapshot に対して実行する自動化された第一段のゲートとして位置づけ、復旧可能性についての最終判断としては使わないでください。

---

## 前提条件

### ONTAP バージョン

- **FlexClone REST API**（`clone.is_flexclone`）: ONTAP 9.8+ で利用可能
- **ボリューム作成/削除 REST API**: ONTAP 9.6+ で利用可能

### AWS 権限

Lambda 実行ロールには以下が必要です:

```
# ONTAP REST API(Secrets Manager の認証情報経由)
- secretsmanager:GetSecretValue

# FSx S3 Access Point ライフサイクル(現時点でこれらのアクションは
# リソースレベル権限をサポートしていません)
- fsx:CreateAndAttachS3AccessPoint
- fsx:DetachAndDeleteS3AccessPoint
- fsx:DescribeS3AccessPointAttachments
- fsx:DescribeVolumes

# S3 Access Point オブジェクト読み取り(スキャン用)+ ポリシー管理
- s3:ListBucket / s3:GetObject (arn:aws:s3:*:*:accesspoint/* にスコープ)
- s3:PutAccessPointPolicy / s3:GetAccessPointPolicy

# 判定結果台帳
- dynamodb:PutItem / dynamodb:UpdateItem (台帳テーブルにスコープ)
```

### ネットワークアクセス

どの Lambda が VPC 内で実行されるかは、「検証ワークフローだから一律 VPC 内」という単純なルールではなく、各 Lambda が何を呼び出すかによって決まります:

| Lambda | 呼び出し先 | VPC 内で実行？ | 理由 |
|--------|-----------|----------------|------|
| `CreateFlexClone` | ONTAP REST API を直接呼び出し（ボリューム作成） | ✅ 実行する | `SubnetIds`/`SecurityGroupId` が提供する管理 IP へのルートが必要 |
| `AttachAccessPoint` | FSx コントロールプレーン API のみ（`CreateAndAttachS3AccessPoint`、`DescribeVolumes`）— ONTAP には直接触れない | ❌ 実行しない | FSx API はパブリックな AWS API であり VPC なしでも到達可能。この 1 ステップのためだけに FSx 用 Interface Endpoint を用意する必要をなくすため、VPC 外で実行 |
| `ScanForIndicators` | 前ステップで作成した **VPC 限定** の S3 Access Point に対する `ListObjectsV2` | ✅ 実行する | ここが最も重要: VPC 限定の Access Point は、束縛された VPC の外からは一切到達できません（下記セキュリティ考慮事項参照）。VPC 外の Lambda では原理的に到達不可能 |
| `RecordVerdict` | DynamoDB + SNS のみ | ❌ 実行しない | いずれの API も VPC アクセスを必要としない |
| `Cleanup` | ONTAP REST API を直接呼び出し（ボリューム削除）**と** FSx コントロールプレーン API（`DetachAndDeleteS3AccessPoint`）の両方 | ✅ 実行する | ONTAP 呼び出しには管理 IP へのルートが必要。VPC 内から FSx API を呼ぶには FSx 用 Interface Endpoint が必要 |

> **重要: VPC Endpoint について**。`CreateFlexClone`/`Cleanup` は（ONTAP 認証情報のために）VPC から Secrets Manager と STS に到達できる必要があります。`Cleanup` はさらに（`DetachAndDeleteS3AccessPoint` のために）**FSx 用 Interface Endpoint** が必要です。`ScanForIndicators` は、ルートテーブル（`RouteTableIds` パラメータ）に紐づいた **S3 Gateway Endpoint** が必要です — これがないと、スキャンステップは VPC 限定の Access Point に一切到達できず、ワークフローは間欠的にではなく毎回そのステートで失敗します。VPC に Secrets Manager・STS・FSx・S3 Gateway Endpoint の 4 つ全てが既に存在している場合を除き、`CreateVpcEndpoints=true`（デフォルト）のままにしてください。[`automated-response.yaml`](automated-response-guide.md) と併せてデプロイする場合、そのスタック自身の Endpoint でカバーされるのは Secrets Manager と STS のみです。本スタックが追加で必要とする FSx と S3 の Endpoint は作成されないため、別途これら 2 つを用意していない限り `CreateVpcEndpoints=true` のままにしてください。

---

## デプロイ

### ワンスタックデプロイ

```bash
aws cloudformation deploy \
  --template-file shared/templates/restore-verification.yaml \
  --stack-name fsxn-restore-verification \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=<secret-arn> \
    FileSystemId=<fs-id> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    RouteTableIds=<route-table-1>,<route-table-2> \
    NotificationTopicArn=<optional-sns-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

スタックが作成するリソース:
- Step Functions ステートマシン（`{stack-name}-workflow`）
- Lambda 関数 5 個（create-clone、attach-ap、scan、record-verdict、cleanup）
- DynamoDB 台帳テーブル（`{stack-name}-ledger`）
- ステートマシン用 CloudWatch Logs（365 日保持）、各 Lambda 用 CloudWatch Logs（90 日保持。record-verdict はコンプライアンスエビデンスも兼ねるため 365 日保持）
- Secrets Manager・STS・FSx 用の Interface Endpoint、および `RouteTableIds` に紐づく S3 Gateway Endpoint（`CreateVpcEndpoints=true`、デフォルトの場合）— どの Lambda がどの Endpoint を必要とするかは上記[ネットワークアクセス](#ネットワークアクセス)を参照

### 検証実行の開始

```bash
aws stepfunctions start-execution \
  --state-machine-arn <StateMachineArn の出力値> \
  --input '{
    "svm_name": "svm-prod-01",
    "volume_name": "vol_data",
    "snapshot_name": "incident_response_20260708_143022",
    "vpc_id": "vpc-0123456789abcdef0"
  }'
```

[自動インシデント対応ガイド](automated-response-guide.md)の `create_snapshot` アクションの後段に本ワークフローを連結するには、SOAR プレイブックまたは Step Functions ファンアウト（同ガイドの FAQ 参照）から、封じ込め完了後に新規作成された Snapshot 名を指定してこのステートマシンを呼び出してください。

### 台帳のクエリ

```bash
aws dynamodb query \
  --table-name fsxn-restore-verification-ledger \
  --key-condition-expression "snapshot_key = :sk" \
  --expression-attribute-values '{":sk": {"S": "svm-prod-01/vol_data/incident_response_20260708_143022"}}'
```

---

## 設定リファレンス

| パラメータ | デフォルト | 用途 |
|-----------|-----------|------|
| `SuspiciousRatioThreshold` | 0.05 | 「suspicious」判定に必要な、ランサムウェア関連拡張子を持つスキャン対象オブジェクトの比率 |
| `SuspiciousMinCount` | 20 | 疑わしいオブジェクト数の絶対的な下限（小規模ボリュームでの誤検知を回避） |
| `StepTimeoutSeconds` | 180 | Step Functions の各 Lambda タスクのタイムアウト |
| `UnixUser` | root | 検証用 S3 Access Point がファイルシステムアクセスチェックに使用する UNIX ID |
| `LambdaMemorySize` | 512 MB | 検証用 5 Lambda 全てのメモリサイズ |

---

## セキュリティ考慮事項

- **本番データへの経路なし**: FlexClone は copy-on-write で親ボリュームとブロックを共有しますが、S3 Access Point が公開するのは *クローン* のみで、親ボリュームは公開されません。クリーンアップ時にクローンを削除しても、親ボリュームや元の Snapshot には影響しません。
- **VPC 限定の Access Point**: Access Point は作成時に VPC に束縛され、VPC 外からは到達できません。これは、ポリシーのみで制御するインターネット起点の Access Point よりも強い保証です — 詳細は [AWS のネットワーク起点比較](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)を参照してください。この特性のため、Access Point のオブジェクトを一覧化する `ScanForIndicators` は、束縛された VPC 内で S3 へのルート（本スタックが作成する S3 Gateway Endpoint）を持って実行される*必要があります* — インターネット起点の Access Point とは異なり、VPC 限定の Access Point にはポリシーだけで VPC 外から到達する方法がありません。
- **`fsx:*S3AccessPoint*` アクションの最小権限**: これらのアクションは現時点で、他の FSx アクションほど細かいリソースレベル権限や条件キーをサポートしていません。本スタックの IAM ポリシーではこれらを `Resource: '*'` にスコープし、その理由をドキュメント化しています。AWS がリソースレベルのサポートを追加した場合は見直してください。
- **判定結果台帳はエビデンスであり、ガバナンスの代替ではない**: DynamoDB 台帳は、誰が何をいつ検証し、どのような結果だったかという監査可能なエビデンスを提供し、CSF 2.0 の Govern プログラムが入力として利用できます — 本リポジトリがガバナンスプログラム自体を自動化しようとしない理由については、[DII Capability Map](dii-capability-map.md#サイバーレジリエンス全体での位置づけ-nist-csf-20) の Govern 機能に関する議論を参照してください。

---

## テスト

`restore_verification.py` モジュールには 23 のユニットテストがあります:

| カテゴリ | 検証内容 |
|---------|---------|
| FlexClone 作成/削除 | 成功、ジョブ失敗、クローン解決失敗、既に削除済み（404） |
| S3 Access Point 接続/切断 | 成功、fsvol 解決タイムアウト、MISCONFIGURED 状態、ClientError 処理、切断時の not-found |
| ランサムウェア痕跡スキャン | クリーンなボリューム、疑わしいボリューム、空のボリューム、大文字小文字を区別しない拡張子マッチング |
| フルオーケストレーション | clean 判定、suspicious 判定、最小件数未満での誤検知回避、クリーンアップを伴うエラー経路、クローン作成後のエラーでのクリーンアップ、結果シリアライズの上限処理 |

```bash
python3 -m pytest shared/python/tests/test_restore_verification.py -v
# 23 passed in 0.11s
```

---

## 関連ドキュメント

- [DII Capability Map](dii-capability-map.md) — 本ガイドが対応する「残存するギャップ」と CSF 2.0 RECOVER 機能に関する議論
- [自動インシデント対応ガイド](automated-response-guide.md) — 本ワークフローの実行前に通常先行する、Respond フェーズのブロックと保護 Snapshot 作成
- [ARP インシデント対応ガイド](arp-incident-response-guide.md) — 本ワークフローのスキャンが補完する（代替するのではない）、本番ボリュームに対するリアルタイムのエントロピー検知
- [コンテンツレベル PII 分類スキャナー](content-classification-scanner.md) — 同じ FlexClone + S3 Access Point パターンを基盤とした、CSF 2.0 の Identify 機能（データ分類）向けの関連コンテンツスキャン機能
- [ガバナンス・コンプライアンス](governance-and-compliance.md) — 判定結果台帳が Govern 機能のエビデンスとしてどう位置づけられるか
- [コンプライアンスエビデンスパック](compliance-evidence-pack.md) — 監査証跡エビデンスのテンプレート

## FAQ

**Q: 「clean」判定は、その Snapshot が安全にリストアできることを保証しますか？**
A: いいえ — 上記の Recovery/BC-DR の視点を参照してください。これはファイル拡張子パターンに基づく高速で自動化された事前フィルタであり、完全なマルウェアスキャンやアプリケーションレベルの整合性チェックではありません。必要な第一段のゲートとして扱い、最終判断とはしないでください。

**Q: 本番ボリュームを直接スキャンせず、なぜ FlexClone を使うのですか？**
A: 稼働中のボリュームをスキャンすると本番の I/O と競合し、進行中の攻撃と干渉するリスクがあります。FlexClone は copy-on-write でブロックを共有する、隔離された時点の読み書き可能なコピーです。検証はこのクローンに対して本番への影響ゼロで実行され、完了後に削除されます。

**Q: NFS/SMB でクローンをマウントせず、なぜ S3 Access Point を使うのですか？**
A: マウントには SVM のデータ LIF へのネットワークレベルのアクセスと、検証環境で稼働する NFS/SMB クライアントが必要です。S3 Access Point を使えば、ステートレスな Lambda がマウント手順なしに S3 API 経由でファイルを一覧・読み取りできます。VPC 限定にした場合は、読み取り専用の Access Point 自体を除けば本番データプレーンへの経路も一切生まれません。

**Q: ワークフローが途中で失敗した場合、クローンは残置されますか？**
A: されません。Step Functions の `Catch` ブロックは、どの失敗モードも正常系と同じ `Cleanup` Lambda にルーティングします。Cleanup Lambda は部分的な状態（例: クローンは作成されたが Access Point の接続が失敗した場合）を許容し、存在するものだけをクリーンアップします。

**Q: 自動応答モジュールが作成した Snapshot 以外にも実行できますか？**
A: できます。`verify_snapshot()` および Step Functions の入力に必要なのは `svm_name`、`volume_name`、`snapshot_name` のみです。既存の ONTAP Snapshot であれば、インシデントとは無関係なスケジュール Snapshot ポリシーによる Snapshot も含めて動作します。
