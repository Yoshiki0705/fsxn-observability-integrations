# DII Storage Workload Security — 機能マップと対応関係の整理

🌐 **日本語**（このページ） | [English](../en/dii-capability-map.md)

## このドキュメントの目的

これまで本リポジトリでは、NetApp DII（Data Infrastructure Insights）Storage Workload Security への言及を複数箇所に追加してきました — [自動インシデント対応ガイド](automated-response-guide.md)内の比較表、ルート README のコールアウト、[NetApp Console<!-- allow:naming --> 統合](../../integrations/netapp-console/)への言及などです。しかしそれぞれは DII のある一側面（主に *封じ込め/対応* 側）を個別にカバーするに留まり、DII が全体としてどんな機能を持つのかを先に整理していませんでした。結果として「DII のようにユーザーをブロックする方法」は見つかるが、「DII は全体として何をしていて、本リポジトリはそのうちどこまでカバーしているか」が分からない、虫食い状態になっていました。

このドキュメントはまず DII SWS の機能セット全体をフェーズごとに整理し、その上で本リポジトリが「既に提供している部分」「既存の要素を組み合わせれば実現できる部分」「本当のギャップとして残っている部分」を示します。詳細な手順は各ガイドにリンクする形にし、重複記載は避けています。

> **エビデンスの区分**: 以下の DII SWS の機能説明は NetApp の公開ドキュメント（各記述に出典リンクを付記）に基づいています。「本リポジトリの対応」列は、このコードベースで実装済み・E2E 検証済みの機能を指します（例外は明記）。

## サイバーレジリエンス全体での位置づけ: NIST CSF 2.0

DII SWS の個別フェーズに入る前に、DII と本リポジトリの両方を、より広いサイバーレジリエンスの枠組みの中に位置づけておくと理解しやすくなります。[NIST Cybersecurity Framework（CSF）2.0](https://www.nist.gov/cyberframework) は、組織の *全体* のサイバーセキュリティリスク管理プログラムを 6 つの機能 — **Govern（統制）、Identify（識別）、Protect（保護）、Detect（検知）、Respond（対応）、Recover（復旧）** — に整理しており、NIST はこれに対応するランサムウェア専用プロファイルとして [NIST IR 8374r1 — Ransomware Risk Management: A Cybersecurity Framework 2.0 Community Profile](https://csrc.nist.gov/pubs/ir/8374/r1/final) を公開しています。クラウド・ストレージベンダー各社も、本ドキュメントと同じ理由で自社の CSF マッピングを公開しています — 自社ツールがどの機能をカバーし、どこが依然として組織側の責任かを顧客に示すためです。AWS は [Ransomware Risk Management on AWS Using the NIST CSF](https://docs.aws.amazon.com/whitepapers/latest/ransomware-risk-management-on-aws-using-nist-csf/technical-capabilities.html) を公開し、AWS サービスを技術的能力（Backup、Event detection、Forensics and analytics、Mitigation and containment など）として CSF 機能別に整理しています。NetApp も同様に、BlueXP<!-- allow:naming -->、ONTAP、DII SWS を CSF の各機能へマッピングした解説を公開しています（出典: [Fortify your cybersecurity defenses with NIST framework](https://www.netapp.com/it/blog/fortify-cybersecurity-nist-framework/)）。

### CSF 2.0 と、以下の NIST SP 800-61 マッピングの関係

本ドキュメントは既に DII SWS を NIST SP 800-61 のインシデント対応ライフサイクル（Protect → Detect → Contain/Respond → Recover）にマッピングしています。これは封じ込めの仕組みを比較する上でより粒度の細かい運用レベルの視点だからです。**CSF 2.0 と SP 800-61 は競合するフレームワークではなく、異なる高度で動作しています。** CSF 2.0 は Govern を頂点に置く組織全体のリスク管理の「輪」であり、SP 800-61 は実際のインシデント発生時に CSF の Detect/Respond/Recover 機能が委譲する戦術的なインシデント対応プロセスです。本ドキュメントは上から下へ読むと理解しやすくなります: 下記の CSF 2.0 表は各機能がどの組織的機能に対応するかを示し、さらに下の SP 800-61 ベースの機能対応表は Detect/Respond/Recover 内部の運用詳細を示します。

### CSF 2.0 機能マッピング

| CSF 2.0 機能 | ランサムウェア関連の達成目標 | DII SWS のアプローチ | 本リポジトリのアプローチ | ステータス |
|-------------|------------------------------|----------------------|--------------------------|-----------|
| **Govern（統制）** | リスク管理戦略、役割、ポリシー、統治体制の確立と伝達 | DII SWS の機能ではない — 統制は組織的な機能であり、DII のツールはそれを支援するが提供はしない | 本リポジトリも同様に提供していない — これは観測性/対応の「パイプライン」であり、統制プログラムではない。CloudFormation によるコード化と CloudWatch Logs の監査証跡は、統制プログラムが利用できるエビデンス（誰が何をデプロイしたか、いつ・なぜブロックが発火したか）を提供するが、戦略・役割・取締役会レベルの報告は依然として組織側の責任 | ⚠️ 設計上スコープ外 — エビデンス層については [ガバナンス・コンプライアンス](governance-and-compliance.md) と [コンプライアンスエビデンスパック](../en/compliance-evidence-pack.md) を参照 |
| **Identify（識別）** | 重要な資産・データ・依存関係の棚卸しと理解 | BlueXP<!-- allow:naming --> のデータ分類機能がストレージ全体をスキャンし、データをワークロードの重要度にマッピングして分類 | [データ分類ガイド](../en/data-classification.md) が audit/FPolicy フィールドに対するフィールドレベルの分類マトリクス（PII/Sensitive/Internal）を定義。[コンテンツレベル PII 分類スキャナー](content-classification-scanner.md) が Amazon Comprehend `DetectPiiEntities` によるコンテンツレベルの発見を追加(プレーンテキスト/構造化データ形式に限定 — ドキュメント形式のパースは未対応。詳細は同ガイドの「本当の限界」参照) | ✅ スキーマレベル分類とテキスト/構造化データのコンテンツスキャンは完全対応。ドキュメント形式(Office/PDF)のコンテンツ抽出は未対応のまま |
| **Protect（保護）** | インシデントの発生可能性と影響を抑える保護策 | ユーザー別アクセスベースライン（パッシブ監視）。基盤には ONTAP 自身の Snapshot/SnapLock による不変性を利用 | プロアクティブな ONTAP ネイティブの制御（export-policy、name-mapping）に加え、ONTAP が提供する同じ Snapshot/SnapLock 不変性を利用 — これは DII や本リポジトリ固有ではなく、共有の ONTAP プラットフォーム機能 | ✅ ストレージ層の保護策としては完全対応（共有 ONTAP メカニズム）。パイプライン自体の攻撃対象領域は IAM 最小権限と Secrets Manager のローテーションでカバー — [セキュリティ考慮事項](../en/automated-response-guide.md#security-considerations) 参照 |
| **Detect（検知）** | 継続的な監視による異常や有害イベントの発見 | ML ベースのユーザー別行動異常検知（SaaS バックエンド）に加え、ARP アラート統合 | ONTAP ARP（ネイティブのランサムウェアシグネチャ/エントロピー検知）+ EMS イベントカタログ + SIEM への委譲 ML（Datadog Watchdog、Elastic ML Jobs、Splunk MLTK） | ⚠️ 行動 ML については組み合わせが必要（下記機能対応表参照）。シグネチャ/エントロピーベース検知とクォータ異常検知は ✅ 完全対応 |
| **Respond（対応）** | 検知されたインシデントへの対応: 分析、低減、報告（CSF 2.0 では RS.AN などのサブ機能に分かれる） | DII 自身の ML 検知を起点とした、ユーザー/IP の自動ブロック + 保護 Snapshot + 管理者アラート | 任意の検知ソースから SNS 経由でトリガー可能な、同じ ONTAP ブロック/Snapshot メカニズム — [自動インシデント対応ガイド](automated-response-guide.md) 参照。Forensics ダッシュボード（本ドキュメント）が RS.AN（分析）サブ機能に対応 | ✅ 低減・分析ツールとして完全対応 |
| **Recover（復旧）** | システム・データの復旧、および関係者との復旧連携（CSF 2.0 では RC.RP — Incident Recovery Plan Execution と RC.CO — Incident Recovery Communication に分割） | 検知時点の自動 Snapshot により復旧を簡略化。RC.CO 相当のツールはアラート以上のものは公開されていない | 保護 Snapshot は存在する（Respond フェーズ）。[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) が、検証対象 Snapshot を FlexClone として複製し、隔離された S3 Access Point 経由でランサムウェア痕跡をスキャンして合否判定を記録することで RC.RP のギャップを解消 — 人間がリストアを決断する前に実行。SNS 通知は最小限の RC.CO 信号をカバーするが、関係者レベルの復旧連携ではない | ✅ RC.RP 検証は完全対応（高速な事前フィルタであり、完全なフォレンジックスキャンではない）。RC.CO の関係者連携は依然最小限の SNS 信号のまま |

> **レジリエンス成熟度の視点**: CSF 2.0 の RECOVER 機能に関する業界分析（例: [Elastio による ransomware recovery の CSF 2.0 マッピング](https://elastio.com/blog/mapping-ransomware-recovery-to-nist-csf-20)）は、ここで踏まえておくべき重要な指摘をしています — Snapshot やバックアップが存在すること自体は **Protect** のエビデンスであり、RC.RP が運用上信頼できることの証明にはなりません。RC.RP が信頼できると言えるのは、実際にテストされ、侵害されていないことが確認された復旧ポイントを指し示せる場合のみであり、単に Snapshot ジョブが完了したことではありません。自動応答モジュールは保護 Snapshot を作成します（Respond フェーズ）。[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) が、この未対応だった検証ステップ（FlexClone + 隔離スキャン + 判定結果の記録）を追加します。「Snapshot が作成された」ことと「検証済みでクリーンな復旧ポイントがあり、テスト済みである」ことは異なる成熟度レベルとして扱ってください — 本リポジトリは現在両方を提供していますが、その検証は拡張子ベースの高速な事前フィルタであり、フォレンジックグレードの完全なコンテンツスキャンではありません（両者の正確な境界については同ガイドの比較セクションと FAQ を参照）。

本ドキュメントの残りの部分では、以下で既に確立している、より粒度の細かい NIST SP 800-61 ライフサイクル（Protect/Detect/Respond/Recover/Forensics）を使用します。これは組織的なリスク態勢ではなく、封じ込めと調査の仕組みを比較するのに適した解像度だからです。

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
| Recover | 検知時点 Snapshot からの高速リストア | Respond フェーズで作成した保護 Snapshot からの手動 `volume snapshot restore` | ⚠️ 組み合わせが必要 — リストア自体は依然手動の ONTAP 操作 | [本当のギャップ](#本当のギャップ未対応部分) 項目3 |
| Recover | リストア前の検証済みクリーン復旧ポイント（RC.RP） | FlexClone + 隔離された S3 Access Point スキャン + 判定結果の記録 | ✅ 完全対応（高速な事前フィルタであり、完全なフォレンジックスキャンではない） | [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) |
| Identify | コンテンツレベルの PII/データ分類 | Amazon Comprehend `DetectPiiEntities` を S3 Access Point 経由で実行 | ✅ テキスト/構造化データ形式は完全対応。❌ Office/PDF のコンテンツ抽出はギャップ | [コンテンツレベル PII 分類スキャナー](content-classification-scanner.md) |
| Forensics | Forensic User Overview（ユーザー別活動サマリ） | audit log / FPolicy パイプラインに既に存在する正規化済み `user`/`client_ip`/`path`/`operation` フィールドから構築可能 | ⚠️ 組み合わせが必要 — 下記ベンダー別ガイダンス参照 | [ベンダー別 Forensics ダッシュボード実装](#ベンダー別-forensics-ダッシュボード実装) |
| Forensics | All Activity（時系列、フィルタ可能） | 同じ基盤フィールド。ベンダーごとにダッシュボード/保存検索が必要 | ⚠️ 組み合わせが必要 | [ベンダー別 Forensics ダッシュボード実装](#ベンダー別-forensics-ダッシュボード実装)、各ベンダーの「Forensics - All Activity」相当 |
| Forensics | User Activity Data（ドリルダウン） | 同じ基盤フィールド | ⚠️ 組み合わせが必要 | [ベンダー別 Forensics ダッシュボード実装](#ベンダー別-forensics-ダッシュボード実装)、各ベンダーの IP 別ドリルダウン（例: Splunk `ip-centric-activity.spl`） |
| Forensics | Entities Page（ファイル/オブジェクト中心の履歴） | 同じ基盤フィールド、`path` でグループ化 | ⚠️ 組み合わせが必要 | [ベンダー別 Forensics ダッシュボード実装](#ベンダー別-forensics-ダッシュボード実装)、各ベンダーのファイル中心ビュー（例: Splunk `file-entity-history.spl`） |
| Forensics | 31 日フィルタ付き CSV エクスポート | ベンダーネイティブのエクスポート（Datadog Log Explorer export、Splunk `outputcsv`、Kibana Discover CSV、Grafana パネルエクスポート） — 保持期間は設定したインデックス/保持ポリシーに依存し、31 日固定ではない | ✅ 完全対応（ベンダーネイティブ、DII の固定ウィンドウより柔軟な場合が多い） | [ベンダー別 Forensics ダッシュボード実装](#ベンダー別-forensics-ダッシュボード実装) |

凡例: ✅ 完全対応 = 同等以上の機能が存在し実装・検証済み。⚠️ 組み合わせが必要 = 基盤データは存在するが、既製のダッシュボード/Runbook は未整備 — 下記の[ベンダー別 Forensics ダッシュボード実装](#ベンダー別-forensics-ダッシュボード実装)節が Forensics ダッシュボード自体（Splunk の `.spl` 検索、Datadog Notebook、Grafana ダッシュボード JSON、Elastic の Kibana 保存検索）を提供し、[検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md)がリストア検証 Runbook を提供します。❌ ギャップ = 実際に存在せず、新規開発が必要。

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
2. **全データを横断する既製の単一ダッシュボードがない — 構築は可能だが未提供。** 本リポジトリは本質的にマルチベンダー構成であり、複数の SIEM に配信する場合、フォレンジック調査は現状ベンダーごとに個別に行うことになります。これは技術的な限界ではなく、パッケージングのギャップです。解消する経路は2つあります: (a) 全ベンダーを [OTel Collector 統合](../../integrations/otel-collector/) 経由で単一の OTLP ネイティブバックエンドにルーティングし、1 つの UI に統合する（そのバックエンドが単一のクエリポイントになるトレードオフはあります）。(b) 各ベンダーパイプラインは同じ [正規化イベントスキーマ](normalized-event-schema.md) のフィールド（`source`、`svm`、`user`、`path`、`operation`）を出力するため、ベンダー固有のストア横断でクエリできる層（例: エクスポート済みログに対する Athena、ベンダー別コネクタを持つ BI ツール）を用意すれば、特定ベンダーを単一の正とすることなく統合ビューを再構築できます。いずれも現時点で本リポジトリには既製の形で含まれていません。
3. **Snapshot リストアの検証は高速な事前フィルタであり、完全なフォレンジックグレードのスキャンやエンドツーエンドのリストアリハーサルではない。** [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) が、元々あった「検証済みでクリーンな復旧ポイントのワークフローがない」というギャップを解消します。検証対象 Snapshot を FlexClone として複製し、隔離された S3 Access Point 経由でランサムウェア関連のファイル拡張子をスキャンし、人間がリストアを決断する前に合否判定を記録する仕組みです。本当に未対応のまま残っている部分: このスキャンは拡張子パターンマッチングであり、深いコンテンツ検査ではなく、実際のリストアをエンドツーエンドで試験実施するものでもありません。「検証済み」がここで何を意味するかの正確な境界は、同ガイドの比較セクションを参照してください。
4. **ストレージシステムを横断する既製のビューがない — 構築は可能だが未提供。** DII SWS は 1 テナントからオンプレミス + クラウドのフリート全体をネイティブに見渡せます。本リポジトリはデフォルトでは FSx for ONTAP に限定されており、他の NetApp システム（オンプレミスの ONTAP、他の FSx for ONTAP ファイルシステム、他リージョン/他アカウント）は標準では相関されません。これは提供範囲のギャップであり、技術的な限界ではありません: 本リポジトリと同じ audit log / FPolicy パイプラインは、FPolicy/audit log の経路を持つ任意の ONTAP ベースシステム（オンプレミスまたはクラウド）に対してデプロイ可能であり、[マルチアカウントデプロイ](multi-account-deployment.md) の StackSets パターンは既にこのパイプラインを複数の AWS アカウント・リージョンにファンアウトしています。各デプロイのイベントに識別可能な `source`/`svm` の値を付与し（[正規化イベントスキーマ](normalized-event-schema.md) 参照）、ベンダー/クエリ層で集計すればフリート全体のビューが得られます — 本リポジトリはこの集計ダッシュボードを提供していませんが、アーキテクチャ上これを構築することを妨げるものはありません。
5. **コンテンツレベルの PII 発見は、テキスト/構造化データ形式のみをカバーする — これも技術的な上限ではない。** [コンテンツレベル PII 分類スキャナー](content-classification-scanner.md) が、元々あった「コンテンツレベルのデータ分類/発見がない」というギャップを `.txt`/`.csv`/`.json`/`.log` などの形式について Amazon Comprehend `DetectPiiEntities` により解消し、本リポジトリの [データ分類ガイド](../en/data-classification.md) のスキーマレベル（フィールド名）分類を補完します。本当に未対応のまま残っている部分: Office ドキュメントや PDF はテキスト抽出されないため、これらの形式のコンテンツレベル PII は現状検出されません。これは Comprehend やスキャン処理自体の限界ではなく、前処理ステップが未実装であることによるものです — Amazon Textract（またはドキュメントパース用の Lambda Layer）で抽出したテキストを本スキャナー既存の `classify_object` ロジックに渡せば、これらの形式もカバーできます。具体的な拡張ポイントは同ガイドの「本当の限界」と FAQ を参照してください。
6. **Govern 機能のツールがない。** リスク管理戦略、ポリシー、取締役会レベルの報告（CSF 2.0 の Govern）は依然として組織側の責任であり、本リポジトリはこれを自動化しようとしていません — DII SWS を含むどのストレージ層ツールも、このプログラムの代替にはなりません。詳細は上記の CSF 2.0 機能マッピング表を参照してください。

## FAQ

**Q: Splunk、Datadog、Grafana、Elastic の 4 つすべてを実装する必要がありますか？**
A: 不要です — 既に audit/FPolicy イベントを配信している SIEM についてのみ Forensics ダッシュボードを構築してください。本ドキュメントは 4 つすべてを扱っていますが、それは本リポジトリが 4 つすべてを配信先としてサポートしているためであり、同時に 4 つ必要という意味ではありません。

**Q: これは DII SWS の Detect フェーズ（ML モデル）も置き換えますか？**
A: いいえ。本ドキュメントは ML 行動ベースラインが本当のギャップである（「本当のギャップ」項目 1）ことを明確にしています。手動での閾値調整なしのユーザー別 ML 異常検知が必須要件であれば、DII SWS（または SIEM 側の同等の ML 機能を別途設定したもの）が引き続き必要です。本リポジトリが置き換えるのは *Respond* メカニズムと *Forensics* 調査面であり、これは DII 自身が使っているものと同じ ONTAP API・同じ FPolicy/audit データを使用しています。

**Q: なぜ Forensics の項目で本リポジトリの既知のギャップと同じ NetApp KB の制約を参照しているのですか？**
A: DII SWS も本リポジトリの FPolicy パイプラインも、最終的には同じ ONTAP FPolicy メカニズムに依存しているためです。FPolicy から見えない操作（API 経由の変更、NFS 4.1）は、*両方の* システムから見えません — これはどちらかの実装が解決していない、共有のプラットフォーム制約です。

**Q: CSF 2.0 の Govern 機能はどこに位置づけられますか？本ドキュメントでは扱っていないようですが。**
A: 意図的に扱っていません。Govern（リスク管理戦略、役割、ポリシー、取締役会による監督）は組織側の責任であり、DII SWS を含むどのストレージ層ツールも代行できません。本ドキュメントの CSF 2.0 表では Govern を設計上スコープ外と明記し、[ガバナンス・コンプライアンス](governance-and-compliance.md) と [コンプライアンスエビデンスパック](../en/compliance-evidence-pack.md) を、Govern プログラムが *入力として利用できる* エビデンス（監査証跡、コードとしてのデプロイ、ブロック/対応ログ）の参照先として案内しています。これらはプログラム自体の代替ではありません。

## 関連ドキュメント

- [自動インシデント対応ガイド](automated-response-guide.md) — Respond フェーズの実装（本リポジトリで DII 対応度が最も高い領域）
- [検証済みクリーン復旧ポイントガイド](verified-recovery-point-guide.md) — RC.RP 検証（FlexClone + 隔離スキャン + 判定結果の記録）、「本当のギャップ」項目3を解決
- [コンテンツレベル PII 分類スキャナー](content-classification-scanner.md) — Amazon Comprehend によるコンテンツレベルの PII 発見、テキスト/構造化データ形式について「本当のギャップ」項目5を解決
- [ARP インシデント対応ガイド](arp-incident-response-guide.md) — ONTAP ネイティブのランサムウェア検知による Protect/Detect
- [EMS 検知機能リファレンス](ems-detection-capabilities.md) — Detect フェーズのイベントカタログ
- [検知ユースケース](detection-use-cases.md) — Detect フェーズ設定のためのソース選定
- [正規化イベントスキーマ](normalized-event-schema.md) — 上記すべての Forensics 実装の基盤となる共有フィールド定義
- [データ分類ガイド](../en/data-classification.md) — Forensics ダッシュボードで表示される user/IP/path フィールドの PII 取り扱い、およびコンテンツレベル PII 分類スキャナーが補完するスキーマレベル分類
- [ガバナンス・コンプライアンス](governance-and-compliance.md) — 本ドキュメントが参照する Govern 機能のエビデンス層
- [コンプライアンスエビデンスパック](../en/compliance-evidence-pack.md) — Govern/RC.CO 報告用の監査証跡エビデンス
- [セキュリティ監視ナビゲーション](security-monitoring-index.md) — 全セキュリティドキュメントへのロール別ナビゲーション

## 外部参照

- [NIST Cybersecurity Framework（CSF）2.0](https://www.nist.gov/cyberframework)
- [NIST IR 8374r1 — Ransomware Risk Management: A Cybersecurity Framework 2.0 Community Profile](https://csrc.nist.gov/pubs/ir/8374/r1/final)
- [AWS — Ransomware Risk Management on AWS Using the NIST CSF](https://docs.aws.amazon.com/whitepapers/latest/ransomware-risk-management-on-aws-using-nist-csf/technical-capabilities.html)
- [NetApp — Fortify your cybersecurity defenses with NIST framework](https://www.netapp.com/it/blog/fortify-cybersecurity-nist-framework/)
- [NetApp — Data Infrastructure Insights Storage Workload Security](https://docs.netapp.com/us-en/ontap-technical-reports/ransomware-solutions/ransomware-DII-workload-security.html)
- [NetApp — Forensics Activity FAQ](https://kb.netapp.com/Cloud/BlueXP/Cloud_Insights/FAQ:_Storage_Workload_Security_Forensics_Activity) <!-- allow:naming -->
- [Elastio — Mapping Ransomware Recovery to NIST CSF 2.0](https://elastio.com/blog/mapping-ransomware-recovery-to-nist-csf-20)
