# 検証済みクリーン復旧ポイントガイド — CSF 2.0 RC.RP のギャップを埋める

🌐 **日本語**（このページ） | [English](../en/verified-recovery-point-guide.md)

## エグゼクティブサマリ

[サイバーレジリエンス機能マップ](cyber-resilience-capability-map.md#recover復旧) では、本リポジトリがこれまで対応していなかったギャップを明確に指摘していました。保護 Snapshot が存在すること自体は **Protect** フェーズのエビデンスであり、その Snapshot が実際にクリーンで復旧に使えることの証明にはなりません。NIST CSF 2.0 の **RC.RP**（Incident Recovery Plan Execution）サブカテゴリが信頼できると言えるのは、復旧ポイントが実際にテストされ、侵害されていないことが確認された場合のみであり、単にその存在が確認されたことではありません。

本ガイドは、この未対応だった検証ステップを AWS ネイティブサービスのみで実装します。

1. **FlexClone**: 検証対象の Snapshot を読み書き可能なクローンとして複製します（ONTAP REST API）。本番ボリュームや元の Snapshot には一切触れません。
2. **VPC 限定の S3 Access Point** をクローンに接続します（AWS FSx API）。NFS/SMB でマウントせずに S3 API 経由でクローンのファイルを公開するため、検証処理は本番データプレーンへのネットワーク経路を一切持ちません。
3. **クローンのファイル一覧をスキャン**します（S3 Access Point 経由の `ListObjectsV2`）。ランサムウェアに関連するファイル拡張子を検出する高速な事前フィルタであり、ONTAP ARP のエントロピー分析の代替ではありません。
4. **clean/suspicious/error の判定結果を DynamoDB に記録**し（任意で SNS 通知も送信）、結果に関わらず S3 Access Point と FlexClone を**常に削除**します。

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

> **顧客説明時の位置づけに関する補足**: ランサムウェアレジリエンスのために FSx for ONTAP を評価している顧客に本ガイドを説明する際、正確な一文での位置づけは「人間がリストアサイクルを無駄にする前に、明らかに侵害された Snapshot を除外する自動化された事前フィルタであり、Snapshot がマルウェアを含まないことの証明書ではない」です。顧客との対話や RFP 回答において、「clean」判定を完全なフォレンジック証明と同等のものとして提示しないでください — 本ガイド内の他の Resilience-maturity や 脅威インテリジェンスに関する補足が、その位置づけがなぜ機能を過大に見せることになるかを正確に説明しています。正確でありながら十分に説得力のある主張は、自動化とエビデンストレイル自体です — これは、以前は存在しなかったギャップ（検証済みでクリーンな復旧ポイントのワークフローがなかった）を AWS ネイティブサービスと DynamoDB の監査証跡で解消するものであり、スキャンの深さを過剰に売り込む必要のない、正当な差別化要因です。

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

> **図の説明（テキストによる代替）**: Step Functions ステートマシンは 5 つのステートを順に実行します — `CreateFlexClone`（ONTAP REST API）→ `AttachAccessPoint`（AWS FSx API、VPC 限定）→ `ScanForIndicators`（Access Point 経由の S3 `ListObjectsV2`）→ `RecordVerdict`（DynamoDB、任意で SNS）→ `Cleanup`（S3 Access Point のデタッチと FlexClone の削除。このステートは常に実行されます）。最初の 3 ステートのいずれかが失敗すると、制御は `CleanupAfterError` に移り、同じ `Cleanup` Lambda を呼び出した後、`RecordErrorVerdict` が失敗結果を台帳に記録し、実行は `Fail` ステートで終了します。上記の図は ASCII アートです。この段落がスクリーンリーダー利用者向けの完全なテキスト版に相当します。

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

> **並行実行に関する補足**: `clone_name` は `verify_{volume_name}_{timestamp}` から生成され、`timestamp` は 1 秒単位の精度です（`%Y%m%d_%H%M%S`）。同じ `volume_name` に対して同じ 1 秒以内に開始された 2 つの Step Functions 実行 — 例えばスケジュール実行と手動トリガーが同時に発火した場合 — は、同一名の ONTAP ボリュームを作成しようとし、2 回目の `POST /storage/volumes` 呼び出しは処理を継続できずに名前の衝突エラーで失敗します。本ワークフローには、これを防ぐための実行レベルのロック（DynamoDB の条件付き書き込みや Step Functions の名前重複排除など）はありません。実際にはこの衝突ウィンドウは狭く、トリガーパターンとしても頻度は高くありませんが、同じボリュームに対して複数の独立したトリガー（例: スケジュールと SOAR プレイブックの両方）から本ワークフローを呼び出す場合は、同一秒での衝突を避けるため、識別用のサフィックス（短いランダムトークンや呼び出し元の実行 ID など）を追加することを検討してください。

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

> **レジリエンス成熟度に関する補足**: これは意図的に粗く高速な事前フィルタであり、攻撃発生中に本番ボリュームに対して動作する [ONTAP ARP](arp-incident-response-guide.md) のファイル内容エントロピー分析の代替ではありません。本スキャンが答えるのは、より狭く、より後段の問いです — 「この特定の Snapshot は、ランサムウェアによってリネームされたファイルが多数を占めるボリュームを捉えているように見えるか」。ここでの「clean」判定は RC.RP のエビデンスにはなりますが、汎用的なマルウェアスキャンではなく、ファイルの *内容* は検査しません（データ分類を目的とした補完的な内容スキャン機能については、[コンテンツレベル PII 分類スキャナー](content-classification-scanner.md)を参照してください — こちらはランサムウェア検知ではなく別の課題に対応するものです）。

> **脅威インテリジェンスに関する補足**: `SUSPICIOUS_EXTENSIONS` は、既知のランサムウェアファミリーに歴史的に関連付けられている拡張子（`.locky`、`.wcry`、`.cerber` など）の固定リストです。これはシグネチャベースのアプローチであり、シグネチャベースならではの盲点を引き継いでいます — ランダムまたは被害者固有の拡張子を付与するランサムウェア（拡張子ベースの検知を回避するために、まさにこの目的で最近の攻撃キャンペーンで増加傾向にあるパターン）は、このリストのどの項目にも一致しないため、そのようなバリアントによって暗号化された Snapshot でも、本スキャン単独では「clean」判定を受ける可能性があります。このリストは新しいランサムウェアファミリーに合わせて自動的に更新される仕組みではありません — 出荷時のリストを網羅的なものとして扱わず、最新の脅威インテリジェンス（SIEM ベンダーの脅威フィードやメンテナンスされている公開リストなど）と照らし合わせて `SUSPICIOUS_EXTENSIONS` を定期的に見直し・拡張してください。これは、ここでの「clean」判定が事前フィルタであり保証ではない、（上記で既に述べた理由に加えた）2 つ目の独立した理由です — [ONTAP ARP](arp-incident-response-guide.md) のエントロピーベース検知は特定の拡張子を認識することに依存しないため、まさにこの盲点に対する意味のある補完となります。

### ステップ4: 判定結果の記録

clean、suspicious、error のいずれであっても、全ての実行結果は DynamoDB 台帳テーブル（パーティションキー `snapshot_key` = `{svm}/{volume}/{snapshot}`、ソートキー `started_at`）に記録されます。これにより、どの復旧ポイントがいつ検証され、どのような結果だったかをクエリ可能な履歴として保持できます。このテーブルが、監査時に RC.RP のエビデンスとして提示するアーティファクトになります。

### ステップ5: クリーンアップの保証

Cleanup Lambda は設計上べき等的に振る舞います。`access_point_name` や `volume_uuid` が欠落している場合（例: 早期の失敗によりクリーンアップ実行時にまだそれらのリソースが存在しない場合）は no-op として扱われ、エラーにはなりません。S3 Access Point のデタッチと FlexClone の削除は、いずれも「既に削除済み」（404 / `NotFound`）の応答を許容します。

> **API契約に関する補足**: Step Functions のステート間の契約は、バージョン管理されたスキーマではなく、暗黙的で型のない dict のマージです — 各 Lambda はステートマシン定義内の `"ResultPath": "$"` を通じて、前段のステートまでに積み上がった JSON ペイロード全体を受け取り、自身の新しいキーを追加した `dict(event)` を返します。そのため下流のステートは、上流のキー名が変わらないことに暗黙的に依存しています。5 つのステートで構成される単一目的のワークフローで、全ステートを一体で保守する場合はこれで十分機能しますが、デプロイ時にキー名の誤字やフィールド名の変更を検知するスキーマ検証がないことを意味します — 不一致は `RecordVerdict` や `Cleanup` 内で `event.get(...)` が明確なエラーではなく暗黙のデフォルト値を返す形で、実行時にキーの欠落として初めて表面化する可能性が高いです。本ワークフローを拡張する場合（例: コンテンツレベル PII 分類スキャナーの リストア検証に関する補足注記にある通り、追加のステートとして挿入する場合）は、異なる形のペイロードを導入するのではなく、同じ暗黙のパススルーの慣習を維持してください。そうしないと、挿入したステートの出力が、後続のステートが依存するキーを静かに落としてしまう可能性があります。

---

## 比較: Snapshot の存在 vs 検証済みクリーン復旧ポイント

| 観点 | Snapshot が存在する（Respond フェーズ） | 検証済みクリーン復旧ポイント（本ワークフロー） |
|------|------------------------------------------|--------------------------------------------------|
| CSF 2.0 機能 | Protect（Snapshot 自体） | Recover — 具体的には RC.RP |
| 何を証明するか | 時点コピーが取得されたこと | そのコピーが検査され、ランサムウェアの痕跡が見られないこと |
| 本番への影響 | なし（Snapshot 作成はほぼ即時） | なし（FlexClone は copy-on-write、スキャンはクローンへの読み取り専用） |
| リストア判断への確度 | 低い — 攻撃 *中* に取得した Snapshot 自体に暗号化済みファイルが含まれる可能性がある | より高い — 人間がリストアを決断する前の自動 go/no-go 信号 |
| 本リポジトリでの自動化状況 | ✅ 完全対応（[自動インシデント対応ガイド](automated-response-guide.md)） | ✅ 完全対応（本ガイド） |

> **復旧十分性に関する補足**: 本ワークフローの「clean」判定は、リストア前の *必要条件* であって *十分条件* ではないものとして扱ってください。粗く分かりやすいケース（ランサムウェアによってリネームされたファイルが多数を占めるボリューム）を、高速かつ低コストに除外するものです。アプリケーションレベルのデータ整合性の検証や、Snapshot がエンドツーエンドでクリーンにリストアできることの検証、あるいは完全な DR テストの代替にはなりません。定期的な完全リストアテストは別途スケジュールし、本ワークフローは全ての検証対象 Snapshot に対して実行する自動化された第一段のゲートとして位置づけ、復旧可能性についての最終判断としては使わないでください。

> **DR Runbook連携に関する補足**: これは上記の復旧十分性に関する補足とは異なります — あちらは「clean」判定の技術的な十分性を扱いますが、こちらは本ワークフローがより広範な DR 計画の運用上の連携にどう位置づけられるかを扱います。このステップは、他の DR Runbook のステップ（フェイルオーバー判断、関係者への通知、アプリケーション再起動の順序）と比べてどこに位置しますか？妥当な配置は次のようになります: インシデント検知 → 保護 Snapshot の取得（Respond） → **本検証の実行** → 「clean」の場合のみ、その Snapshot が、既存の DR 判断基準（RTO/RPO の目標、事業影響評価）と併せて（代替としてではなく）、リストアまたはフェイルオーバーの判断者に提示される。現在の DR Runbook が「Snapshot が存在すること」をリストア開始の十分条件として扱っている場合は、本ワークフローの判定結果をゲートとするよう Runbook を更新してください。ただしこれは、DR 計画への文書化された変更として行い、実際のインシデント時にその Runbook を実行する担当者に伝達すべきものであり、本ガイドの中に埋め込まれた暗黙の前提として扱うべきではありません。

---

## 前提条件

### ONTAP バージョン

- **FlexClone REST API**（`clone.is_flexclone`）: ONTAP 9.8+ で利用可能
- **ボリューム作成/削除 REST API**: ONTAP 9.6+ で利用可能

> **パッチ管理に関する補足**: 本ガイドが示すのは各 API が必要とする*最低*バージョンであり、実行を*推奨*するバージョンではありません。本ワークフローは、ONTAP 管理エンドポイントに触れる他のどのコンポーネントとも同様に扱ってください — 稼働中の ONTAP バージョンについて [NetApp のセキュリティアドバイザリ](https://security.netapp.com/)を追跡し、組織の通常のサイクルでパッチを適用してください。`secretsmanager:GetSecretValue` 権限を持つ認証情報で ONTAP REST API を自ら呼び出す検証ワークフローだからといって、他の ONTAP API 利用者と同じパッチ管理の規律から免除されるわけではありません。別の観点として、Lambda ランタイム（`python3.12`）とその `boto3`/`botocore`/`urllib3` 依存関係（CloudFormation テンプレートのインライン `ZipFile` コード参照）は、本スタック内で特定バージョンに固定されていません — Lambda はデプロイ時点で利用可能な最新の `python3.12` マネージドランタイムとそこに同梱された SDK バージョンを解決するため、AWS の Lambda ランタイム廃止スケジュールを追跡し、一度デプロイしたら永続的に最新の状態が保たれると想定せず、定期的に再デプロイしてください。

> **セキュリティに関する補足 — 本番投入前の必須修正事項**: `CreateFlexClone` と `Cleanup`（ONTAP REST API を直接呼び出す 2 つの Lambda）は、`urllib3.PoolManager` を `cert_reqs="CERT_NONE"` で構築しています — 本スタックのインライン Lambda コードでは TLS 証明書検証が無条件に無効化されており、Secrets Manager から取得した ONTAP 管理者認証情報を送信するこの通信経路では、（中間者攻撃者が提示する自己署名証明書を含む）任意の TLS 証明書が検証なしに受け入れられます。本スタックのロジックの元になっているスタンドアロンの `restore_verification.py` ライブラリには、適切な検証を有効にするための `ca_cert_path` パラメータが*存在します*が、CloudFormation テンプレートのインライン `ZipFile` コードはこのオプションを公開・利用しておらず、`CERT_NONE` を固定でハードコードしています。これは隔離されたラボ VPC での PoC としては許容範囲ですが、実際の ONTAP 管理者認証情報を通信路に流す本番デプロイでは許容できません。本番利用前に、(a) FSx for ONTAP 管理エンドポイントの CA 証明書を Lambda に提供し（Lambda Layer、バンドルした証明書を指す環境変数、または Secrets Manager 経由）、`cert_reqs` を `"CERT_REQUIRED"` に変更して対応する `ca_certs` を設定する、または (b) 補完的なネットワーク制御（例: Lambda が ONTAP 管理 IP に到達する経路が、トランジットされないプライベートな VPC サブネットのみである）により、自社の環境では経路上での TLS 傍受が現実的に不可能であることを確認し、その判断を暗黙のデフォルトとして残さず明示的に文書化してください。

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

> **重要: VPC Endpoint について**。`CreateFlexClone`/`Cleanup` は（ONTAP 認証情報のために）VPC から Secrets Manager と STS に到達できる必要があります。`Cleanup` はさらに（`DetachAndDeleteS3AccessPoint` のために）**FSx 用 Interface Endpoint** が必要です。`ScanForIndicators` は、ルートテーブル（`RouteTableIds` パラメータ）に紐づいた **S3 Gateway Endpoint** が必要です — これがないと、スキャンステップは VPC 限定の Access Point に一切到達できず、ワークフローは間欠的にではなく毎回そのステートで失敗します。この 4 つの Endpoint それぞれに独立したパラメータ（`CreateSecretsManagerEndpoint`/`CreateStsEndpoint`/`CreateFsxEndpoint`/`CreateS3GatewayEndpoint`、いずれもデフォルト `true`）が用意されています — VPC に既に存在するものだけを `false` に設定してください。全部か無しかの二択として扱う必要はありません。これら 4 つの値を選ぶ前に何を確認すべきかは、直後の「デプロイ前チェック」を参照してください。

---

## デプロイ前チェック: 既存の VPC Endpoint を確認する

これは本スタックで最も頻発するデプロイ失敗であり、しかもエラーメッセージを一読しただけでは診断を誤りやすい形で失敗します。同じ VPC 内に、同じサービス向けの Interface VPC Endpoint が `PrivateDnsEnabled: true` で既に存在する場合、CloudFormation は**2 つ目**の Interface Endpoint 作成を拒否します。両方の Endpoint が同じプライベート DNS ドメイン（例: `secretsmanager.<region>.amazonaws.com`）を VPC 内に登録しようとするためです。エラーメッセージは競合している DNS ドメイン名を示しますが、それを既に登録しているリソースの名前は示さないため、見当違いの場所を調査してしまいがちです。

**`CreateXxxEndpoint` パラメータの値を決める前に、必ず以下を実行してください:**

```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<対象VPCのID>" \
  --query "VpcEndpoints[].{Service:ServiceName,Type:VpcEndpointType,State:State}" \
  --output table
```

出力結果を以下の表と照合してください:

| 出力に表示されるもの | このパラメータを設定 |
|---------------------|----------------------|
| `com.amazonaws.<region>.secretsmanager`（Interface） | `CreateSecretsManagerEndpoint=false` |
| `com.amazonaws.<region>.sts`（Interface） | `CreateStsEndpoint=false` |
| `com.amazonaws.<region>.fsx`（Interface） | `CreateFsxEndpoint=false` |
| `com.amazonaws.<region>.s3`（Gateway）、かつ本デプロイで指定する `RouteTableIds` と同じルートテーブルに既に関連付けられている | `CreateS3GatewayEndpoint=false` |
| 上記のいずれも存在しない | 4 つ全てデフォルトの `true` のままでよい |

[`automated-response.yaml`](automated-response-guide.md) と同じ VPC に本スタックをデプロイする場合、そのスタック自身は VPC Endpoint を一切作成しません — 元々その VPC に存在していた Endpoint に依存する構成です。したがって上記のチェックはそのまま全て適用されます。「`automated-response.yaml` が先にデプロイされているから、この 4 つの Endpoint のいずれかが既に存在するはずだ」という前提は置かないでください。

> **Route53 プライベートホストゾーンに関する補足**: 組織によっては、FSx for ONTAP や他の AWS サービスを実行する VPC 自体が、Transit Gateway・VPC ピアリング・Virtual Private Gateway経由で共有サービス VPC に接続された「スポーク」であり、Interface VPC Endpoint はその共有サービス VPC 側に集中的に作成され、そのプライベートホストゾーンが（`AssociateVPCWithHostedZone` により）解決を必要とする各スポーク VPC に関連付けられている、という構成を取っている場合があります。自社の VPC がこの種のトポロジーにおけるスポークである場合、スポーク VPC に対して `describe-vpc-endpoints` を実行しても Endpoint は**何も表示されません** — たとえ（例えば）`secretsmanager.<region>.amazonaws.com` がその VPC 内で既に解決可能であっても、Endpoint リソース自体は別の VPC に存在し、そのVPCへ届いているのは Route 53 のプライベートホストゾーン関連付けだけだからです。このトポロジーでは、本スタック自身の Interface Endpoint を `PrivateDnsEnabled: true` で作成しようとすると、同じ DNS ドメイン競合エラーで失敗しますが、`describe-vpc-endpoints` だけでは事前に警告されません。`describe-vpc-endpoints` で何も表示されないにもかかわらず共有サービス型トポロジーが疑われる場合は、`CreateXxxEndpoint=true` が安全だと判断する前に、`aws route53 list-hosted-zones-by-vpc --vpc-id <対象VPCのID> --vpc-region <リージョン>` を追加で実行し、対象 AWS サービスのドメイン（例: `secretsmanager.<region>.amazonaws.com.`）に一致するプライベートホストゾーンがないか確認してください。一致するゾーンが存在する場合、そのサービスは既に中央管理された Endpoint 経由でその VPC 内でプライベートに解決可能であり、本スタック自身がそのサービス向けに Endpoint を作成しようとしても、文字通りの重複と同じ形で失敗します。これは仮定の話ではありません — 本プロジェクト自身の検証デプロイが、FSx・Secrets Manager・SSM・SNS 関連のプライベートホストゾーンが VPC 外から既に関連付けられた共有サービス型 VPC に対して、まさにこの失敗モードに遭遇しています。

**それでもデプロイして競合に遭遇した場合**: スタックは自動的にロールバックし（`ROLLBACK_COMPLETE`）、CloudFormation はそのステートのスタックに対して `deploy`/`create-stack` を再試行させません — 先に削除する必要があります:

```bash
# 失敗を確認し、どのリソースが競合したかを確認する
aws cloudformation describe-stack-events \
  --stack-name fsxn-restore-verification \
  --query "StackEvents[?ResourceStatus=='CREATE_FAILED'].{Resource:LogicalResourceId,Reason:ResourceStatusReason}" \
  --output table

# ロールバックしたスタックを削除する(安全です — 動作可能な状態に一度も
# 到達していないため、台帳テーブルに失う検証履歴はありません)
aws cloudformation delete-stack --stack-name fsxn-restore-verification
aws cloudformation wait stack-delete-complete --stack-name fsxn-restore-verification

# 上記の表に従って正しい CreateXxxEndpoint の値を指定して再デプロイする
```

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
    CreateSecretsManagerEndpoint=<true-or-false> \
    CreateStsEndpoint=<true-or-false> \
    CreateFsxEndpoint=<true-or-false> \
    CreateS3GatewayEndpoint=<true-or-false> \
  --capabilities CAPABILITY_NAMED_IAM
```

4 つの `CreateXxxEndpoint` の値は、上記の[デプロイ前チェック](#デプロイ前チェック-既存の-vpc-endpoint-を確認する)の表に従って設定してください — `describe-vpc-endpoints` による確認を行わずにデフォルト値のままデプロイしないでください。

スタックが作成するリソース:
- Step Functions ステートマシン（`{stack-name}-workflow`）
- Lambda 関数 5 個（create-clone、attach-ap、scan、record-verdict、cleanup）
- DynamoDB 台帳テーブル（`{stack-name}-ledger`）
- ステートマシン用 CloudWatch Logs（365 日保持）、各 Lambda 用 CloudWatch Logs（90 日保持。record-verdict はコンプライアンスエビデンスも兼ねるため 365 日保持）
- `true` のままにした Secrets Manager・STS・FSx（Interface）・S3 Gateway の各 VPC Endpoint — どの Lambda がどの Endpoint を必要とするかは上記[ネットワークアクセス](#ネットワークアクセス)、それぞれを独立して選ぶ方法は[デプロイ前チェック](#デプロイ前チェック-既存の-vpc-endpoint-を確認する)を参照

> **変更管理に関する補足**: 変更承認プロセス向けに、本デプロイが触れるものと触れないものを明確にしておきます — 本デプロイは新規かつ追加的なリソース（新しい Step Functions ステートマシン、新しい Lambda 群、新しい DynamoDB テーブル、選択した VPC Endpoint）のみを作成し、FSx for ONTAP ファイルシステム本体、既存の ONTAP ボリューム、あるいは既存の VPC ネットワーク構成は一切変更しません。デプロイ失敗時の影響範囲はこれらの新規リソースに限定され、`cloudformation delete-stack` によるロールバックは本番ストレージに一切触れずにこれらを削除します。変更チケットで明記すべき唯一の共有状態リスクは次の点です: いずれかの `CreateXxxEndpoint` パラメータを `true` のままにした対象サービスについて、対象 VPC に既に別のスタック（例: `automated-response.yaml` の VPC、あるいは中央管理された共有サービス VPC — 上記の Route53 プライベートホストゾーンに関する補足を参照）による Interface Endpoint が存在している場合、本デプロイは既存の Endpoint を暗黙的に再利用するのではなく、重複 Endpoint の DNS 競合でスタック全体がロールバックします。この確認は最初の失敗後に後追いで行うのではなく、変更チケットのデプロイ前検証の一部として[デプロイ前チェック](#デプロイ前チェック-既存の-vpc-endpoint-を確認する)を実行してください。

> **リソースタグ付けに関する補足**: 本スタックの CloudFormation テンプレートでは、`VerificationLedgerTable` のみが `Project`/`Purpose` のタグペアを持っており、5 つの Lambda 関数と Step Functions ステートマシンには `Tags` プロパティが一切設定されていません。組織がコスト配分タグやリソースグループタグに依存してコストの帰属やタグ付けポリシーを強制している場合（例: AWS Config の `required-tags` ルールや、タグなしリソースの作成を拒否するサービスコントロールポリシー）、DynamoDB テーブルは正しくタグ付けされているにもかかわらず、本スタックはそのまま出荷された状態ではその強制を通過できないか、Lambda/Step Functions の支出がコスト帰属から漏れてしまいます。タグ付けガバナンスが強制されているアカウントにデプロイする前に、`AWS::Lambda::Function` リソースと `AWS::StepFunctions::StateMachine` リソースに同等の `Tags` ブロックを追加してください。

> **スタック更新に関する補足**: 本テンプレート内のどのリソースにも `DeletionPolicy` や `UpdateReplacePolicy` は設定されていません（上記で既に触れた DynamoDB テーブル自体の削除保護のギャップは別として）— `VerificationLedgerTable` を置き換えることになる CloudFormation スタックの**更新**（例: `KeySchema` や `AttributeDefinitions` への変更は、インプレース更新ではなく置き換えを強制します）は、デフォルトでは古いテーブルとその検証履歴全体を削除してしまいます。これは、スタック**削除**の場合として既に文書化されているリスクよりも狭い範囲ですが、見落としやすいリスクです — 通常のメンテナンス作業中の、善意によるテンプレート変更が同じデータ損失を引き起こす可能性があります。本スタックの DynamoDB テーブル定義に何らかの変更を加える前には、必ず `aws cloudformation create-change-set` を先に実行し、その出力で対象テーブルが `Replacement: True` になっていないかを確認してください。なっている場合は、事前にテーブルの内容をエクスポートするか、`VerificationLedgerTable` に `DeletionPolicy: Retain` を追加して、更新による置き換えが発生しても古いテーブルが削除されず孤立した状態で残るようにしてください。

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

> **キャパシティ計画に関する補足**: 本ワークフローは `ReservedConcurrentExecutions` や `MaxConcurrency` をどこにも設定していません — 各 Step Functions 実行は、アカウント/リージョンで共有される未予約の同時実行プールに対して、それぞれ 5 つの Lambda 呼び出しを行います。多数の Snapshot がほぼ同時に検証される大規模フリート（例: 数百のボリュームに対するスケジュールされた一斉スイープ、または多数の `create_snapshot` アクションを一度に発火させる大規模インシデントシナリオ）では、検証実行の同時実行バーストが、`automated-response.yaml` のレスポンスハンドラーを含むアカウント内の他の全 Lambda 関数と同じプールを争うことになります。大規模フリートに対して本ワークフローをスケジュールする前に、想定される同時検証実行数をアカウントの Lambda 同時実行数の上限と比較検討し、実行をファンアウトする仕組み（EventBridge Scheduler、Step Functions の `Map` ステート、または SOAR ツール）側に `MaxConcurrency` の上限を設定することを検討してください。アカウント全体の上限を暗黙のスロットルとして依存するのではなく。

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

> **コストに関する補足**: 1 回の検証実行あたりの主なコスト要因は、Lambda の実行時間（5 つの短命な関数、それぞれ数秒程度）、DynamoDB のオンデマンド書き込み（`PAY_PER_REQUEST` テーブルへの `PutItem`/`UpdateItem` 呼び出しが実行あたり 2〜3 回）、そして `CreateVpcEndpoints=true` の場合は Interface VPC Endpoint（Secrets Manager、STS、FSx）の時間課金とデータ処理量あたりの課金です。S3 Gateway Endpoint 自体には時間課金はありません。これらはいずれも、コンテンツレベル PII 分類スキャナーの [Amazon Comprehend の課金](https://aws.amazon.com/comprehend/pricing/)のようにスキャン対象オブジェクト単位で課金されるものではなく、コストは*実行頻度*に応じて増減します（ボリュームサイズには依存しません）。そのため、大規模なフリート内の全 Snapshot に対して 1 時間おきに本ワークフローを実行するのと、インシデントごとに一度だけ実行するのとでは、コストの規模が大きく異なります。同じ VPC 内で本スタックと `automated-response.yaml` の Interface VPC Endpoint を共用し（`CreateVpcEndpoints=false`）、重複課金を避けてください。

> **サステナビリティに関する補足**: これは計算炭素の観点から見て根本的に軽量なワークロードです — 1 回の実行あたり 5 つの短命な Lambda 呼び出しがあり、それぞれ持続的な CPU バウンドの計算ではなく I/O バウンドの作業（ONTAP REST 呼び出し、S3 一覧取得、DynamoDB 書き込み）を行い、実行間にアイドリングする永続的なコンピュート（常時起動の EC2 やコンテナ）もありません。上記のコストに関する補足と同じ観察が、単位を変えてここにも当てはまります — 消費エネルギーにとって重要なレバーは*実行頻度*であり、ボリュームサイズではありません。これは `ScanForIndicators` がファイルの内容を読むのではなくオブジェクトキーを一覧化するだけ（`ListObjectsV2`）であるためです。大規模フリートの全 Snapshot に対して 1 時間おきに本ワークフローをスケジュールすると、呼び出し回数（したがってエネルギー消費）はスケジュール頻度に線形に比例して増加します。目的がインシデント後の検証ではなく定期的な復旧レディネスチェックであれば、フリート全体を毎時スキャンするよりも、代表的なボリュームに対して日次または週次のケイデンスで実行する方が、有意に少ない総エネルギー消費で同じ目的を達成できる可能性が高いです。

---

## セキュリティ考慮事項

- **本番データへの経路なし**: FlexClone は copy-on-write で親ボリュームとブロックを共有しますが、S3 Access Point が公開するのは *クローン* のみで、親ボリュームは公開されません。クリーンアップ時にクローンを削除しても、親ボリュームや元の Snapshot には影響しません。
- **VPC 限定の Access Point**: Access Point は作成時に VPC に束縛され、VPC 外からは到達できません。これは、ポリシーのみで制御するインターネット起点の Access Point よりも強い保証です — 詳細は [AWS のネットワーク起点比較](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)を参照してください。この特性のため、Access Point のオブジェクトを一覧化する `ScanForIndicators` は、束縛された VPC 内で S3 へのルート（本スタックが作成する S3 Gateway Endpoint）を持って実行される*必要があります* — インターネット起点の Access Point とは異なり、VPC 限定の Access Point にはポリシーだけで VPC 外から到達する方法がありません。

> **データレジデンシーに関する補足**: 本ワークフローが作成する全てのリソース — FlexClone（定義上、親の FSx for ONTAP ファイルシステムと同じリージョン）、S3 Access Point、DynamoDB 台帳テーブル、Lambda 関数自体 — は、本スタックをデプロイした単一の AWS リージョン内に留まります。本ワークフロー内でリージョンを跨いだデータ移動は一切ありません。これはデータレジデンシーのアンケートに対して、推測に頼らず積極的に確認・肯定できる点です。組織が複数リージョンで本ワークフローを運用する場合（サイバーレジリエンス機能マップで参照されている[マルチアカウントデプロイ](multi-account-deployment.md)パターンに従い、リージョンごとに 1 スタック）、各リージョンの台帳は独立しています — 検証履歴のリージョン横断レプリケーションや集約は組み込まれていないため、レジデンシー要件に基づくマルチリージョン展開では、独自の集約レイヤーを構築しない限り、リージョンごとに独立したエビデンストレイルになります。
- **`fsx:*S3AccessPoint*` アクションの最小権限**: これらのアクションは現時点で、他の FSx アクションほど細かいリソースレベル権限や条件キーをサポートしていません。本スタックの IAM ポリシーではこれらを `Resource: '*'` にスコープし、その理由をドキュメント化しています。AWS がリソースレベルのサポートを追加した場合は見直してください。

> **IAM設計に関する補足**: `VerificationLambdaRole` は 5 つの Lambda 全てに割り当てられる単一の共有ロールであり（CloudFormation テンプレート参照）、各関数が実際に必要とする権限に絞った 5 つの個別ロールにはなっていません。`ScanForIndicators`（`s3:ListBucket`/`s3:GetObject` のみが必要）は、技術的には `AttachAccessPoint`/`Cleanup` が実際に使用している同じ広範な `Resource: '*'` の `fsx:*S3AccessPoint*` 権限も引き継いでいますが、これらの API を一切呼び出しません。これは単一目的のスタックにおいてよくある合理的なトレードオフです（監査対象のロール数が減り、ロール間の `iam:PassRole` の複雑さがない）が、`ScanForIndicators` の実行環境が侵害された場合、そのコード自体が必要とする範囲よりも広い IAM の到達範囲を持つことを意味します。組織の IAM 標準が単一ワークフロー内でも関数単位の最小権限を求める場合は、`VerificationLambdaRole` を各関数のコードパスが実際に呼び出すポリシーステートメントのみに絞った、関数別のロールに分割してください。
- **判定結果台帳はエビデンスであり、ガバナンスの代替ではない**: DynamoDB 台帳は、誰が何をいつ検証し、どのような結果だったかという監査可能なエビデンスを提供し、CSF 2.0 の Govern プログラムが入力として利用できます — 本リポジトリがガバナンスプログラム自体を自動化しようとしない理由については、[サイバーレジリエンス機能マップ](cyber-resilience-capability-map.md#govern統制) の Govern 機能に関する議論を参照してください。
- **台帳テーブルにはデフォルトで削除保護がない**: `VerificationLedgerTable` は Point-in-Time Recovery を有効にして作成されますが、`DeletionProtectionEnabled` や明示的な `DeletionPolicy: Retain` は設定されていません。このテーブルを定期的なリストア検証の主要なエビデンスとして利用する場合（下記のサイバー保険エビデンスに関する補足を参照）、監査目的で依拠する前に `DeletionProtectionEnabled: true` を追加し、`DeletionPolicy: Retain` の上書きも検討してください — うっかり `aws cloudformation delete-stack` を実行しても、エビデンスの履歴が消えてしまうことがないようにするためです。

> **保管時暗号化に関する補足**: `VerificationLedgerTable` の `SSESpecification` は `SSEEnabled: true` で暗号化を有効にしていますが、`SSEType`/`KMSMasterKeyId` は設定していません。つまり、カスタマー管理の KMS キーではなく AWS 所有の DynamoDB キーで暗号化されます。これはほとんどのワークロードにとって妥当なデフォルトであり「保管時に暗号化されている」という要件は満たしますが、組織の鍵管理ポリシーがカスタマー管理 KMS キー（独立したローテーション管理、クロスアカウントのキーポリシー、特定のコンプライアンスマッピングのため）を要求する場合は、`SSEType: KMS` と `KMSMasterKeyId: <自社のキー ARN>` を明示的に追加してください — 現在のテンプレートはこれをパラメータとして公開していません。同じことが、ステートマシンと各 Lambda の CloudWatch Log Group にも当てはまります（こちらもデフォルトで AWS 所有の CloudWatch Logs キーで暗号化され、いずれの `AWS::Logs::LogGroup` リソースにも `KmsKeyId` は設定されていません）。

> **監査証跡の完全性に関する補足**: `VerificationStateMachine` の `LoggingConfiguration` は `Level: ALL` と `IncludeExecutionData: true` を設定しており、これは完全な可観測性のためには望ましい設定です — しかし、ここでの「完全な可観測性」は、DynamoDB 台帳の厳選されたフィールドだけでなく、全ての実行における全ステートの入出力ペイロード全体（`svm_name`、`volume_name`、`snapshot_name`、および `reason`/`error` のテキストを含む）が CloudWatch Logs に書き込まれることも意味します。自社の環境で `volume_name` や `snapshot_name` の値にセンシティブな文脈（インシデントチケット番号、Snapshot ラベルに含まれた顧客名など）が埋め込まれている場合、その文脈は台帳テーブルだけでなく、本スタックのログ保持期間（365 日）を持つ CloudWatch Logs にも存在することになります — 単一の正となる情報源が台帳テーブルだけだと想定していると、この点を見落としがちです。Snapshot・ボリュームの命名規則をこの点を踏まえて見直すか、ログ内の完全なペイロードが許容できる露出範囲を超える場合は `IncludeExecutionData: false` を設定してください（その場合、対応するデバッグ情報の詳細さは失われます）。

> **サイバー保険エビデンスに関する補足**: サイバー保険の引受チェックリストでは、バックアップの存在だけでなく*テスト済み*であることのエビデンスが求められる傾向が強まっています — 2026 年時点の複数の引受ガイドで「定期的なリストア検証（periodic restore verification）」が明示的に挙げられています。本ワークフローが生成する DynamoDB 台帳（実行ごとにタイムスタンプ付きの `snapshot_key`、判定結果、`reason` を記録）は、この問いに対する合理的なエビデンスアーティファクトになりますが、保険会社側のエビデンス提出フォーマットを念頭に設計されたものではありません。更新時のアンケート提出用に PDF/CSV へエクスポートする機能は組み込まれておらず（上記の通り）、エビデンス自体を守る削除保護もありません。引受や更新の際に本台帳を提示する予定がある場合は、まず上記の削除保護を有効化した上で、該当する `dynamodb query` の出力結果のスナップショットを他の管理エビデンスと一緒にエクスポートしてください。

> **監査エビデンスに関する補足**: 本ワークフローが内部監査や SOX のコントロールマトリクスにおける統制として引用される場合（例: 「復旧ポイントはリストア前に検証される」というコントロールの主張）、運用の実効性を検証する監査担当者は通常、次のようなエビデンスを求めます: (1) その統制が*存在する*だけでなく、サンプル期間中に実際に*実行された*というエビデンス — DynamoDB 台帳の `started_at`/`completed_at` タイムスタンプはこれを裏付けます。(2) 「suspicious」または「error」判定を、適切な権限を持つ誰かが*レビューし*、対応を取ったというエビデンス — これは本ワークフロー自体が生成するものではありません。SNS 通知が発火したことは、アラートが*送信された*エビデンスであり、誰かが*対応した*エビデンスではありません。(3) 本スタックの IAM 権限/コードを変更できる担当者（事実上「clean」の意味を制御する立場）と、その判定結果に依拠してリストアを承認する担当者との間の職務分離。SOX のコントロールが本ワークフローに依拠する場合は、自動化された判定結果と、人間によるレビューと対応を記録する手動のアテステーションステップ（チケット、承認ワークフローなど）を組み合わせ、そのアテステーションを DynamoDB の記録と併せて実際の監査エビデンスとして保持してください — 台帳単体では、スキャンが実行されたことは記録されますが、誰かがその結果に対して判断を下したことは記録されません。

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

> **テストカバレッジに関する補足**: 23 件のテストは全て `boto3` クライアントと ONTAP への HTTP レスポンスをモックした状態で実行され、実際の FSx for ONTAP ファイルシステムや実際の S3 Access Point には一切アクセスしません。これによりテストスイートは高速かつ CI 上で安全に実行できます（AWS 認証情報や稼働中のインフラは不要）が、その反面、モックされた API の契約と実際の ONTAP REST API/AWS FSx API の挙動との間にずれが生じても検出できません。`pytest` の成功は、ワークフローがエンドツーエンドで動作するための必要条件ではあっても十分条件ではないものとして扱ってください — 本番投入前に実際の（本番でない）FSx for ONTAP ファイルシステムで検証し、FlexClone や S3 Access Point の API に関わる ONTAP や AWS SDK のバージョンアップ後は再検証してください。

> **ライセンスに関する補足**: 本ワークフローの実行時依存関係は `boto3`、`botocore`、`urllib3` であり、いずれも本リポジトリにベンダリングされているのではなく Lambda の `python3.12` マネージドランタイムに同梱されているため、直接ライセンススキャンできる `requirements.txt` やロックファイルは本スタック内に存在しません。3 つとも [Apache License 2.0](https://github.com/boto/boto3/blob/develop/LICENSE) であり、これはコピーレフト義務を課さない許諾性の高いライセンスです。そのためライセンスコンプライアンスの観点からは低リスクな依存関係セットと言えます。組織がサプライチェーンレビューの一環として自動ライセンススキャン（SBOM 生成ツールや `pip-licenses` のようなツールなど）を実行している場合、本スタックのインライン CloudFormation `ZipFile` コードを直接スキャンしても、`requirements.txt` ベースのデプロイの場合とは異なりこれらの依存関係は検出されない点に注意してください — 代わりに Lambda マネージドランタイム自身が公開している依存関係マニフェストに対してスキャンする必要があります。あるいは、上記の パッチ管理に関する補足注記で触れた固定依存関係方式のデプロイに移行すれば、このスキャンも容易になります。

> **運用トリアージに関する補足**: 検証実行の失敗でアラートを受けた場合、まず次の手順で確認してください: (1) 該当する `StateMachineExecutionArn` の Step Functions 実行履歴を確認し、失敗したステート名から 5 つの Lambda のうちどれが失敗したかを特定する。(2) その Lambda の CloudWatch Logs（`/aws/lambda/{stack-name}-{create-clone|attach-ap|scan|record-verdict|cleanup}`）で実際の例外内容を確認する。(3) 該当する `snapshot_key` で DynamoDB 台帳を検索する — `error` 判定と `reason` フィールドだけで、ログを見ずにトリアージできることも多いです。失敗した実行そのものは深夜 2 時の即時対応を必要としません — ワークフロー自身の `Cleanup`/`CleanupAfterError` ステートが、FlexClone や S3 Access Point の残置を既に保証しているためです（上記アーキテクチャ参照）。そのため基本的には「都合のよいときに調査すればよい」アラートであり、「今すぐ止血が必要」なアラートではありません。ただし同じ `snapshot_key` が繰り返し失敗する場合は、ONTAP 側または IAM 側の問題である可能性があり、早めのエスカレーションを検討してください。

> **障害注入に関する補足**: 上記のテスト節は正常系といくつかのモック済み失敗モードを検証していますが、「クリーンアップはどの経路でも実行される」（アーキテクチャ参照）という主張は、Step Functions の `Catch` 構成を信頼するだけでなく、実際の（本番でない）デプロイに対して実際に障害を注入して検証するのが最も確実です。試す価値のある実験: (1) `ScanForIndicators` Lambda の実行中に強制的に失敗させ（例: `s3:ListBucket` への一時的な IAM 拒否）、ステートマシンが成功を報告しているだけでなく、FlexClone が実際に削除されたことを確認する。(2) `Cleanup` 自体（下流に独自の catch を持たない唯一の Lambda）の実行中に ONTAP API のタイムアウトを注入し、クリーンアップ自体のセーフティネットがない状況で、残置されたクローンを検出・手動修復できるか確認する。(3) `RecordVerdict` は成功したが、続く `Cleanup` ステップの Lambda 呼び出し自体が開始に失敗する場合（アプリケーションエラーではなく Step Functions レベルの障害）に何が起こるかを検証し、CloudWatch アラームが実際にそのギャップを検知するかを確認する。これらはいずれも本番データを必要とせず、使い捨ての SVM/ボリュームと合成的な Snapshot で十分です。

> **リトライポリシーに関する補足**: 本ワークフローの `DefinitionString` 内の全ステートは `Catch` ブロックを定義していますが、`Retry` ブロックはどのステートにも定義されていません — 一時的な障害（ONTAP 管理エンドポイントが瞬間的に到達不能、Secrets Manager や DynamoDB の短時間のスロットリング、VPC 内での一過性のネットワーク不調など）は、最初の試行でリトライすることなく即座に `CleanupAfterError`/`RecordErrorVerdict` に流れます。つまり、2 回目の試行なら成功していたはずのワークフローが、代わりに永続的な「error」判定を記録し、実際には回復可能な一時的な不調に対して完全なクローン作成とクリーンアップのサイクルを丸ごと発生させてしまいます。自社の環境で一時的な ONTAP API や AWS API のエラーが時々発生する場合は、`Catch` に流れる前に `Retry` ブロック（例: `ErrorEquals: ["States.Timeout", "States.TaskFailed"]` と短い `IntervalSeconds`/`MaxAttempts`/`BackoffRate`）を Lambda 呼び出しステートに追加することを検討してください — これは Step Functions の標準的なパターンですが、本ワークフローは現状これを使用していません。

> **SNS 配信に関する補足**: `RecordVerdict` と `RecordErrorVerdict` の両方の SNS `publish` 呼び出しは、失敗時に警告ログを出すだけの単純な `try`/`except Exception` でラップされています（`logger.warning("Verdict notification failed: %s", e)`）— それ以前の DynamoDB `put_item` は必ず成功するかエラーを発生させますが、SNS publish の失敗（トピックの削除、権限変更、スロットリング）は呼び出し元から見ると静かに握り潰されます。Step Functions の実行自体は成功を報告し、DynamoDB 台帳にも正しい判定結果が記録されますが、「suspicious」な結果を知るために依拠していた通知自体は単純に届かなかった可能性があります。しかも本ワークフロー自身の CloudWatch メトリクスには、「PII なし・通知不要」と「通知を試みたが失敗した」を区別する仕組みが何もありません。SNS の配信がインシデント対応のトリガーチェーンの一部である場合は、アラートの欠如を「疑わしい判定がなかった」ことと同義に扱うのではなく、この Lambda 自身のログパターン（`"notification failed"`）に対する CloudWatch アラームを追加してください。

---

## 関連ドキュメント

- [サイバーレジリエンス機能マップ](cyber-resilience-capability-map.md#recover復旧) — 本ガイドが対応する Recover 機能に関する議論
- [自動インシデント対応ガイド](automated-response-guide.md) — 本ワークフローの実行前に通常先行する、Respond フェーズのブロックと保護 Snapshot 作成
- [ARP インシデント対応ガイド](arp-incident-response-guide.md) — 本ワークフローのスキャンが補完する（代替するのではない）、本番ボリュームに対するリアルタイムのエントロピー検知
- [コンテンツレベル PII 分類スキャナー](content-classification-scanner.md) — 同じ FlexClone + S3 Access Point パターンを基盤とした、CSF 2.0 の Identify 機能（データ分類）向けの関連コンテンツスキャン機能
- [ガバナンス・コンプライアンス](governance-and-compliance.md) — 判定結果台帳が Govern 機能のエビデンスとしてどう位置づけられるか
- [コンプライアンスエビデンスパック](compliance-evidence-pack.md) — 監査証跡エビデンスのテンプレート

## FAQ

**Q: 「clean」判定は、その Snapshot が安全にリストアできることを保証しますか？**
A: いいえ — 上記の 復旧十分性に関する補足を参照してください。これはファイル拡張子パターンに基づく高速で自動化された事前フィルタであり、完全なマルウェアスキャンやアプリケーションレベルの整合性チェックではありません。必要な第一段のゲートとして扱い、最終判断とはしないでください。

**Q: 本番ボリュームを直接スキャンせず、なぜ FlexClone を使うのですか？**
A: 稼働中のボリュームをスキャンすると本番の I/O と競合し、進行中の攻撃と干渉するリスクがあります。FlexClone は copy-on-write でブロックを共有する、隔離された時点の読み書き可能なコピーです。検証はこのクローンに対して本番への影響ゼロで実行され、完了後に削除されます。

**Q: NFS/SMB でクローンをマウントせず、なぜ S3 Access Point を使うのですか？**
A: マウントには SVM のデータ LIF へのネットワークレベルのアクセスと、検証環境で稼働する NFS/SMB クライアントが必要です。S3 Access Point を使えば、ステートレスな Lambda がマウント手順なしに S3 API 経由でファイルを一覧・読み取りできます。VPC 限定にした場合は、読み取り専用の Access Point 自体を除けば本番データプレーンへの経路も一切生まれません。

**Q: ワークフローが途中で失敗した場合、クローンは残置されますか？**
A: されません。Step Functions の `Catch` ブロックは、どの失敗モードも正常系と同じ `Cleanup` Lambda にルーティングします。Cleanup Lambda は部分的な状態（例: クローンは作成されたが Access Point の接続が失敗した場合）を許容し、存在するものだけをクリーンアップします。

**Q: 自動応答モジュールが作成した Snapshot 以外にも実行できますか？**
A: できます。`verify_snapshot()` および Step Functions の入力に必要なのは `svm_name`、`volume_name`、`snapshot_name` のみです。既存の ONTAP Snapshot であれば、インシデントとは無関係なスケジュール Snapshot ポリシーによる Snapshot も含めて動作します。

**Q: 顧客/ユーザーから「検証が終わらない」と報告されました。エスカレーションする前に最初に確認すべきことは？**
A: まず、コンソールまたは `describe-execution` で、その Step Functions 実行の現在のステートを確認してください — 「終わらない」はほぼ常に特定のステートで止まっている状態を意味し、どこかで静かにハングしているわけではありません。`AttachAccessPoint` または `ScanForIndicators` で止まっている場合、最も一般的な原因は VPC ネットワーキングのギャップです（上記のネットワークアクセス参照 — 例えば `ScanForIndicators` に S3 Gateway Endpoint がないケースは間欠的ではなく毎回確実に失敗します）。`CreateFlexClone` で止まっている場合は、リクエスト内の ONTAP ボリューム/SVM 名が実際に存在するか、また ONTAP ジョブが管理エンドポイントに対する `GET /api/cluster/jobs/{uuid}` の直接呼び出しで進捗を示しているかを確認してください。各 Lambda には `StepTimeoutSeconds`（デフォルト 180 秒）の上限があるため、本当のハングは無期限に実行されるのではなく、その時間内に Step Functions の `States.Timeout` エラーとして表面化するはずです — `StepTimeoutSeconds` × 5 よりもかなり長く「実行中」の実行を見かけた場合、それ自体がタイムアウト機構が期待通り機能していないことを示す異常としてエスカレーションする価値があります。

**Q: 既存の FSx for ONTAP フリートを本検証ワークフローに移行する場合、どこから始めればよいですか？**
A: まず 1 つのボリュームに対して本スタックをデプロイし、既存のスケジュール Snapshot に対して `verify_snapshot()` を手動で実行してみてください — これにより、自動トリガーに組み込む前に、自社の特定の環境（ONTAP バージョン、VPC 構成）に対して ONTAP 権限、VPC ネットワーキング、FSx S3 Access Point のサポートが実際に機能することを確認できます。本ワークフローが存在する前に作成された既存の Snapshot も、特別な処理なしに動作します — 本ワークフローが Snapshot に遡って要求するメタデータやタグ付けはありません。1 つのボリュームで検証できたら、ボリュームやアカウント単位で手動デプロイするのではなく、サイバーレジリエンス機能マップで参照されている同じ[マルチアカウントデプロイ](multi-account-deployment.md)の StackSets パターンを使ってフリート全体に展開してください。

**Q: DynamoDB 台帳に「suspicious」判定が記録されているのに、誰も SNS 通知を受け取っていません。これは想定される挙動ですか？**
A: 通知パイプライン全体が壊れていると結論する前に、`RecordVerdict` Lambda の CloudWatch Logs で `"Verdict notification failed"` という警告がないか確認してください。SNS の `publish` 呼び出しは try/except でラップされており、失敗時はログを出して処理を継続します（上記セキュリティ考慮事項の SNS 配信に関する補足参照）— これは意図的な設計で、通知配信の問題が判定結果の記録をブロックしないようにするためですが、その特定のログ行を監視していない限り、通知の失敗は静かに起こります。このアラートをインシデント対応のトリガーとして利用している場合は、そのログパターンに対する CloudWatch アラームを追加してください。「アラートを受け取らなかった」ことを「何も疑わしいことは起きなかった」ことと同義に扱わないでください。

**Q: DynamoDB テーブルのキースキーマを変更したところ、過去の検証履歴が消えてしまいました。何が起きたのですか？**
A: `VerificationLedgerTable` の `KeySchema` や `AttributeDefinitions` を変更する CloudFormation スタックの更新は、インプレース更新ではなく DynamoDB テーブルの置き換えを強制します。本テンプレートはそのテーブルに `DeletionPolicy: Retain` を設定していないため（上記デプロイ節のスタック更新に関する補足参照）、置き換えを適用する過程で CloudFormation が古いテーブルを削除しました。これが復旧可能なのは、Point-in-Time Recovery が有効になっていて、その保持期間内にリストアする場合のみです。今後は、スキーマに影響する更新の前に必ず `aws cloudformation create-change-set` を実行し、出力に `Replacement: True` がないか確認してください。
