# Research runs

This guide covers everything about `/research` that the [README](../../README.md) leaves out:
starting a run, plan approval, how each stage works, steering a run while it goes, parallelism
and cost, and what is written to disk.

## Starting a run

Research runs in a project folder and needs at least one Sister (`misaka create 10032`).

**In chat** (Last Order's window in the panel, or `misaka chat`):

- `/research` on its own opens a picker, then takes your next message as the question. It asks
  for the depth (2 for a quick pass, 5 for standard deep research, 10 for an exhaustive and costly
  one), how many Last Order nodes may run at once (4, 1 or 8), how many Sister cards each node may
  run at once (4, 1 or 8), how many extra rounds a node may take (2, 0 or 4), whether plans
  wait for your approval, when this run's sessions compact their context (your global
  `lcm.context_threshold`, 0.5 or 0.85 of the window) and how long each reply may be (each model's
  own maximum, 64k or 32k tokens). The last two apply only to this run -- the window you started it
  in while the run works there, its fork nodes and its Sisters' cards -- and never change your
  settings; an output limit above a model's own maximum stays at that maximum. "Other" takes your
  own value (`0.6` or `60%`; `48k`). Choose "Chat about this" to talk the options over with Last Order first.
- `/research [--depth N] [--parallel N] [--sister-parallel N] [--followups N] QUESTION` starts at once.
  Unset options take the defaults: depth 3, 4 nodes at once, 4 Sister cards per node, 2 extra
  rounds, and plan approval as `research.plan_approval` in `settings.json` says (on by default).
  A question may start with a number (`/research 1968 student movements in Japan`). A bare number
  is read as the depth only when nothing but options follows it: `/research 3` sets the depth and
  takes your next message as the question, and `/research 3 --parallel 2 QUESTION` works as before.

**From the shell**, in the project folder:

```sh
misaka research --depth 3 --parallel 4 --sister-parallel 4 --followups 2 "QUESTION"
```

Depth runs from 0 to 12, with the question itself at depth 0. Extra rounds run from 0 to 6.

## Plan approval

Every plan, the root's, each fork's and each follow-up round's, can wait for your go-ahead.
Two modes:

- **Require approval** (the default). A plan is written and waits. You talk it over with the Last
  Order who wrote it, and she starts it once you agree. There is no approve command and no
  keyword; she records the start when the conversation has settled it.
- **Automatic.** An accepted plan goes ahead at once. A plan that genuinely needs your input still
  asks for it.

The mode you pick is saved with the run and applies to its forks, its follow-up rounds and any
resume. `research.plan_approval: false` in `settings.json` makes Automatic the default.

Where a plan waits:

| Plan | Where you discuss it |
|---|---|
| the root's | the window you started the run in |
| a fork's | that fork's own tab in the panel |
| any plan of a shell run | the session the command prints: `misaka chat --attach --session PATH` |

While a plan waits, Last Order can revise it (a revision replaces the last in its plan file; a
plan too large for one reply arrives in several appending calls) or start it. For a follow-up round she can also withdraw the round, so the node
concludes from what it already has. For a fork's first plan she can skip the node if you decide
it is not worth researching: it closes with no cards and no conclusion, and its objection stays
on record, with your reason, for the final adjudication. To give up on the whole run, use
`/research stop`.

When a run nobody is talking to needs an answer before it can plan, it pauses with its
questions. Answer them with `/research resume RUN_ID ANSWER`.

## Inside a node

Every node, the root included, runs the same routine. Code keeps the order, the depth, the
saved state and the files straight; the models make the judgements.

**Plan.** The plan is a research design, not an answer. Last Order works out what the question
is really asking and which premises are untested, then sets out evidence needs, deliverables,
dependencies and acceptance criteria, suggests methods and source strategies with their blind
spots, and explains why each Sister fits her assignment. She names the red-team Sister, and she
ends the plan with the coverage maps she consulted and the gaps that remain. The plan is saved as
`plan.md` (and `plan.json`).

**Cards.** Each assignment becomes a card, created in dependency order. A Sister can hold several
cards at once, each in its own session. As she works she declares findings with
`misaka_card_note`: the claim, its type (fact, inference, interpretation or normative), its
source file or document and page, and an optional quotation. Declarations accumulate, and a
correction names the one it revises. The ledger records them; it does not judge them. That is
the red team's and Last Order's job.

**Rounds.** When the cards are back, Last Order either concludes or assigns another round
(`plan-2.md`, then `plan-3.md`, …), up to the run's limit. On the last allowed round she has to
conclude and say what remains unsupported.

**Conclusion.** Last Order reads the full sources, not only the summaries, and writes
`synthesis.md`: shared and competing findings, key evidence and counterevidence, methodological
limits, value premises and open questions, ending with a `## Sources` list.

**Red team.** The Sister named in the plan receives the conclusion, every plan of the node, the
evidence, and `deliberation.md`, which is Last Order's own reasoning from her turns. She writes
`critique.md` and records each issue with its kind, question, rationale, priority and whether it
is material. Only material issues lead anywhere. With none, or at the depth limit, the review is
filed in Last Order's conversation without spending a model turn, and any issues at the limit are
kept for the final adjudication.

**Children.** For each material issue, Last Order dispatches a fork of her own conversation as a
child node one level deeper, which runs this same routine with its own Sisters and red team. The
tree grows breadth-first: every node at one depth runs (up to `--parallel` at a time) before the
next depth starts.

## The final report

Once every node has closed, the root Last Order, still in the conversation she planned in, writes:

1. a **survey**: one section per node, with its question, methods, conclusion, key evidence, the
   full red-team objections and what each child found, without deciding between them;
2. a **draft** answer to the original question, keeping competing accounts, limits and what would
   change the answer;
3. after an **independent red team** reviews that exact draft (the review is tied to the draft's
   checksum), the **final report**: she accepts, rejects or leaves open each objection with her
   reasons, and ends with a section saying which objections changed the answer.

A run that stops early, because you stopped it or because the token budget ran out, writes
`final/<run>-partial.md` instead: each node's conclusion so far, how many findings the ledger
holds, and the issues left unsettled. No model call is spent on it.

## Watching and steering a run

**In the panel,** each fork node opens in a tab of its own, where its Last Order runs as an
interactive window with her Sisters in a grid beside her. What you type in that tab is a turn of
that Last Order. The tab stays open after the node closes, so you can ask her about what she
found. Closing it while the node is still running ends the node; `/research resume` retries it.

**From the shell,** there is no panel: the command owns the root, and the nodes run as background
processes. `misaka chat --attach --session PATH` connects you to any of them. Your input goes to
that session directly, with no second model in between. Enter steers a busy session or starts a
turn in an idle one. `/pause` holds the session at its next request, tool or workflow boundary,
and `/resume` releases it; tools and agents already running are not stopped. Closing an attached
window only detaches.

| To | In chat | From the shell |
|---|---|---|
| see a run's state | `/research status [RUN_ID]` | `misaka board` |
| stop a run | `/research stop [RUN_ID]` | Ctrl+C in the running command |
| resume a run | `/research resume [RUN_ID] [ANSWER]` | `misaka research --resume RUN_ID` |
| resume in another window | `/research resume RUN_ID --here` | |

A resumed run needs the Sisters its cards were assigned to; recreate any you removed. While a
run is paused, the Last Order of that conversation will talk about it but will not carry on the
research herself.

## Parallelism and cost

`--parallel N` limits how many Last Order nodes run at once (default 4). `--sister-parallel N`
limits how many Sister cards each node runs at once (default 4); two sessions of the same Sister
take two slots. Both are saved with the run and reused on resume and in forks.

The machine sets its own ceiling on top: `network.max_concurrent_sisters` (free memory divided
by 256 MiB, between 4 and 12) and `network.max_concurrent_per_sister`. Cards waiting on other
cards also wait. These limits count cards, not windows or the sub-agents a Sister starts.

`research.token_cap` sets a token budget for the board (0, the default, means none). When it
runs out, the run stops with a partial report.

## On disk

```
your-project/
├── PROJECT.md                          the brief; Last Order keeps it current
├── nodes/<node>/                       the root's folder is named after the run
│   ├── plan.md, plan.json              plan-2.md … for later rounds
│   ├── synthesis.md                    the node's conclusion
│   ├── deliberation.md                 Last Order's reasoning, for the red team
│   ├── cards/<card>/                   each card's output, its own SOURCES.md and sources/
│   └── SOURCES.md, sources/            what the node's conclusion cites
└── final/
    ├── <run>-question.md
    ├── <run>-survey.md
    ├── <run>-draft.md
    ├── <run>-final.md                  (or <run>-partial.md)
    └── <run>-SOURCES.md, <run>-sources/
```

`SOURCES.md` and `sources/` are rebuilt from scratch each time a card, node or run settles.
They are derived: never registered, indexed or committed, and anything edited by hand in them is
gone at the next rebuild. Each file in `sources/` is a hard link to where it already lives in the
project, or a copy where a link is impossible. Cite the original files, not the bundle.

`/research resume` in the window belongs to the run's own Last Order conversation; another window is
refused and told which session to open, and `--here` adopts it on purpose (that Last Order will not
remember the run's earlier turns). The CLI form reopens the saved conversation itself.

If the project is a git repository, MISAKA commits when a node closes, when a run stops and when
it finishes: the nodes' plans and conclusions, every card's contract and output folder (without
its derived bundle), and `PROJECT.md`. `misaka init` writes a `.gitignore` for the caches, the
download folder and the bundles. Conversations are kept under
`~/.misaka/state/sessions/research/<run>--<scope>/`.
