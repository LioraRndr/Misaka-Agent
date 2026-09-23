"""The compaction fence must not compound round after round.

2026-09-23 (card t_9f10b6, gpt-6-astra, 272k window): upstream's preserved-objective row is
recognised by ``startswith`` on its prefix. The host fenced the whole row, prefix included, so
every round upstream failed to recognise it, preserved it again, and the host fenced the new
row again: 31 rounds later the row was 2.9 MB, 31 fences deep, and the prompt had grown from
300k to 894k tokens with no new material -- straight into ``context_length_exceeded``."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from misaka.core.platform.prompt_guard import MARKER
from misaka.extensions.misaka_lcm.host import context_engine
from misaka.extensions.misaka_lcm.vendor.reconcile import (
    _PRESERVED_OBJECTIVE_CONTEXT_PREFIX as PREFIX,
)

SUMMARY = "[Session Arc Summary (d1, node 42)]\nWhat the round found."


@pytest.fixture
def tainted(monkeypatch):
    monkeypatch.setattr(context_engine.fence, "is_tainted", lambda *a, **k: True)
    monkeypatch.setattr(context_engine, "_summary_scope", lambda *_, **__: nullcontext())
    return SimpleNamespace(current_session_id="s1")


def test_a_fenced_summary_is_not_fenced_again(tainted):
    once = context_engine._guarded_summary(tainted, SUMMARY)
    assert once.startswith(f'<<<{MARKER} name="lcm:compaction:s1">>>')
    assert context_engine._guarded_summary(tainted, once) == once
    assert once.count("<<<UNTRUSTED-DATA") == 1


def test_the_preserved_objective_keeps_its_prefix_in_front(tainted):
    row = f"{PREFIX}\n{SUMMARY}"
    guarded = context_engine._guarded_summary(tainted, row)
    assert guarded.lstrip().startswith(PREFIX)                       # upstream's startswith still matches
    assert guarded.split("\n", 1)[1].startswith(f'<<<{MARKER} name="lcm:compaction:s1">>>')
    assert context_engine._guarded_summary(tainted, guarded) == guarded


def test_the_round_trip_with_upstream_is_stable(tainted):
    """Upstream re-preserves any objective row it does not recognise; with the prefix in front
    it recognises ours, so the row stops growing after the first round."""
    def upstream_preserve(content):
        return content if content.lstrip().startswith(PREFIX) else f"{PREFIX}\n{content}"

    row = f"{PREFIX}\n{SUMMARY}"
    sizes = []
    for _ in range(6):
        row = context_engine._guarded_summary(tainted, upstream_preserve(row))
        sizes.append(len(row))
    assert len(set(sizes)) == 1
    assert row.count(PREFIX) == 1 and row.count("<<<UNTRUSTED-DATA") == 1
    assert "-ESCAPED" not in row


def test_untainted_summaries_pass_through(monkeypatch):
    monkeypatch.setattr(context_engine.fence, "is_tainted", lambda *a, **k: False)
    built = SimpleNamespace(current_session_id="s1")
    assert context_engine._guarded_summary(built, SUMMARY) == SUMMARY
