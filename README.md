<h1 align="center">
  <img src="assets/logo.svg" alt="" width="96" height="96"><br>
  MISAKA
</h1>

<p align="center"><strong>A research team of AI agents for the humanities and social sciences.</strong></p>

<p align="center"><em>Every conclusion faces a red team and keeps its sources beside it, says Misaka.</em></p>

<p align="center">
  <a href="LICENSE"><img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/licence-Apache_2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS, Linux and Windows" src="https://img.shields.io/badge/runs_on-macOS_%7C_Linux_%7C_Windows-555">
</p>

<p align="center">English · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a></p>

You ask a question. **Last Order**, the coordinator, plans the research with you and hands the
parts to **Sisters**, the specialists you create. They work in parallel in your terminal, a red
team attacks every conclusion, and the paths a conclusion passed over become research of their
own. The report arrives in your project folder as a research article, beside every file it cites.

<p align="center">
  <img src="assets/tui.png" alt="The MISAKA panel: spaces, sessions and agents beside Last Order's window" width="820">
</p>

<table>
<tr><td><b>Conclusions that survive a red team</b></td><td>Every conclusion faces a red-team Sister. Last Order answers each objection on the record: she revises, rebuts, or accepts it as a cost the answer carries.</td></tr>
<tr><td><b>The roads not taken, explored</b></td><td>Hypotheses, methods and readings a conclusion passed over become research of their own, each with its own team and red team. A question two lines raise is researched once, and lines that meet are joined.</td></tr>
<tr><td><b>Evidence you can open</b></td><td>Every finding names its source and page. Each conclusion keeps the files it cites beside it, and agents find the page a quotation is on.</td></tr>
<tr><td><b>Claims labelled for what they are</b></td><td>Facts, inferences, interpretations and value judgements are declared as such. Where the evidence cannot decide, rival conclusions stand side by side.</td></tr>
<tr><td><b>Books read by chapter and page</b></td><td>PageIndex outlines long documents, so agents read a book by chapter, cite the printed page and find the page a quotation is on. OCR reads scans in English, Chinese and Japanese, DjVu included, and literature scans show where a question sits in the scholarship.</td></tr>
<tr><td><b>A memory that loses nothing</b></td><td>When a conversation outgrows the model, lossless context management (LCM) summarises it, and every summary leads back to the exact words it came from. Every agent in a project searches the same memory, and recall by meaning can run on a small local model.</td></tr>
<tr><td><b>A record you can audit</b></td><td>Plans, cards, every version of a conclusion, critiques and source lists are Markdown files in your project, which is a git repository. MISAKA commits only when you ask and have seen the files, so how an argument changed under criticism stays on the record.</td></tr>
<tr><td><b>A team of different minds</b></td><td>Each Sister has her own specialty, skills and model: Claude, GPT, Gemini, or one on your own machine. Claude Code and Codex join as teammates and take cards like any Sister.</td></tr>
<tr><td><b>Research you steer</b></td><td>Every plan waits for your word, given in plain conversation. Each branch has its own tab in the panel, with every agent in a pane you can step into. Runs stop and resume.</td></tr>
</table>

## Quick start

```sh
uv tool install "misaka[providers] @ git+https://github.com/Luciole-Studio/Misaka-Agent.git"

mkdir my-research
cd my-research
misaka setup     # sign in, pick a model, create your first two Sisters
misaka           # open MISAKA and type /research
```

You need macOS, Linux or Windows (x86_64 or arm64) with [uv](https://docs.astral.sh/uv/), git,
[ripgrep](https://github.com/BurntSushi/ripgrep), [fd](https://github.com/sharkdp/fd) and
poppler, and access to a model provider: an API key, or a ChatGPT or GitHub Copilot subscription.
A Claude account signs in too; Anthropic bills that use per token as extra usage. Install from
this repository: the `misaka` package on PyPI is an unrelated project.

[Getting started](docs/getting-started.md) walks you through each step and your first research
question.

## How a research run works

> *The plan's ready! Misaka Misaka starts the moment you say so, says Misaka Misaka, holding it out with both hands.*

A run is a graph of possibilities. Your question is its first node, and the possibilities a
conclusion passed over become the nodes below it, one level at a time.

<p align="center">
  <img src="assets/research-graph.svg" alt="A research run as a graph: your question; at level 1, another hypothesis, another method and a critique of the question; at level 2, a path one of them passed over, a question two lines raised and researched once, and two lines joined where they meet; then the report" width="820">
</p>

1. **Every node is a piece of research.** Last Order plans it with you and starts when you agree.
   The Sisters work their cards in parallel and record each finding with its source, and Last
   Order writes the conclusion.
2. **A red team reviews it.** A red-team Sister challenges the conclusion, then reads it again for
   the possibilities it passed over and the gaps it left. Last Order answers every objection and
   fills every gap inside the node; a revised conclusion goes back for review.
3. **The graph grows.** Only real alternatives, resting on different premises, open as new nodes,
   each with its own Last Order, Sisters and red team, level by level down to the depth you
   choose. A question two lines raise is researched once, no possibility is opened twice, and
   lines that reach the same place are joined, where they confront each other.
4. **The report.** When every node has closed, Last Order surveys them all and writes the answer
   as a research article, with notes, a bibliography and appendices that record every line of
   inquiry, the costs the answer accepts and the paths not taken. An independent red team reviews
   the draft, and Last Order rules on each objection in the final report.

The [research guide](docs/guide/research.md) covers depth, parallelism, following a run and
resuming it.

## What you get

> *Every source is filed where you can check it, Misaka reports.*

Everything is written into your project folder:

```text
my-research/
├── final/<run>-final.md     the report, with the costs it accepts and the paths not taken
├── final/<run>-sources/     every file the report cites, linked in place
└── nodes/<node>/            each piece of research
    ├── plan.md              what Last Order planned, and why these Sisters
    ├── cards/<card>/        each Sister's work, and the red team's critique
    ├── synthesis.md         the conclusion (synthesis-2.md once revised)
    └── SOURCES.md           every file the conclusion cites, and which claims rest on it
```

MISAKA commits only when you ask. If the project is a git repository, `/commit` commits it after
you have seen the files and agreed.

## Everyday commands

| To | Type |
|---|---|
| open MISAKA | `misaka` |
| start a research run | `/research`, then your question |
| check, stop or resume a run | `/research status`, `/research stop`, `/research resume` |
| talk to one Sister | `/sister 10032` |
| create a Sister | `misaka create 10036 --desc "Econometrics and causal inference"` |
| index your documents | `misaka doc scan sources/` |
| choose a model, sign in | `/model`, `/login` |
| see every command | `/` in chat, `misaka --help` in the terminal |
| see the panel's keys | `ctrl+b`, then `?` ([panel guide](docs/guide/panel.md)) |
| update | `misaka update --apply` |

The [command reference](docs/reference/commands.md) lists them all.

## Documentation

| To | Read |
|---|---|
| install and run your first question | [Getting started](docs/getting-started.md) |
| run and steer research | [Research runs](docs/guide/research.md) |
| build your team, add Claude Code or Codex | [The team](docs/guide/team.md) |
| find your way around the panel: tabs, panes, keys | [The panel](docs/guide/panel.md) |
| sign in, choose models, use a local model | [Models](docs/guide/models.md) |
| work with your documents and the web | [Documents and the web](docs/guide/sources.md) |
| fix a problem | [Troubleshooting](docs/guide/troubleshooting.md) |
| look up a command or a setting | [Commands](docs/reference/commands.md), [Configuration](docs/reference/configuration.md) |

[docs/README.md](docs/README.md) is the map of every page, with the words MISAKA uses.

## Your data and your bill

Everything MISAKA keeps stays on your machine: settings, credentials and history in
`~/.misaka/`, research output in your project folder. Your prompts go only to the model
providers you set up. Web searches go to the search services you set up, or to the free public
tiers of Exa, Parallel, Firecrawl and Keenable when there are none or one fails
(`misaka web set keyless_fallback false` turns that off). Literature scans send a question's
search terms to OpenAlex. MISAKA sends no telemetry.

A research run fans out: by default up to four branches at once, each with up to four Sisters
working as far as your machine's memory allows, so a deep run makes many model calls. Choose a
smaller depth for a cheaper run, and set `research.token_cap` in `~/.misaka/settings.json` for a
hard budget across all runs.

## About the name

MISAKA takes its names from Kazuma Kamachi's *A Certain Magical Index* and *A Certain
Scientific Railgun*, in which the Sisters, clones of the Railgun Misaka Mikoto, share their
memories through the Misaka Network.

| In the story | In MISAKA |
|---|---|
| **Misaka Mikoto**, the original every Sister comes from | `MISAKA.md`, the identity every agent loads before her own |
| **The Sisters**, known by serial number: Misaka 10032, 10033, … | your specialists, each with a number, a specialty and her own `SOUL.md` |
| **Last Order**, Misaka 20001, who commands the network | the coordinator you talk to |
| **The Misaka Network**, where what one Sister learns, the others can recall | the project's conversations, which every agent in it can search |

The "says Misaka" lines in this README are flavour; your agents talk however their `SOUL.md`
tells them to. One line in `SOUL.md` makes them talk like the Sisters.

MISAKA is an independent project. It is not affiliated with or endorsed by the author or the
publishers of the series.

## Built on

MISAKA's agent kernel is a Python port of [pi](https://github.com/earendil-works/pi), and its
panel is a port of [herdr](https://github.com/herdrdev/herdr), with
[ghostty](https://github.com/ghostty-org/ghostty)'s terminal library behind every pane. It
builds on [hermes-lcm](https://github.com/stephenschoettler/hermes-lcm) for long conversations
and [PageIndex](https://github.com/VectifyAI/PageIndex) for document structure, and ports web
tools and skills from [Hermes Agent](https://github.com/NousResearch/hermes-agent) and Office
support from [FrontierAgent](https://github.com/ApodexAI/FrontierAgent).
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) records what came from where.

## Licence

[Apache License 2.0](LICENSE). Third-party components keep their own licences, recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

If you redistribute MISAKA or build on it, keep the attribution in [NOTICE](NOTICE): Apache-2.0
requires it to travel with your distribution.

<p align="center"><em>Misaka Network, signing off, says Misaka Misaka.</em></p>
