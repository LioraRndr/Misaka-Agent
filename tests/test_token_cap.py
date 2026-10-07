"""research.token_cap: every model request leased and recorded, per research run (issue #10 plan).

A run used to get one fixed 32,768-token slice for its whole life -- smaller than one research
request, so a cap stopped every run at its first call -- and only a session's own turns were
bounded: compaction, the vision bridge, MoA and LCM spent outside it, most of them unrecorded."""
import asyncio
import json
import threading
import time
from contextlib import closing
from types import SimpleNamespace

import pytest

from misaka.ai import api_registry
from misaka.ai.api_registry import ApiProvider, register_api_provider
from misaka.ai.models import get_model
from misaka.ai.providers._common import _empty_usage
from misaka.ai.stream import complete_simple
from misaka.ai.types import (
    AssistantMessage,
    DoneEvent,
    SimpleStreamOptions,
    TextContent,
    TextDeltaEvent,
)
from misaka.ai.utils.event_stream import AssistantMessageEventStream
from misaka.ai.utils.retry import RETRYABLE_PROVIDER_ERROR_PATTERN
from misaka.core.network import dispatch, worker
from misaka.core.platform import budget, metering, repo, tasks
from misaka.core.research import runs

USED = 1500


@pytest.fixture
def board(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "enabled", lambda *a, **k: False)
    monkeypatch.setattr(tasks, "task_state_dir", lambda tid: str(tmp_path / "state" / tid))
    path = str(tmp_path / "board.db")
    with closing(tasks.connect(path)) as con:
        runs.init(con)
        run = runs.create(con, workspace=str(tmp_path), question="How was the salt monopoly run?")
        card = tasks.create_task(con, "licences", assignee="10032", workspace=str(tmp_path))
        runs.link_task(con, run["id"], card, kind="research", node=runs.root(con, run["id"]), local_id="a")
        yield SimpleNamespace(con=con, path=path, run=run["id"], card=card)


# -- the ledger ----------------------------------------------------------------------------------------

def test_a_request_is_granted_waits_or_stops_at_the_cap(board):
    con, run = board.con, board.run
    granted = budget.lease_request(con, 10_000, run, 1, need=2_000, want=8_000)
    assert granted["status"] == "granted" and granted["tokens"] == 8_000
    assert budget.lease_request(con, 10_000, board.card, 1, need=3_000, want=5_000)["status"] == "wait", \
        "the card shares its run's cap; what is in flight ends"
    assert budget.settle_request(con, granted["lease"], run, 1, 7_500)
    assert budget.lease_request(con, 10_000, board.card, 1, need=3_000, want=5_000)["status"] == "exhausted", \
        "what is spent does not come back"
    assert budget.spent(con, task_ids=budget.scope(con, run)) == 7_500
    assert budget.status(con, 10_000, task_id=board.card)["used"] == 7_500


def test_outside_a_run_nothing_is_capped_but_everything_is_recorded(board):
    con = board.con
    reading = budget.lease_request(con, 10, "dm:10032", 0, need=5_000, want=9_000)
    assert reading == {"status": "granted", "lease": None, "tokens": 9_000, "used": 0, "held": 0, "cap": 0}
    assert budget.settle_request(con, None, "dm:10032", 0, 9_000)
    assert budget.spent(con, task_ids={"dm:10032"}) == 9_000
    assert not budget.exhausted(con, 10, task_id="dm:10032")
    assert budget.exhausted(con, 9_000, task_id=board.run) is False


def test_an_expired_lease_is_charged_once(board):
    con, run = board.con, board.run
    lease = budget.lease_request(con, 100_000, run, 1, need=1_000, want=4_000)["lease"]
    con.execute("UPDATE budget_reservations SET expires_at=0 WHERE id=?", (lease,))
    assert budget.reserved(con, task_id=run) == 0
    assert budget.spent(con, task_ids={run}) == 4_000, "a request whose process died is charged in full"
    assert budget.settle_request(con, lease, run, 1, 1_200) is False
    assert budget.spent(con, task_ids={run}) == 4_000


def test_spent_plus_in_flight_never_passes_the_cap(board):
    cap, errors = 200_000, []

    def client():
        with closing(tasks.connect(board.path)) as con:
            for _ in range(60):
                reading = budget.lease_request(con, cap, board.card, 1, need=500, want=3_000)
                spent = budget.spent(con, task_ids=budget.scope(con, board.run))
                if spent + budget.reserved(con, task_id=board.run) > cap:
                    errors.append(spent)
                if reading["status"] == "granted":
                    budget.settle_request(con, reading["lease"], board.card, 1, reading["tokens"] // 2)

    threads = [threading.Thread(target=client) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert budget.spent(board.con, task_ids=budget.scope(board.con, board.run)) <= cap


# -- the meter -------------------------------------------------------------------------------------------

@pytest.fixture
def provider(monkeypatch):
    """A provider that answers with fixed usage and remembers the options it was sent."""
    sent = []

    def stream_simple(model, context, options=None):
        sent.append(options)
        out = AssistantMessageEventStream()

        async def answer():
            usage = _empty_usage()
            usage.input, usage.output, usage.totalTokens = USED - 500, 500, USED
            message = AssistantMessage(content=[TextContent(text="the yards")], api=model.api, provider=model.provider,
                                       model=model.id, usage=usage, stopReason="stop", timestamp=0)
            out.push(TextDeltaEvent(contentIndex=0, delta="the yards", partial=message))
            out.push(DoneEvent(reason="stop", message=message))
            out.end(message)

        asyncio.get_running_loop().create_task(answer())
        return out

    register_api_provider(ApiProvider(api="metered-test", stream=stream_simple, streamSimple=stream_simple),
                          source_id="token-cap-test")
    monkeypatch.setattr(api_registry, "_request_meter", metering.meter)
    model = get_model("anthropic", "claude-sonnet-4-5").model_copy(update={"api": "metered-test", "maxTokens": 8_000})
    yield SimpleNamespace(model=model, sent=sent)
    api_registry.unregister_api_providers("token-cap-test")


def _ask(model, options=None):
    return asyncio.run(complete_simple(model, {"messages": [{"role": "user", "content": "hi", "timestamp": 0}]}, options))


def test_a_request_is_recorded_and_its_lease_given_back(board, provider):
    with budget.usage_context(board.path, board.card, 1, 1_000_000):
        message = _ask(provider.model, SimpleStreamOptions(reasoning="high", maxTokens=50_000))
    assert message.stopReason == "stop"
    assert budget.spent(board.con, task_ids={board.card}) == USED, "recorded once, as it ended"
    assert budget.reserved(board.con) == 0
    options = provider.sent[0]
    assert options.reasoning == "high", "the lease pays for reasoning; it is no longer switched off"
    assert options.maxTokens <= provider.model.maxTokens


def test_the_output_limit_shrinks_to_what_the_run_has_left(board, provider):
    with budget.usage_context(board.path, board.card, 1, 6_000):
        _ask(provider.model)
    assert provider.sent[0].maxTokens < 6_000 - 4_096


def test_a_run_that_has_spent_its_cap_stops_with_a_reason_no_retry_matches(board, provider):
    budget.settle_request(board.con, None, board.run, 1, 99_000)
    with budget.usage_context(board.path, board.card, 1, 100_000):
        message = _ask(provider.model)
    assert message.stopReason == "error" and worker.stopped_at_cap(message.errorMessage)
    assert not RETRYABLE_PROVIDER_ERROR_PATTERN.search(message.errorMessage)
    assert provider.sent == [], "nothing was sent"


def test_without_a_ledger_a_request_is_untouched(provider, monkeypatch):
    for name in ("MISAKA_USAGE_DB", "MISAKA_USAGE_TASK_ID"):
        monkeypatch.delenv(name, raising=False)
    _ask(provider.model, SimpleStreamOptions(maxTokens=123))
    assert provider.sent[0].maxTokens == 123


def test_a_local_allowance_bounds_a_session_with_no_board(provider):
    async def two():
        with metering.local_allowance(USED + 5_000):
            context = {"messages": [{"role": "user", "content": "hi", "timestamp": 0}]}
            first = await complete_simple(provider.model, context)
            second = await complete_simple(provider.model, context)
            return first, second, metering.allowance()
    first, second, left = asyncio.run(two())
    assert first.stopReason == "stop" and second.stopReason == "error"
    assert left == (5_000, USED + 5_000)


def test_a_wait_ends_when_the_request_is_aborted(board, provider):
    lease = budget.lease_request(board.con, 20_000, board.run, 1, need=1_000, want=19_000)["lease"]
    assert lease
    signal = SimpleNamespace(aborted=False)

    async def abort_soon():
        await asyncio.sleep(0.3)
        signal.aborted = True

    async def ask():
        asyncio.get_running_loop().create_task(abort_soon())
        with budget.usage_context(board.path, board.card, 1, 20_000):
            return await complete_simple(provider.model, {"messages": []}, SimpleStreamOptions(signal=signal))

    started = time.monotonic()
    message = asyncio.run(ask())
    assert message.stopReason == "aborted" and time.monotonic() - started < 3


def test_the_provider_gets_the_callers_signal(board, provider):
    """0.18.9 deep-copied the options: an Event a provider had already waited on dragged the running
    loop into the copy ("cannot pickle '_asyncio.Task' object" on every card's second request), and
    the copy's signal never fired, so nothing could abort a metered request."""
    from misaka.agent.agent import AbortController

    async def ask():
        controller = AbortController()
        waiter = asyncio.ensure_future(controller.signal.wait())     # a provider waited on it before
        await asyncio.sleep(0)
        with budget.usage_context(board.path, board.card, 1, 1_000_000):
            message = await complete_simple(provider.model, {"messages": []},
                                            SimpleStreamOptions(signal=controller.signal, maxTokens=4_000))
        waiter.cancel()
        return controller, message

    controller, message = asyncio.run(ask())
    assert message.stopReason == "stop"
    assert provider.sent[0].signal is controller.signal
    assert provider.sent[0].maxTokens <= 4_000


# -- no second count ----------------------------------------------------------------------------------------

def test_an_agent_end_event_carries_no_usage_any_more():
    line = json.dumps({"type": "agent_end", "messages": [{"role": "assistant", "usage": {"totalTokens": 900}}]})
    assert dispatch._compact_event(line) == '{"type": "agent_end"}'


def test_a_card_stopped_by_the_cap_waits_ready_instead_of_failing():
    assert worker.stopped_at_cap(f"{budget.EXHAUSTED_MESSAGE}: this research run has spent 10 of 10 tokens.")
    assert not worker.stopped_at_cap("Connection error.")


def test_a_refused_request_stops_the_whole_run_until_the_cap_is_raised(board, provider):
    """A request that does not fit stops every driver and card of the run -- not only its own
    session, or a card sent back to ready would be relaunched for ever while spent < cap."""
    with budget.usage_context(board.path, board.card, 1, 3_000):
        message = _ask(provider.model)
    assert worker.stopped_at_cap(message.errorMessage)
    assert "the next request needs up to" in message.errorMessage
    assert budget.exhausted(board.con, 3_000, task_id=board.run), "spent is 0, and the run has still reached it"
    assert budget.status(board.con, 3_000, task_id=board.run)["mode"] == "stop"
    assert not budget.exhausted(board.con, 2_000_000, task_id=board.run), "a higher cap clears it"
