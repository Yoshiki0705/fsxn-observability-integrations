# ローカル開発・UI/UX 検証ガイド

FSx for ONTAP Management Console の UI/UX をローカル環境で検証するための手順書です。

## 目次

1. [前提条件](#前提条件)
2. [環境構築](#環境構築)
3. [Appsmith（Management UI）の検証](#appsmithmanagement-uiの検証)
4. [Grafana（Observability Layer）の検証](#grafanaobservability-layerの検証)
5. [Grafana パネル埋め込みの検証](#grafana-パネル埋め込みの検証)
6. [ONTAP REST API モックの構築](#ontap-rest-api-モックの構築)
7. [検証チェックリスト](#検証チェックリスト)
8. [クリーンアップ](#クリーンアップ)

---

## 前提条件

| ツール | バージョン | 用途 |
|--------|-----------|------|
| Docker | 20.10+ | コンテナ実行 |
| Colima (macOS) | 0.5+ | Docker ランタイム（Docker Desktop 代替） |
| ブラウザ | Chrome/Firefox 最新版 | UI 検証 |
| curl | 任意 | ヘルスチェック |
| jq | 任意 | JSON パース |

### Colima の起動

```bash
# macOS の場合（Docker Desktop を使用していない場合）
colima start --cpu 4 --memory 4 --disk 20
```

---

## 環境構築

### Step 1: Docker ネットワーク作成

```bash
docker network create fsxn-mgmt-dev
```

### Step 2: Appsmith 起動（Management UI）

```bash
docker run -d \
  --name appsmith \
  --network fsxn-mgmt-dev \
  -p 80:80 \
  -p 443:443 \
  appsmith/appsmith-ce:latest
```

> 初回起動は約 60 秒かかります（MongoDB + Redis の内部初期化）。

### Step 3: Grafana 起動（Observability Layer）

```bash
docker run -d \
  --name grafana-local \
  --network fsxn-mgmt-dev \
  -p 3001:3000 \
  -e GF_AUTH_ANONYMOUS_ENABLED=true \
  -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
  -e GF_SECURITY_ALLOW_EMBEDDING=true \
  -e GF_SERVER_ROOT_URL=http://localhost:3001 \
  grafana/grafana:latest
```

> `GF_SECURITY_ALLOW_EMBEDDING=true` は iframe 埋め込みに必須です。

### Step 4: 起動確認

```bash
# Appsmith
curl -s -o /dev/null -w "%{http_code}" http://localhost:80
# 期待値: 200

# Grafana
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001
# 期待値: 200
```

---

## Appsmith（Management UI）の検証

### 初期セットアップ

1. ブラウザで `http://localhost` にアクセス
2. 管理者アカウントを作成（メール、パスワード）
3. プロファイル設定を完了

![Appsmith セットアップ画面](../images/appsmith-setup-page.png)

### アプリケーション作成

1. ダッシュボードから「New Application」をクリック
2. アプリ名を「FSx for ONTAP Management Console」に変更

![Appsmith ダッシュボード](../images/appsmith-dashboard.png)

### UI コンポーネントの構築

エディタ画面で以下のウィジェットを配置します：

![Appsmith エディタ](../images/appsmith-editor-empty.png)

#### タブナビゲーション

1. 左サイドバー → UI → 「New UI element」
2. 「Tabs」ウィジェットをキャンバスにドラッグ
3. タブを追加: Dashboard, Volumes, SVMs, Snapshots, Replication, S3 Files, Settings

#### Volume テーブル

1. Volumes タブ内に「Table」ウィジェットを配置
2. テーブルデータに以下のモックデータを設定:

```json
[
  {"name": "vol_data_01", "svm": "svm-prod", "used": "450 GB", "total": "1 TB", "percent_used": 45, "state": "online"},
  {"name": "vol_data_02", "svm": "svm-prod", "used": "1.6 TB", "total": "2 TB", "percent_used": 78, "state": "online"},
  {"name": "vol_backup_01", "svm": "svm-dr", "used": "200 GB", "total": "500 GB", "percent_used": 40, "state": "online"},
  {"name": "vol_archive", "svm": "svm-prod", "used": "4.5 TB", "total": "5 TB", "percent_used": 90, "state": "online"}
]
```

#### 確認ダイアログ

1. 「Modal」ウィジェットを追加
2. タイトル: "Delete Volume"
3. メッセージ: "Are you sure you want to delete volume '{{selectedRow.name}}'?"
4. ボタン: "Cancel" + "Delete"（赤色）

#### Grafana パネル埋め込み

1. 「iframe」ウィジェットを Volume Detail セクションに配置
2. URL: `http://localhost:3001/d-solo/...?panelId=1&from=now-1h&to=now`

---

## Grafana（Observability Layer）の検証

### アクセス

ブラウザで `http://localhost:3001` にアクセスします。匿名アクセスが有効なので、ログイン不要です。

![Grafana ホーム](../images/grafana-home.png)

### ダッシュボード作成

1. 左メニュー → Dashboards → New Dashboard
2. 「Add visualization」をクリック
3. データソースとして「-- Grafana --」を選択（テスト用）
4. パネルタイトルを「Volume IOPS」に設定

### Harvest ダッシュボードのインポート

本番環境では `scripts/import-dashboards.sh` を使用しますが、ローカルでは手動インポートも可能です：

1. Grafana 左メニュー → Dashboards → Import
2. `harvest/dashboards/` ディレクトリの JSON ファイルをアップロード
3. データソースを選択して Import

![Grafana ダッシュボード一覧](../images/grafana-dashboards-list.png)

---

## Grafana パネル埋め込みの検証

### 埋め込み URL の確認

Grafana パネルを Appsmith の iframe に埋め込む際の URL 形式：

```
http://localhost:3001/d-solo/<dashboard-uid>/<dashboard-slug>?orgId=1&panelId=<panel-id>&from=now-1h&to=now&refresh=1m
```

### 検証手順

1. Grafana でダッシュボードを作成し、パネルを追加
2. パネルの「Share」→「Embed」から埋め込み URL を取得
3. Appsmith の iframe ウィジェットに URL を設定
4. 以下を確認:
   - パネルが 10 秒以内に表示されること
   - 60 秒ごとに自動リフレッシュされること
   - パネルが表示されない場合のフォールバックメッセージ

### 注意事項

- ローカル環境では Cognito 認証がないため、Grafana の匿名アクセスを有効にしています
- 本番環境では ALB の Cognito セッション Cookie が共有されるため、追加認証は不要です
- `GF_SECURITY_ALLOW_EMBEDDING=true` が設定されていないと iframe 内でパネルが表示されません

---

## ONTAP REST API モックの構築

実際の FSx for ONTAP がなくても、モック API サーバーで UI 操作を検証できます。

### json-server を使用する場合

```bash
npm install -g json-server

# モックデータ作成
cat > /tmp/ontap-mock-db.json << 'EOF'
{
  "storage-volumes": {
    "records": [
      {
        "uuid": "vol-uuid-001",
        "name": "vol_data_01",
        "svm": {"name": "svm-prod", "uuid": "svm-uuid-001"},
        "space": {"size": 1099511627776, "used": 494780232499, "available": 604731395277},
        "state": "online",
        "aggregates": [{"name": "aggr1"}],
        "nas": {"path": "/vol_data_01"}
      },
      {
        "uuid": "vol-uuid-002",
        "name": "vol_data_02",
        "svm": {"name": "svm-prod", "uuid": "svm-uuid-001"},
        "space": {"size": 2199023255552, "used": 1715177736396, "available": 483845519156},
        "state": "online",
        "aggregates": [{"name": "aggr1"}],
        "nas": {"path": "/vol_data_02"}
      }
    ],
    "num_records": 2
  },
  "svm-svms": {
    "records": [
      {
        "uuid": "svm-uuid-001",
        "name": "svm-prod",
        "state": "running",
        "ip_interfaces": [{"ip": {"address": "10.0.x.x"}, "name": "lif-nfs-01"}],
        "nfs": {"enabled": true},
        "cifs": {"enabled": true},
        "s3": {"enabled": true}
      }
    ],
    "num_records": 1
  }
}
EOF

json-server --watch /tmp/ontap-mock-db.json --port 8443
```

### Appsmith でモック API に接続

1. Appsmith → Data Sources → REST API
2. URL: `http://host.docker.internal:8443`（Docker 内から macOS ホストにアクセス）
3. テスト接続で Volume 一覧が返ることを確認

---

## 検証チェックリスト

### UI ナビゲーション（Requirement 9）

- [ ] タブ切り替えが 200ms 以内に完了する
- [ ] アクティブタブが視覚的に区別される
- [ ] アコーディオンパネルが 1 つずつ展開される
- [ ] ブラウザの戻る/進むでタブ状態が復元される
- [ ] 1280px〜2560px で水平スクロールなし

### Volume 管理（Requirement 4）

- [ ] Volume 一覧テーブルに名前、SVM、使用量、状態が表示される
- [ ] 作成フォームのバリデーション（名前: 1-203文字、英数字+アンダースコア）
- [ ] 削除時に確認ダイアログが表示される
- [ ] エラー時にエラーメッセージが表示される

### Grafana 埋め込み（Requirement 8）

- [ ] iframe 内に Grafana パネルが表示される
- [ ] 10 秒以内にパネルがロードされる
- [ ] ロード失敗時にフォールバックメッセージが表示される
- [ ] 60 秒ごとに自動リフレッシュされる

### レスポンシブ表示

- [ ] 1280px 幅で全要素が表示される
- [ ] 1920px 幅で適切にレイアウトされる
- [ ] 2560px 幅でコンテンツが中央寄せまたは適切に拡張される

---

## クリーンアップ

```bash
# コンテナ停止・削除
docker rm -f appsmith grafana-local

# ネットワーク削除
docker network rm fsxn-mgmt-dev

# Colima 停止（必要に応じて）
colima stop
```

---

## 補足: ローカルで検証できないもの

以下の機能は AWS 環境でのみ検証可能です：

| 機能 | 理由 | 代替検証方法 |
|------|------|------------|
| Cognito 認証フロー | ALB + Cognito は AWS 上のみ | Appsmith のビルトイン認証で代替 |
| S3 AP ファイルブラウザ | Lambda + S3 AP は AWS 上のみ | モック API で UI のみ検証 |
| AMP メトリクス | AMP は AWS マネージドサービス | ローカル Prometheus で代替可能 |
| AMG ダッシュボード | AMG は AWS マネージドサービス | ローカル Grafana で代替 |
| VPC ネットワーク分離 | VPC は AWS 上のみ | Docker ネットワークで概念検証 |
