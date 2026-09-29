"""Every message has exactly one recipient, fixed when it is sent.

2026-09-29: a message to a bare name (`10036`) was a row every live session of that role could
claim, and one home held a test space's `10036`/`10037` windows beside a research run's
`10036`/`10037` cards -- whichever polled first read the mail. Now a card id reaches that card's
running attempt, a session id that conversation, and a name the one live session of that role in
the sender's panel space; with none there the role's contact session (`misaka dm`) gets it, with
several the message is refused and they are listed.

Nothing here is mocked but the process start of a wake-up: the catalog, the board, the mailbox and
the liveness check are the real ones, in the test's own home."""
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from misaka.config import CFG, home
from misaka.core import session_catalog
from misaka.core.network import messages
from misaka.core.platform import cards, processes, tasks

BODY = "## deliverable\nnotes.md\n"
SPACE_T1 = "w1111aaaa"      # the research run's space
SPACE_T2 = "w2222bbbb"      # a test space on the same home
ME = os.getpid()
MY_IDENTITY = processes.identity(ME)


def _sid():
    return str(uuid.uuid4())


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Sisters, a board, a mailbox and a catalog index, all in this test's home."""
    for name in ("MISAKA_USAGE_DB", "MISAKA_SISTER_OWNER_DB", "MISAKA_NET_SPACE", "MISAKA_USAGE_GENERATION",
                 "MISAKA_SISTER_OWNER_GENERATION", "MISAKA_USAGE_CLAIM_LOCK", "MISAKA_SISTER_OWNER_CLAIM_LOCK",
                 "MISAKA_USAGE_TASK_ID"):
        monkeypatch.delenv(name, raising=False)
    for sister in ("10032", "10036", "10037", "10038"):
        os.makedirs(os.path.join(CFG["profiles_root"], sister), exist_ok=True)
    index = session_catalog._index_dir()
    index.mkdir(parents=True, exist_ok=True)
    board = tasks.connect(CFG["db"])
    mail = messages.connect()
    workspace = tmp_path / "project"
    workspace.mkdir()
    yield SimpleNamespace(board=board, mail=mail, index=index, workspace=str(workspace), tmp=tmp_path)
    board.close()
    mail.close()


def _running(world, assignee="10032", generation=1, title="T card"):
    task_id = cards.create(world.board, world.workspace, title, BODY, assignee)
    world.board.execute("UPDATE tasks SET status='running', generation=? WHERE id=?", (generation, task_id))
    world.board.commit()
    return task_id


def _live(world, session_id, *, role, space=None, task_id=None, kind=None, inbox="role", alive=True):
    """A catalog record, as CatalogPart writes it, for a session of this test process."""
    pid, identity = (ME, MY_IDENTITY) if alive else (_gone_pid(), "gone")
    value = {"id": session_id, "path": None, "pid": pid, "identity": identity, "role": role,
             "kind": kind or ("card" if task_id else "foreground"), "task_id": task_id,
             "workspace": world.workspace, "inbox": role if inbox == "role" else inbox,
             "space": space, "state": "working"}
    (world.index / f"{session_id}.json").write_text(json.dumps(value), encoding="utf-8")
    return session_id


def _gone_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _resolve(addr, **kw):
    kw.setdefault("sender", "10032")
    return messages.resolve_address(addr, **kw)


# ── resolution: ids ─────────────────────────────────────────────────────────────────────

def test_a_card_is_addressed_by_its_id(world):
    sibling = _running(world, generation=3, title="T sibling")
    _live(world, _sid(), role="10032", task_id=sibling)
    target = _resolve(sibling, sender_task="t_000000")
    assert target["to_addr"] == "10032" and target["to_task"] == sibling
    assert target["generation"] == 3 and target["to_session"] is None
    assert target["label"] == f"card {sibling} (10032, attempt 3: T sibling)"


def test_a_session_is_addressed_by_its_id(world):
    lo = _live(world, _sid(), role="last-order")
    target = _resolve(lo, sender_session=_sid())
    assert target == {"to_addr": "last-order", "to_task": None, "to_session": lo, "generation": None,
                      "after_turn": False, "label": f"session {lo} (last-order)"}


def test_your_own_card_and_session_are_refused(world):
    mine = _running(world)
    me = _live(world, _sid(), role="10032", task_id=mine)
    with pytest.raises(ValueError, match="this card"):
        _resolve(mine, sender_task=mine)
    with pytest.raises(ValueError, match="this session"):
        _resolve(me, sender_session=me)


def test_a_card_that_is_not_running_or_has_no_live_session_is_refused(world):
    stopped = cards.create(world.board, world.workspace, "T stopped", BODY, "10032")
    with pytest.raises(ValueError, match="no live session"):
        _resolve(stopped)
    running = _running(world)                      # running on the board, nobody live
    with pytest.raises(ValueError, match="no live session"):
        _resolve(running)
    _live(world, _sid(), role="10032", task_id=running, alive=False)
    with pytest.raises(ValueError, match="no live session"):
        _resolve(running)


def test_a_session_that_is_gone_or_reads_no_mail_is_refused(world):
    with pytest.raises(ValueError, match="not live"):
        _resolve(_sid())
    quiet = _live(world, _sid(), role="10038", inbox=None)
    with pytest.raises(ValueError, match="reads no mail"):
        _resolve(quiet)


def test_an_unknown_name_lists_what_can_be_reached(world):
    with pytest.raises(ValueError) as refusal:
        _resolve("nobody", space=SPACE_T1)
    text = str(refusal.value)
    assert "last-order" in text and "10038" in text and "card's id" in text and "session's id" in text


# ── resolution: names, inside the sender's space ────────────────────────────────────────

def test_a_name_reaches_the_one_window_of_that_role_in_the_space(world):
    window = _live(world, _sid(), role="10036", space=SPACE_T2)
    target = _resolve("10036", sender="10037", space=SPACE_T2, sender_session=_sid())
    assert target == {"to_addr": "10036", "to_task": None, "to_session": window, "generation": None,
                      "after_turn": False, "label": f"session {window} (10036)"}


def test_a_name_reaches_the_one_card_of_that_role_in_the_space(world):
    card = _running(world, assignee="10036", generation=4, title="T archives")
    _live(world, _sid(), role="10036", task_id=card, space=SPACE_T1)
    target = _resolve("10036", sender="10037", space=SPACE_T1)
    assert target["to_task"] == card and target["generation"] == 4 and target["to_session"] is None
    assert target["to_addr"] == "10036"


def test_the_same_role_in_another_space_is_not_a_candidate(world, monkeypatch):
    _live(world, _sid(), role="10036", space=SPACE_T1)
    target = _resolve("10036", sender="10037", space=SPACE_T2)
    assert target["to_task"] is None and target["to_session"] is None     # the contact session
    assert session_catalog.live_readers("10036", SPACE_T2) == []
    assert len(session_catalog.live_readers("10036", SPACE_T1)) == 1


async def test_no_candidate_leaves_the_contact_session_and_wakes_it(world, monkeypatch):
    spawned = []
    monkeypatch.setattr(messages.subprocess, "Popen",
                        lambda argv, **kw: spawned.append((argv, kw["env"])) or SimpleNamespace())
    monkeypatch.setenv("MISAKA_NET_SPACE", SPACE_T2)
    me = _live(world, _sid(), role="10037", space=SPACE_T2)
    out = await _part(me, sender="10037")._send("fixture", {"to": "10038", "message": "hello", "summary": "hi"},
                                               None, None, SimpleNamespace())
    assert out["details"]["contact"] is True
    assert out["details"]["to_task"] is None and out["details"]["to_session"] is None
    assert "the 10038 contact session" in out["content"][0]["text"]
    assert len(spawned) == 1
    argv, env = spawned[0]
    assert argv[-1] == "10038" and argv[argv.index("--wait-message") + 1] == str(out["details"]["message_id"])
    assert "MISAKA_NET_SPACE" not in env and "MISAKA_NET_PANE" not in env
    rows = messages.pending(world.mail, "10038", contact=True)
    assert [row["body"] for row in rows] == ["hello"]


def test_two_candidates_are_refused_with_their_ids_and_titles(world):
    first = _running(world, assignee="10036", generation=2, title="T periodicals")
    _live(world, _sid(), role="10036", task_id=first, space=SPACE_T1)
    window = _live(world, _sid(), role="10036", space=SPACE_T1)
    with pytest.raises(ValueError) as refusal:
        _resolve("10036", sender="10037", space=SPACE_T1)
    text = str(refusal.value)
    assert "2 live sessions in this space" in text
    assert f"card {first} (10036, attempt 2: T periodicals)" in text
    assert f"session {window} (10036)" in text
    assert "by its card id or session id" in text


def test_a_sender_without_a_space_has_no_neighbours(world):
    _live(world, _sid(), role="10036", space=SPACE_T1)
    _live(world, _sid(), role="10036", space=None)
    target = _resolve("10036", sender="10037", space=None)
    assert target["to_task"] is None and target["to_session"] is None
    assert target["label"] == "the 10036 contact session"


def test_your_own_role_with_nobody_else_of_it_here_is_refused(world):
    me = _live(world, _sid(), role="10032", space=SPACE_T1)
    with pytest.raises(ValueError, match="your own role"):
        _resolve("10032", space=SPACE_T1, sender_session=me)
    with pytest.raises(ValueError, match="your own role"):
        _resolve("10032", space=None)
    other = _live(world, _sid(), role="10032", space=SPACE_T1)
    assert _resolve("10032", space=SPACE_T1, sender_session=me)["to_session"] == other


# ── the reader side ─────────────────────────────────────────────────────────────────────

def _send(world, to_addr, body, **kw):
    return messages.send(world.mail, to_addr, body, summary=body[:20], sender="10037", **kw)


def test_a_pinned_row_reaches_only_its_session_or_card_and_an_unpinned_one_only_the_contact(world):
    session_a, session_b = _sid(), _sid()
    _send(world, "10036", "for nobody")
    _send(world, "10036", "for card A", to_task="t_aaaaaa", generation=2)
    _send(world, "10036", "for session B", to_session=session_b)
    bodies = lambda **kw: [r["body"] for r in messages.pending(world.mail, "10036", **kw)]
    assert bodies(session_id=session_a, task_id="t_aaaaaa") == ["for card A"]
    assert bodies(session_id=session_b) == ["for session B"]
    assert bodies(session_id=session_a) == []                    # a window it was not for
    assert bodies(session_id=_sid(), contact=True) == ["for nobody"]
    assert bodies() == []
    assert [r["body"] for r in messages.pending(world.mail, "10037", contact=True)] == []


def test_a_note_for_an_earlier_attempt_is_dropped_not_read(world):
    stale = _send(world, "10036", "for attempt 1", to_task="t_aaaaaa", generation=1)
    fresh = _send(world, "10036", "for attempt 2", to_task="t_aaaaaa", generation=2)
    rows = messages.pending(world.mail, "10036", task_id="t_aaaaaa")
    deliverable, discard = messages.delivery_plan(rows, task_generation=2)
    assert deliverable == {fresh} and discard == {stale}


def test_a_mailbox_shaped_by_another_build_is_refused_not_reshaped(tmp_path):
    """Pre-release data is not migrated: the queue stays exactly as that build left it."""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, to_addr TEXT NOT NULL, sender TEXT,"
        " body TEXT NOT NULL, summary TEXT, task_id TEXT, generation INTEGER, workspace TEXT,"
        " created_at INTEGER NOT NULL, delivered_at INTEGER, lease_expires INTEGER, lease_token TEXT);"
        "INSERT INTO messages (to_addr, body, created_at) VALUES ('10032', 'legacy', 1);")
    old.commit()
    old.close()
    with pytest.raises(RuntimeError, match="pre-release MISAKA"):
        messages.connect(str(path))
    old = sqlite3.connect(str(path))
    assert {row[1] for row in old.execute("PRAGMA table_info(messages)")} == {
        "id", "to_addr", "sender", "body", "summary", "task_id", "generation", "workspace",
        "created_at", "delivered_at", "lease_expires", "lease_token"}                  # untouched
    old.close()


def test_the_mailbox_carries_a_version_and_a_newer_one_asks_for_an_update(tmp_path):
    """0.18.0 compatibility: messages.db is stamped like the board, so a later build can migrate it,
    and an older build meeting a newer queue says to update instead of reshaping it."""
    import sqlite3
    path = tmp_path / "messages.db"
    messages.connect(str(path)).close()
    raw = sqlite3.connect(str(path))
    assert raw.execute("SELECT version FROM schema_migrations WHERE component='messages'").fetchone()[0] \
        == messages.MESSAGES_SCHEMA_VERSION
    raw.execute("UPDATE schema_migrations SET version=? WHERE component='messages'", (messages.MESSAGES_SCHEMA_VERSION + 1,))
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="newer MISAKA.*misaka update"):
        messages.connect(str(path))


def test_the_queue_has_no_workspace_column():
    assert "workspace" not in messages.COLUMNS
    assert {"to_task", "to_session", "sender_task", "sender_session"} <= messages.COLUMNS


# ── the tool end to end ─────────────────────────────────────────────────────────────────

class _Manager:
    flushed = True

    def __init__(self, session_id):
        self._id = session_id

    def getSessionId(self):
        return self._id

    def getEntries(self):
        return []


def _part(session_id, *, sender, card_task=None, receive=False, contact=False, delivered=None):
    part = messages.MessagesPart(sender=sender, card_task=card_task, receive=receive, contact=contact)

    async def sendCustomMessage(message, options):
        if delivered is not None:
            delivered.append(message)
        options["_onPersist"]()

    part.attach(SimpleNamespace(sessionManager=_Manager(session_id), _customMessageReceipts={},
                                sendCustomMessage=sendCustomMessage))
    return part


async def _deliver(part, con):
    await part._deliver_once(con)


async def test_two_spaces_with_10036_and_10037_each_do_not_cross(world, monkeypatch):
    """The live run of 2026-09-29: a test space's windows and a research run's cards, one home."""
    monkeypatch.setattr(messages.subprocess, "Popen", lambda *a, **k: pytest.fail("nobody is woken"))
    # T1: the research run -- 10036 and 10037 are cards.
    card36 = _running(world, assignee="10036", generation=1, title="T1 archives")
    card37 = _running(world, assignee="10037", generation=1, title="T1 methods")
    t1_36 = _live(world, _sid(), role="10036", task_id=card36, space=SPACE_T1)
    t1_37 = _live(world, _sid(), role="10037", task_id=card37, space=SPACE_T1)
    # T2: a test space -- 10036 and 10037 are windows.
    t2_36 = _live(world, _sid(), role="10036", space=SPACE_T2)
    t2_37 = _live(world, _sid(), role="10037", space=SPACE_T2)

    from_t2 = await _part(t2_37, sender="10037")._send(
        "fixture", {"to": "10036", "message": "T2 window note", "summary": "t2"}, None, None, SimpleNamespace())
    from_t1 = await _part(t1_37, sender="10037", card_task=card37)._send(
        "fixture", {"to": "10036", "message": "T1 card note", "summary": "t1"}, None, None, SimpleNamespace())
    assert from_t2["details"]["to_session"] == t2_36 and from_t2["details"]["to_task"] is None
    assert from_t1["details"]["to_task"] == card36 and from_t1["details"]["to_session"] is None

    got = {}
    for name, session_id, card in (("t2_36", t2_36, None), ("t1_36", t1_36, card36)):
        delivered = []
        if card:
            monkeypatch.setenv("MISAKA_USAGE_GENERATION", "1")
        await _deliver(_part(session_id, sender="10036", card_task=card, receive=True, delivered=delivered),
                       world.mail)
        monkeypatch.delenv("MISAKA_USAGE_GENERATION", raising=False)
        got[name] = "\n".join(message["content"] for message in delivered)
    assert "T2 window note" in got["t2_36"] and "T1 card note" not in got["t2_36"]
    assert "T1 card note" in got["t1_36"] and "T2 window note" not in got["t1_36"]
    assert f"<from-card>{card37}</from-card>" in got["t1_36"]
    assert f"<from-session>{t2_37}</from-session>" in got["t2_36"]
    # The contact session of 10036 has nothing to read, and both rows are delivered.
    assert messages.pending(world.mail, "10036", contact=True) == []
    assert world.mail.execute("SELECT COUNT(*) FROM messages WHERE delivered_at IS NULL").fetchone()[0] == 0


async def test_a_help_request_goes_to_a_last_order_and_is_pinned(world, monkeypatch):
    monkeypatch.setattr(messages.subprocess, "Popen", lambda *a, **k: pytest.fail("nobody is woken"))
    card = _running(world, assignee="10032", generation=3)
    world.board.execute("UPDATE tasks SET claim_lock='lock-1', claim_expires=? WHERE id=?",
                        (int(time.time()) + 600, card))
    world.board.commit()
    monkeypatch.setenv("MISAKA_USAGE_GENERATION", "3")
    monkeypatch.setenv("MISAKA_USAGE_CLAIM_LOCK", "lock-1")
    me = _live(world, _sid(), role="10032", task_id=card, space=SPACE_T1)
    lo = _live(world, _sid(), role="last-order", space=SPACE_T1)
    part = _part(me, sender="10032", card_task=card)
    with pytest.raises(ValueError, match="must go to a Last Order"):
        await part._send("fixture", {"to": "10038", "message": "help", "summary": "help", "request_input": True},
                         None, None, SimpleNamespace())
    with pytest.raises(ValueError, match="is for a Sister task card"):
        await _part(lo, sender="last-order")._send(
            "fixture", {"to": "10032", "message": "x", "summary": "x", "request_input": True},
            None, None, SimpleNamespace())
    out = await part._send("fixture", {"to": "last-order", "message": "which archive?", "summary": "help",
                                       "request_input": True}, None, None, SimpleNamespace())
    assert out["details"]["to_session"] == lo and "parked" in out["content"][0]["text"]
    assert tasks.get(world.board, card)["status"] == "blocked"
    rows = messages.pending(world.mail, "last-order", session_id=lo)
    assert [(r["task_id"], r["generation"], r["to_session"]) for r in rows] == [(card, 3, lo)]
    assert messages.pending(world.mail, "last-order", contact=True) == []
    deliverable, discard = messages.delivery_plan(rows)
    assert deliverable == {rows[0]["id"]} and discard == set()


def test_catalog_records_its_space_from_the_environment_and_keeps_it(world, monkeypatch):
    from misaka.core.wiring import SessionSpec

    path = world.tmp / "s.jsonl"
    path.write_text(json.dumps({"type": "session", "id": "fixture", "cwd": world.workspace}) + "\n")
    manager = SimpleNamespace(getSessionId=lambda: "fixture", getSessionFile=lambda: str(path),
                              isPersisted=lambda: True, flushed=True, getCwd=lambda: world.workspace)
    spec = SessionSpec(profile_dir=world.workspace, role="10036", workspace=world.workspace,
                       kind="foreground", receive_messages=True)
    monkeypatch.setenv("MISAKA_NET_SPACE", SPACE_T1)
    first = session_catalog.CatalogPart(spec)
    first._publish(SimpleNamespace(sessionManager=manager), "idle")
    assert session_catalog.find_session("fixture")["space"] == SPACE_T1
    first._retire()
    assert session_catalog.find_session("fixture")["state"] == "saved"
    monkeypatch.setenv("MISAKA_NET_SPACE", SPACE_T2)            # opened again in another space
    second = session_catalog.CatalogPart(spec)
    second._publish(SimpleNamespace(sessionManager=manager), "working")
    assert session_catalog.find_session("fixture")["space"] == SPACE_T1
    assert session_catalog.spaces_in_use() == {SPACE_T1}
    rows = {row["id"]: row for row in session_catalog.list_entries(None, extra_paths=[str(path)])}
    assert rows["fixture"]["space"] == SPACE_T1
    second._retire()
    contact = session_catalog.CatalogPart(SessionSpec(
        profile_dir=world.workspace, role="10036", workspace=world.workspace, kind="dm", receive_messages=True))
    dm_path = world.tmp / "dm.jsonl"
    dm_manager = SimpleNamespace(getSessionId=lambda: "dm-fixture", getSessionFile=lambda: str(dm_path),
                                 isPersisted=lambda: True, flushed=False, getCwd=lambda: world.workspace)
    contact._publish(SimpleNamespace(sessionManager=dm_manager), "idle")
    assert session_catalog.find_session("dm-fixture")["space"] is None
    assert session_catalog.live_contact("10036") and not session_catalog.live_contact("10037")
    contact._retire()


def test_spaces_in_use_counts_saved_sessions_too(world):
    _live(world, _sid(), role="10036", space=SPACE_T1)
    saved = _sid()
    _live(world, saved, role="10037", space=SPACE_T2)
    record = world.index / f"{saved}.json"
    value = json.loads(record.read_text())
    record.write_text(json.dumps({**value, "state": "saved"}))
    _live(world, _sid(), role="10038", space=None)
    assert session_catalog.spaces_in_use() == {SPACE_T1, SPACE_T2}
    assert session_catalog.live_readers("10037", SPACE_T2) == []       # saved is not a reader


def test_the_contact_wake_leaves_the_row_to_a_running_contact_turn(world, monkeypatch):
    from misaka.cli import dm

    monkeypatch.setattr(dm, "LIVE_POLL_SECONDS", 0.01)
    calls = []
    assert dm._left_to_contact("10036", lambda: calls.append(1)) is False and calls == []
    _live(world, _sid(), role="10037", kind="dm")
    _live(world, _sid(), role="10036", space=SPACE_T1)                # a window is no contact
    assert dm._left_to_contact("10036", lambda: True) is False
    _live(world, _sid(), role="10036", kind="dm")
    answers = iter([False, True])
    assert dm._left_to_contact("10036", lambda: next(answers)) is True


def test_the_contact_turn_reads_only_unpinned_rows(world):
    pinned = _send(world, "10036", "for a window", to_session=_sid())
    loose = _send(world, "10036", "for the contact")
    rows = messages.pending(world.mail, "10036", contact=True)
    assert [row["id"] for row in rows] == [loose] and pinned != loose


def test_an_ally_reaches_the_last_order_of_its_own_space(world, monkeypatch):
    """An ally's SendMessage (its MCP bridge calls ``send_as``) names its card and resolves in the
    space of the pane its card runs in, as a Sister's does."""
    monkeypatch.setattr(messages.subprocess, "Popen", lambda *a, **k: pytest.fail("nobody is woken"))
    _live(world, _sid(), role="last-order", space=SPACE_T1)
    lo_t2 = _live(world, _sid(), role="last-order", space=SPACE_T2)
    card = _running(world)
    messages.send_as("codex", "last-order", "done with the draft", "draft", card_task=card, space=SPACE_T2)
    by_session = {row["to_session"]: (row["sender"], row["body"])
                  for row in world.mail.execute("SELECT * FROM messages")}
    assert by_session == {lo_t2: ("codex", f"[card {card}]\ndone with the draft")}


def test_a_research_card_is_told_its_node_last_order_by_session_id(world):
    from misaka.core.research import planner

    lo_file = Path(home.path("sessions")) / "research" / "lo.jsonl"
    lo_file.parent.mkdir(parents=True, exist_ok=True)
    lo_id = _sid()
    lo_file.write_text(json.dumps({"type": "session", "version": 3, "id": lo_id, "cwd": world.workspace}) + "\n")
    task = {"question": "Q", "rationale": "R", "deliverable": "notes.md"}
    body = planner.task_body(task, lo_session=home.stored(lo_file))
    assert f"Your node's Last Order is session `{lo_id}`" in body
    assert "Last Order is session" not in planner.task_body(task)


def test_card_and_session_ids_are_told_apart_from_names():
    session = _sid()
    assert messages.CARD_ID.match("t_1a2b3c") and not messages.CARD_ID.match("t_1a2b3c4")
    assert messages.SESSION_ID.match(session) and not messages.SESSION_ID.match("10032")
    assert not messages.CARD_ID.match("last-order") and not messages.SESSION_ID.match("last-order")


def test_the_catalog_finds_a_live_session_and_a_live_card(world):
    card_session, gone = _sid(), _sid()
    _live(world, card_session, role="10032", task_id="t_aaaaaa")
    _live(world, gone, role="last-order", alive=False)
    assert session_catalog.live_session(card_session)["task_id"] == "t_aaaaaa"
    assert session_catalog.live_session(gone) is None
    assert session_catalog.find_session(gone)["id"] == gone              # a record, if not live
    assert session_catalog.live_card_session("t_aaaaaa")["id"] == card_session
    assert session_catalog.live_card_session("t_zzzzzz") is None
    Path(world.index / f"{card_session}.json").unlink()
    assert session_catalog.live_session(card_session) is None


def test_the_pump_asks_as_contact_only_in_a_contact_session(world):
    _send(world, "10036", "loose")
    pinned_to = _sid()
    _send(world, "10036", "pinned", to_session=pinned_to)
    got = {}
    for name, part_id, contact in (("window", pinned_to, False), ("contact", _sid(), True)):
        delivered = []
        asyncio.run(_deliver(_part(part_id, sender="10036", receive=True, contact=contact, delivered=delivered),
                             world.mail))
        got[name] = "\n".join(message["content"] for message in delivered)
    assert "pinned" in got["window"] and "loose" not in got["window"]
    assert "loose" in got["contact"] and "pinned" not in got["contact"]
