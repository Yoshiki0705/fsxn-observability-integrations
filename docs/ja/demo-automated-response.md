# 自動応答デモ手順書

## 目的

自動インシデント対応機能のエンドツーエンドデモ手順書。カバー範囲: デプロイ → 検知トリガー → 自動ブロック確認 → アクセス拒否確認 → ブロック解除 → アクセス復元確認。

用途:
- お客様デモ（ライブまたは録画）
- ブログ公開前の E2E 検証
- 内部トレーニング

---

## 前提条件

| 項目 | 要件 |
|------|------|
| FSx for ONTAP | 稼働中、少なくとも 1 ボリュームで ARP 有効 |
| VPC アクセス | Lambda サブネットが ONTAP 管理 IP に到達可能（TCP 443） |
| ONTAP 認証情報 | `fsxadmin` ユーザー名/パスワードが Secrets Manager に保存済み |
| SMB クライアント | CIFS 経由で SVM にマウント済みの Windows または Linux ホスト |
| NFS クライアント | NFS 経由で SVM にマウント済みの Linux ホスト |
| AWS CLI | 適切な IAM 権限で設定済み |
| jq | JSON フォーマット用にインストール済み |

---

## Phase 1: 自動応答スタックのデプロイ

### ステップ 1.1: CloudFormation デプロイ

```bash
aws cloudformation deploy \
  --template-file shared/templates/automated-response.yaml \
  --stack-name fsxn-automated-response \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=<secret-arn> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    DefaultSvmName=<svm-name> \
    NotificationEmail=<your-email> \
  --capabilities CAPABILITY_NAMED_IAM
```

### ステップ 1.2: スタック出力の確認

```bash
aws cloudformation describe-stacks \
  --stack-name fsxn-automated-response \
  --query 'Stacks[0].Outputs' \
  --output table
```

📸 **スクリーンショット 1**: CloudFormation スタック出力（TriggerTopicArn と NotificationTopicArn）

### ステップ 1.3: CLI 環境変数の設定

```bash
export RESPONSE_TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name fsxn-automated-response \
  --query 'Stacks[0].Outputs[?OutputKey==`TriggerTopicArn`].OutputValue' \
  --output text)

export DEFAULT_SVM="<svm-name>"
echo "Topic: $RESPONSE_TOPIC_ARN"
```

---

## Phase 2: SMB ユーザーブロックのデモ

### ステップ 2.1: 現在のアクセス確認（ブロック前）

SMB クライアントから正常アクセスを確認:

```bash
# SMB クライアント上（テストユーザーとして）
ls //fsxn-share/test-data/
cat //fsxn-share/test-data/sample-file.txt
echo "write test" > //fsxn-share/test-data/write-test.txt
```

📸 **スクリーンショット 2**: テストユーザーによるファイル操作成功（ls, read, write）

### ステップ 2.2: SMB ユーザーブロックのトリガー

```bash
./shared/scripts/automated-response-cli.sh block-smb \
  --domain <DOMAIN> --user <test-user> \
  --reason "デモ: 内部脅威シミュレーション"
```

📸 **スクリーンショット 3**: CLI 出力（SNS publish 成功、MessageId 返却）

### ステップ 2.3: Lambda 実行の確認

```bash
sleep 15

aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-automated-response-handler \
  --start-time $(date -v-2M +%s000 2>/dev/null || date -d '2 minutes ago' +%s000) \
  --filter-pattern "block_smb_user" \
  --query 'events[*].message' \
  --output text | tail -5
```

📸 **スクリーンショット 4**: CloudWatch Logs に "Blocking SMB user" ログ行

### ステップ 2.4: ONTAP でのブロック確認

```bash
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
```

📸 **スクリーンショット 5**: ONTAP CLI の name-mapping エントリ（DOMAIN\\user → " "）

### ステップ 2.5: アクセス拒否の確認（ブロック後）

```bash
# SMB クライアント上（ブロックされたテストユーザーとして）
ls //fsxn-share/test-data/
# → 期待: Permission denied / Access denied
```

📸 **スクリーンショット 6**: ブロックされたユーザーの "Permission denied" 表示

### ステップ 2.6: ユーザーのブロック解除

```bash
./shared/scripts/automated-response-cli.sh unblock-smb \
  --domain <DOMAIN> --user <test-user>
```

### ステップ 2.7: アクセス復元の確認

```bash
# SMB クライアント上（再接続が必要な場合あり）
ls //fsxn-share/test-data/
# → 期待: 成功
```

📸 **スクリーンショット 7**: ブロック解除後のアクセス復元

---

## Phase 3: NFS IP ブロックのデモ

### ステップ 3.1: 現在の NFS アクセス確認

```bash
ls /mnt/fsxn/test-data/
touch /mnt/fsxn/test-data/nfs-write-test.txt
```

📸 **スクリーンショット 8**: NFS ファイル操作成功

### ステップ 3.2: NFS IP ブロックのトリガー

```bash
CLIENT_IP=$(hostname -I | awk '{print $1}')
echo "Blocking IP: $CLIENT_IP"

./shared/scripts/automated-response-cli.sh block-nfs \
  --ip "$CLIENT_IP" \
  --reason "デモ: 不審 IP からの大量削除シミュレーション"
```

📸 **スクリーンショット 9**: NFS IP ブロック publish 成功

### ステップ 3.3: ONTAP でのブロック確認

```bash
ssh fsxadmin@<management-ip> "export-policy rule show -clientmatch *fsxn_auto_response*"
```

📸 **スクリーンショット 10**: ONTAP の export-policy ルール（fsxn_auto_response マーカー付き）

### ステップ 3.4: NFS アクセス拒否の確認

```bash
# NFS クライアント上（再マウントが必要な場合あり）
umount /mnt/fsxn && mount -t nfs <svm-nfs-lif>:/vol_data /mnt/fsxn
ls /mnt/fsxn/test-data/
# → 期待: Permission denied またはマウント失敗
```

> **NFS キャッシュに関する注記**: Linux NFS クライアントはアクセス判定を最大 60 秒間キャッシュします（`actimeo` デフォルト値）。ブロック後、拒否が即座に効くまで最大 60 秒待つか、テスト時は `mount -o actimeo=0` で再マウントしてください。

📸 **スクリーンショット 11**: IP ブロック後の NFS アクセス拒否

### ステップ 3.5: IP ブロック解除

```bash
./shared/scripts/automated-response-cli.sh unblock-nfs --ip "$CLIENT_IP"
```

---

## Phase 4: 全面封じ込めのデモ（ARP → 自動ブロック）

### ステップ 4.1: ARP アクティブ状態の確認

```bash
ssh fsxadmin@<management-ip> "security anti-ransomware volume show -vserver $DEFAULT_SVM"
```

📸 **スクリーンショット 12**: ONTAP で ARP が "active" 状態

### ステップ 4.2: ランサムウェアシミュレーション（テスト環境のみ）

```bash
# 注意: テスト環境の廃棄可能データでのみ実行
ssh fsxadmin@<management-ip> \
  "security anti-ransomware volume attack simulate -vserver $DEFAULT_SVM -volume <test-vol>"
```

📸 **スクリーンショット 13**: ONTAP CLI の ARP 攻撃シミュレーションコマンド

### ステップ 4.3: 検知チェーンの観察

EMS イベント配信まで ~30 秒待機:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-ems-fpolicy-handler \
  --start-time $(date -v-2M +%s000 2>/dev/null || date -d '2 minutes ago' +%s000) \
  --filter-pattern "arw.volume.state" \
  --query 'events[*].message' --output text
```

📸 **スクリーンショット 14**: Lambda ログの `arw.volume.state` EMS イベント受信

### ステップ 4.4: 全面封じ込めトリガー

```bash
./shared/scripts/automated-response-cli.sh contain-smb \
  --domain <DOMAIN> --user <suspect-user> \
  --volume <test-vol> \
  --reason "ARP 検知 - arw.volume.state alert"
```

### ステップ 4.5: 封じ込め結果の確認

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-automated-response-handler \
  --start-time $(date -v-2M +%s000 2>/dev/null || date -d '2 minutes ago' +%s000) \
  --filter-pattern "contain_smb_threat" \
  --query 'events[*].message' --output text
```

📸 **スクリーンショット 15**: Lambda ログの 3 つの封じ込めステップ（snapshot + block + disconnect）

### ステップ 4.6: Snapshot 作成の確認

```bash
ssh fsxadmin@<management-ip> \
  "volume snapshot show -vserver $DEFAULT_SVM -volume <test-vol> -snapshot incident_response_*"
```

📸 **スクリーンショット 16**: ONTAP の incident_response snapshot（タイムスタンプ付き）

### ステップ 4.7: SNS 通知の受信確認

📸 **スクリーンショット 17**: メール通知の封じ込め結果 JSON

---

## Phase 5: TTL 自動解除のデモ

### ステップ 5.1: TTL スタックのデプロイ

```bash
aws cloudformation deploy \
  --template-file shared/templates/automated-response-ttl.yaml \
  --stack-name fsxn-automated-response-ttl \
  --parameter-overrides \
    OntapMgmtIp=<management-ip> \
    OntapCredentialsSecretArn=<secret-arn> \
    VpcId=<vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2> \
    SecurityGroupId=<sg-id> \
    DefaultSvmName=$DEFAULT_SVM \
    BlockTtlMinutes=5 \
    CheckIntervalMinutes=1 \
    NotificationTopicArn=<notification-topic-arn> \
  --capabilities CAPABILITY_NAMED_IAM
```

### ステップ 5.2: ブロック作成

```bash
./shared/scripts/automated-response-cli.sh block-smb \
  --domain <DOMAIN> --user <test-user> \
  --reason "TTL デモ - 5 分後に自動解除"
```

### ステップ 5.3: TTL 失効待ち

```bash
echo "ブロック作成完了。TTL クリーンアップ Lambda は 1 分ごとに実行。"
echo "ブロックは約 5 分以内に自動解除されます。"
echo "CloudWatch Logs を監視（7 分でタイムアウト）..."

# クリーンアップ Lambda を監視（無限に待たないようタイムアウト付き）
timeout 420 aws logs tail /aws/lambda/fsxn-automated-response-ttl-cleanup --follow
# タイムアウトしても削除メッセージが見えない場合、Lambda エラーを確認:
# aws logs filter-log-events --log-group-name /aws/lambda/fsxn-automated-response-ttl-cleanup --filter-pattern "ERROR"
```

> **注記**: TTL クリーンアップは現在、各実行時に `fsxn_auto_response` マーカーを持つ全ブロックを削除します。個別のブロック作成時刻は追跡しません。本番環境では DynamoDB による追跡テーブルの実装を検討してください。

📸 **スクリーンショット 18**: CloudWatch Logs の "TTL expired — removed SMB block" メッセージ

### ステップ 5.4: 自動解除の確認

```bash
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
# → 期待: エントリなし（ブロックが TTL により自動削除）
```

📸 **スクリーンショット 19**: ONTAP の空の name-mapping（TTL によりブロック自動解除）

---

## Phase 6: アクティブブロック一覧（運用可視化）

```bash
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
ssh fsxadmin@<management-ip> "export-policy rule show -clientmatch *fsxn_auto_response*"
```

📸 **スクリーンショット 20**: 現在のアクティブブロック状態（またはクリア済みの場合は空）

---

## スクリーンショット一覧

| # | 内容 | ファイル名 | フェーズ |
|---|------|----------|---------|
| 1 | CloudFormation スタック出力 | `01-cfn-stack-outputs.png` | デプロイ |
| 2 | SMB アクセス成功（ブロック前） | `02-smb-access-before.png` | SMB ブロック |
| 3 | SNS publish 成功（MessageId） | `03-sns-publish-block-smb.png` | SMB ブロック |
| 4 | Lambda ログ: "Blocking SMB user" | `04-lambda-log-block-smb.png` | SMB ブロック |
| 5 | ONTAP name-mapping エントリ | `05-ontap-name-mapping-blocked.png` | SMB ブロック |
| 6 | SMB アクセス拒否（ブロック後） | `06-smb-access-denied.png` | SMB ブロック |
| 7 | SMB アクセス復元（ブロック解除後） | `07-smb-access-restored.png` | SMB ブロック |
| 8 | NFS アクセス成功（ブロック前） | `08-nfs-access-before.png` | NFS ブロック |
| 9 | SNS publish 成功（NFS ブロック） | `09-sns-publish-block-nfs.png` | NFS ブロック |
| 10 | ONTAP export-policy ルール（マーカー付き） | `10-ontap-export-policy-blocked.png` | NFS ブロック |
| 11 | NFS アクセス拒否（ブロック後） | `11-nfs-access-denied.png` | NFS ブロック |
| 12 | ONTAP ARP アクティブ状態 | `12-ontap-arp-active.png` | 全面封じ込め |
| 13 | ARP 攻撃シミュレーションコマンド | `13-ontap-arp-simulate.png` | 全面封じ込め |
| 14 | Lambda ログ: arw.volume.state 受信 | `14-lambda-ems-arp-event.png` | 全面封じ込め |
| 15 | Lambda ログ: contain_smb_threat ステップ | `15-lambda-containment-steps.png` | 全面封じ込め |
| 16 | ONTAP incident_response snapshot | `16-ontap-incident-snapshot.png` | 全面封じ込め |
| 17 | メール通知（封じ込め結果） | `17-email-notification-containment.png` | 全面封じ込め |
| 18 | Lambda ログ: TTL expired auto-remove | `18-lambda-ttl-cleanup.png` | TTL |
| 19 | ONTAP 空の name-mapping（自動クリア） | `19-ontap-ttl-cleared.png` | TTL |
| 20 | ONTAP アクティブブロック一覧 | `20-ontap-active-blocks-status.png` | 運用 |

---

## 所要時間の目安

| フェーズ | 所要時間 | 備考 |
|---------|---------|------|
| Phase 1（デプロイ） | ~5 分 | CloudFormation デプロイ |
| Phase 2（SMB ブロック） | ~3 分 | ブロック + 確認 + 解除 |
| Phase 3（NFS ブロック） | ~3 分 | ブロック + 確認 + 解除 |
| Phase 4（全面封じ込め） | ~5 分 | ARP シミュレート + 封じ込め |
| Phase 5（TTL） | ~7 分 | デプロイ + TTL 失効待ち |
| Phase 6（運用確認） | ~1 分 | 状態チェック |
| **合計** | **~24 分** | 全フェーズ実行 |

短縮版デモ（お客様ミーティング用）: Phase 1 + Phase 2 + Phase 4 = ~13 分。

---

## クリーンアップ

```bash
# テストブロックの全削除
ssh fsxadmin@<management-ip> "vserver name-mapping show -direction win-unix -replacement \" \""
# 残っているエントリを手動削除

# テスト Snapshot の削除
ssh fsxadmin@<management-ip> "volume snapshot delete -vserver $DEFAULT_SVM -volume <test-vol> -snapshot incident_response_*"

# CloudFormation スタック削除（オプション）
aws cloudformation delete-stack --stack-name fsxn-automated-response-ttl
aws cloudformation delete-stack --stack-name fsxn-automated-response
```

---

## 関連ドキュメント

- [自動応答ガイド](automated-response-guide.md)
- [ARP インシデント対応ガイド](arp-incident-response-guide.md)
- [EMS 検知機能リファレンス](ems-detection-capabilities.md)
- [デモシナリオ（全ベンダー）](demo-scenarios.md)
- [CLI ヘルパー](../../shared/scripts/automated-response-cli.sh)
