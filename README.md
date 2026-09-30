<h1 align="center">
  <img src="assets/logo.svg" alt="" width="96" height="96"><br>
  MISAKA
</h1>

<p align="center"><strong>Pairing a DAG with symptomatic reading to unearth plural narratives: an AI agent architecture built for the humanities and social sciences.</strong></p>

<p align="center"><em>More important than presence is absence! says Misaka Misaka, rapping you on the head.</em></p>

<p align="center">
  <a href="LICENSE"><img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/licence-Apache_2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS, Linux and Windows" src="https://img.shields.io/badge/runs_on-macOS_%7C_Linux_%7C_Windows-555">
</p>

<p align="center">English · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a></p>

Break the question down with **Last Order**, the coordinator, and refine the research plan; send
each branch of the inquiry to **Sisters**, specialists who report, liaise and consult; gather
their reports, read them and write; defend the conclusion before the reviewers; and turn whatever
it cannot cover into new research. Graph algorithms manage the graph of research branches, and
the final report arrives in your project folder as a research article, every citation traceable.

<p align="center">
  <img src="assets/tui.png" alt="The MISAKA panel: spaces, sessions and agents beside Last Order's window" width="820">
</p>

<table>
<tr><td><b>No conclusion before the materials</b></td><td>Until the specialists' materials come back, Last Order draws no conclusion: she breaks the question into sub-questions and prior questions and works out how they bear on one another. The views grow out of the materials, and the final report arranges the arguments the research reached, so views that run against the mainstream are not smoothed away.</td></tr>
<tr><td><b>Each specialist with her craft</b></td><td>Each Sister brings her own specialty, skills and model to her field: Claude, GPT, Gemini, or one on your own machine; Claude Code and Codex join and take cards too. Last Order need not think about tools and keeps her context for what the specialists hand in. Spared the means, she can master the ends.</td></tr>
<tr><td><b>Symptomatic reading</b></td><td>Beyond checking facts and reasoning, the red-team Sister reads Last Order's thinking for what the conclusion leaves unsaid yet leans on. The divergence review that follows sorts these absences: an oversight the line can repair is filled inside the node; a direction its own premises keep out of view goes to Last Order, who opens it as new research or records why not. These are the two kinds of not-seeing Althusser distinguished in symptomatic reading: what was overlooked, and what the problematic does not let one see.</td></tr>
<tr><td><b>A graph of possibilities</b></td><td>Each new direction forks from Last Order's conversation, carrying all the thinking before it, and becomes a node with its own team and red team. The graph grows level by level: no possibility opens twice, a question two lines raise is researched once, and lines that meet are joined, integrated where they can be and, where they cannot, kept apart with the disagreement drawn sharply.</td></tr>
<tr><td><b>Questions can be wrong too</b></td><td>Research may conclude that a question rests on a conceptual confusion or an ideological presupposition and cannot stand as asked. That is a legitimate result; if it is your question that would change, Last Order asks you first.</td></tr>
<tr><td><b>Beyond the commonplace</b></td><td>Ask once, and a model mostly tells you what it says most often. Every plan carries a coverage table whose empty cells are declared gaps; the coverage maps come from the schemes disciplines use to classify their own literature, and literature scans show where a question sits in the scholarship.</td></tr>
<tr><td><b>Traceable</b></td><td>Citations trace to the page: PageIndex outlines long documents, so agents read a book by chapter, cite the printed page and find the page a quotation is on; OCR reads scans in English, Chinese and Japanese, DjVu included. Memory traces to the words: when a conversation outgrows the model, lossless context management (LCM) summarises it, every summary leads back to the original, and every agent in a project searches the same memory.</td></tr>
<tr><td><b>A record you can audit</b></td><td>Plans, cards, every version of a conclusion, critiques and source lists are Markdown files in your project, which is a git repository. MISAKA commits only when you ask and have seen the files, so how an argument changed under criticism stays in its history.</td></tr>
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

A run is a graph grown from possibilities. Your question is its first node, and every
possibility a conclusion passed over grows into a node below it, one level at a time.

<p align="center">
  <img src="assets/research-graph.svg" alt="A research run as a graph: your question; at level 1, another hypothesis, another method and a critique of the question; at level 2, a path one of them passed over, a question two lines raised and researched once, and two lines joined where they meet; then the report" width="820">
</p>

1. **Every node is a piece of research.** Last Order plans it with you and starts when you agree.
   Until the materials come back she breaks the question down and concludes nothing; the Sisters
   work their cards in parallel and record each finding with its source, and Last Order reads
   them before she writes the conclusion.
2. **Red team and divergence review.** A red-team Sister checks the facts and the reasoning and
   reads what the conclusion leaves unsaid; then, in a fresh session, a divergence review
   separates the possibilities the conclusion passed over from the gaps it left. Last Order
   answers every objection and fills every gap inside the node; a revised conclusion goes back for
   review.
3. **The graph grows.** Only real alternatives, resting on different premises, fork from Last
   Order's conversation as new nodes, carrying all the thinking before them, each with its own
   Last Order, Sisters and red team, level by level down to the depth you choose. A question two
   lines raise is researched once, no possibility is opened twice, and lines that reach the same
   place are joined, where they confront each other.
4. **The report.** When every node has closed, Last Order surveys them all and arranges the
   arguments the research reached into a research article, with notes, a bibliography and
   appendices that record every line of inquiry, the costs the answer accepts and the paths not
   taken. An independent red team reviews the draft, and Last Order rules on each objection in the
   final report.

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

Pi is the base because its kernel is simple and a mature community maintains it, so MISAKA can
follow its updates directly. MISAKA's graph governs the content and possibilities of research: a
node is a finished piece of research, an edge a line of questioning that forked off with its
thinking.

## Licence

[Apache License 2.0](LICENSE). Third-party components keep their own licences, recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

If you redistribute MISAKA or build on it, keep the attribution in [NOTICE](NOTICE): Apache-2.0
requires it to travel with your distribution.

<p align="center"><em>Misaka Network, signing off, says Misaka Misaka.</em></p>
