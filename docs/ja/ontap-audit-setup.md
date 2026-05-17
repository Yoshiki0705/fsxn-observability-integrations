# ONTAP 監査設定ガイド

本ガイドでは、Amazon FSx for NetApp ONTAP における ONTAP ファイルアクセス監査の完全なセットアップ手順を説明します。監査ボリュームの作成、監査設定、ログローテーション、検証までをカバーします。

> **参考**: [AWS ドキュメント — ファイルアクセス監査](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/file-access-auditing.html)

## 前提条件

- SVM が 1 つ以上存在する FSx for ONTAP ファイルシステム
- `fsxadmin` 認証情報による ONTAP CLI アクセス
- 監査ログ用の十分なストレージ容量

## 監査ボリュームの作成

監査ログファイルを保存するための専用ボリュームを作成します。本番ワークロードから監査データを分離し、容量管理を簡素化するために、専用ボリュームの使用を推奨します。

```bash
# Create audit volume on the SVM's aggregate
vol create -vserver svm-prod-01 -volume audit_logs -aggregate aggr1 \
  -size 50GB -state online -type RW -security-style ntfs \
  -snapshot-policy none -tiering-policy none
```

### ジャンクションパスの設定

SVM からアクセス可能なジャンクションパスに監査ボリュームをマウントします：

```bash
# Create junction path for the audit volume
vol mount -vserver svm-prod-01 -volume audit_logs -junction-path /audit
```

> **注意**: 監査を有効化する前にジャンクションパスが存在している必要があります。ONTAP はこのパスに監査ログを書き込みます。

## 監査設定

### 監査設定の作成

`vserver audit create` を使用して SVM の監査ポリシーを定義します：

```bash
# Create audit configuration with EVTX format and time-based rotation
vserver audit create -vserver svm-prod-01 \
  -events file-ops \
  -format evtx \
  -destination /audit \
  -rotate-schedule-month - \
  -rotate-schedule-dayofweek - \
  -rotate-schedule-day - \
  -rotate-schedule-hour 0,6,12,18 \
  -rotate-schedule-minute 0
```

### 監査の有効化と管理

```bash
# Enable auditing on the SVM
vserver audit enable -vserver svm-prod-01

# Verify audit configuration
vserver audit show -vserver svm-prod-01 -instance

# Disable auditing (if needed)
vserver audit disable -vserver svm-prod-01
```

## EVTX vs XML フォーマット選択

環境と統合要件に基づいてログフォーマットを選択します：

| Criteria | EVTX | XML |
|----------|------|-----|
| Protocol support | SMB + NFS | SMB + NFS |
| File size | Smaller (binary) | Larger (text) |
| Parsing complexity | Requires EVTX parser | Standard XML parser |
| Windows Event Viewer | Compatible | Not compatible |
| Programmatic processing | Needs specialized library | Any XML library |
| FSx S3 Access Point retrieval | Supported | Supported |
| Recommended for | Windows-centric environments | Programmatic log pipelines |

### 選択ガイドライン

- **EVTX を選択する場合**: Windows Event Viewer との互換性が必要、ストレージ効率を重視、または既存ツールが EVTX パースに対応している場合。
- **XML を選択する場合**: プログラムによるパースの簡便さを重視、テキストベースのログパイプラインとの統合、またはバイナリフォーマットへの依存を避けたい場合。

> **本プロジェクトでの注意**: `shared/lambda-layers/log-parser/` は EVTX と XML の両フォーマットに対応しています。運用上の好みに応じて選択してください。

## ログローテーション設計

### 時間ベースのローテーション

時間ベースのローテーションは、ファイルサイズに関係なく、スケジュールされた間隔で新しいログファイルを作成します：

```bash
# Rotate every 6 hours
vserver audit create -vserver svm-prod-01 \
  -events file-ops \
  -format evtx \
  -destination /audit \
  -rotate-schedule-month - \
  -rotate-schedule-dayofweek - \
  -rotate-schedule-day - \
  -rotate-schedule-hour 0,6,12,18 \
  -rotate-schedule-minute 0
```

### サイズベースのローテーション

サイズベースのローテーションは、アクティブログが指定サイズに達した時に新しいログファイルを作成します：

```bash
# Rotate when log file reaches 100MB
vserver audit create -vserver svm-prod-01 \
  -events file-ops \
  -format evtx \
  -destination /audit \
  -rotate-size 100MB
```

### ローテーション戦略の比較

| Strategy | Use Case | Pros | Cons |
|----------|----------|------|------|
| Time-based | Predictable processing schedules | Consistent file creation timing | File sizes vary |
| Size-based | High-volume environments | Consistent file sizes | Unpredictable timing |
| Combined | Production environments | Balanced approach | More complex configuration |

### 推奨設定

EventBridge Scheduler ベースのログ処理（本プロジェクトのパターン）との統合に適した設定：

- **1〜6 時間ごとの時間ベースローテーション**がスケジュールされた Lambda 呼び出しと整合します
- 予測可能な間隔でローテーション済みファイルが処理可能になります
- Lambda スケジュール間隔より短いローテーション間隔は避けてください

## 監査ボリュームのサイジングガイドライン

環境のファイル操作量に基づいて監査ボリュームサイズを見積もります：

| Environment | Daily File Ops | Estimated Daily Log Size | Recommended Volume |
|-------------|---------------|--------------------------|-------------------|
| Small (< 50 users) | ~10,000 | ~50 MB | 10 GB |
| Medium (50–500 users) | ~100,000 | ~500 MB | 50 GB |
| Large (500+ users) | ~1,000,000+ | ~5 GB+ | 200 GB+ |

### サイジングの考慮事項

- EVTX フォーマットは同じイベントに対して XML より約 30〜50% 小さくなります
- クリーンアップ前に少なくとも 7 日分のローテーション済みログを保持してください
- バースト活動（月末処理、マイグレーション）を考慮してください
- ONTAP の `vol show -fields used` でボリューム使用率を監視してください

```bash
# Check audit volume usage
vol show -vserver svm-prod-01 -volume audit_logs -fields size,used,available
```

## SMB 向け SACL 設定

システムアクセス制御リスト（SACL）は、SMB アクセスに対してどのファイル操作が監査イベントを生成するかを定義します。SACL は Windows セキュリティツールを使用して個々のファイルまたはディレクトリに設定します。

### SACL の設定

```powershell
# PowerShell: Set audit SACL on a shared folder
$acl = Get-Acl "\\fsxn-server\share\sensitive-data"
$auditRule = New-Object System.Security.AccessControl.FileSystemAuditRule(
    "Everyone",
    "Read,Write,Delete",
    "ContainerInherit,ObjectInherit",
    "None",
    "Success,Failure"
)
$acl.AddAuditRule($auditRule)
Set-Acl "\\fsxn-server\share\sensitive-data" $acl
```

### SACL のベストプラクティス

| Recommendation | Rationale |
|---------------|-----------|
| Audit specific folders, not entire volumes | Reduces log volume and noise |
| Focus on `Write` and `Delete` operations | Most relevant for security monitoring |
| Include both `Success` and `Failure` | Failure events indicate unauthorized access attempts |
| Use group-based rules | Easier to manage than per-user rules |

## NFS 向け NFSv4 ACL 監査フラグ

NFS ファイルアクセス監査では、ONTAP は NFSv4 ACL 監査フラグ（SACL 相当のフラグ）を使用して、どの操作を監査するかを決定します。

### NFSv4 監査フラグの設定

```bash
# Set audit flags on a directory using nfs4_setfacl
nfs4_setfacl -a "A:fdS:EVERYONE@:rwaxtTnNcCoy" /mnt/fsxn/audit-target/

# Verify audit flags
nfs4_getfacl /mnt/fsxn/audit-target/
```

### NFSv4 監査フラグリファレンス

| Flag | Meaning | Audited Operation |
|------|---------|-------------------|
| `S` | Successful access | Audit successful operations |
| `F` | Failed access | Audit failed operations |
| `r` | Read data | File read operations |
| `w` | Write data | File write operations |
| `a` | Append data | File append operations |
| `x` | Execute | File execution |
| `d` | Delete | File/directory deletion |
| `D` | Delete child | Delete items within directory |

## アクティブログファイル vs ローテーション済みログファイルの動作

アクティブログファイルとローテーション済みログファイルの違いを理解することは、ログ処理パイプラインにとって重要です。

### アクティブログファイル

- ファイル名: `audit.evtx` または `audit.xml`（タイムスタンプサフィックスなし）
- ONTAP によって書き込み中
- **アクティブログファイルを処理しないでください** — 不完全またはロックされている可能性があります
- 配置場所: `/audit/audit.evtx`

### ローテーション済みログファイル

- ファイル名にタイムスタンプを含む: `audit_<timestamp>.evtx`
- 完了してクローズ済み — 処理可能
- ローテーショントリガー（時間またはサイズ閾値）で作成
- 配置場所: `/audit/audit_20260115120000.evtx`

```bash
# List rotated audit log files
vol file show -vserver svm-prod-01 -volume audit_logs -path /audit/audit_*.evtx
```

### 処理上の影響

| Aspect | Active Log | Rotated Log |
|--------|-----------|-------------|
| Status | Being written | Closed/complete |
| Safe to read | No | Yes |
| File name pattern | `audit.evtx` | `audit_<timestamp>.evtx` |
| Lambda processing | Skip | Process |
| S3 AP visibility | Visible but incomplete | Visible and complete |

> **設計ルール**: 本プロジェクトの Lambda ログプロセッサは、ローテーション済みファイル（`audit_*.evtx` または `audit_*.xml` パターンに一致するファイル）のみを読み取ります。アクティブログファイルは常にスキップされます。

## 監査ボリューム満杯時の動作

監査ボリュームが容量に達した場合、ONTAP の動作は `rotate-limit` とボリューム設定に依存します：

### デフォルトの動作

1. ONTAP はアクティブログファイルのローテーションを試みます
2. 容量不足でローテーションが失敗した場合、**最も古いローテーション済みログファイルが削除**されます
3. 削除可能なローテーション済みファイルがない場合、**監査が停止**しイベントが失われます

### 緩和策

```bash
# Set rotation limit to control maximum number of rotated files
vserver audit modify -vserver svm-prod-01 -rotate-limit 100

# Enable volume autogrow
vol autosize -vserver svm-prod-01 -volume audit_logs \
  -mode grow -maximum-size 200GB -grow-threshold-percent 85
```

| Strategy | Configuration | Trade-off |
|----------|--------------|-----------|
| Rotation limit | `-rotate-limit 100` | Oldest logs auto-deleted |
| Volume autogrow | `vol autosize -mode grow` | Uses more storage |
| External cleanup | Lambda-based cleanup | Requires additional automation |
| Monitoring alerts | CloudWatch on volume usage | Reactive, not preventive |

> **推奨**: ボリュームの自動拡張とローテーション制限を組み合わせてください。ボリューム使用率を監視し、80% でアラートを設定してください。

## 検証

### ローテーション済みファイルの存在確認

監査を有効化し、最初のローテーション間隔を待った後、ローテーション済みログファイルが作成されていることを確認します：

```bash
# SSH to FSx ONTAP CLI and list audit files
vserver audit show -vserver svm-prod-01 -instance

# List files in the audit volume
vol file show -vserver svm-prod-01 -volume audit_logs -path /

# Check for rotated files (should see timestamped files)
vol file show -vserver svm-prod-01 -volume audit_logs -path /audit_*.evtx
```

期待される出力には以下のようなファイルが表示されます：
- `audit.evtx`（アクティブログ）
- `audit_20260115000000.evtx`（ローテーション済み）
- `audit_20260115060000.evtx`（ローテーション済み）

### FSx S3 Access Point 経由でのファイル可視性確認

監査ログファイルが FSx for ONTAP S3 Access Point 経由でアクセス可能であることを確認します：

```bash
# List objects via S3 Access Point
aws s3api list-objects-v2 \
  --bucket arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --prefix "svm-prod-01/audit/" \
  --region ap-northeast-1

# Download a rotated file to verify content
aws s3api get-object \
  --bucket arn:aws:s3:ap-northeast-1:123456789012:accesspoint/fsxn-audit-ap \
  --key "svm-prod-01/audit/audit_20260115000000.evtx" \
  --region ap-northeast-1 \
  /tmp/test-audit.evtx

# Verify file is valid EVTX (check magic bytes)
xxd /tmp/test-audit.evtx | head -1
# Expected: 456c 6646 696c 6500 (ElfFile\0)
```

> **トラブルシューティング**: S3 Access Point 経由でファイルが表示されない場合、以下を確認してください：
> 1. S3 Access Point が正しい SVM に設定されていること
> 2. ジャンクションパスが監査先と一致していること
> 3. IAM 権限に Access Point ARN に対する `s3:GetObject` が含まれていること
> 4. ネットワーク接続性（VPC 外の Lambda、または VPC 内の場合は NAT Gateway）

## まとめ

| Step | Command / Action | Verification |
|------|-----------------|--------------|
| 1. Create volume | `vol create` | `vol show` |
| 2. Mount volume | `vol mount` | `vol show -junction-path` |
| 3. Create audit config | `vserver audit create` | `vserver audit show` |
| 4. Enable auditing | `vserver audit enable` | `vserver audit show -state` |
| 5. Configure SACLs/ACLs | Windows SACL or NFSv4 flags | Test file access |
| 6. Verify rotation | Wait for interval | `vol file show` |
| 7. Verify S3 AP access | `aws s3api list-objects-v2` | Files listed |
