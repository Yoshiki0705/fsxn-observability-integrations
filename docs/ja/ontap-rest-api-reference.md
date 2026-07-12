# ONTAP REST API クイックリファレンス (FSx for ONTAP)

🌐 **日本語**（このページ） | [English](../en/ontap-rest-api-reference.md)

## 概要

本プロジェクトでは ONTAP REST API を以下の目的で使用しています:
- FPolicy 設定（エンジン、イベント、ポリシーの作成）
- 自動応答アクション（ユーザーブロック、IP ブロック、Snapshot 作成）
- ARP（Autonomous Ransomware Protection）管理

本リファレンスは、FSx for ONTAP (ONTAP 9.17.1P7D1) での実機デプロイに基づく実践的なパターン、よくある落とし穴、検証済みの挙動をまとめています。

---

## 認証

```bash
# 認証情報を設定（Secrets Manager から取得 — ハードコード厳禁）
export ONTAP_USER="fsxadmin"
export ONTAP_PASS=$(aws secretsmanager get-secret-value \
  --secret-id <secret-arn> --query 'SecretString' --output text | jq -r .password)

# Basic Auth（全エンドポイント共通）
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" https://<management-ip>/api/cluster
```

**Secrets Manager での認証情報管理**（推奨）:
```json
{
  "username": "fsxadmin",
  "password": "<password>"
}
```

管理 IP の取得:
```bash
aws fsx describe-file-systems --file-system-ids <fs-id> \
  --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]' \
  --output text
```

> **セキュリティに関する補足**: テスト環境では自己署名証明書のため `verify=False` / `-k` を使用します。本番環境では `security certificate show -type root-ca -vserver <svm>` で CA 証明書を取得し、HTTP クライアントに提供してください。

---

## よくある落とし穴（検証済み）

### 1. `svm.uuid` 重複エラー（コード 262188）

**症状**: `Field "svm.uuid" was specified twice`

**原因**: URL パスに既に SVM UUID が含まれている（例: `/api/protocols/fpolicy/{svm-uuid}/engines`）場合、リクエストボディにも `"svm": {"uuid": "..."}` を含めると競合する。

**解決策**: URL パスが SVM を指定している場合、ボディから `svm` フィールドを削除:

```python
# 間違い — 262188 エラーを起こす
url = f"https://{mgmt_ip}/api/protocols/fpolicy/{svm_uuid}/engines"
body = {"svm": {"uuid": svm_uuid}, "name": "my_engine", ...}

# 正しい
url = f"https://{mgmt_ip}/api/protocols/fpolicy/{svm_uuid}/engines"
body = {"name": "my_engine", "port": 9898, "primary_servers": ["10.0.12.74"], ...}
```

### 2. `allow_privileged_access` 設定不可（コード 262196）

**症状**: `Field "allow_privileged_access" cannot be set in this operation`

**原因**: FSx for ONTAP の FPolicy ポリシー作成エンドポイントでは、このフィールドは読み取り専用。

**解決策**: リクエストボディから `allow_privileged_access` を削除:

```python
# 間違い
body = {"name": "my_policy", "allow_privileged_access": False, ...}

# 正しい
body = {"name": "my_policy", "engine": {"name": "my_engine"}, "events": [...], ...}
```

### 3. FPolicy Scope — 別エンドポイントではなくインライン指定

**症状**: `POST /api/protocols/fpolicy/{svm-uuid}/policies/{policy}/scope` が 404 を返す

**原因**: ONTAP 9.17.1 では、scope はポリシー作成時にインラインで設定する（別サブリソースではない）。

**解決策**: ポリシー作成ボディに `scope` を含める:

```python
body = {
    "name": "my_policy",
    "engine": {"name": "my_engine"},
    "events": [{"name": "my_event"}],
    "mandatory": False,
    "scope": {
        "include_volumes": ["target_volume"]
    }
}
requests.post(f"https://{mgmt_ip}/api/protocols/fpolicy/{svm_uuid}/policies", json=body)
```

### 4. 非同期ジョブ — 最終状態の確認が必須

**症状**: 操作が成功したように見えるが（HTTP 202）、実際には失敗している。

**原因**: 多くの ONTAP REST API 操作は HTTP 202 とジョブ UUID を返す。実際の結果はジョブをポーリングしないと分からない。

**解決策**: ジョブエンドポイントを必ずポーリング:

```python
response = requests.patch(url, json=body)
if response.status_code == 202:
    job_uuid = response.json()["job"]["uuid"]
    # 完了までポーリング
    while True:
        job = requests.get(f"https://{mgmt_ip}/api/cluster/jobs/{job_uuid}").json()
        if job["state"] in ("success", "failure"):
            break
        time.sleep(2)
    if job["state"] == "failure":
        raise RuntimeError(f"Job failed: {job.get('message')}")
```

> **コストに関する補足**: HTTP ステータスだけを見て「成功」と判定するコードは、ジョブが実際には `state: failure` で終わっていることに気づかない。

---

## ARP/AI（Autonomous Ransomware Protection）— 主要な挙動

### ARP 有効化（REST API）

```bash
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"anti_ransomware":{"state":"enabled"}}' \
  "https://<mgmt-ip>/api/storage/volumes/<volume-uuid>"
```

HTTP 202（非同期ジョブ）が返る。ジョブをポーリングして成功を確認すること。

### ARP/AI: ONTAP 9.16.1 以降は学習期間不要

ONTAP 9.16.1 以降の ARP/AI では、有効化後**即座にアクティブ**になります。学習期間（dry-run）は不要です。API レスポンスに `dry_run_start_time` フィールドが表示されることがありますが、待機が必要なことを意味しません。

### `attack simulate` コマンド — 利用不可

CLI コマンド `security anti-ransomware volume attack simulate` は ONTAP 9.17.1 には**存在しません**。テスト目的で ARP 検知をトリガーするには:

1. ボリュームに通常のファイルを作成する
2. パスワード付きで暗号化する（例: `zip -e -P <password> file.ext file`）
3. 元ファイルを削除する
4. 暗号化ファイルは新しい（これまでに見たことのない）拡張子にする

ARP/AI が検知するパターン:
- 高エントロピーデータの書き込み
- 作成後のファイル削除
- これまでに見たことのないファイル拡張子（閾値: 48 時間以内に 5 種類以上）

### 利用可能な ARP サブコマンド（ONTAP 9.17.1）

```
security anti-ransomware volume attack clear-suspect   # 疑わしいレコードをクリア
security anti-ransomware volume attack generate-report # 攻撃レポートを生成
```

`show-suspect-files` も CLI コマンドとしては**利用不可**です。

### ARP EMS イベント

| イベント名 | 重大度 | トリガー |
|-----------|--------|---------|
| `arw.volume.state` | notice | ARP 状態変更（有効化/無効化） |
| `callhome.arw.activity.seen` | alert | 攻撃活動を検知 |
| `arw.snapshot.created` | notice | ARP Snapshot が作成された |
| `arw.analytics.probability` | alert | 攻撃確率が変化 |
| `arw.new.file.extn.seen` | notice | 新しいファイル拡張子を観測 |

---

## FPolicy 設定（完全な手順例）

### ステップ 1: 外部エンジンの作成

```bash
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_engine",
    "port": 9898,
    "primary_servers": ["<fargate-task-ip>"],
    "type": "synchronous",
    "format": "xml",
    "ssl_option": "no_auth"
  }' \
  "https://<mgmt-ip>/api/protocols/fpolicy/<svm-uuid>/engines"
```

### ステップ 2: イベントの作成

```bash
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_event",
    "file_operations": {
      "create": true,
      "write": true,
      "rename": true,
      "delete": true
    },
    "protocol": "cifs",
    "volume_monitoring": true
  }' \
  "https://<mgmt-ip>/api/protocols/fpolicy/<svm-uuid>/events"
```

### ステップ 3: ポリシー作成（scope インライン指定）

```bash
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "name": "fpolicy_policy",
    "engine": {"name": "fpolicy_engine"},
    "events": [{"name": "fpolicy_event"}],
    "mandatory": false,
    "scope": {
      "include_volumes": ["target_volume"]
    }
  }' \
  "https://<mgmt-ip>/api/protocols/fpolicy/<svm-uuid>/policies"
```

### ステップ 4: ポリシーの有効化

```bash
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "priority": 1}' \
  "https://<mgmt-ip>/api/protocols/fpolicy/<svm-uuid>/policies/fpolicy_policy"
```

---

## 自動応答 — SMB ユーザーブロックの仕組み

自動応答 Lambda は ONTAP の name-mapping を使って SMB ユーザーをブロックします:

```bash
# 拒否マッピングを作成（認証時にブロック）
curl -sk -u "${ONTAP_USER}:${ONTAP_PASS}" -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "direction": "win_unix",
    "index": 1,
    "pattern": "DOMAIN\\\\username",
    "replacement": ""
  }' \
  "https://<mgmt-ip>/api/name-services/name-mappings/<svm-uuid>"
```

### 挙動に関する重要な補足: ブロックのタイミング

name-mapping ブロックは、既存の SMB セッションを**即座に切断しません**。`soft` オプションの既存マウントはセッショントークンが期限切れになるまで動作し続けます。

**新規接続（再認証）は即座に拒否されます。**

即座のセッション終了が必要な場合、`contain_smb_threat` 複合アクションはセッション切断エンドポイントも呼び出します:
```
DELETE /api/protocols/cifs/sessions/{svm-uuid}/{connection-id}/{identifier}
```

---

## EMS Webhook ペイロード形式

ONTAP が EMS イベントを Webhook 宛先に送信する際、ペイロードは**ハイフン区切り**のフィールド名を使用します:

```json
{
  "message-name": "arw.volume.state",
  "message-severity": "alert",
  "message-timestamp": "2026-07-12T00:42:06+00:00",
  "parameters": {
    "vserver-name": "svm-prod",
    "volume-name": "vol_data",
    "state": "attack-detected"
  }
}
```

> **注意**: キャメルケース（`messageName`）やスネークケース（`message_name`）ではありません。ハイフン区切り: `message-name`、`message-severity`、`message-timestamp`。

---

## 関連ドキュメント

- [前提条件とデプロイガイド](prerequisites.md)
- [自動応答ガイド](automated-response-guide.md)
- [ARP インシデント対応ガイド](arp-incident-response-guide.md)
- [EMS 検知機能リファレンス](ems-detection-capabilities.md)
- [FPolicy セットアップ（Grafana 例）](../../integrations/grafana/docs/ja/fpolicy-setup.md)
