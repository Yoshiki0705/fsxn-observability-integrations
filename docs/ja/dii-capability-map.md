# DII Storage Workload Security — 機能マップと対応関係の整理

## このドキュメントの目的

これまで本リポジトリでは、NetApp DII（Data Infrastructure Insights）Storage Workload Security への言及を複数箇所に追加してきました — [自動インシデント対応ガイド](automated-response-guide.md)内の比較表、ルート README のコールアウト、[NetApp Console<!-- allow:naming --> 統合](../../integrations/netapp-console/)への言及などです。しかしそれぞれは DII のある一側面（主に *封じ込め/対応* 側）を個別にカバーするに留まり、DII が全体としてどんな機能を持つのかを先に整理していませんでした。結果として「DII のようにユーザーをブロックする方法」は見つかるが、「DII は全体として何をしていて、本リポジトリはそのうちどこまでカバーしているか」が分からない、虫食い状態になっていました。

このドキュメントはまず DII SWS の機能セット全体をフェーズごとに整理し、その上で本リポジトリが「既に提供している部分」「既存の要素を組み合わせれば実現できる部分」「本当のギャップとして残っている部分」を示します。詳細な手順は各ガイドにリンクする形にし、重複記載は避けています。

> **エビデンスの区分**: 以下の DII SWS の機能説明は NetApp の公開ドキュメント（各記述に出典リンクを付記）に基づいています。「本リポジトリの対応」列は、このコードベースで実装済み・E2E 検証済みの機能を指します（例外は明記）。

## DII Storage Workload Security の全体像

DII SWS は NetApp DII（旧 Cloud Insights）の 1 モジュールです。NetApp 自身の説明によると、SWS は「環境内のすべての認証済みユーザーのファイル活動を追跡する、ユーザー中心のアプローチ」を取り、ML によって確立した行動ベースラインにより、ランサムウェアシグネチャを必要とせずに異常を検知します。出典: [Data Infrastructure Insights Storage Workload Security](https://docs.netapp.com/us-en/ontap-technical-reports/ransomware-solutions/ransomware-DII-workload-security.html)。

DII SWS の機能を NIST SP 800-61 のインシデント対応ライフサイクル（Preparation/Protect → Detect → Contain/Respond → Recover）と、全フェーズを横断する Forensics（調査）レイヤーにマッピングすると:

| フェーズ | DII SWS が行うこと | 実現メカニズム |
|---------|---------------------|----------------|
| **Protect（保護）** | ユーザー別のアクセスベースラインを確立。ONTAP ARP のアラートを単一インターフェースに統合 | FPolicy データコレクター + ONTAP ARP Webhook |
| **Detect（検知）** | シグネチャ不要の ML ベース行動異常検知。ユーザーの通常/季節的アクセスパターンからの逸脱を検知 | ユーザー別 ML ベースラインモデル（クラウドホスト、SaaS バックエンド） |
| **Respond（対応）** | 疑わしいユーザーアカウント **と** IP アドレスを自動ブロック。保護 Snapshot を作成。管理者へアラート | 本リポジトリと同じ ONTAP メカニズム: `name-mapping`（SMB）、export-policy ルール（NFS）、`volume snapshot create` |
| **Recover（復旧）** | 検知時点で自動作成された Snapshot により、復旧を簡略化・高速化 | ONTAP Snapshot からのリストア（SWS の自動 Snapshot 作成後、リストア自体は手動ステップ） |
| **Forensics（横断的機能）** | どのユーザーが、どの IP から、どのファイル/パスに触れ、どんなアクションを行ったかを表示するダッシュボード。最大 31 日間フィルタ、CSV エクスポート可能 | FPolicy コレクターから DII のバックエンド DB へ集約されたデータ。**CIFS/NFS 操作のみ** — API 経由の操作（System Manager、PowerShell API、クラスタ CLI）は明示的に対象外（出典: [Forensics Activity FAQ](https://kb.netapp.com/Cloud/BlueXP/Cloud_Insights/FAQ:_Storage_Workload_Security_Forensics_Activity) <!-- allow:naming -->） |

同 FAQ によると、DII SWS には具体的に 4 種類の Forensics ビューがあります: **Forensic User Overview**、**Forensics - All Activity**、**Forensic User Activity Data**、**Forensic Entities Page**（ファイル/オブジェクト中心のビュー）。本ドキュメントのベンダー別実装ガイダンスは、この 4 ビューと同等のものを作ることを目標に構成しています。

> **重要な区別**: DII の *Detect* フェーズは、NetApp の SaaS バックエンドで動作するユーザー別行動 ML を使用します。本リポジトリが既に統合している ONTAP 自身の Autonomous Ransomware Protection（ARP）（[ARP インシデント対応ガイド](arp-incident-response-guide.md)参照）は、ファイル内容のエントロピー/拡張子変更分析を使用しており、ユーザー別行動 ML ではありません。DII SWS は ARP アラートを自身の ML に加えた「追加の入力」として自インターフェースに表示しているだけです。**この 2 つは異なる検知メカニズムであり、ARP はユーザー行動 ML の代替にはなりません**。本リポジトリはユーザー別 ML ベースラインモデルを提供していません。この役割を何が代替するかは下記の Detect 行を参照してください。

## 機能対応表

| フェーズ | DII SWS の機能 | 本リポジトリの対応 | ステータス | 参照先 |
|---------|-----------------|---------------------|-----------|--------|
| Protect | ARP アラートの統合表示 | ARP からの EMS Webhook をネイティブ統合、~30 秒で配信 | ✅ 完全対応 | [EMS 検知機能リファレンス](ems-detection-capabilities.md) |
| Protect | ユーザー別アクセスベースライン（パッシブ） | 該当なし — ML なしのパッシブベースラインは提供不可（Detect 参照） | ❌ ギャップ | — |
| Detect | ML ベースの行動異常検知 | 使用する SIEM の ML/異常検知機能に委譲（Datadog Watchdog、Elastic ML Jobs、Splunk MLTK） — **組み込みではなく**、SIEM 側の設定・学習データが必要 | ⚠️ 組み合わせが必要 | [検知ユースケース](detection-use-cases.md) |
| Detect | ファイル内容ベースのランサムウェアシグネチャ/エントロピー検知 | ONTAP ARP（ネイティブ、DII も同じメカニズムを利用） | ✅ 完全対応 | [ARP インシデント対応ガイド](arp-incident-response-guide.md) |
| Detect | クォータ/容量異常 | ONTAP EMS クォータイベント | ✅ 完全対応 | [EMS 検知機能リファレンス](ems-detection-capabilities.md) |
| Respond | ユーザー自動ブロック（SMB） | `name-mapping` による拒否、同じ ONTAP API | ✅ 完全対応 | [自動インシデント対応ガイド](automated-response-guide.md) |
| Respond | IP 自動ブロック（NFS） | export-policy 拒否ルール、同じ ONTAP API | ✅ 完全対応 | [自動インシデント対応ガイド](automated-response-guide.md) |
| Respond | 検知時の保護 Snapshot | ストームー防止クールダウン付き `create_snapshot` アクション | ✅ 完全対応 | [自動インシデント対応ガイド](automated-response-guide.md) |
| Respond | 管理者へのアラート | SNS 通知トピック（後段は任意: メール、Slack、PagerDuty） | ✅ 完全対応 | [自動インシデント対応ガイド](automated-response-guide.md) |
| Respond | 時間制限付きアクセス制限 | EventBridge Scheduler による自動解除（付随 TTL スタック） | ✅ 完全対応（ガイド内の TTL 制約に関する注記を参照） | [自動インシデント対応ガイド](automated-response-guide.md) |
| Recover | 検知時点 Snapshot からの高速リストア | Respond フェーズで作成した保護 Snapshot からの手動 `volume snapshot restore` | ⚠️ 組み合わせが必要 — パッケージ化されたリストア Runbook は未整備 | 下記「本当のギャップ」参照 |
| Forensics | Forensic User Overview（ユーザー別活動サマリ） | audit log / FPolicy パイプラインに既に存在する正規化済み `user`/`client_ip`/`path`/`operation` フィールドから構築可能 | ⚠️ 組み合わせが必要 — 下記ベンダー別ガイダンス参照 | 本ドキュメント「Forensics レイヤーの構築」 |
| Forensics | All Activity（時系列、フィルタ可能） | 同じ基盤フィールド。ベンダーごとにダッシュボード/保存検索が必要 | ⚠️ 組み合わせが必要 | 本ドキュメント |
| Forensics | User Activity Data（ドリルダウン） | 同じ基盤フィールド | ⚠️ 組み合わせが必要 | 本ドキュメント |
| Forensics | Entities Page（ファイル/オブジェクト中心の履歴） | 同じ基盤フィールド、`path` でグループ化 | ⚠️ 組み合わせが必要 | 本ドキュメント |
| Forensics | 31 日フィルタ付き CSV エクスポート | ベンダーネイティブのエクスポート（Datadog Log Explorer export、Splunk `outputcsv`、Kibana Discover CSV、Grafana パネルエクスポート） — 保持期間は設定したインデックス/保持ポリシーに依存し、31 日固定ではない | ✅ 完全対応（ベンダーネイティブ、DII の固定ウィンドウより柔軟な場合が多い） | 下記ベンダー別ドキュメント |

凡例: ✅ 完全対応 = 同等以上の機能が存在し実装・検証済み。⚠️ 組み合わせが必要 = 基盤データは存在するが、既製のダッシュボード/Runbook は未整備（本ドキュメントで提供）。❌ ギャップ = 実際に存在せず、新規開発が必要。

## Forensics が「同じデータの二重実装」である理由

DII の Forensics ダッシュボードと本リポジトリの audit パイプラインがほぼ同等の水準に到達できる理由は、**両者が同じデータソースに依拠している**ためです: CIFS/NFS 操作を監視する FPolicy コレクターです。DII 自身の FAQ は、本リポジトリの [normalized-event-schema.md](normalized-event-schema.md) が既に文書化している同じ盲点を確認しています:

| 制約 | DII SWS（NetApp KB より） | 本リポジトリ |
|------|---------------------------|---------------|
| API 経由の操作（System Manager、PowerShell API、クラスタ CLI） | Forensics には記録されない — 生の ONTAP クラスタログにのみ表示 | 同じギャップ — FPolicy は API コールを見ない。API 経由の変更可視性には audit log（`EventID` ベース）を使用すること |
| FPolicy エージェントの停止/切断 | 停止中は Forensics データなし | 同様 — Lambda/ECS Fargate の FPolicy ハンドラー停止中は FPolicy イベントなし。ただし独立した audit-log パイプライン（EventBridge Scheduler）は影響を受けず継続 |
| `svm`/`user` フィールドの完全性 | DII の FAQ には既知の問題として記載なし | 本リポジトリでは既知のギャップとして文書化: FPolicy がハンドシェイクコンテキストから解決できない場合 `svm` が "unknown" になる可能性、一部操作で `user` が空になる可能性あり — [正規化イベントスキーマ](normalized-event-schema.md#notes) 参照 |
| プロトコルカバレッジ | CIFS/NFS のみ（SWS データコレクターのスコープ） | 同様 — FPolicy パイプラインは CIFS/NFS。NFS 4.1 は NetApp 自身の KB でも FPolicy 非対応と明記 |

**実務上の意味**: 本リポジトリでは audit log と FPolicy が独立した 2 本のパイプラインである（DII は Forensics に関して FPolicy のみに依存）ため、FPolicy 側のギャップを同一のファイル操作について audit-log パイプラインの `EventID` ベースの記録と相互チェックできます — これは DII のシングルコレクター構成にはない突き合わせオプションです。この点は下記のベンダー別ガイダンスでも再度触れます。

## Forensics レイヤーの構築: データソースの選択

いずれかのベンダーダッシュボードを構成する前に、フォレンジック調査にどちらのパイプラインを問い合わせるか決めます:

| パイプライン | 粒度 | レイテンシ | 適した用途 |
|-------------|------|-----------|-----------|
| **FPolicy**（`operation_type`、`file_path`、`client_ip`、`user`、`protocol`） | アクションレベル（create/write/rename/delete） | サブ秒、イベント駆動 | 「今、何のアクションが起きたか」— DII のリアルタイム Forensics フィードに最も近い |
| **Audit Log**（`operation`、`path`、`user`、`client_ip`、`result`） | アクセスチェックレベル（ReadData/WriteData、Success/Failure） | 分単位（Scheduler 間隔 + ログローテーション間隔） | 「過去 N 日間に何が起きたか」— 31 日相当の履歴ビューに適する。`result: Failure` を持つ唯一のソースであり、アクセス拒否のフォレンジックにも必須 |

DII の 4 つの Forensics ビューの大半は、アクション単位・準リアルタイムの **FPolicy** パイプラインに最も直接的にマッピングされます。**Audit log** パイプラインは相互チェック/網羅性確認、および失敗アクセス試行の詳細が必要な場合の主ソースとして使用してください（FPolicy 通知は通常、ONTAP が *許可した* 操作に対して送られ、拒否操作ではない場合が多い — ONTAP の FPolicy ポリシー設定で拒否操作も送信されるかを確認してください）。

> **PII/コンプライアンスの相互参照**: 以下のダッシュボードを構築する前に、[データ分類ガイド](../en/data-classification.md) を確認してください。同ガイドの Field Classification Matrix では `user`/`UserName` が PII（高リスク）、`path`/`ObjectName` が Sensitive に分類されています。フォレンジックダッシュボードは定義上、これらのフィールドを生の形で調査担当者に表示するものです。同ガイドの Vendor-Specific Data Controls 表を参照し、ベンダーの RBAC でダッシュボードアクセスを制限してください。

## ベンダー別 Forensics ダッシュボード実装

### Splunk

Splunk には本リポジトリ内で最も実装が進んだ出発点があります: `integrations/splunk-serverless/searches/failed-access-attempts.spl` と `last-access-by-user-path.spl` は既に `user`/`client_ip`/`path`/`operation` でグループ化しています。追加で 3 本の検索を用意すれば、DII の 4 ビュー相当が完成します:

| DII ビュー相当 | 検索ファイル | 用途 |
|----------------|-------------|------|
| Forensic User Overview | [`user-activity-timeline.spl`](../../integrations/splunk-serverless/searches/user-activity-timeline.spl) | 1 ユーザーの全活動を時系列で、audit + FPolicy 両 sourcetype を横断して表示 |
| Forensics - All Activity | `failed-access-attempts.spl`（既存） + `last-access-by-user-path.spl`（既存） | 全ユーザーを横断する集計ビュー |
| Forensic User Activity Data（IP 別ドリルダウン） | [`ip-centric-activity.spl`](../../integrations/splunk-serverless/searches/ip-centric-activity.spl) | 1 つの送信元 IP からの全活動 — 横展開/認証情報侵害の調査用 |
| Forensic Entities Page（ファイル中心） | [`file-entity-history.spl`](../../integrations/splunk-serverless/searches/file-entity-history.spl) | 1 ファイル/パスへの全活動を、触れた全ユーザーを横断して表示 |

各 `.spl` ファイルをパネルとして持つ Splunk Dashboard Studio ダッシュボードを構築し、ダッシュボード入力トークン（`$user_tok$`、`$ip_tok$`、`$path_tok$`）を使えば、調査担当者が値を 1 回入力するだけで全パネルがフィルタされます — これが DII のクリックスルー式 Forensics ナビゲーションに最も近い再現方法です。

### Datadog

Datadog には既に [Saved Views](../../integrations/datadog/README.md#saved-views) にパスベースのビューがあります。DII の User Overview → All Activity → ドリルダウンのフローを模した **Forensic Investigation** ノートブック（静的ダッシュボードではなく Datadog Notebooks）を、以下のクエリセルを順に配置して追加します:

```
# セル 1 — User Overview
source:fsxn @user:"{{user}}"
# @operation でグループ化、timeseries + top list として可視化

# セル 2 — そのユーザーの全活動（時系列）
source:fsxn @user:"{{user}}"
# Log Stream ビュー、時刻昇順でソート

# セル 3 — IP 中心のドリルダウン（横展開調査時）
source:fsxn @client_ip:"{{client_ip}}"

# セル 4 — エンティティ/ファイルドリルダウン
source:fsxn @path:"{{path}}"
```

Datadog **Notebook variables**（`{{user}}`、`{{client_ip}}`、`{{path}}`）を使うことで、インシデントごとに作り直すのではなく再利用可能なノートブックになります。調査結果は Log Explorer の CSV エクスポート機能で、調査対象の時間範囲に絞って出力できます。

### Grafana

Loki のラベルカーディナリティ制約（[正規化イベントスキーマ](normalized-event-schema.md#vendor-specific-considerations) に既に文書化済み）により、`user`、`client_ip`、`path` はラベルではなく JSON ログ本文に保持する必要があります。そのため Forensics パネルはラベルフィルタではなく `| json` パース付きの LogQL を使用します。ダッシュボードは [`integrations/grafana/dashboards/forensics-investigation.json`](../../integrations/grafana/dashboards/forensics-investigation.json) として用意されており、以下を含みます:

- `user`、`client_ip`、`path` 用のテンプレート変数（上記のカーディナリティ上の理由から、ラベルベースのドロップダウンではなく自由入力）
- 「User Activity」ログパネル: `{source="fsxn"} | json | user=~"$user"`
- 「IP-Centric Activity」ログパネル: `{source="fsxn"} | json | client_ip=~"$client_ip"`
- 「File/Entity History」ログパネル: `{source="fsxn"} | json | path=~"$path"`
- 有効なフィルタに応じて `operation` でグループ化した「Operation Breakdown」バーチャート

Grafana Cloud の **Dashboards → Import → Upload JSON file** からインポートするか、既存の[アラートルール](../../integrations/grafana/alerting/)と同じサービスアカウントトークンで併せてプロビジョニングしてください。

### Elastic

ECS フィールドマッピング（`user.name`、`source.ip`、`file.path`、`event.action`）が[正規化イベントスキーマ](normalized-event-schema.md#vendor-mapping-matrix)で既に定義されているため、カスタムダッシュボードを構築せずに Kibana の Discover + Lens で対応できます。4 ビュー相当（User Overview、All Activity、IP ドリルダウン、Entity/ファイル履歴）を完成させる具体的な KQL 保存検索と Lens ビジュアライゼーションは、[Elastic セットアップガイド](../../integrations/elastic/docs/ja/setup-guide.md#フォレンジック調査-kibana-discoverlens) を参照してください。

## 本当のギャップ（未対応部分）

本ドキュメントが対応度を過大に見せないよう、明確に「未対応」と言える部分を挙げます:

1. **組み込みのユーザー別行動 ML モデルがない。** DII SWS は学習済みの異常検知モデルを提供しますが、本リポジトリでは SIEM の ML 機能（Datadog Watchdog、Elastic ML Jobs、Splunk MLTK）を個別に設定・学習する必要があります。あるいは閾値ベースの検知（[検知ユースケース](detection-use-cases.md)参照）に頼ることになりますが、これは行動ベースラインとは誤検知の特性が異なります。
2. **全データを横断する単一ダッシュボードがない。** DII はどのストレージシステムがイベントを生成したかに関わらず 1 つの Forensics UI を提示します。本リポジトリは本質的にマルチベンダー構成であり、複数の SIEM に配信する場合、フォレンジック調査はベンダーごとに個別に行うことになります（[OTel Collector 統合](../../integrations/otel-collector/) はこれを軽減しますが完全には解消しません）。
3. **パッケージ化された Snapshot リストア Runbook がない。** Respond フェーズは保護 Snapshot を作成しますが、Recover フェーズでの実際のリストアは、本リポジトリではまだスクリプト/ガイドに落とし込まれていない手動 ONTAP 操作です。
4. **ストレージシステムを横断するビューがない。** DII SWS は 1 テナントからオンプレミス + クラウドのフリート全体を見渡せます。本リポジトリは FSx for ONTAP に限定されており、他の NetApp システムがあってもここでは相関しません。

## FAQ

**Q: Splunk、Datadog、Grafana、Elastic の 4 つすべてを実装する必要がありますか？**
A: 不要です — 既に audit/FPolicy イベントを配信している SIEM についてのみ Forensics ダッシュボードを構築してください。本ドキュメントは 4 つすべてを扱っていますが、それは本リポジトリが 4 つすべてを配信先としてサポートしているためであり、同時に 4 つ必要という意味ではありません。

**Q: これは DII SWS の Detect フェーズ（ML モデル）も置き換えますか？**
A: いいえ。本ドキュメントは ML 行動ベースラインが本当のギャップである（「本当のギャップ」項目 1）ことを明確にしています。手動での閾値調整なしのユーザー別 ML 異常検知が必須要件であれば、DII SWS（または SIEM 側の同等の ML 機能を別途設定したもの）が引き続き必要です。本リポジトリが置き換えるのは *Respond* メカニズムと *Forensics* 調査面であり、これは DII 自身が使っているものと同じ ONTAP API・同じ FPolicy/audit データを使用しています。

**Q: なぜ Forensics の項目で本リポジトリの既知のギャップと同じ NetApp KB の制約を参照しているのですか？**
A: DII SWS も本リポジトリの FPolicy パイプラインも、最終的には同じ ONTAP FPolicy メカニズムに依存しているためです。FPolicy から見えない操作（API 経由の変更、NFS 4.1）は、*両方の* システムから見えません — これはどちらかの実装が解決していない、共有のプラットフォーム制約です。

## 関連ドキュメント

- [自動インシデント対応ガイド](automated-response-guide.md) — Respond フェーズの実装（本リポジトリで DII 対応度が最も高い領域）
- [ARP インシデント対応ガイド](arp-incident-response-guide.md) — ONTAP ネイティブのランサムウェア検知による Protect/Detect
- [EMS 検知機能リファレンス](ems-detection-capabilities.md) — Detect フェーズのイベントカタログ
- [検知ユースケース](detection-use-cases.md) — Detect フェーズ設定のためのソース選定
- [正規化イベントスキーマ](normalized-event-schema.md) — 上記すべての Forensics 実装の基盤となる共有フィールド定義
- [データ分類ガイド](../en/data-classification.md) — Forensics ダッシュボードで表示される user/IP/path フィールドの PII 取り扱い
- [セキュリティ監視ナビゲーション](security-monitoring-index.md) — 全セキュリティドキュメントへのロール別ナビゲーション
