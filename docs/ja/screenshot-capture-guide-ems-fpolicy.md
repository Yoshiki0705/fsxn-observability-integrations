# EMS/FPolicy スクリーンショット撮影ガイド

🌐 **日本語**（このページ） | [English](../en/screenshot-capture-guide-ems-fpolicy.md)

## 撮影手順

以下のスクリーンショットを撮影し、`docs/screenshots/` に配置してください。

---

### 1. Datadog: ARP 検知ログ

**ファイル名**: `datadog-arp-detection.png`

**手順**:
1. https://ap1.datadoghq.com/logs にアクセス
2. 検索バーに `source:fsxn-ems` と入力
3. 時間範囲を「Past 1 Hour」に設定
4. ARP イベント（`arw.volume.state`）が表示されていることを確認
5. ログ一覧が見える状態でスクリーンショットを撮影

---

### 2. Datadog: ARP ログ詳細

**ファイル名**: `datadog-arp-log-detail.png`

**手順**:
1. 上記の検索結果から ARP イベントをクリック
2. ログ詳細パネルが展開される
3. `attributes` セクションを展開して以下が見えることを確認:
   - `event_name`: `arw.volume.state`
   - `severity`: `alert`
   - `parameters.volume_name`: `vol_data`
   - `parameters.state`: `attack-detected`
4. 構造化属性が展開された状態でスクリーンショットを撮影

---

### 3. AWS CloudWatch: EMS Lambda 実行ログ

**ファイル名**: `aws-ems-lambda-logs.png`

**手順**:
1. AWS マネジメントコンソール → CloudWatch → Log groups
2. `/aws/lambda/fsxn-datadog-ems-fpolicy-ems` を選択
3. 最新のログストリームを開く
4. 以下のログメッセージが見えることを確認:
   - `EMS handler invoked: requestId=...`
   - `Parsed 1 EMS event(s)`
   - `Processing complete: {"message": "EMS events processed", "total_events": 1, "shipped": 1}`
5. ログイベントが見える状態でスクリーンショットを撮影

**代替**: AWS CLI で取得した結果をターミナルのスクリーンショットとして使用可能:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/fsxn-datadog-ems-fpolicy-ems \
  --region ap-northeast-1 \
  --start-time $(($(date +%s) - 3600))000 \
  --limit 10
```

---

### 4. Datadog: FPolicy ファイル操作ログ

**ファイル名**: `datadog-fpolicy-suspect-activity.png`

**手順**:
1. https://ap1.datadoghq.com/logs にアクセス
2. 検索バーに `source:fsxn-fpolicy` と入力
3. 時間範囲を「Past 1 Hour」に設定
4. FPolicy イベント（ファイル作成等）が表示されていることを確認
5. ログ一覧が見える状態でスクリーンショットを撮影

---

### 5. ONTAP CLI: ARP ステータス

**ファイル名**: `ontap-arp-status.png`

**手順**:
1. FSx for ONTAP 管理エンドポイントに SSH 接続:
   ```bash
   ssh admin@management.fs-0123456789abcdef0.fsx.ap-northeast-1.amazonaws.com
   ```
2. 以下のコマンドを実行:
   ```
   security anti-ransomware volume show
   ```
3. 出力結果のスクリーンショットを撮影

---

### 6. ONTAP CLI: ARP スナップショット一覧

**ファイル名**: `ontap-arp-snapshot.png`

**手順**:
1. FSx for ONTAP 管理エンドポイントに SSH 接続（上記と同じ）
2. 以下のコマンドを実行:
   ```
   volume snapshot show -snapshot Anti_ransomware*
   ```
3. 出力結果のスクリーンショットを撮影

---

## 配置先

すべてのスクリーンショットを以下のディレクトリに配置:

```
docs/screenshots/
├── datadog-arp-detection.png
├── datadog-arp-log-detail.png
├── aws-ems-lambda-logs.png
├── datadog-fpolicy-suspect-activity.png
├── ontap-arp-status.png
└── ontap-arp-snapshot.png
```

## 撮影のポイント

- **解像度**: 最低 1280x720 以上
- **形式**: PNG
- **個人情報**: API Key やパスワードが映り込まないよう注意
- **タイムスタンプ**: ログのタイムスタンプが見える状態で撮影
- **構造化属性**: Datadog のログ詳細では attributes を展開した状態で撮影
