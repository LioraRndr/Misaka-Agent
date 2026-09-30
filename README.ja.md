<h1 align="center">
  <img src="assets/logo.svg" alt="" width="96" height="96"><br>
  MISAKA
</h1>

<p align="center"><strong>人文・社会科学のための、AI エージェントの研究チーム。</strong></p>

<p align="center"><em>すべての結論はレッドチームの検証を受け、根拠の資料はそのすぐ隣に置かれます、とミサカは報告します。</em></p>

<p align="center">
  <a href="LICENSE"><img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/licence-Apache_2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS, Linux and Windows" src="https://img.shields.io/badge/runs_on-macOS_%7C_Linux_%7C_Windows-555">
</p>

<p align="center"><a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · 日本語</p>

問いを渡すと、取りまとめ役の **Last Order**（打ち止め）があなたと一緒に研究計画を立て、各部分を **Sisters**（妹達）に割り振ります。Sisters はあなたが作る専門家のエージェントで、あなたの端末の中で並行して働きます。どの結論もレッドチームの検証を受け、結論が選ばなかった道はそれぞれ新しい研究になります。最終報告は研究論文として、引用したすべてのファイルと並べてプロジェクトフォルダに保存されます。

<p align="center">
  <img src="assets/tui.png" alt="MISAKA のパネル：スペース、セッション、エージェントの一覧と Last Order のウィンドウ" width="820">
</p>

<table>
<tr><td><b>レッドチームに耐える結論</b></td><td>どの結論もレッドチームの Sister の検証を受けます。Last Order は異議の一つひとつに記録を残して答えます。結論を直すか、反論するか、答えが負う代償として引き受けるか。</td></tr>
<tr><td><b>選ばなかった道も研究する</b></td><td>結論が採らなかった仮説、方法、読み方は、それぞれにチームとレッドチームがつく新しい研究になります。二つの線が挙げた同じ問いは一度だけ研究し、同じところにたどり着いた線は合流させます。</td></tr>
<tr><td><b>開いて確かめられる根拠</b></td><td>発見にはすべて出典とページが付きます。結論の隣には引用したファイルが置かれ、エージェントは引用が何ページにあるかを突き止めます。</td></tr>
<tr><td><b>主張を種類ごとに区別</b></td><td>事実・推論・解釈・価値判断を、それぞれそうと明示します。証拠で決着がつかないときは、対立する結論を並べたまま残します。</td></tr>
<tr><td><b>章で読み、ページで引く</b></td><td>PageIndex が長い文書に目次を作るので、エージェントは本を章ごとに読み、印刷されたページで引用し、引用が何ページにあるかを突き止めます。スキャン画像は英語・中国語・日本語で OCR し、DjVu も読めます。文献スキャンで、問いが研究史のどこに位置するかがわかります。</td></tr>
<tr><td><b>一語も失わない記憶</b></td><td>会話がモデルの容量を超えると、ロスレス・コンテキスト管理（LCM）が要約します。どの要約も、もとの言葉までたどり戻れます。プロジェクトのどのエージェントも同じ記憶を検索でき、意味による想起は手元の小さなモデルでも動きます。</td></tr>
<tr><td><b>検証できる研究の記録</b></td><td>計画、カード、結論のすべての版、批評、出典の一覧は、プロジェクト内の Markdown ファイルで、プロジェクトは git リポジトリです。MISAKA はあなたが求め、ファイルを確かめたときにだけコミットするので、批判を受けて議論がどう変わったかが記録に残ります。</td></tr>
<tr><td><b>異なる頭脳のチーム</b></td><td>Sister ごとに専門、スキル、モデルを持てます。Claude、GPT、Gemini、手元のマシンのモデル。Claude Code や Codex もチームに加わり、Sister と同じようにカードを受け持ちます。</td></tr>
<tr><td><b>舵を取るのはあなた</b></td><td>どの計画もあなたの了承を待ちます。了承はふつうに会話するだけです。枝ごとにパネルのタブがあり、どのエージェントにもそのペインから話しかけられます。研究は止めて、後から再開できます。</td></tr>
</table>

## クイックスタート

```sh
uv tool install "misaka[providers] @ git+https://github.com/Luciole-Studio/Misaka-Agent.git"

mkdir my-research
cd my-research
misaka setup     # サインイン、モデル選択、最初の二人の Sister を作成
misaka           # MISAKA を開いて /research と入力
```

必要なもの：macOS、Linux、または Windows（x86_64 / arm64）と [uv](https://docs.astral.sh/uv/)、git、[ripgrep](https://github.com/BurntSushi/ripgrep)、[fd](https://github.com/sharkdp/fd)、poppler、そしてモデルのプロバイダ（API キー、または ChatGPT や GitHub Copilot のサブスクリプション）。Claude のアカウントでもサインインできますが、その利用は Anthropic によってトークン単位の追加利用として課金されます。インストールはこのリポジトリから行ってください。PyPI の `misaka` は無関係のパッケージです。

[はじめに](docs/getting-started.ja.md)では、各手順と最初の研究の問いまでを順に案内しています。

## 研究の進み方

> *計画ができたよ！あなたが「いいよ」って言ったらすぐ始めるから！ってミサカはミサカは計画書を両手で差し出してみたり。*

一回の研究は、可能性のグラフです。あなたの問いが最初のノードになり、結論が選ばなかった可能性が一層ずつその下のノードになります。

<p align="center">
  <img src="assets/research-graph.ja.svg" alt="一回の研究はグラフです：あなたの問い、第 1 層に別の仮説・別の方法・問いそのものへの批判、第 2 層にそこから選ばなかった道、二つの線が挙げて一度だけ研究する問い、同じところでの合流、そして最終報告" width="820">
</p>

1. **どのノードも一つの研究です。** Last Order があなたと計画を話し合い、了承を得てから始めます。Sisters はカードを並行して進め、発見をひとつずつ出典とともに記録し、Last Order が結論を書きます。
2. **レッドチームの検証。** レッドチームの Sister が結論を検証し、もう一度読み直して、選ばなかった可能性と残した欠落を掘り起こします。Last Order はそのノードの中で異議に一つずつ答え、欠落を埋めます。直した結論は再び審査に回ります。
3. **研究のグラフが育つ。** 前提の異なる実質的な別の可能性だけが新しいノードとして開かれ、それぞれに Last Order、Sisters、レッドチームがつきます。あなたが選んだ深さまで一層ずつ進みます。二つの線が挙げた同じ問いは一度だけ研究し、同じ可能性を二度開くことはなく、同じところにたどり着いた線は合流させて突き合わせます。
4. **報告。** すべてのノードが閉じると、Last Order が全体を総覧し、答えを研究論文として書きます。注と参考文献を備え、付録にはすべての研究の筋、答えが引き受けた代償、選ばなかった道を記録します。草稿は独立したレッドチームの審査を受け、Last Order は異議の一つひとつに最終報告の中で裁定を下します。

深さ、並行数、研究の見守り方と再開は、[研究ガイド](docs/guide/research.md)（英語）にあります。

## 得られるもの

> *引用した資料は、すべて確かめられる場所に綴じてあります、とミサカは報告します。*

成果はすべてプロジェクトフォルダに書き込まれます：

```text
my-research/
├── final/<run>-final.md     最終報告。引き受けた代償と、選ばなかった道も記載
├── final/<run>-sources/     報告が引用したすべてのファイル（元の場所へのリンク）
└── nodes/<node>/            研究の一つひとつ
    ├── plan.md              Last Order の計画と、この Sisters を選んだ理由
    ├── cards/<card>/        各 Sister の成果と、レッドチームの批評
    ├── synthesis.md         結論（修正後は synthesis-2.md）
    └── SOURCES.md           結論が引用した各ファイルと、それに依拠する主張
```

MISAKA がコミットするのは、あなたが頼んだときだけです。プロジェクトが git リポジトリなら、`/commit` で、ファイルを確認して了承してからコミットします。

## よく使うコマンド

| したいこと | 入力 |
|---|---|
| MISAKA を開く | `misaka` |
| 研究を始める | `/research`、続けて問いを入力 |
| 研究の確認・停止・再開 | `/research status`、`/research stop`、`/research resume` |
| 一人の Sister と話す | `/sister 10032` |
| Sister を作る | `misaka create 10036 --desc "計量経済学と因果推論"` |
| 手元の文書を索引化 | `misaka doc scan sources/` |
| モデル選択、サインイン | `/model`、`/login` |
| すべてのコマンドを見る | チャットで `/`、端末で `misaka --help` |
| パネルのキー一覧 | `ctrl+b` を押してから `?`（[パネルガイド](docs/guide/panel.md)） |
| 更新 | `misaka update --apply` |

すべてのコマンドは[コマンドリファレンス](docs/reference/commands.md)（英語）にあります。

## ドキュメント

| したいこと | 読むもの |
|---|---|
| インストールして最初の問いを走らせる | [はじめに](docs/getting-started.ja.md) |
| 研究を走らせ、舵を取る | [研究ガイド](docs/guide/research.md) |
| チームを作る、Claude Code や Codex を加える | [チームガイド](docs/guide/team.md) |
| パネルの使い方：タブ、ペイン、キー | [パネルガイド](docs/guide/panel.md) |
| サインイン、モデル選択、ローカルモデル | [モデル](docs/guide/models.md) |
| 手元の文書とウェブを使う | [文書とウェブ](docs/guide/sources.md) |
| 問題を解決する | [トラブルシューティング](docs/guide/troubleshooting.md) |
| コマンドや設定を調べる | [コマンド](docs/reference/commands.md)、[設定](docs/reference/configuration.md) |

[docs/README.md](docs/README.md) はすべてのページの地図で、MISAKA で使う用語も説明しています。「はじめに」以外のドキュメントは、今のところ英語版のみです。

## データと費用

MISAKA が保存するものはすべてあなたのマシンの中にあります。設定、認証情報、履歴は `~/.misaka/` に、研究の成果物はプロジェクトフォルダに置かれます。プロンプトはあなたが設定したモデルプロバイダにだけ送られます。ウェブ検索は設定した検索サービスに送られ、何も設定していないときや設定したサービスが失敗したときは Exa、Parallel、Firecrawl、Keenable の無料公開枠を使います（`misaka web set keyless_fallback false` で止められます）。文献スキャンでは、問いの検索語が OpenAlex に送られます。MISAKA はテレメトリを一切送りません。

研究は大きく広がります。初期設定では最大四つの枝が同時に動き、各枝で最大四人の Sister が（マシンのメモリが許す範囲で）作業するため、深い研究では多くのモデル呼び出しが発生します。費用を抑えたいときは深さを小さく。すべての研究を通した上限を決めたいときは `~/.misaka/settings.json` に `research.token_cap` を設定してください。

## 名前の由来

MISAKA の名前は、鎌池和馬『とある魔術の禁書目録』『とある科学の超電磁砲』から借りています。原作では、妹達（シスターズ）は「超電磁砲」御坂美琴のクローンで、ミサカネットワークを通じて記憶を共有しています。

| 原作 | MISAKA |
|---|---|
| **御坂美琴**、すべての妹達のオリジナル | `MISAKA.md`：どのエージェントも自分の設定より先に読み込む、共通の人格 |
| **妹達（シスターズ）**、検体番号で呼ばれる：ミサカ10032号、10033号…… | あなたの専門家たち。それぞれ番号と専門分野と自分の `SOUL.md` を持ちます |
| **打ち止め（ラストオーダー）**、ミサカ20001号、ネットワークの上位個体 | あなたが話しかける取りまとめ役 |
| **ミサカネットワーク**、一人が学んだことを他の妹達も思い出せる | プロジェクト内の会話。そこにいるどのエージェントも検索できます |

この README の「とミサカは報告します」は演出です。エージェントの話し方は、それぞれの `SOUL.md` しだいです。妹達のように話してほしければ、`SOUL.md` に一行書き足すだけです。

MISAKA は独立したプロジェクトで、原作者および出版社とは一切関係がなく、公認も受けていません。

## 土台

MISAKA のエージェントカーネルは [pi](https://github.com/earendil-works/pi) の Python 移植で、パネルは [herdr](https://github.com/herdrdev/herdr) の移植です。各ペインの裏では [ghostty](https://github.com/ghostty-org/ghostty) の端末ライブラリが動いています。長い会話の管理は [hermes-lcm](https://github.com/stephenschoettler/hermes-lcm)、文書構造の抽出は [PageIndex](https://github.com/VectifyAI/PageIndex) を土台にし、ウェブツールとスキルは [Hermes Agent](https://github.com/NousResearch/hermes-agent) から、Office 対応は [FrontierAgent](https://github.com/ApodexAI/FrontierAgent) から移植しています。何をどこから取り込んだかは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

## ライセンス

[Apache License 2.0](LICENSE)。サードパーティのコンポーネントはそれぞれのライセンスに従い、すべて [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) に記録しています。

MISAKA を再配布したり、MISAKA をもとに作品を作ったりするときは、[NOTICE](NOTICE) の表記を残してください。Apache-2.0 は、配布物にこの表記を添えることを求めています。

<p align="center"><em>以上、ミサカネットワークより通信を終わります、ってミサカはミサカは締めくくってみたり。</em></p>
