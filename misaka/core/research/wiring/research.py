"""The ``/research`` slash command: the human-only entry point to the persistent Research Workflow."""
from __future__ import annotations

import asyncio
import os
import re
import shlex
import time

from misaka.config import CFG, current_config
from misaka.core import session_overrides
from misaka.core.moments import CoreCommand
from misaka.core.platform import budget
from misaka.core.platform import tasks as task_store
from misaka.core.research import node as research_node
from misaka.core.research import planner, runs, workflow
from misaka.ui.tui.interactive.components.ask_user_question import (
    AskUserQuestionComponent,
)
from misaka.utils.values import read_field

_CON = None
_DEPTH_QUESTION = "How deep should this research run go?"
_PARALLEL_QUESTION = "How many Last Order nodes may run at once?"
_SISTER_PARALLEL_QUESTION = "How many Sister cards may be active per Last Order node?"
_ROUNDS_QUESTION = "After its first cards are back, how many more times may a node send its Sisters out before it concludes?"
_APPROVAL_QUESTION = "Should each research plan wait for your approval?"
_THRESHOLD_QUESTION = "At what share of the context window should this run's sessions compact their context?"
_OUTPUT_QUESTION = "How long may each reply in this run be, at most?"
_GLOBAL_THRESHOLD = "Global setting"
_MODEL_OUTPUT = "Model default"


def _global_threshold_label():
    from misaka.config.product import settings_document

    lcm = settings_document().get("lcm")
    value = lcm.get("context_threshold") if isinstance(lcm, dict) else None
    return f"{_GLOBAL_THRESHOLD} ({value})" if isinstance(value, (int, float)) else _GLOBAL_THRESHOLD


def _parse_threshold(answer):
    """``None`` for the global setting, else a fraction: ``0.6``, ``60%`` and ``60`` all mean 0.6."""
    text = str(answer or "").strip()
    if not text or text.startswith(_GLOBAL_THRESHOLD):
        return None
    try:
        value = float(text.rstrip("%").strip())
    except ValueError:
        raise ValueError(f"Compaction threshold must be a fraction such as 0.6 or a percentage such as 60%, not {text!r}.") from None
    if text.endswith("%") or value >= 1:
        value /= 100
    if not runs.MIN_CONTEXT_THRESHOLD <= value <= runs.MAX_CONTEXT_THRESHOLD:
        raise ValueError(f"Compaction threshold must be between {runs.MIN_CONTEXT_THRESHOLD:g} and "
                         f"{runs.MAX_CONTEXT_THRESHOLD:g} (10% to 95%), not {text!r}.")
    return round(value, 4)


def _parse_output(answer):
    """``None`` for each model's own limit, else tokens: ``64k``, ``64000`` and ``64 k`` all mean 64000."""
    text = str(answer or "").strip()
    if not text or text.startswith(_MODEL_OUTPUT):
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kK])?", text.replace(",", ""))
    if match is None:
        raise ValueError(f"Output limit must be a number of tokens such as 64000 or 64k, not {text!r}.")
    tokens = int(float(match.group(1)) * (1000 if match.group(2) else 1))
    if tokens < 1024:
        raise ValueError(f"Output limit must be at least 1024 tokens, not {text!r}.")
    return tokens


def _session_limits_text(limits):
    """The run's own session settings, for the status and start notices; empty when it has none."""
    parts = []
    if limits.get("context_threshold") is not None:
        parts.append(f"compaction at {limits['context_threshold']:g} of the window")
    if limits.get("max_output_tokens") is not None:
        parts.append(f"output limit {limits['max_output_tokens']:,} tokens")
    return "".join(f" | {part}" for part in parts)
USAGE = (
    "Usage: /research [--depth N] [--parallel N] [--sister-parallel N] [--followups N] [QUESTION]\n"
    f"       Start research at once (depth defaults to {runs.DEFAULT_LIMITS['max_depth']}, LO parallelism to "
    f"{runs.DEFAULT_LIMITS['parallel']}, Sister cards per LO to {runs.DEFAULT_LIMITS['sister_parallel']}, follow-up rounds per node to {runs.DEFAULT_LIMITS['max_followups']}).\n"
    "       Bare /research lets you pick depth, LO parallelism, Sister cards per LO, follow-ups and plan approval; your next message is the question.\n"
    "       Require approval: each root, fork and follow-up plan waits for your go-ahead in its LO window.\n"
    "       Automatic: accepted plans proceed without that extra wait; genuine clarification still applies.\n"
    "       The choice is saved for this run, including resume. The default comes from settings.json research.plan_approval (true).\n"
    "       Options precede QUESTION. A question may start with a number: a bare leading number is the depth\n"
    "       only when nothing but options follows it (/research 3, /research 3 --parallel 2 QUESTION).\n"
    "       --parallel limits LO nodes.\n"
    "       --sister-parallel N limits active Sister cards per LO; global/per-Sister admission limits still apply.\n"
    "       --followups N: after its first cards are back, how many more times a node may send its Sisters out\n"
    "       before it concludes (0-6). Talking a plan over with you is never counted.\n"
    "       /research status [RUN_ID]          show the latest run of this folder, or the run you name\n"
    "       /research stop [RUN_ID]            ask the latest active run (or RUN_ID) to stop\n"
    "       /research resume [RUN_ID] [ANSWER] resume a paused run, optionally answering its clarification questions\n"
    "       /research resume RUN_ID --here     adopt this window as the run's Last Order (it will not remember earlier turns)"
)


def _con():
    global _CON
    if _CON is None:
        _CON = task_store.connect(CFG["db"])
        runs.init(_CON)
    return _CON


def _cfg():
    """Small seam for tests and alternate frontends; production returns the live config."""
    return current_config()


def _positional_depth(words):
    """Whether a leading integer is the depth: only when nothing follows it, or an option does.
    Otherwise it opens the question ("1968 student movements", "3 main causes of ...")."""
    try:
        int(words[0])
    except ValueError:
        return False
    return len(words) == 1 or words[1].startswith("--")


def parse_command(raw):
    line = (raw or "").strip()
    head = line.split(None, 1)[0] if line else ""
    tokens: list[str] = []
    if head == "resume":
        # `resume [RUN_ID] [--here] [ANSWER...]`: the answer is free text, taken from the raw line.
        words = line.split(None, 2)
        run_id = words[1] if len(words) > 1 and words[1].startswith("r_") else None
        rest = ((words[2] if len(words) > 2 else "") if run_id else line[len("resume"):]).strip()
        here = rest == "--here" or rest.startswith("--here ")
        if here:
            rest = rest[len("--here"):].strip()
        return {"action": "resume", "run_id": run_id, "clarification": rest, "here": here}
    if head in {"help", "-h", "--help", "status", "stop"}:
        try:
            tokens = shlex.split(line)
        except ValueError as error:
            raise ValueError(f"Unclosed quote in arguments: {error}") from error
    if tokens and tokens[0] in {"help", "-h", "--help"}:
        return {"action": "help"}
    if tokens and tokens[0] == "status":
        if len(tokens) > 2:
            raise ValueError(USAGE)
        return {"action": "status", "target": tokens[1] if len(tokens) == 2 else None}
    if tokens and tokens[0] == "stop":
        if len(tokens) > 2:
            raise ValueError(USAGE)
        return {"action": "stop", "run_id": tokens[1] if len(tokens) == 2 else None}
    # Activation: [start] [DEPTH (alone or before an option)] [--depth N] [--parallel N] [--sister-parallel N] [QUESTION...]. Use the raw
    # line, not the shlex tokens: an apostrophe in "Stalin's constitution" is not an open quote.
    line = (raw or "").strip()
    words = line.split(None, 1)
    if words and words[0] == "start":
        line = words[1].strip() if len(words) > 1 else ""
        words = line.split(None, 1)
    explicit = bool(words)
    selected = {}
    while words:
        option, separator, value = words[0].partition("=")
        if option in {"--depth", "--parallel", "--sister-parallel", "--followups"}:
            key = {"--depth": "max_depth", "--parallel": "parallel",
                   "--sister-parallel": "sister_parallel", "--followups": "max_followups"}[option]
            if key in selected:
                raise ValueError(f"{option} was supplied more than once.")
            if not separator:
                words = words[1].split(None, 1) if len(words) > 1 else []
                value = words[0] if words else ""
            if not value:
                raise ValueError(f"{option} requires an integer.\n{USAGE}")
            selected[key] = value
        elif "max_depth" not in selected and _positional_depth(words):
            selected["max_depth"] = int(words[0])
        else:
            break  # the rest is the question, including any apostrophes or options within it
        line = words[1].strip() if len(words) > 1 else ""
        words = line.split(None, 1)
    limits = runs.normalize_limits(selected)
    return {"action": "activate", "depth": limits["max_depth"], "parallel": limits["parallel"],
            "sister_parallel": limits["sister_parallel"], "rounds": limits["max_followups"], "explicit": explicit, "question": line}


def _workspace(ctx):
    return task_store.canonical_workspace(getattr(ctx, "cwd", None) or os.getcwd())


def _find_run(con, target, workspace, *, active=False):
    if target:
        return runs.get(con, target)
    return runs.latest(con, workspace=workspace, active_only=active)


def _status(con, target, workspace):
    run = _find_run(con, target, workspace)
    if not run:
        return "No matching research run was found."
    value = runs.summary(con, run["id"])
    reading = budget.status(con, _cfg().get("token_cap"))
    scope = {run["id"], *(t["id"] for t in runs.tasks(con, run["id"]))}
    token_text = f" | tokens added by this run {budget.spent(con, task_ids=scope):,}"
    if reading["cap"]:
        token_text += f" | global tokens {reading['used']:,}/{reading['cap']:,}"
    return (
        f"{value['id']} | project {runs.project_name(run)!r} ({value['workspace']}) | "
        f"{value['status']}/{value['phase']} | depth {value['wave']}/{value['limits']['max_depth']} | "
        f"LO parallelism {value['limits']['parallel']} | Sister cards per LO {value['limits']['sister_parallel']} | "
        f"follow-ups per node {value['limits']['max_followups']} | "
        f"plan approval {'required' if planner.plan_waits_for_user(_cfg(), run) else 'automatic'}"
        f"{_session_limits_text(value['limits'])} | "
        f"tasks {value['tasks']} | nodes {value['nodes']} | open issues {value['open_issues']}"
        + token_text
        + (f" | error {value['last_error']}" if value["last_error"] else "")
    )


class ResearchPart:
    """Last Order's human-only ``/research`` command and run drivers."""

    def __init__(self):
        drivers = {}     # this session's research drivers; another session's are not ours to stop
        con = _con()
        # In a pane, a fork node is a pane too (its own tab beside this one); elsewhere a
        # background process.
        spawner = research_node.PaneSpawner() if os.environ.get("MISAKA_NET_PANE") else research_node.ProcessSpawner()
        self.tools = []
        self.commands = []
        self.session = None

        def send_progress(content, *, run_id=None, details=None):
            from misaka.core.moments import MEMORY

            payload = dict(details or {})
            if run_id:
                payload["run_id"] = run_id
            if payload.get("stage") in TICK_STAGES:
                payload[MEMORY] = False        # shown once in the feed, dropped from every request: not memory
            self.session.moments.send_message(
                {"customType": "research-progress", "display": True,
                 "content": content, "details": payload},
                {"deliverAs": "followUp", "triggerTurn": False},
            )

        async def drive(run_id, ctx, *, resume=False, clarification=""):
            # While the run works in this window, the window's session runs with the run's own
            # compaction threshold and output limit; a paused or finished run gives them back.
            release = session_overrides.apply(self.session, runs.session_overrides(runs.get(con, run_id)))
            try:
                def progress(event):
                    content = f"Research `{run_id}` | {event['message']}"
                    if event.get("tasks"):
                        content += "\n" + "\n".join(
                            f"- {item['title']} → Sister {item['assignee']}"
                            for item in event["tasks"])
                    send_progress(content, run_id=run_id, details=event)

                result = await workflow.run(
                    con, dict(_cfg()), spawner, run_id=run_id, progress=progress, resume=resume, clarification=clarification,
                    origin_session=getattr(getattr(ctx, "sessionManager", None), "sessionId", None), session=self.session)
                if result["reason"] == "waiting_input":
                    questions = "\n".join(f"- {q}" for q in result.get("questions") or [])
                    content = (f"""Research run `{run_id}` needs clarification:
    {questions}

    Continue with `/research resume {run_id} YOUR_ANSWER`.""")
                    kind = "research-clarification"
                    self.session.moments.send_message(
                        {"customType": kind, "display": True, "content": content,
                         "details": {"run_id": run_id, "result": result.get("run")}},
                        {"deliverAs": "followUp", "triggerTurn": False},
                    )
                else:
                    final = result.get("final") or {}
                    content = final.get("content") or f"Research run `{run_id}` finished: {result['reason']}."
                    final_artifact = final.get("artifact") if result["reason"] == "done" else None
                    if final_artifact:
                        content = (f"# Delivered final report — `{run_id}`\n\n"
                                   "This is the authoritative version; it supersedes this run's working drafts.\n"
                                   f"Report: `{final['path']}`\n\n---\n\n" + content)
                    if final.get("survey_path"):
                        content += f"\n\n---\nSurvey by node: `{final['survey_path']}`"
                    self.session.moments.send_message(
                        {"customType": "research-final", "display": True,
                         "content": content,
                         "details": {"run_id": run_id, "result": result.get("run"), "final_artifact": final_artifact}},
                        {"deliverAs": "followUp", "triggerTurn": False,
                         **({"_deliveryId": f"research-final:{run_id}:{final_artifact}"} if final_artifact else {})},
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - infrastructure failures stay visible, and the run stays resumable
                self.session.moments.send_message(
                    {"customType": "research-error", "display": True,
                     "content": f"Research run `{run_id}` paused: {type(error).__name__}: {error}\n"
                                f"Continue with `/research resume {run_id}` after fixing the problem.",
                     "details": {"run_id": run_id}},
                    {"deliverAs": "followUp", "triggerTurn": False},
                )
            finally:
                release()
                drivers.pop(run_id, None)

        def launch(run_id, ctx, *, resume=False, clarification=""):
            existing = drivers.get(run_id)
            if existing and not existing.done():
                return False
            drivers[run_id] = asyncio.create_task(drive(run_id, ctx, resume=resume, clarification=clarification))
            return True

        pending = {"depth": None, "parallel": None, "sister_parallel": None, "rounds": None, "workspace": None, "plan_approval": None,
                   "session": None}
        starts = set()

        async def begin(question, depth, parallel, workspace, ctx, rounds, sister_parallel, plan_approval, session=None):
            from misaka.core.platform import cards as card_files
            await asyncio.to_thread(card_files.init_project, workspace, draft_brief=False)
            run = runs.create(
                con, workspace=workspace, question=question,
                limits={"max_depth": depth, "parallel": parallel, "sister_parallel": sister_parallel, "plan_approval": plan_approval,
                        **({"max_followups": rounds} if rounds is not None else {}), **(session or {})},
                token_start=budget.spent(con),
                origin_session=getattr(getattr(ctx, "sessionManager", None), "sessionId", None),
            )
            # The discipline itself is not written into the transcript: `context` puts it in
            # front of the model on every request while a run of this conversation is open
            # (2026-09-18, B31: the one-off copy scrolled away, and after a while Last Order
            # went back to being an ordinary assistant in the middle of a paused run).
            self.session.moments.send_message(
                {"customType": "research-discipline", "display": True,
                 "content": f"Research mode is on for run {run['id']}: the research workflow's "
                            "rules apply to this conversation for as long as the run is open.",
                 "details": {"run_id": run["id"]}},
                {"deliverAs": "followUp", "triggerTurn": False},
            )
            launch(run["id"], ctx)
            ctx.ui.notify(
                f"Research run started: {run['id']} | project {runs.project_name(run)!r} | "
                f"maximum depth {depth} | LO parallelism {parallel} | Sister cards per LO {sister_parallel} | follow-ups per node "
                f"{runs.limits(run)['max_followups']} | plan approval {'required' if plan_approval else 'automatic'}"
                f"{_session_limits_text(runs.limits(run))}. Use /research status to check progress.",
                "info",
            )

        async def begin_safely(question, depth, parallel, workspace, ctx, rounds, sister_parallel, plan_approval, session=None):
            try:
                await begin(question, depth, parallel, workspace, ctx, rounds, sister_parallel, plan_approval, session)
            except Exception as error:  # noqa: BLE001 - the failure is shown and the question is kept for a retry
                pending["depth"] = depth
                pending["parallel"] = parallel
                pending["sister_parallel"] = sister_parallel
                pending["rounds"] = rounds
                pending["plan_approval"] = plan_approval
                pending["session"] = session
                pending["workspace"] = workspace
                send_progress(
                    f"Research startup failed: {type(error).__name__}: {error}\n"
                    "Research mode is still waiting for a question: send it again, or enter /research to leave research mode.",
                    details={"stage": "startup_error", "depth": depth, "parallel": parallel, "sister_parallel": sister_parallel,
                             "plan_approval": plan_approval},
                )

        def start_question(question, depth, parallel, workspace, ctx, rounds, sister_parallel, plan_approval, session=None):
            """Persist the question, then let this window plan it as the run's root LO."""
            self.session.moments.send_message(
                {"customType": "research-question", "display": True,
                 "content": f"Research question | {question}",
                 "details": {"question": question, "depth": depth, "parallel": parallel, "sister_parallel": sister_parallel, "rounds": rounds,
                             "workspace": workspace, "plan_approval": plan_approval, "session": session or {}}},
                {"deliverAs": "followUp", "triggerTurn": False},
            )
            task = asyncio.create_task(begin_safely(question, depth, parallel, workspace, ctx, rounds, sister_parallel, plan_approval,
                                                    session))
            starts.add(task)
            task.add_done_callback(starts.discard)

        async def capture_question(event, ctx):
            if pending["depth"] is None or event.get("source") == "extension":
                return {"action": "continue"}
            question = str(event.get("text") or "").strip()
            if not question:
                return {"action": "handled"}
            depth, parallel, rounds, workspace = pending["depth"], pending["parallel"], pending["rounds"], pending["workspace"]
            sister_parallel = pending["sister_parallel"]
            plan_approval, session = pending["plan_approval"], pending["session"]
            pending.update(depth=None, parallel=None, sister_parallel=None, rounds=None, workspace=None, plan_approval=None,
                           session=None)
            start_question(question, depth, parallel, workspace, ctx, rounds, sister_parallel, plan_approval, session)
            return {"action": "handled"}

        self._capture_question = capture_question

        async def command(raw, ctx):
            try:
                spec = parse_command(raw)
                if spec["action"] == "help":
                    ctx.ui.notify(USAGE, "info")
                    return
                if spec["action"] == "status":
                    if starts and not spec["target"]:
                        ctx.ui.notify("Research startup in progress. This window will plan the root node.", "info")
                    elif pending["depth"] is not None and not spec["target"]:
                        ctx.ui.notify(f"Research mode is waiting for a question | maximum depth {pending['depth']} | "
                                      f"LO parallelism {pending['parallel']} | Sister cards per LO {pending['sister_parallel']} | "
                                      f"plan approval {'required' if pending['plan_approval'] else 'automatic'}.", "info")
                    else:
                        ctx.ui.notify(_status(con, spec["target"], _workspace(ctx)), "info")
                    return
                if spec["action"] == "stop":
                    run = _find_run(con, spec["run_id"], _workspace(ctx), active=True)
                    if not run:
                        if pending["depth"] is not None:
                            pending.update(depth=None, parallel=None, sister_parallel=None, rounds=None, workspace=None, plan_approval=None, session=None)
                            ctx.ui.notify("Research mode closed.", "info")
                            return
                        ctx.ui.notify("No active research run.", "info")
                        return
                    runs.request_stop(con, run["id"])
                    # A waiting-input run has no driver left to observe this request.
                    if not run["driver_lock"]:
                        launch(run["id"], ctx)
                    ctx.ui.notify(
                        f"Stop request recorded for {run['id']}. Running tasks will stop or drain.",
                        "info",
                    )
                    return
                if spec["action"] == "resume":
                    run = _find_run(con, spec["run_id"], _workspace(ctx))
                    if not run:
                        raise ValueError("No research run to resume.")
                    if run["status"] == "done":
                        raise ValueError(f"Research run {run['id']} is done; start a new run.")
                    saved = run["root_session"]
                    here = getattr(getattr(ctx, "sessionManager", None), "sessionFile", None)
                    if saved and here and not spec.get("here") and os.path.realpath(saved) != os.path.realpath(here):
                        # The run's Last Order is a conversation. Driving it from another window
                        # silently rebound root_session to a Last Order that remembered none of
                        # the run's turns (2026-09-23); the CLI path already reopens the saved one.
                        raise ValueError(
                            f"Research run {run['id']} belongs to the Last Order conversation {saved}; open that "
                            f"session and resume there. `/research resume {run['id']} --here` adopts this window "
                            "instead, and its Last Order will not remember the run's earlier turns.")
                    if not launch(run["id"], ctx, resume=True, clarification=spec["clarification"]):
                        ctx.ui.notify(f"Research run {run['id']} is already running in this session.", "info")
                    else:
                        ctx.ui.notify(f"Resumed research run {run['id']}.", "info")
                    return

                if not ctx.isIdle():
                    ctx.ui.notify("The current turn is still running. Enter /research after it finishes.", "error")
                    return
                if starts or drivers:
                    ctx.ui.notify("A research run is already active in this window; stop it before starting another.", "info")
                    return
                if pending["depth"] is not None and not spec["explicit"]:
                    pending.update(depth=None, parallel=None, sister_parallel=None, rounds=None, workspace=None, plan_approval=None, session=None)
                    ctx.ui.notify("Research mode closed.", "info")
                    return
                spec["plan_approval"] = planner.plan_waits_for_user(_cfg())
                if spec.get("question"):
                    # `/research [--depth N] QUESTION`: no picker, no waiting for the next message.
                    pending.update(depth=None, parallel=None, sister_parallel=None, rounds=None, workspace=None, plan_approval=None, session=None)
                    start_question(spec["question"], spec["depth"], spec["parallel"], _workspace(ctx), ctx, spec["rounds"], spec["sister_parallel"], spec["plan_approval"])
                    return
                if not spec["explicit"]:
                    approval_options = [
                        {"label": "Require approval", "description": "Each root, fork and follow-up plan waits for your go-ahead before execution."},
                        {"label": "Automatic", "description": "Accepted plans proceed without an extra approval wait; genuine clarification still needs your input."},
                    ]
                    if not spec["plan_approval"]:
                        approval_options.reverse()
                    result = await ctx.ui.custom(
                        lambda tui, _theme, keybindings, done: AskUserQuestionComponent(
                            [{
                                "header": "Research depth",
                                "question": _DEPTH_QUESTION,
                                "multiSelect": False,
                                "options": [
                                    {"label": "2", "description": "Quick pass: follow-up branches go at most 2 levels deep."},
                                    {"label": "5", "description": "Standard deep research: follow-up branches go at most 5 levels deep."},
                                    {"label": "10", "description": "Exhaustive: follow-up branches go at most 10 levels deep. Slow and costly."},
                                ],
                            }, {
                                "header": "LO parallelism",
                                "question": _PARALLEL_QUESTION,
                                "multiSelect": False,
                                "options": [
                                    {"label": "4", "description": "Default: up to 4 LO nodes at once; independent of Sister cards per LO."},
                                    {"label": "1", "description": "One LO node at a time; lowest concurrent resource use."},
                                    {"label": "8", "description": "Up to 8 LO nodes at once; more simultaneous sessions and requests."},
                                ],
                            }, {
                                "header": "Sister cards per LO",
                                "question": _SISTER_PARALLEL_QUESTION,
                                "multiSelect": False,
                                "options": [
                                    {"label": "4", "description": "Default: up to 4 active Sister cards per LO; global admission limits still apply."},
                                    {"label": "1", "description": "One active Sister card per LO at a time."},
                                    {"label": "8", "description": "Up to 8 active Sister cards per LO, including multiple sessions of the same Sister."},
                                ],
                            }, {
                                "header": "Follow-ups",
                                "question": _ROUNDS_QUESTION,
                                "multiSelect": False,
                                "options": [
                                    {"label": "2", "description": "Default: up to two more rounds of cards after the first, per node."},
                                    {"label": "0", "description": "None: every node concludes from its first cards."},
                                    {"label": "4", "description": "Up to four more rounds per node; thorough and slow, with more plans to review if approval is required."},
                                ],
                            }, {
                                "header": "Plan approval",
                                "question": _APPROVAL_QUESTION,
                                "multiSelect": False,
                                "options": approval_options,
                            }, {
                                "header": "Compaction",
                                "question": _THRESHOLD_QUESTION,
                                "multiSelect": False,
                                "options": [
                                    {"label": _global_threshold_label(),
                                     "description": "Default: settings.json lcm.context_threshold, as every other session uses."},
                                    {"label": "0.5", "description": "Compact at half the window: smaller requests, earlier summaries."},
                                    {"label": "0.85", "description": "Compact late: more of the conversation stays verbatim; larger, costlier requests."},
                                ],
                            }, {
                                "header": "Output limit",
                                "question": _OUTPUT_QUESTION,
                                "multiSelect": False,
                                "options": [
                                    {"label": _MODEL_OUTPUT,
                                     "description": "Default: each model's own maximum (models.json or the built-in catalog)."},
                                    {"label": "64k", "description": "At most 64,000 tokens per reply, or the model's own maximum if lower."},
                                    {"label": "32k", "description": "At most 32,000 tokens per reply, or the model's own maximum if lower."},
                                ],
                            }],
                            done,
                            tui=tui,
                            keybindings=keybindings,
                        )
                    )
                    if not isinstance(result, dict) or result.get("action") == "cancel":
                        return
                    if result.get("action") == "clarify":
                        self.session.moments.send_user_message(
                            "I chose \"Chat about this\" in the research-options picker. Ask me what I want "
                            "to clarify and talk through depth, LO parallelism, Sister cards per LO, rounds, plan approval, the compaction threshold "
                            "and the output limit; do not start research yet."
                        )
                        return
                    answers = result.get("answers") or {}
                    approval = answers.get(_APPROVAL_QUESTION)
                    if approval is not None:
                        choices = {"require approval": True, "automatic": False}
                        choice = str(approval).strip().lower()
                        if choice not in choices:
                            raise ValueError("Plan approval must be Require approval or Automatic.")
                        spec["plan_approval"] = choices[choice]
                    picked = {"max_depth": answers.get(_DEPTH_QUESTION), "parallel": answers.get(_PARALLEL_QUESTION),
                              "sister_parallel": answers.get(_SISTER_PARALLEL_QUESTION),
                              "max_followups": answers.get(_ROUNDS_QUESTION)}
                    picked.update(context_threshold=_parse_threshold(answers.get(_THRESHOLD_QUESTION)),
                                  max_output_tokens=_parse_output(answers.get(_OUTPUT_QUESTION)))
                    limits = runs.normalize_limits({k: v for k, v in picked.items() if v is not None})
                    spec.update(depth=limits["max_depth"], parallel=limits["parallel"],
                                sister_parallel=limits["sister_parallel"], rounds=limits["max_followups"],
                                session=session_overrides.clean(limits))
                pending["depth"] = spec["depth"]
                pending["parallel"] = spec["parallel"]
                pending["sister_parallel"] = spec["sister_parallel"]
                pending["rounds"] = spec["rounds"]
                pending["plan_approval"] = spec["plan_approval"]
                pending["session"] = spec.get("session") or {}
                pending["workspace"] = _workspace(ctx)
                ctx.ui.notify(
                    f"Research mode enabled | maximum depth {spec['depth']} | LO parallelism {spec['parallel']} | "
                    f"Sister cards per LO {spec['sister_parallel']} | follow-ups per node {spec['rounds']} | "
                    f"plan approval {'required' if spec['plan_approval'] else 'automatic'}"
                    f"{_session_limits_text(pending['session'])} | "
                    f"workspace {pending['workspace']}. Your next regular message becomes the "
                    "research question; this Last Order writes the brief and root plan together.",
                    "info",
                )
            except (ValueError, RuntimeError) as error:
                ctx.ui.notify(str(error), "error")

        self.commands.append(CoreCommand(
            "research", "Start a persistent Research Workflow run, or check, stop, or resume one.", command))

        async def cleanup(_event, _ctx):
            startup_tasks = list(starts)
            for task in startup_tasks:
                task.cancel()
            live = list(drivers.items())
            for run_id, _task in live:       # the drivers own the run's state: they see the stop, stop their nodes and settle
                runs.request_stop(con, run_id)
            for _run_id, task in live:
                if not task.done():
                    task.cancel()
            if live:
                await asyncio.gather(*(task for _run_id, task in live), return_exceptions=True)
            if startup_tasks:
                await asyncio.gather(*startup_tasks, return_exceptions=True)
            for run_id, _task in live:
                current = runs.get(con, run_id)
                if current and current["status"] == "stopping" and not current["driver_lock"]:
                    await workflow.run(con, dict(_cfg()), spawner, run_id=run_id)

        self._cleanup = cleanup

    def attach(self, session):
        self.session = session

    async def input(self, event, ctx):
        return await self._capture_question(event, ctx)

    async def context(self, event, ctx):
        """What the model sees of the run, without editing the transcript or tool pairs: the
        status ticks of every node and card (still displayed) and the completion notices of
        research cards the phases already consumed are left out -- a run of a dozen nodes puts
        hundreds of them in the root window, and they were the bulk of what compaction ate --
        a delivered final report archives its superseded drafts, and while a run of this
        conversation is open its rules stand at the head of the request, rebuilt each time from
        the board rather than remembered from the transcript."""
        messages = event["messages"]
        session_id = getattr(getattr(ctx, "sessionManager", None), "sessionId", None)
        try:
            own_runs = runs.for_session(_con(), session_id)
        except Exception:  # noqa: BLE001 - the board is not this hook's to fail the request over
            own_runs = []
        notice = mode_notice(own_runs)
        active = {run["id"] for run in own_runs if run["status"] in runs.ACTIVE}
        delivered = {read_field(message, "details", {}).get("run_id") for message in messages
                     if read_field(message, "customType") == "research-final"
                     and (read_field(message, "details") or {}).get("final_artifact")}
        out, drafting, changed = [], False, bool(notice)
        if notice:
            out.append({"role": "custom", "customType": "research-mode", "display": False,
                        "content": notice, "timestamp": int(time.time() * 1000)})
        for message in messages:
            role, kind = read_field(message, "role"), read_field(message, "customType")
            if role == "custom" and _feed_noise(kind, read_field(message, "details") or {}, active):
                changed = True
                continue
            if kind == "research-phase" and delivered:
                details = read_field(message, "details") or {}
                drafting = details.get("stage") == "adjudication_draft" and details.get("run_id") in delivered
                if drafting:
                    changed = True
                    out.append({"role": "custom", "customType": kind, "display": False, "details": details,
                                "timestamp": read_field(message, "timestamp"),
                                "content": f"Archived adjudication drafting phase for {details['run_id']}. "
                                           "Use its delivered final report, not its superseded working drafts."})
                    continue
            elif role == "user" or (role == "custom" and kind not in {"research-progress", "sister-notification"}):
                drafting = False
            elif (role == "assistant" and drafting and read_field(message, "stopReason") == "stop"
                  and not any(read_field(part, "type") == "toolCall" for part in read_field(message, "content", []))):
                # The first completed answer belongs to this phase. A queued follow-up
                # after it is ordinary conversation and must remain in context.
                drafting = False
                changed = True
                continue
            out.append(message)
        return {"messages": out} if changed else None

    async def session_shutdown(self, event, ctx):
        await self._cleanup(event, ctx)


# Progress stages that are ticks -- a card changed status, a node changed phase, a card was
# created -- as opposed to the events Last Order acts on or the user is asked about.
TICK_STAGES = {"tasks", "node", "assigned", "red_team", "planning", "level"}


def _feed_noise(kind, details, active_runs=frozenset()):
    """A custom message of the run's feed that the model has no use for: a status tick, or the
    completion notice of a research card whose result the phase turn already read -- which is
    only ever true while that run's driver is running; a card finishing under a paused run is
    news for Last Order (2026-09-18, B26)."""
    if kind == "research-progress":
        return details.get("stage") in TICK_STAGES
    if kind == "sister-notification":
        research = details.get("research") or {}
        return (bool(research) and research.get("run_id") in active_runs
                and details.get("boardStatus", details.get("status")) == "done")
    return False


PAUSED_STATUSES = {"failed", "stopped"}


def mode_notice(own_runs):
    """The standing notice for the runs a conversation started: the workflow discipline while
    any of them is being driven, the paused notice while none is and some are not finished,
    nothing once they are all done (or there never were any)."""
    active = [run for run in own_runs if run["status"] in runs.ACTIVE]
    if active:
        ids = ", ".join(run["id"] for run in active)
        return f"{workflow.RESEARCH_DISCIPLINE.rstrip()}\nActive research run(s) of this conversation: {ids}."
    paused = [run for run in own_runs if run["status"] in PAUSED_STATUSES]
    if paused:
        return workflow.RESEARCH_PAUSED.format(
            run_ids=", ".join(run["id"] for run in paused),
            statuses=", ".join(sorted({run["status"] for run in paused})))
    return None


SESSION_KINDS = {"foreground", "dm"}
ROLES = {"last_order"}


def part(spec):
    from misaka.core.research.wiring.node import node_identity
    if spec.research_context or node_identity():  # an existing workflow already owns this session
        return None
    return ResearchPart()
