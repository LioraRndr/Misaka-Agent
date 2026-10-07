"""A streaming reply must not fall behind the provider while the TUI paints it (GitHub issue #6).

The panel's Last Order died at plan submission on DeepSeek with "Connection error." while the same
run from `misaka research` (no TUI) succeeded. Reproduced against a local DeepSeek-shaped server:
every frame re-estimated the whole context for the footer (~22 ms of a ~25 ms frame), frames ran
back to back once a frame outlasted the 16 ms interval, and the OpenAI adapters spent several loop
turns per SSE event on a fresh abort task. The reply advanced about one event per frame and was
165 s behind the server after 20k characters of thinking; with a bounded receive window the server
gave up on the client mid-reply. These tests pin each of the three repairs.
"""

import asyncio
import io
import time

import httpx
import openai
import pytest

from misaka.ai.providers import (
    azure_openai_responses,
    openai_completions,
    openai_responses,
)
from misaka.ai.utils.retry import RETRYABLE_PROVIDER_ERROR_PATTERN
from misaka.core.session_manager import SessionManager
from misaka.ui.tui.interactive.components.footer import FooterComponent
from misaka.ui.tui.terminal import ProcessTerminal
from misaka.ui.tui.tui import TUI


class Terminal(ProcessTerminal):
    def __init__(self):
        super().__init__()
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()

    @property
    def columns(self):
        return 80

    @property
    def rows(self):
        return 24

    def start(self, onInput, onResize):
        self.inputHandler = onInput
        self.resizeHandler = onResize

    def stop(self):
        return None


class SlowContent:
    def render(self, _width):
        time.sleep(0.03)
        return ["a long reply, laid out whole every frame"]


@pytest.mark.asyncio
async def test_a_slow_frame_leaves_the_loop_as_long_as_it_took(monkeypatch):
    ui = TUI(Terminal())
    ui.addChild(SlowContent())
    ui.doRender()
    assert ui.lastRenderCostMs >= 30

    loop = asyncio.get_running_loop()
    delays = []
    real_call_later = loop.call_later
    monkeypatch.setattr(loop, "call_later", lambda delay, *args: delays.append(delay) or real_call_later(delay, *args))

    ui.lastRenderAt = time.perf_counter() * 1000
    ui.renderRequested = True
    ui._scheduleRender()
    ui._cancel_render_timer()
    # pi's 16 ms from the frame's start would have rendered again at once.
    assert delays[-1] >= 2 * ui.lastRenderCostMs / 1000 - 0.01

    ui.lastRenderCostMs = 1.0
    ui.lastRenderAt = time.perf_counter() * 1000
    ui._scheduleRender()
    ui._cancel_render_timer()
    assert 0.01 <= delays[-1] <= ui.MIN_RENDER_INTERVAL_MS / 1000


class Session:
    def __init__(self, cwd):
        self.sessionManager = SessionManager.inMemory(cwd=cwd)
        self.model = object()
        self.estimates = 0

    def getContextUsage(self):
        self.estimates += 1
        return {"tokens": 1, "contextWindow": 10, "percent": 10.0}


def test_footer_estimates_the_context_once_per_session_change(tmp_path):
    session = Session(str(tmp_path))
    footer = FooterComponent(session, footerData=None)

    footer.getSessionStats()
    footer.getSessionStats()
    assert session.estimates == 1, "a streaming frame must not re-estimate an unchanged session"

    session.sessionManager.appendMessage({"role": "user", "content": "hi", "timestamp": 0})
    footer.getSessionStats()
    assert session.estimates == 2

    session.model = object()
    footer.getSessionStats()
    assert session.estimates == 3


class Signal:
    aborted = False

    def __init__(self):
        self.waits = 0
        self._event = asyncio.Event()

    async def wait(self):
        self.waits += 1
        await self._event.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [openai_completions, openai_responses, azure_openai_responses])
async def test_openai_streams_wait_on_the_abort_signal_once(adapter):
    async def items():
        for index in range(50):
            yield {"index": index}

    signal = Signal()
    received = [item async for item in adapter._iterate_stream(items(), signal)]
    assert [item["index"] for item in received] == list(range(50))
    assert signal.waits == 1


def test_connection_error_names_the_transport_failure():
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    try:
        try:
            raise httpx.ReadError("[WinError 10054] An existing connection was forcibly closed")
        except httpx.ReadError as transport_error:
            raise openai.APIConnectionError(request=request) from transport_error
    except openai.APIConnectionError as error:
        message = openai_completions._format_completion_error(error)

    assert message == "Connection error. (ReadError: [WinError 10054] An existing connection was forcibly closed)"
    assert RETRYABLE_PROVIDER_ERROR_PATTERN.search(message)
    assert openai_completions._format_completion_error(RuntimeError("boom")) == "boom"
