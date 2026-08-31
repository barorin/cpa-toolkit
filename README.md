# cpa-toolkit

公認会計士業務のためのプラグイン。12のワークフロー(スキル)と7つの専任サブエージェントで構成され、**高度な推論は高推論モデル(メインセッション)、情報収集・データ処理・文書読解・整形は低コストモデル** に振り分けることで、品質を保ちながら使用量を節約します。品質が要の査閲工程(reviewer)だけは逆に高推論モデルで動きます。

## 構成

### スキル(ワークフロー)

| スキル                | 用途                                                 | 主な振り分け(メイン以外)                          |
| --------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| accounting-consult    | 会計論点の相談(出典明記・最新基準の確認付き)         | 引用突合=standards-checker                        |
| company-research      | 企業調査(概要・商流・会計論点・不正リスク)とレポート | 収集=researcher / 整形=report-writer              |
| journal-analysis      | 仕訳データ分析(JET)                                  | 処理=data-processor                               |
| audit-workpaper       | 基礎資料を用いた監査調書ドラフト                     | 整形=report-writer / 査閲=reviewer                |
| analytical-procedures | 分析的手続(増減・比率・期待値分析)                   | 集計=data-processor / 整形=report-writer          |
| sampling              | 監査サンプリング(MUS・無作為・属性)                  | 抽出=data-processor                               |
| minutes-review        | 議事録・契約書からの重要事項抽出と評価               | 抽出=doc-extractor                                |
| audit-planning        | 重要性算定・RMM評価・監査アプローチ設計              | 計算=data-processor / 査閲=reviewer               |
| disclosure-check      | 財務諸表・注記の開示チェック                         | 機械的照合=data-processor/doc-extractor           |
| standards-watch       | 会計・監査基準の新着ウォッチ(定期実行対応)           | 収集=researcher                                   |
| financial-dd          | 財務DD(正常収益力・ネットデット・運転資本)           | 収集・読解・計算・整形=低コスト群 / 査閲=reviewer |
| cpa-setup             | 共通設定(事務所方針・様式・閾値)の初期登録・変更     | メインで完結                                      |

### サブエージェント

| エージェント      | model(エイリアス) | 役割                                                                                                            |
| ----------------- | ----------------- | --------------------------------------------------------------------------------------------------------------- |
| researcher        | sonnet            | Web検索・公開情報の収集(出典付き)。判断はしない                                                                 |
| data-processor    | sonnet            | データの前処理・集計・機械的テスト・サンプル抽出。解釈はしない                                                  |
| doc-extractor     | sonnet            | PDF・議事録・契約書等の大量文書からの構造化抽出。評価はしない                                                   |
| report-writer     | sonnet            | 整理済みの結論の文書整形。判断の追加・出典の創作はしない                                                        |
| standards-checker | sonnet            | 基準引用(号数・項番号)の原文突合ファクトチェック                                                                |
| translator        | haiku             | 英文資料の一次翻訳(重要文書はメインがレビュー)                                                                  |
| reviewer          | **best**          | 独立のコールドレビュー(査閲)。`best` = 利用可能な最上位モデル(Fableが使えればFable、使えなければOpus)に自動解決 |

## モデル設定の考え方(名称変更への備え)

このプラグインは、**将来モデル名が変わっても原則ノーメンテ**で動くように設計しています。

1. **スキル本文にはモデル名を書いていません。** スキルは「メイン(高推論モデル)」「低コストモデル」という役割語とエージェント名だけで書かれています。モデル名が変わってもスキルの修正は不要です。
2. **エージェントには具体的なモデルIDではなくエイリアス(`sonnet` / `haiku` / `best`)を指定しています。** エイリアスは常にその系統の現行モデルを指すため、バージョンアップ(例: Sonnet 5 → Sonnet 6)は自動で追従します。`best` は「利用可能な最上位」を指すため、Fableが使えるプランではFable、使えなければOpusに自動で解決されます。メインセッションも `claude --model best` で起動すれば同じ挙動になります。
3. **モデル指定が存在する場所は agents/\*.md のフロントマター7行だけです。** エイリアス体系自体が変わった場合(新しい階層名の登場など)も、直す場所はここだけです:

```bash
# 現在の設定を一覧
grep -n '^model:' agents/*.md
# 一括変更の例: sonnet指定を全部newnameに
sed -i 's/^model: sonnet$/model: newname/' agents/*.md
```

CLIにコピーして使っている場合は `~/.claude/agents/*.md` に対して同じ操作をします。Coworkの場合はチャットで「エージェントのモデルを〇〇に変えて」と頼めば改訂版プラグインを作れます。

4. **ファイルを編集せずに一時的に切り替えたい場合**は環境変数が使えます: `CLAUDE_CODE_SUBAGENT_MODEL=inherit`(全サブエージェントをメインと同じモデルに一括上書き。reviewerも対象になる点に注意)、`ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5` など(エイリアスの解決先を特定バージョンに固定)。

※もしお使いの環境で `best` エイリアスが未対応の場合は、上記の方法で `agents/reviewer.md` の1行を `model: opus` に変更してください。

## インストール

### Cowork(デスクトップアプリ)

チャットに届いた `.plugin` ファイルのプレビューから「追加」を押すだけです。

### Claude Code(CLI)

このリポジトリはプラグイン本体であると同時に、マーケットプレイス(`barorin-plugins`)としても登録できます。

```bash
# マーケットプレイスを登録
claude plugin marketplace add barorin/cpa-toolkit

# プラグインをインストール
claude plugin install cpa-toolkit@barorin-plugins
```

Claude Code のセッション内から行う場合は `/plugin marketplace add barorin/cpa-toolkit` → `/plugin install cpa-toolkit@barorin-plugins` です。更新は `claude plugin update cpa-toolkit`(`marketplace.json` の `version` を上げた時に配布されます)。

プラグインとして使わない場合は、中身を個人設定フォルダにコピーするだけでも動きます:

```bash
cp cpa-toolkit/agents/*.md ~/.claude/agents/
cp -r cpa-toolkit/skills/* ~/.claude/skills/
```

## 使い方

メインセッションを高推論モデルで起動します(重要):

```bash
claude --model best   # Fableが使えればFable、なければOpus
```

あとは普通に依頼するだけで、スキルが自動的に工程を振り分けます:

- 「〇〇の会計処理を相談したい」 → accounting-consult
- 「株式会社〇〇の企業調査をしてレポートにして」 → company-research
- 「この仕訳データを分析して」(CSV添付) → journal-analysis
- 「この資料から売掛金の調書を作って」 → audit-workpaper
- 「売上の増減分析をして」 → analytical-procedures
- 「この母集団から25件サンプル抽出して」 → sampling
- 「議事録から重要事項を抽出して」 → minutes-review
- 「重要性基準値の算定とリスク評価をしたい」 → audit-planning
- 「注記のチェックをして」 → disclosure-check
- 「今月の基準の新着をまとめて」「毎週届けて」 → standards-watch
- 「この会社の財務DDを手伝って」 → financial-dd

### 運用チップス

- 軽い作業の日はセッション自体を `/model sonnet` に切り替えれば、さらに節約できます。
- `opusplan` モード(計画=Opus、実行=Sonnet)は「考えてから書く」タスクと相性が良いです。
- standards-watch は週次のスケジュールされたタスクとして登録すると、毎週自動で届きます。

## 設定・記憶・スクリプト

- **共通設定**: 「初期設定をして」で cpa-setup スキルが事務所の既定値(適用基準、重要性方針、JET閾値、様式、想定読者等)を `${CLAUDE_PLUGIN_DATA}/config.json`(CLI直コピー運用では `~/.claude/cpa-toolkit-data/config.json`)に保存します。以後、全スキルが設定済み項目の確認質問を省略します。プラグイン更新でも消えない場所です。
- **記憶**: standards-watch は実行ログを持ち、前回報告分を除いた差分だけを報告します。accounting-consult は相談ログを蓄積し、過去の類似論点との整合を保ちます。
- **同梱スクリプト**: 仕訳テスト(`skills/journal-analysis/scripts/jet_tests.py`)とサンプリング(`skills/sampling/scripts/sampling.py`)は検証済みスクリプトで実行され、毎回コードを書き直しません。実行のたびにロジックが揺れず、再実行・再現が確実になり、生成トークンも節約されます。
- **Gotchas を育てる**: 各スキル末尾の Gotchas は実際の失敗を蓄積する場所です。Claudeが新しい罠を踏んだら追記してください(CLI ではファイルを直接編集、Cowork ではチャットで「〇〇のGotchasに追記して改訂版を作って」と依頼)。スキルはこの積み重ねで良くなります。

## 設計上の原則

1. サブエージェントはメインの会話コンテキストを引き継がないため、各スキルは「委譲時に必ず渡す引き渡し資料」をテンプレート化しています。
2. 低コストモデルの成果物は必ずメイン(高推論モデル)が最終レビューし、重要な成果物は reviewer(最上位モデル)の独立レビューも経てから納品します。
3. 会計基準の引用は基準名・号数・項番号まで明記し、Web検索で最新の改正状況を確認のうえ、文書納品時は standards-checker が原文と突合します。
4. 監査調書・DD報告書等はドラフト(作成補助)であり、専門家としての結論は利用者自身の責任である旨を成果物に明記します。
