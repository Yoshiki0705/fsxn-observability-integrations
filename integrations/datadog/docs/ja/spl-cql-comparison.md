# SPL vs CQL クエリ対比表 — FSxN 監査ログ

Splunk と CrowdStrike LogScale の両方を使用する SOC アナリスト向けに、FSxN 監査ログの一般的なクエリを SPL と CQL で対比します。

## クエリ対比表

| 操作 | Splunk SPL | LogScale CQL |
|------|-----------|--------------|
| **5分バケット** | `\| bin _time span=5m` | `\| bucket(span=5m)` |
| **上位10ユーザー** | `\| top limit=10 user` | `\| top(user, limit=10)` |
| **ユーザー別カウント** | `\| stats count by user` | `\| groupBy(user, function=count())` |
| **フィルタ+集計** | `source="fsxn" event_type=4660 \| stats count by user` | `#repo=fsxn_audit event_type="4660" \| groupBy(user, function=count())` |
| **時間範囲** | `earliest=-1h latest=now` | クエリ時間ピッカー or `@timestamp > now() - 1h` |
| **ワイルドカード** | `path="*finance*"` | `path = /share/finance/*`（glob） |
| **除外パターン** | `NOT user="svc-*"` | `user != "svc-*"` |
| **ユニーク値** | `\| stats dc(user) as unique_users` | `\| count(user, distinct=true)` |

## 検知クエリ例

### 大量ファイル削除

**Splunk SPL:**
```spl
index=fsxn_audit sourcetype=fsxn:audit:xml event_type=4660
| bin _time span=5m
| stats count by _time, user, client_ip
| where count > 50
| sort - count
```

**LogScale CQL:**
```
#repo=fsxn_audit event_type="4660"
| bucket(span=5m)
| groupBy([_bucket, user, client_ip], function=count())
| _count > 50
| sort(_count, order=desc)
```

### 業務時間外アクセス

**Splunk SPL:**
```spl
index=fsxn_audit sourcetype=fsxn:audit:xml
| eval hour=strftime(_time, "%H")
| where hour > "19" OR hour < "07"
| stats count by user, path
| sort - count
```

**LogScale CQL:**
```
#repo=fsxn_audit
| parseTimestamp(field=timestamp, format="yyyy-MM-dd'T'HH:mm:ss")
| hour := formatTime(field=@timestamp, format="HH")
| hour > "19" OR hour < "07"
| groupBy([user, path], function=count())
| sort(_count, order=desc)
```

## 主な違い

| 観点 | SPL | CQL |
|------|-----|-----|
| リポジトリ/インデックス | `index=fsxn_audit` | `#repo=fsxn_audit` |
| パイプモデル | 逐次変換 | 類似（関数名が異なる） |
| 時刻フィールド | `_time`（自動） | `@timestamp`（自動） |
| 大文字小文字 | デフォルトで大文字小文字を区別しない | 大文字小文字を区別 |

## 正規化フィールドスキーマ

両プラットフォームとも FSxN パーサーからの同じフィールド名を使用:

| フィールド | 説明 | 例 |
|-----------|------|-----|
| `user` | Windows ドメインユーザー | `CORP\user-finance-01` |
| `path` | ファイル/ディレクトリパス | `/share/finance/report.xlsx` |
| `client_ip` | ソースワークステーション IP | `10.0.x.x` |
| `event_type` | Windows EventID | `4660` |
| `result` | 監査結果 | `Audit Success` / `Audit Failure` |
| `svm` | Storage Virtual Machine | `ProductionSVM` |
| `operation` | 操作タイプ | `File` |
| `timestamp` | イベント時刻（ISO 8601） | `2026-06-14T12:13:00.000000Z` |

---

## 関連ドキュメント

- [本番チェックリスト](production-checklist.md)
- [セットアップガイド](setup-guide.md)
- [フィールドマッピング](field-mapping.md)
- [README（メイン）](../../README.md)
- [CrowdStrike LogScale 統合](../../../crowdstrike/README.md)
- [Splunk 統合](../../../splunk-serverless/README.md)
