# 自動インシデント対応ガイド — ONTAP REST API によるユーザー/IP ブロック

## エグゼクティブサマリ

本ガイドでは、Amazon FSx for NetApp ONTAP に対する自動脅威封じ込め（ユーザーブロック、IP ブロック、保護 Snapshot）を、AWS ネイティブの検知サービスと ONTAP REST API の応答アクションを組み合わせて実装する方法を解説します。専用のストレージセキュリティ製品と同等の封じ込め能力を、AWS エコシステムとサードパーティ Observability プラットフォーム内で実現します。

**主要機能:**
- ONTAP name-mapping による SMB ユーザーブロック（全ボリュームでアクセス拒否）
- export-policy ルールによる NFS IP ブロック
- 証拠保全のための保護 Snapshot 作成（ストーム防止クールダウン付き）
- 侵害ユーザーの CIFS セッション即時切断
- 上記を一括実行する複合封じ込めアクション

**検知ソース（任意の組み合わせ）:**
- CloudWatch Log Alarm（管理監査ログの異常検知）
- EMS Webhook（ARP ランサムウェア検知、クォータイベント）
- FPolicy 分析（大量削除、異常な拡張子変更）
- サードパーティ SIEM モニター（Datadog、Splunk、Elastic など）

---

## アーキテクチャ

```
+-------------------------------------------------------------------+
| Detection Layer (AWS-native + SaaS Observability)                 |
+-------------------------------------------------------------------+
|                                                                   |
|  CloudWatch Log Alarm --+                                         |
|  EMS Webhook -> Monitor-+                                         |
|  FPolicy -> SIEM -------+-- SNS Trigger Topic                     |
|  Manual invocation -----+                                         |
|                                                                   |
+-------------------------------------------------------------------+
| Response Layer (Lambda + ONTAP REST API)                          |
+-------------------------------------------------------------------+
|                                                                   |
|  SNS -> Lambda (VPC) -> ONTAP REST API                            |
|           |                                                       |
|           +-> Block SMB user (name-mapping)                       |
|           +-> Block NFS IP (export-policy rule)                   |
|           +-> Create protective snapshot                          |
|           +-> Disconnect CIFS sessions                            |
|           +-> SNS notification (action result)                    |
|                                                                   |
|  DLQ -> Alarm -> Notification (failed actions)                    |
|                                                                   |
+-------------------------------------------------------------------+
```

---

## ブロックの仕組み

### SMB ユーザーブロック

ONTAP の name-mapping を利用してアクセスを拒否します:

| ステップ | 動作 | ONTAP CLI 相当 |
|---------|------|---------------|
| 1 | Lambda がドメインとユーザー名を含むトリガーを受信 | — |
| 2 | name-mapping を作成: `DOMAIN\user` → `" "`（空文字） | `vserver name-mapping create -direction win-unix -pattern "DOMAIN\\user" -replacement " "` |
| 3 | ユーザーの次のファイル操作が拒否される | SID→UNIX 変換失敗 → アクセス拒否 |
| 4 | SVM 内の全ボリュームに影響 | name-mapping は SVM 全体に適用 |

**スコープ**: ブロックは SVM 全体に適用されます。SVM 内の全ボリューム、共有、エクスポートでアクセスが拒否されます。

**解除**: name-mapping エントリを削除するとアクセスが復元されます。

### NFS IP ブロック

export-policy に拒否ルールを追加します:

| ステップ | 動作 | ONTAP CLI 相当 |
|---------|------|---------------|
| 1 | Lambda がクライアント IP を含むトリガーを受信 | — |
| 2 | export-policy ルール作成: `clientmatch=<marker>,<ip>`, `ro_rule=never`, `rw_rule=never` | `export-policy rule create -clientmatch "fsxn_auto_response,<ip>" -rorule never -rwrule never` |
| 3 | ルールがポジション 1 に挿入（最優先） | 許可ルールより先に評価 |
| 4 | クライアント IP が該当ポリシーの全 NFS アクセスからブロック | — |

**スコープ**: 指定した export-policy を使用する全ボリュームに影響します。

**マーカー**: ルールの clientmatch に `fsxn_auto_response` を含めることで、識別と一括クリーンアップが容易です。

**解除**: レスポンスマーカーを含む export-policy ルールを削除します。

### CIFS セッション切断

ブロックされたユーザーが操作を続行できないよう、アクティブなセッションを強制切断します:

- ユーザーまたは IP に一致するアクティブ CIFS セッションを列挙
- REST API で各セッションを削除
- ユーザーブロックと併用して即時効果を実現

---

## 比較: 本アプローチ vs 専用ストレージセキュリティ製品

専用のストレージセキュリティ製品（DII Storage Workload Security など）は、ML ベースの行動分析と統合された封じ込めを提供します。本プロジェクトでは、AWS ネイティブおよび SaaS の検知と ONTAP REST API の応答を組み合わせて同等の封じ込めを実現します:

| 機能 | 専用製品 | 本アプローチ |
|------|---------|------------|
| SMB ユーザーブロック | ✅ 自動 | ✅ 自動（同じ ONTAP API） |
| NFS IP ブロック | ✅ 自動 | ✅ 自動（同じ ONTAP API） |
| 保護 Snapshot | ✅ 自動 | ✅ 自動（クールダウン付き） |
| セッション切断 | ✅ 自動 | ✅ 自動 |
| ユーザー行動 ML | ✅ 内蔵（ユーザー別ベースライン） | SIEM 経由（Datadog ML Anomaly、Elastic ML Jobs 等） |
| AD ユーザー追跡 | ✅ 専用コレクタ | FPolicy ログ（user フィールド）+ AD ルックアップ |
| 検知スコープ | ストレージのみ | ストレージ + ネットワーク + アプリケーション（より広い文脈） |
| データ残留場所 | SaaS（外部） | AWS リージョン（データは VPC 内に留まる） |
| SIEM 連携 | 限定的なエクスポート | ネイティブ（検知が SIEM から発生） |
| コストモデル | ノード単位ライセンス | 従量課金（Lambda 実行回数） |

> **ストレージ運用レンズ**: 基盤となる ONTAP メカニズムは同一です。両方のアプローチが同じ REST API エンドポイントを使用します。違いは検知インテリジェンスの配置場所です。専用製品は ML を SaaS に組み込み、本アプローチは顧客が選択した Observability プラットフォームに検知を委ねます。

> **セキュリティアーキテクトレンズ**: AWS ネイティブの検知は、ストレージ専用ソリューションでは相関できない広範な攻撃コンテキスト（VPC Flow Logs、CloudTrail、GuardDuty findings）を提供します。既存の SIEM 投資がある組織にとって、これはセキュリティ運用ワークフローの自然な拡張です。

---

## 前提条件

### ONTAP バージョン

- **FSx for ONTAP**: 現在サポートされている全バージョン（ONTAP 9.11.1+）
- **Name-mapping REST API**: ONTAP 9.6+ から利用可能
- **Export-policy REST API**: ONTAP 9.6+ から利用可能
- **CIFS sessions REST API**: ONTAP 9.8+ から利用可能
- **ARP (Autonomous Ransomware Protection)**: ONTAP 9.10.1+（学習モード）、9.13.1+（ARP/AI）

### ONTAP 権限

Lambda 実行ロールは、Secrets Manager に保存された `fsxadmin` 認証情報で ONTAP に接続します。以下の ONTAP 操作を使用します:

```
# 必要な権限（fsxadmin にはデフォルトで付与済み）
- GET /api/svm/svms
- GET /api/storage/volumes
- POST /api/storage/volumes/{uuid}/snapshots
- GET/POST/DELETE /api/name-services/name-mappings
- GET/POST/DELETE /api/protocols/nfs/export-policies/{id}/rules
- GET/DELETE /api/protocols/cifs/sessions
```

### ネットワークアクセス

Lambda 関数は以下の VPC 内にデプロイする必要があります:
- ONTAP 管理エンドポイントへのルートを持つプライベートサブネット
- ONTAP 管理 IP への HTTPS（TCP 443）アウトバウンドを許可する Security Group
- NAT Gateway は不要（ONTAP エンドポイントはプライベート）

#### ネットワーク前提条件チェックリスト

| 要件 | 確認方法 |
|------|---------|
| Lambda サブネットが ONTAP mgmt IP へのルートを持つ | `aws ec2 describe-route-tables` — ONTAP CIDR へのルートを確認 |
| Security Group が TCP 443 を許可 | SG アウトバウンドルール: `TCP 443 → <ONTAP-mgmt-IP>/32` |
| ONTAP 管理 LIF が UP | `network interface show -role cluster-mgmt`（ONTAP に SSH） |
| クロス VPC（該当する場合） | VPC ピアリングまたは Transit Gateway ルート + SG 参照 |
| 同一 VPC 異なるサブネット | NACL がサブネット間の TCP 443 をブロックしていないか確認 |

> **TLS に関する注記**: デフォルトのモジュール設定は証明書検証を無効にしています（`CERT_NONE`）。本番環境では FSx for ONTAP の CA 証明書を取得し、`CA_CERT_PATH` 環境変数で指定してください。証明書取得方法: `security certificate show -type root-ca -vserver <svm>`（ONTAP CLI）。

### Secrets Manager

ONTAP 認証情報を JSON として保存:
```json
{
  "username": "fsxadmin",
  "password": "<your-password>"
}
```

---

## デプロイ

### CloudFormation スタックのデプロイ

```bash
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=arn:aws:secretsmanager:<region>:<account>:secret:<name> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    DefaultSvmName=<svm-name> \
    NotificationEmail=admin@example.com \
  --capabilities CAPABILITY_NAMED_IAM
```

### 検知ソースの接続

デプロイ後、トリガー SNS トピックに検知ソースをサブスクライブします:

**CloudWatch Log Alarm → SNS:**
```bash
# Log Alarm の Action が Trigger Topic を指すよう設定
# （Log Alarm 作成時に設定）
```

**Datadog Monitor → SNS:**
```
Datadog モニターのメッセージで @sns-<topic-name> を使用
```

**手動テスト実行:**
```bash
aws sns publish \
  --topic-arn <スタック出力の TriggerTopicArn> \
  --message '{
    "action": "contain_smb_threat",
    "svm_name": "svm-prod-01",
    "domain": "CORP",
    "username": "test-user",
    "volume_name": "vol_data",
    "reason": "手動テスト"
  }'
```

---

## サポートされるアクション

### 個別アクション

| アクション | 必須フィールド | 説明 |
|-----------|-------------|------|
| `block_smb_user` | svm_name, domain, username | name-mapping で SMB ユーザーをブロック |
| `unblock_smb_user` | svm_name, domain, username | SMB ユーザーブロックを解除 |
| `block_nfs_ip` | svm_name, client_ip | export-policy ルールで IP をブロック |
| `unblock_nfs_ip` | svm_name, client_ip | IP ブロックを解除 |
| `create_snapshot` | svm_name, volume_name | 保護 Snapshot を作成 |

### 複合アクション（マルチステップ）

| アクション | ステップ | ユースケース |
|-----------|---------|------------|
| `contain_smb_threat` | Snapshot → ユーザーブロック → セッション切断 | 侵害された AD ユーザーを検知 |
| `contain_nfs_threat` | Snapshot → IP ブロック | 不審な NFS クライアント活動 |

---

## SNS メッセージフォーマット

```json
{
  "action": "contain_smb_threat",
  "svm_name": "svm-prod-01",
  "domain": "CORP",
  "username": "jdoe",
  "volume_name": "vol_data",
  "policy_name": "default",
  "reason": "ARP ランサムウェア検知 - arw.volume.state alert"
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| action | はい | サポートされるアクション名のいずれか |
| svm_name | はい（または DEFAULT_SVM_NAME を設定） | 対象 SVM |
| domain | SMB アクション | Windows ドメイン名 |
| username | SMB アクション | Windows ユーザー名 |
| client_ip | NFS アクション | クライアント IP アドレス |
| volume_name | Snapshot / 複合アクション | 保護対象ボリューム |
| policy_name | NFS アクション | エクスポートポリシー（デフォルト: "default"） |
| reason | いいえ | 人間が読める理由（ログに記録） |

---

## 連携例

### 重大度ベースのルーティング（重要 — 誤検知によるロックアウト防止）

ARP は 2 つの重大度レベルでイベントを発火します。**`alert`（高信頼）の場合のみ自動ブロック**:

| ARP 重大度 | 信頼度 | 推奨アクション | 根拠 |
|-----------|--------|-------------|------|
| `alert` | 高（ファイル改ざん + 暗号化確認済み） | ✅ 自動封じ込め (`contain_smb_threat`) | 高信頼度、被害進行中 |
| `warning` | 中（疑わしいが未確認） | ⚠️ 通知のみ（自動ブロック禁止） | 学習期間中の誤検知の可能性 |

> **ARP 学習期間**: ARP は行動ベースラインの構築に 30 日を要します。この期間中、`warning` イベントは頻発し多くは良性です（大量ファイル変換、バックアップソフトウェア）。学習期間中に `warning` で自動ブロックすると正当なユーザーを妨害します。

**検知ルール設定例（Datadog Monitor）**:
```
# 自動封じ込め: severity=alert のみ
source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.severity:alert
→ トリガー: contain_smb_threat via SNS

# 通知のみ: severity=warning
source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.severity:warning
→ トリガー: Slack/PagerDuty 通知（調査のみ）
```

### 例 1: CloudWatch Log Alarm → 自動ブロック

管理監査ログで 5 分以内にログイン失敗が 10 回以上検知された場合:

```
CloudWatch Log Alarm (クエリ: ログイン失敗 > 10)
  → SNS (Trigger Topic)
  → Lambda
  → ONTAP: block_smb_user + create_snapshot
  → SNS 通知 → セキュリティチーム
```

### 例 2: Datadog ARP Monitor → 全面封じ込め

Datadog が ARP EMS イベントを受信しモニターが発火:

```
ONTAP ARP → EMS Webhook → Datadog
  → Datadog Monitor 発火
  → Workflow → SNS publish (contain_smb_threat)
  → Lambda → ONTAP: snapshot + block + disconnect
  → PagerDuty エスカレーション
```

### 例 3: FPolicy 大量削除 → IP ブロック

FPolicy 分析で単一 IP から 5 分以内に 50 回以上の削除を検知:

```
FPolicy → SQS → Lambda → Datadog/Elastic
  → SIEM ルール発火（大量削除閾値）
  → SNS publish (contain_nfs_threat)
  → Lambda → ONTAP: snapshot + IP ブロック
```

---

## 運用手順

### ブロック済みユーザー/IP の確認

```bash
# FSx for ONTAP 管理エンドポイントに SSH
ssh fsxadmin@<management-ip>

# ブロック済み SMB ユーザー（空の replacement を持つ name-mapping）
vserver name-mapping show -direction win-unix -replacement " "

# ブロック済み NFS IP（マーカー付きルール）
export-policy rule show -clientmatch *fsxn_auto_response*
```

### 手動解除

SNS メッセージ経由:
```bash
aws sns publish \
  --topic-arn <TriggerTopicArn> \
  --message '{"action":"unblock_smb_user","svm_name":"svm-prod-01","domain":"CORP","username":"jdoe"}'
```

ONTAP CLI 経由（緊急時）:
```bash
# SMB ユーザーのブロック解除
vserver name-mapping delete -direction win-unix -position <position>

# NFS IP のブロック解除
export-policy rule delete -vserver <svm> -policyname <policy> -ruleindex <index>
```

### 監視

| メトリクス | ソース | アラート閾値 |
|-----------|--------|------------|
| DLQ 深度 | CloudWatch（自動作成アラーム） | > 0 メッセージ |
| Lambda エラー | CloudWatch Lambda メトリクス | 5 分で > 0 |
| 応答レイテンシ | Lambda Duration メトリクス | p95 > 10s |
| アクティブブロック数 | カスタムメトリクス（オプション） | トラッキングのみ |

---

## セキュリティ考慮事項

- **最小権限**: Lambda ロールは Secrets Manager（読取）、SNS（発行）、ONTAP への VPC ネットワークアクセスのみ。広範な IAM 権限なし。
- **認証情報ローテーション**: Secrets Manager の自動ローテーションを ONTAP 認証情報に使用。
- **監査証跡**: 全アクションは CloudWatch Logs に相関 ID 付きで記録。
- **クールダウン保護**: Snapshot 作成に設定可能なクールダウン（デフォルト 15 分）を適用し、持続的攻撃時のストレージ枯渇を防止。
- **マーカーベースのクリーンアップ**: 全応答ルールに `fsxn_auto_response` マーカーを含め、安全な識別と一括削除を実現。
- **時間制限付きブロック**: 設定可能な期間後にブロックを自動解除するスケジュール Lambda の実装を推奨（専用製品の時間制限付きアクセス制限と同等）。

---

## コスト見積もり

| コンポーネント | 月額（一般的） | 備考 |
|-------------|-------------|------|
| Lambda | ~$0.10 | 月 100 回未満の実行（インシデント対応のみ） |
| SNS | ~$0.01 | 低メッセージ量 |
| Secrets Manager | ~$0.40 | 1 シークレット |
| VPC ENI | $0（Lambda VPC） | 既存 VPC と共有 |
| **合計** | **~$0.51/月** | VPC/NAT コスト除外（共有） |

---

## 関連ドキュメント

- [ARP インシデント対応ガイド](arp-incident-response-guide.md)
- [EMS Webhook セットアップ](../integrations/datadog/docs/ja/ems-webhook-setup.md)
- [FPolicy 運用ノート](operational-notes-fpolicy.md)
- [パイプライン SLO](pipeline-slo.md)
- [CloudWatch Log Alarm ガイド](syslog-vpce-setup-guide.md)

---

## トラブルシューティング

### Lambda 実行の失敗

| 症状 | 原因 | 解決策 |
|------|------|--------|
| Lambda タイムアウト (60s) | ONTAP 管理エンドポイント到達不可 | Security Group ルール（TCP 443 アウトバウンド）確認、ONTAP 管理 LIF のステータス確認 |
| ONTAP から HTTP 401 | 認証情報が期限切れまたは不正 | Secrets Manager のシークレット値を確認、fsxadmin パスワードを検証 |
| ONTAP から HTTP 403 | 権限不足 | fsxadmin ロールが必要な API アクセスを持つか確認（デフォルト: フル） |
| `SVM not found` エラー | SVM 名の不一致 | SVM 名が正確に一致するか確認（大文字小文字区別）。`vserver show` で一覧 |
| `Volume not found` エラー | ボリュームが存在しないか SVM が違う | ボリューム名と SVM の関連付けを確認 |
| DLQ メッセージの蓄積 | 繰り返しの失敗 | Lambda CloudWatch Logs で根本原因を確認、DLQ からリプレイ |

### ブロックが効かない

| 症状 | 原因 | 解決策 |
|------|------|--------|
| ブロック後も SMB ユーザーがアクセス可能 | 既存セッションがアクティブ | `contain_smb_threat`（セッション切断含む）を使用するか、セッションタイムアウトを待つ |
| ブロック後も NFS クライアントがアクセス可能 | NFS 属性キャッシュ | 60 秒待つ（デフォルト `actimeo`）か、テスト時は `mount -o actimeo=0` で再マウント |
| ブロック存在するが ONTAP にエントリなし | SVM が違う | SNS メッセージの SVM 名がターゲット SVM と一致するか確認 |

### TTL 自動解除の問題

| 症状 | 原因 | 解決策 |
|------|------|--------|
| ブロックが削除されない | EventBridge Scheduler が実行されていない | EventBridge コンソールでスケジューラー状態を確認 |
| 全ブロックが早期に削除される | TTL Lambda が全レスポンスマーカー付きブロックを削除 | 下記「TTL の制限事項」参照 |
| クリーンアップ Lambda エラー | TTL Lambda から ONTAP に到達不可 | メイン Lambda と同じ VPC/SG 要件 |

> **TTL の制限事項**: 現在の TTL 実装は、各実行時に `fsxn_auto_response` マーカーを持つ ALL ブロックを作成時刻に関係なく削除します。ONTAP の name-mapping エントリは作成タイムスタンプを持ちません。正確な時間ベースの TTL 実施には、ブロック作成時刻を記録する DynamoDB テーブルを実装し、TTL Lambda がそのテーブルを確認してから削除する必要があります。将来の拡張として追跡中です。

---

## FAQ

**Q: これは DII Storage Workload Security を完全に置き換えますか？**
A: 同じ *封じ込めアクション*（ブロック/Snapshot/切断）を提供します。検知インテリジェンスは異なります: DII は内蔵のユーザー別 ML ベースラインを使用し、本アプローチは顧客が選択した SIEM の分析機能を使用します。既存の SIEM 投資がある組織では、組み合わせアプローチにより、ストレージ単体の検知よりも広い文脈（ネットワーク + アプリケーション + ストレージ）を提供できます。

**Q: Lambda が ONTAP に到達できない場合はどうなりますか？**
A: 実行が失敗し、メッセージが DLQ に入り、DLQ アラームが発火します。ネットワーク接続性（Security Group、ルートテーブル、ONTAP 管理 LIF の状態）を調査してください。

**Q: 複数の SVM で同時にユーザーをブロックできますか？**
A: SVM ごとに 1 つの SNS メッセージを送信してください。複合アクションは 1 回の実行で単一 SVM を対象とします。マルチ SVM ブロックには、以下の Step Functions ファンアウトパターンまたは CLI ループを使用:

```
EventBridge / SIEM Alert
  -> Step Functions (fan-out)
       -> Parallel state:
            Branch 1: SNS publish (svm-prod-01, contain_smb_threat)
            Branch 2: SNS publish (svm-prod-02, contain_smb_threat)
            Branch 3: SNS publish (svm-dr-01, contain_smb_threat)
       -> Wait for all branches
       -> Notify: "3 SVM でユーザーをブロック"
```

CLI ヘルパーでのループ:
```bash
for SVM in svm-prod-01 svm-prod-02 svm-dr-01; do
  ./shared/scripts/automated-response-cli.sh contain-smb \
    --svm "$SVM" --domain CORP --user jdoe \
    --volume vol_data --reason "ARP detection - multi-SVM block"
done
```

**Q: ブロックはどのくらいの速さで有効になりますか？**
A: SMB name-mapping ブロックは新しい接続に対して即時有効です。既存セッションは切断されるまでアクティブのままです（`contain_smb_threat` アクションがこれを処理します）。NFS export-policy ルールは新しいマウントに対して即時有効ですが、既存マウントはキャッシュの有効期限切れが必要な場合があります。

**Q: 正当なユーザーをブロックしてしまうリスクはありますか？**
A: はい — これは全ての自動応答システムに共通です。対策: (1) 検知閾値を保守的に設定、(2) 通知トピックでオペレーターに即時通知、(3) 自動解除付きの時間制限ブロックの実装、(4) 迅速な手動解除の手順書を整備。
