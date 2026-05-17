# Datadog フィールドマッピング

## イベントソースとタグ

| ソース | `source` タグ | `service` タグ | トリガー |
|--------|-------------|---------------|---------|
| ファイルアクセス監査ログ | `fsxn` | `fsxn-ontap` | EventBridge Scheduler |
| EMS Webhook | `fsxn-ems` | `fsxn-ontap` | API Gateway |
| FPolicy イベント | `fsxn-fpolicy` | `fsxn-ontap` | SQS → Lambda |

## ファイルアクセス監査ログ属性

| Datadog 属性 | ONTAP ソース (EVTX) | ONTAP ソース (XML) | 説明 |
|-------------------|--------------------|--------------------|-------------|
| `attributes.svm` | SVMName | Computer | Storage Virtual Machine 名 |
| `attributes.user` | UserName | SubjectUserName | 操作を実行したユーザー |
| `attributes.client_ip` | ClientIP | IpAddress | クライアント IP アドレス |
| `attributes.operation` | Operation | ObjectType | 操作タイプ (ReadData, WriteData 等) |
| `attributes.path` | ObjectName | ObjectName | ファイル/ディレクトリパス |
| `attributes.result` | Result | Keywords | Success または Failure |
| `attributes.event_type` | EventID | EventID | Windows Event ID (4663, 4656 等) |
| `host` | — | — | ONTAP ノード名 |
| `timestamp` | Record timestamp | TimeCreated SystemTime | イベントタイムスタンプ (ISO 8601) |

## EMS イベント属性

| Datadog 属性 | EMS フィールド | 説明 |
|-------------------|-----------|-------------|
| `attributes.event_name` | messageName | EMS イベント名 (例: `arw.volume.state`) |
| `attributes.severity` | severity | イベント重要度 (alert, error, warning, info) |
| `attributes.source_node` | node | イベントを生成した ONTAP ノード |
| `attributes.svm` | svmName | SVM 名 |
| `attributes.parameters.*` | parameters.* | イベント固有パラメータ |
| `host` | node | ONTAP ノード名 |
| `message` | message | 人間が読めるイベント説明 |

### ARP (Anti-Ransomware) イベント例

```json
{
  "source": "fsxn-ems",
  "service": "fsxn-ontap",
  "host": "fsxn-node-01",
  "message": "Anti-ransomware: Volume vol_data state changed to attack-detected",
  "attributes": {
    "event_name": "arw.volume.state",
    "severity": "alert",
    "source_node": "fsxn-node-01",
    "svm": "svm-prod-01",
    "parameters": {
      "volume_name": "vol_data",
      "state": "attack-detected"
    }
  }
}
```

## FPolicy イベント属性

| Datadog 属性 | FPolicy フィールド | 説明 |
|-------------------|--------------|-------------|
| `attributes.operation` | operation | ファイル操作 (create, write, delete, rename, open) |
| `attributes.file_path` | file_path | フルファイルパス |
| `attributes.user` | user | ユーザー ID |
| `attributes.client_ip` | client_ip | クライアント IP アドレス |
| `attributes.vserver` | vserver | SVM (vserver) 名 |
| `attributes.protocol` | protocol | アクセスプロトコル (cifs, nfs) |
| `host` | vserver | SVM 名 |
| `message` | — | フォーマット: `FPolicy: <op> <path> by <user> from <ip>` |

## Datadog 検索クエリ

| ユースケース | クエリ |
|----------|-------|
| 全 FSx ONTAP 監査ログ | `source:fsxn` |
| 失敗したアクセス試行 | `source:fsxn @attributes.result:Failure` |
| ARP ランサムウェアアラート | `source:fsxn-ems @attributes.event_name:arw.volume.state` |
| FPolicy ファイル操作 | `source:fsxn-fpolicy` |
| 特定ユーザーのアクティビティ | `source:fsxn @attributes.user:admin@corp.local` |
| 特定ファイルパス | `source:fsxn @attributes.path:"/vol/data/confidential/*"` |

## Datadog Monitor 例

### ARP ランサムウェア検知

```json
{
  "name": "FSx ONTAP: Ransomware Detected (ARP)",
  "type": "log alert",
  "query": "source:fsxn-ems @attributes.event_name:arw.volume.state @attributes.parameters.state:attack-detected",
  "message": "🚨 ONTAP Autonomous Ransomware Protection detected encryption activity.\n\nVolume: {{attributes.parameters.volume_name}}\nSVM: {{attributes.svm}}\nNode: {{host}}\n\nImmediate actions:\n1. Create snapshot of affected volume\n2. Disable client access\n3. Investigate with FPolicy logs",
  "options": {
    "thresholds": {"critical": 0},
    "notify_no_data": false
  }
}
```

### 大量アクセス失敗

```json
{
  "name": "FSx ONTAP: Bulk Failed Access Attempts",
  "type": "log alert",
  "query": "source:fsxn @attributes.result:Failure",
  "message": "⚠️ Multiple failed file access attempts detected.\n\nUser: {{attributes.user}}\nClient IP: {{attributes.client_ip}}\n\nThis may indicate unauthorized access attempts.",
  "options": {
    "thresholds": {"critical": 10, "warning": 5},
    "timeframe": "5m"
  }
}
```


## Datadog PoC チェックリスト

PoC デプロイの検証に使用してください:

- [ ] CloudFormation スタックが正常にデプロイされた
- [ ] EventBridge Scheduler が Lambda を起動している（CloudWatch Logs 確認）
- [ ] Datadog Log Explorer で `source:fsxn` のログが表示される
- [ ] 必要な属性が入力されている（`@attributes.svm`, `@attributes.user`, `@attributes.operation`, `@attributes.path`, `@attributes.result`）
- [ ] Failed access クエリが期待通りの結果を返す
- [ ] Delete operation クエリが期待通りの結果を返す
- [ ] DLQ が空（失敗イベントなし）
- [ ] CloudWatch アラームが OK 状態
- [ ] コスト見積もりを実際の使用量と照合
- [ ] Part 3 の次ステップ Monitor を特定（ARP、bulk delete、failed access spike）
