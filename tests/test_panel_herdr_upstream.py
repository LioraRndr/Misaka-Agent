"""herdr v0.8.2 -> HEAD catch-up for misaka/ui/panel (docs/audits/herdr-upstream-2026-09-27.md).

Cases marked with a herdr test name are ports of that test (src/raw_input.rs,
src/input/parse.rs, src/input/encode.rs, src/pane.rs at herdr c33fd40e).
"""
import asyncio
import re

import pytest
import regex

from misaka.ui.panel import daemon as dm
from misaka.ui.panel import geometry as hui
from misaka.ui.panel import ghostty as vt
from misaka.ui.panel import host_input as hin
from misaka.ui.panel import pane_input as pin
from misaka.ui.panel import panel as panel_mod
from misaka.ui.panel import selection as selmod
from misaka.ui.panel.host_input import (
    ALT,
    CTRL,
    SHIFT,
    SUPER,
    Focus,
    HostInput,
    Key,
    Mouse,
    Paste,
)
from misaka.ui.panel.text_editor import TextEditor, grapheme_width


def _framer(**kwargs):
    return HostInput(**kwargs)


def _feed(host, data):
    return host.feed(data, now=0.0)


def _flush(host):
    return host.flush(now=0.0)


# ── R2-R5: key parsing (parse.rs) ────────────────────────────────────────────────────


@pytest.mark.parametrize(("seq", "code", "mods"), [
    ("\x1b[11;2~", "f1", SHIFT), ("\x1b[12;1~", "f2", 0), ("\x1b[13;1:1~", "f3", 0),
    ("\x1b[13;2~", "f3", SHIFT), ("\x1b[14;3~", "f4", ALT),
])
def test_parse_parameterized_csi_tilde_f1_through_f4(seq, code, mods):
    key = hin.parse_key(seq)
    assert (key.code, key.mods, key.kind) == (code, mods, "press")


@pytest.mark.parametrize(("seq", "code"), [
    ("\x1b[57364;1u", "f1"), ("\x1b[57365;1u", "f2"), ("\x1b[57366;1u", "f3"),
    ("\x1b[57368;1u", "f5"), ("\x1b[57375;1u", "f12"), ("\x1b[57376;1u", "f13"),
])
def test_kitty_f1_through_f12_codepoints_are_recognized(seq, code):
    assert hin.parse_key(seq) == Key(code)


def test_parse_xterm_special_sequences_with_associated_text():
    assert hin.parse_key("\x1b[1;1;63233B") == Key("down")
    assert hin.parse_key("\x1b[5;1;63276~") == Key("pageup")
    assert hin.parse_key("\x1b[1;1;63233;63234B") is None


@pytest.mark.parametrize(("seq", "code", "kind"), [
    ("\x1b[13;1;13u", "enter", "press"), ("\x1b[13;1:3u", "enter", "release"),
    ("\x1b[127::8;1;8u", "backspace", "press"), ("\x1b[127::8;1:3u", "backspace", "release"),
    ("\x1b[27;1;27u", "esc", "press"), ("\x1b[9;1;9u", "tab", "press"),
])
def test_parse_wezterm_control_associated_text_keeps_report_all_key_events(seq, code, kind):
    key = hin.parse_key(seq)
    assert (key.code, key.mods, key.kind, key.text) == (code, 0, kind, None)


@pytest.mark.parametrize("seq", [
    "\x1b[32;;1114112u", "\x1b[32;;20320:bad:u", "\x1b[32;;27u", "\x1b[32;;133u",
    "\x1b[13;1;8u", "\x1b[127::8;1;13u", "\x1b[13;1;13:10u", "\x1b[9;1;27u", "\x1b[27;1;9u",
    "\x1b[9;1;9:97u", "\x1b[27;1;27:27u",
    "\x1b[97;1;9u",          # a whitespace control is still a control character
    "\x1b[97;0u", "\x1b[97;256u", "\x1b[97;:3u",
])
def test_reject_malformed_kitty_associated_text_and_modifiers(seq):
    assert hin.parse_key(seq) is None


def test_kitty_associated_text_is_kept():
    assert hin.parse_key("\x1b[20320;;20320:22909u").text == "你好"


# ── mouse reports (raw_input.rs parse_sgr_mouse / parse_mouse_cb) ────────────────────


def test_parses_sgr_mouse():
    assert hin.parse_mouse("\x1b[<0;20;10M") == Mouse("press", 0, 19, 9)


def test_parses_default_mouse_encoding():
    assert hin.parse_mouse("\x1b[MCN1") == Mouse("move", 3, 45, 16)


@pytest.mark.parametrize("seq", ["\x1b[<160;20;10M", "\x1b[<161;20;10M"])
def test_parses_extended_button_drag_as_mouse_motion(seq):
    assert hin.parse_mouse(seq) == Mouse("move", 3, 19, 9)


def test_mouse_report_without_a_button_is_a_left_release():
    assert hin.parse_mouse("\x1b[M#!!") == Mouse("release", 0, 0, 0)
    assert hin.parse_mouse("\x1b[<0;5;5m") == Mouse("release", 0, 4, 4)


@pytest.mark.parametrize("seq", ["\x1b[<128;5;5M", "\x1b[<0;0;5M", "\x1b[<0;5;65536M", "\x1b[<256;5;5M"])
def test_mouse_reports_herdr_cannot_represent_are_dropped(seq):
    assert hin.parse_mouse(seq) is None


# ── R1: host input framing (raw_input.rs RawInputByteFramer) ─────────────────────────


def test_lone_escape_is_buffered_until_timeout_flush():
    host = _framer()
    assert _feed(host, b"\x1b") == []
    assert _flush(host) == [Key("esc")]


def test_escape_followed_by_arrow_before_flush_does_not_emit_escape():
    host = _framer()
    assert _feed(host, b"\x1b") == []
    assert _feed(host, b"[B") == [Key("down")]


def test_escape_followed_by_sgr_mouse_before_flush_does_not_emit_text():
    host = _framer()
    assert _feed(host, b"\x1b") == []
    assert _feed(host, b"[<65;43;26M") == [Mouse("wheel_down", 1, 42, 25)]


@pytest.mark.parametrize("report", [b"\x1b[<35;10;20M", b"\x1b[<35;10;20m"])
def test_lone_escape_then_complete_sgr_mouse_report_emits_both_events(report):
    host = _framer()
    assert _feed(host, b"\x1b") == []
    assert _feed(host, report) == [Key("esc"), Mouse("move", 3, 9, 19)]
    assert _flush(host) == []


def test_sgr_mouse_sequence_split_after_button_prefix_is_reassembled_before_timeout():
    host = _framer()
    assert _feed(host, b"\x1b[<3") == []
    assert _feed(host, b"5;58;30M") == [Mouse("move", 3, 57, 29)]


def test_timed_out_split_sgr_mouse_tail_is_discarded_and_following_input_is_preserved():
    host = _framer()
    assert _feed(host, b"\x1b[<3") == []
    assert _flush(host) == []
    assert _feed(host, b"5;58;30Mx") == [Key("x")]


def test_captured_sgr_mouse_tail_after_second_idle_flush_is_discarded():
    host = _framer()
    assert _feed(host, b"\x1b[<3") == []
    assert _flush(host) == []
    assert _flush(host) == []
    assert _feed(host, b"5;28;31M") == []


def test_timed_out_sgr_mouse_invalid_completion_is_preserved_after_idle():
    host = _framer()
    assert _feed(host, b"\x1b[<3") == []
    assert _flush(host) == []
    assert _feed(host, b"M") == [Key("M", SHIFT)]


@pytest.mark.parametrize("split", range(len(b"5;28;31M") + 1))
def test_timed_out_sgr_mouse_completion_survives_read_splits_and_idle(split):
    tail = b"5;28;31M"
    host = _framer()
    assert _feed(host, b"\x1b[<3") == []
    assert _flush(host) == []
    assert _feed(host, tail[:split]) == []
    _flush(host)
    assert _feed(host, tail[split:] + b"x\x1b[A") == [Key("x"), Key("up")]
    assert host.deadline() is None


@pytest.mark.parametrize("tail", [b"5;0;31M", b"5;;31M", b"5;28;31;1M", b"999;28;31M", b"5;65536;31M"])
def test_timed_out_sgr_mouse_invalid_syntax_releases_continuation(tail):
    host = _framer()
    assert _feed(host, b"\x1b[<3") == []
    assert _flush(host) == []
    typed = "".join(event.code for event in _feed(host, tail))
    assert typed == tail.decode()


def test_sgr_mouse_tail_after_lone_escape_timeout_is_discarded():
    host = _framer()
    assert _feed(host, b"\x1b") == []
    assert _flush(host) == [Key("esc")]
    assert _feed(host, b"[<65;43;26M") == []


def test_input_after_discarded_complete_sgr_mouse_tail_is_preserved():
    host = _framer()
    _feed(host, b"\x1b")
    assert _flush(host) == [Key("esc")]
    assert _feed(host, b"[<65;43;26Mx") == [Key("x")]


def test_invalid_orphaned_sgr_mouse_tail_after_escape_timeout_is_preserved():
    host = _framer()
    _feed(host, b"\x1b")
    assert _flush(host) == [Key("esc")]
    assert [event.code for event in _feed(host, b"[<x")] == ["[", "<", "x"]


def test_double_split_sgr_mouse_tail_after_lone_escape_timeout_is_discarded():
    host = _framer()
    _feed(host, b"\x1b")
    assert _flush(host) == [Key("esc")]
    assert _feed(host, b"[<65;4") == []
    assert _flush(host) == []
    assert _flush(host) == []
    assert _feed(host, b"3;26Mx") == [Key("x")]


def test_escape_followed_by_alt_char_before_flush_becomes_alt_key():
    host = _framer()
    assert _feed(host, b"\x1b") == []
    assert _feed(host, b"b") == [Key("b", ALT)]


def test_mouse_active_escape_sequences_get_longer_reassembly_window():
    for data in (b"\x1b", b"\x1b[", b"\x1b[<3", b"\x1b[M"):
        host = _framer()
        host.feed(data, now=10.0)
        assert host.deadline() == pytest.approx(10.0 + hin.MOUSE_ACTIVE_ESCAPE_SEQUENCE_FLUSH_TIMEOUT)
        quiet = _framer(mouse_capture=False)
        quiet.feed(data, now=10.0)
        assert quiet.deadline() == pytest.approx(10.0 + hin.RAW_INPUT_IDLE_FLUSH_TIMEOUT)
    unrelated = _framer()
    unrelated.feed(b"\x1b[49:33;2:", now=10.0)
    assert unrelated.deadline() == pytest.approx(10.0 + hin.RAW_INPUT_IDLE_FLUSH_TIMEOUT)


def test_captured_mouse_report_split_after_csi_survives_idle_gap():
    # herdr #4630: ESC[ and its continuation arrived 32.9 ms apart, inside the mouse grace.
    host = _framer()
    host.feed(b"\x1b[I", now=0.0)
    assert host.feed(b"\x1b[", now=1.0) == []
    assert host.deadline() > 1.0329
    assert host.feed(b"<35;64;37M\x1b[<35;65;36M\x1b[<35;64;36M", now=1.0329) == [
        Mouse("move", 3, 63, 36), Mouse("move", 3, 64, 35), Mouse("move", 3, 63, 35)]
    assert host.deadline() is None


def test_idle_flush_runs_at_most_twice_per_read():
    host = _framer()
    host.feed(b"\x1b[<3", now=0.0)
    host.flush(now=0.2)                   # prefix retained: nothing pending in the buffer
    assert host.deadline() is None
    host.feed(b"5;28", now=0.3)           # a partial continuation: held twice, then waits
    assert host.flush(now=0.31) == []
    assert host.deadline() == pytest.approx(0.32)
    assert host.flush(now=0.32) == []
    assert host.deadline() is None


def test_incomplete_osc_is_discarded_after_timeout_and_its_tail_does_not_leak():
    host = _framer()
    assert _feed(host, b"\x1b]11;rgb:1e1e/") == []
    assert _flush(host) == []
    assert _feed(host, b"1e1e/2e2e\x1b\\x") == [Key("x")]


def test_bracketed_paste_terminator_split_across_reads():
    host = _framer()
    assert _feed(host, b"\x1b[200~hello") == []
    assert _feed(host, b" world\x1b[20") == []
    assert _feed(host, b"1~x") == [Paste("hello world"), Key("x")]


def test_macos_policy_preserves_legacy_doubled_escape(monkeypatch):
    monkeypatch.setattr(hin, "PRESERVE_LEGACY_DOUBLED_ESCAPE_INPUT", True)
    assert _feed(_framer(), b"\x1b\x1b[D") == [Key("left", ALT)]
    monkeypatch.setattr(hin, "PRESERVE_LEGACY_DOUBLED_ESCAPE_INPUT", False)
    assert _feed(_framer(), b"\x1b\x1b[D") == [Key("esc"), Key("left")]


@pytest.mark.parametrize(("prefix", "tail"), [(b"\x1b", b"[<0;5;5M"), (b"\x1b[", b"<0;5;5M"), (b"\x1b[<0;", b"5;5M")])
def test_confirmed_host_disambiguation_retains_split_sgr_mouse_without_escape(prefix, tail):
    host = _framer(escape_disambiguation=True)
    assert _feed(host, prefix) == []
    assert _flush(host) == []
    assert _flush(host) == []
    assert _feed(host, tail) == [Mouse("press", 0, 4, 4)]


def test_confirmed_host_disambiguation_drops_stale_escape_before_plain_input():
    host = _framer(escape_disambiguation=True)
    assert _feed(host, b"\x1b") == []
    assert _flush(host) == []
    assert _feed(host, b"x") == [Key("x")]


def test_confirmed_host_disambiguation_keeps_kitty_escape_immediate():
    assert _feed(_framer(escape_disambiguation=True), b"\x1b[27u") == [Key("esc")]


def test_focus_events_and_eight_bit_meta_still_frame():
    host = _framer()
    assert _feed(host, b"\x1b[I\x1b[O") == [Focus(True), Focus(False)]
    assert _feed(host, bytes([0xE1])) == [Key("a", ALT)]


# ── keyboard enhancement probe (terminal_setup.rs) ──────────────────────────────────


def test_keyboard_probe_consumes_replies_and_keeps_other_input():
    buffered = bytearray(b"a\x1b[?7u\x1b[200~\x1b[?9u\x1b[201~b\x1b[?62;22c")
    state = {}
    hin.consume_keyboard_probe_responses(buffered, state)
    assert bytes(buffered) == b"a\x1b[200~\x1b[?9u\x1b[201~b"
    assert state == {"flags": 7, "primary_device_attributes": True}
    assert hin.escape_disambiguation_confirmed(state)
    assert not hin.escape_disambiguation_confirmed({"primary_device_attributes": True})
    assert not hin.escape_disambiguation_confirmed({"flags": 1})


def test_keyboard_probe_waits_for_a_split_reply():
    buffered, state = bytearray(b"\x1b[?1"), {}
    hin.consume_keyboard_probe_responses(buffered, state)
    assert bytes(buffered) == b"\x1b[?1" and state == {}
    buffered += b"u\x1b[?1;2c"
    hin.consume_keyboard_probe_responses(buffered, state)
    assert bytes(buffered) == b"" and hin.escape_disambiguation_confirmed(state)


# ── R6-R7: legacy chords (encode.rs legacy_chord_needs_csi_u) ────────────────────────


def test_super_and_ctrl_shift_letter_use_csi_u_in_legacy_panes():
    legacy = dict(pin.DEFAULT_STATE)
    assert pin.encode_key(Key("c", SUPER), legacy) == b"\x1b[99;9u"
    assert pin.encode_key(Key("a", CTRL | SHIFT), legacy) == b"\x1b[97;6u"
    assert pin.encode_key(Key("a", CTRL), legacy) == b"\x01"
    assert pin.encode_key(Key("1", CTRL | SHIFT), legacy) != b"\x1b[49;6u"   # letters only
    assert pin.encode_key(Key("c", SUPER, "release"), legacy) == b""
    assert pin.encode_key(Key("enter", SHIFT), legacy) == b"\r"


def test_kitty_panes_are_unchanged_by_the_legacy_chord_rule():
    kitty = dict(pin.DEFAULT_STATE, kitty_flags=1)
    assert pin.encode_key(Key("a", CTRL | SHIFT), kitty) == b"\x1b[97;6u"
    assert pin.encode_key(Key("c", SUPER), kitty) == b"\x1b[99;9u"


# ── R8: pane environment (pane.rs apply_pane_terminal_env / apply_pane_launch_env) ───


def test_pane_env_clears_outer_terminal_and_agent_identity():
    outer = {key: "outer" for key in dm.PANE_HOST_IDENTITY + dm.PANE_OUTER_AGENT_IDENTITY}
    outer.update(TERM="xterm-kitty", TERM_PROGRAM="iTerm.app", ANTHROPIC_API_KEY="k", DISPLAY=":42")
    env = dm._pane_env(outer)
    for key in dm.PANE_HOST_IDENTITY + dm.PANE_OUTER_AGENT_IDENTITY:
        assert key not in env
    assert env["TERM"] == "xterm-256color" and env["COLORTERM"] == "truecolor"
    assert env["TERM_PROGRAM"] == "misaka" and env["TERM_PROGRAM_VERSION"]
    assert env["ANTHROPIC_API_KEY"] == "k" and env["DISPLAY"] == ":42"


def test_pane_env_explicit_launch_env_can_opt_back_in():
    env = dm._pane_env({"CLAUDECODE": "1"}, {"CLAUDE_CODE_SESSION_ID": "child", "ITERM_SESSION_ID": "host"})
    assert "CLAUDECODE" not in env
    assert env["CLAUDE_CODE_SESSION_ID"] == "child" and env["ITERM_SESSION_ID"] == "host"


# ── R10: terminal geometry (platform terminal_grid_size) ────────────────────────────


def test_terminal_size_is_unavailable_on_error_or_zero(monkeypatch):
    from misaka.ui.panel import panel

    monkeypatch.setattr(panel.fcntl, "ioctl", lambda *a: (_ for _ in ()).throw(OSError()))
    assert panel._term_size() is None
    monkeypatch.setattr(panel.fcntl, "ioctl", lambda *a: b"\0" * 8)
    assert panel._term_size() is None
    monkeypatch.setattr(panel.fcntl, "ioctl", lambda *a: bytes([40, 0, 120, 0, 0, 0, 0, 0]))
    assert panel._term_size() == (40, 120)


# ── R11: idle scrollback compression (pane.rs TerminalCompressionTask) ──────────────


class _PaneStub:
    def __init__(self, term):
        self.id, self.term = "p1", term
        self.compression = dm._Compression(self)


def _fill(term, lines=20000):
    line = ("scrollback " * 8 + "\r\n").encode()
    for index in range(lines):
        term.write(f"{index:06d} ".encode() + line)


def test_compression_runs_once_idle_and_keeps_contents():
    async def scenario():
        term = vt.Terminal(100, 30)
        _fill(term)
        before = term.read_text((0, 0), (99, 5))
        pane = _PaneStub(term)
        pane.compression.start()
        await asyncio.sleep(dm.COMPRESSION_IDLE / 2)
        assert not pane.compression.done
        await asyncio.sleep(dm.COMPRESSION_IDLE * 4)
        assert pane.compression.done or pane.compression.off
        assert term.read_text((0, 0), (99, 5)) == before
        pane.compression.cancel()
        term.close()

    asyncio.run(scenario())


def test_compression_waits_while_the_terminal_keeps_changing():
    async def scenario():
        term = vt.Terminal(80, 24)
        pane = _PaneStub(term)
        pane.compression.start()
        for _ in range(6):
            await asyncio.sleep(dm.COMPRESSION_IDLE / 3)
            term.write(b"more output\r\n")
            pane.compression.wake()
        assert not pane.compression.done
        # One idle period to see the last change settle, one to confirm it, then the steps.
        await asyncio.sleep(dm.COMPRESSION_IDLE * 4)
        assert pane.compression.done or pane.compression.off
        pane.compression.cancel()
        term.close()

    asyncio.run(scenario())


def test_compression_is_cancelled_before_the_terminal_is_freed():
    async def scenario():
        term = vt.Terminal(80, 24)
        pane = _PaneStub(term)
        pane.compression.start()
        pane.compression.cancel()
        term.close()
        await asyncio.sleep(dm.COMPRESSION_IDLE * 2)   # a stray timer would call into freed memory
        assert pane.compression.handle is None and pane.compression.off

    asyncio.run(scenario())


def test_wake_after_a_completed_pass_schedules_another():
    async def scenario():
        term = vt.Terminal(80, 24)
        _fill(term, 3000)
        pane = _PaneStub(term)
        pane.compression.start()
        await asyncio.sleep(dm.COMPRESSION_IDLE * 4)
        if pane.compression.off:          # target without retained-mapping reclamation
            return
        assert pane.compression.done
        pane.compression.wake()
        assert not pane.compression.done and pane.compression.handle is not None
        await asyncio.sleep(dm.COMPRESSION_IDLE * 4)
        assert pane.compression.done
        pane.compression.cancel()
        term.close()

    asyncio.run(scenario())


# ── B1-B9, P1, P11: tab bar (client/shell/tabs.rs) ──────────────────────────────────



def _tab_row(names, active, width, scroll=0, reveal=True):
    area = hui.Rect(0, 0, width, 1)
    view = hui.compute_tab_bar_view(names, active, area, scroll, reveal, True)
    line = panel_mod.render_tab_bar(names, active, view, area, view.scroll)
    return view, re.sub(r"\x1b\[[0-9;]*m", "", line)


@pytest.mark.parametrize(("widths", "available", "expected"), [
    ([], 0, 0), ([8, 13], 0, 1), ([8, 13], 1, 1), ([8, 13], 12, 1), ([8, 13], 21, 1),
    ([8, 13], 22, 0), ([8, 13], 30, 0), ([8, 65535], 65535, 1),
])
def test_trailing_scroll_limit_accounts_for_full_widths_and_separators(widths, available, expected):
    assert hui.max_tab_scroll(widths, available) == expected


def test_the_last_tab_of_an_overflowing_strip_is_revealed_whole():
    names = [f"alpha-long-name-{index}" for index in range(6)]
    view, line = _tab_row(names, 5, 60)
    assert view.tab_hit_areas[5].width == hui.tab_width(names, 5)
    assert "alpha-long-name-5" in line
    assert " > " in line and line.endswith(" + ")           # the truncated label no longer covers ">"
    assert view.scroll == view.max_scroll


def test_scroll_right_button_is_enabled_until_the_last_suffix_fits():
    names = [f"alpha-long-name-{index}" for index in range(6)]
    view = hui.compute_tab_bar_view(names, 0, hui.Rect(0, 0, 60, 1), 0, True, True)
    assert view.scroll == 0 and view.max_scroll > 0          # ">" can scroll
    line = panel_mod.render_tab_bar(names, 0, view, hui.Rect(0, 0, 60, 1), 0)
    assert f"{hui.sgr_fg(hui.OVERLAY1)}{hui.sgr_bg(hui.SURFACE0)} > " in line
    assert "\x1b[2m" not in line                              # scroll buttons are never DIM


def test_any_clipping_counts_as_overflow_but_not_below_the_minimum_strip():
    view, _line = _tab_row(["one", "two", "three"], 0, 26)
    assert view.scroll_left_hit_area.width == 3               # 8+8+8+2+3 = 29 > 26
    view, line = _tab_row(["one", "two"], 1, 16)              # 16 < MIN_TAB_STRIP_WIDTH
    assert view.scroll_left_hit_area.width == 0
    assert [rect.width for rect in view.tab_hit_areas] == [8, 4]
    assert line == "  one    two   +"


def test_new_tab_button_follows_one_gap_after_the_last_tab():
    view, _line = _tab_row(["one", "two"], 0, 30)
    assert view.new_tab_hit_area == hui.Rect(18, 0, 3, 1)


def test_overflow_controls_are_pinned_to_the_right_edge():
    view, _line = _tab_row([f"tab-{index}" for index in range(8)], 0, 40)
    assert view.scroll_right_hit_area.x == 40 - 6 and view.new_tab_hit_area.x == 40 - 3


def test_ellipsis_keeps_the_background_of_its_cell():
    names = [f"alpha-long-name-{index}" for index in range(6)]
    area = hui.Rect(0, 0, 60, 1)
    view = hui.compute_tab_bar_view(names, 3, area, 0, True, True)
    line = panel_mod.render_tab_bar(names, 3, view, area, view.scroll)
    cells = []
    style = ""
    for token in re.findall(r"\x1b\[[0-9;]*m|[^\x1b]", line):
        if token.startswith("\x1b"):
            style = "" if token == "\x1b[0m" else style + token
        else:
            cells.append((token, style))
    marks = [(index, style) for index, (token, style) in enumerate(cells) if token == "…"]
    assert len(marks) == 2                                    # tabs cut off on both sides
    for index, style in marks:
        assert hui.sgr_fg(hui.OVERLAY0) in style
        under_a_tab = any(rect.width and rect.x <= index < rect.x + rect.width for rect in view.tab_hit_areas)
        expected_bg = hui.SURFACE0 if under_a_tab else hui.PALETTE["panel_bg"]
        assert hui.sgr_bg(expected_bg) in style
    assert any(rect.width and rect.x == marks[0][0] for rect in view.tab_hit_areas)   # the left one sits on a tab


# ── D-M1, K2: token under a double-click (app/actions.rs word_bounds_at_column) ─────


def _col_of(row, needle):
    return sum(vt.codepoint_width(ord(ch)) for ch in row[:row.index(needle)])


def _selected_word(row, col):
    bounds = selmod.word_bounds_at_column(row, col)
    if bounds is None:
        return None
    out, column = [], 0
    for ch in row:
        width = vt.codepoint_width(ord(ch))
        if bounds[0] <= column <= bounds[1]:
            out.append(ch)
        column += width
    return "".join(out)


@pytest.mark.parametrize(("row", "click", "expected"), [
    ("see https://example.com/a-b_c?q=x@y.", "example.com", "https://example.com/a-b_c?q=x@y"),
    ("open \"https://example.com/a,b;c?q=x\";", "example.com", "https://example.com/a,b;c?q=x"),
    ("see https://en.wikipedia.org/wiki/Foo_(bar_(baz)),", "wikipedia", "https://en.wikipedia.org/wiki/Foo_(bar_(baz))"),
    ("see https://example.com/a(b[c{d}e]f),", "example.com", "https://example.com/a(b[c{d}e]f)"),
    ("see (https://example.com/a(b(c)d)))", "example.com", "https://example.com/a(b(c)d)"),
    ("open /tmp/foo-bar/baz_qux/", "foo-bar", "/tmp/foo-bar/baz_qux/"),
    ("open ./src/app/actions.rs:795", "actions", "./src/app/actions.rs:795"),
    ("open ../herdr-worktrees/issue-1", "herdr", "../herdr-worktrees/issue-1"),
    ("edit src/app/actions.rs,then", "actions", "src/app/actions.rs"),
    ("cat \"/tmp/build output/log.txt\"", "output", "/tmp/build output/log.txt"),
    ("cat '/Users/me/Library/Application Support/app/config.json'", "Support",
     "/Users/me/Library/Application Support/app/config.json"),
    ("echo 你好-world done", "好", "你好-world"),
    ("註解已補（slice 4 5b5fcc0715）：整合原本", "5b5fcc0715", "5b5fcc0715"),
    ("先跑 cargo test", "cargo", "cargo"),
    ("export PATH=$HOME/.cargo/bin:$PATH", "$HOME", "PATH=$HOME/.cargo/bin:$PATH"),
    ("git checkout feature/foo-bar_baz", "foo", "feature/foo-bar_baz"),
    ("refs #123 and @owner/name", "#123", "#123"),
    ("refs #123 and @owner/name", "owner", "@owner/name"),
    ("cargo test --package=herdr", "--package", "--package=herdr"),
    ("cargo test app::actions::tests", "app::", "app::actions::tests"),
    ("image ghcr.io/org/app:latest", "ghcr", "ghcr.io/org/app:latest"),
    ("ERROR [worker-1] request_id=abc-123", "worker", "worker-1"),
    ("tmux|newhoo|fixhoo|newmoo|notification|window_bell|herdr", "newhoo", "newhoo"),
    ("render_status_line(app, area)", "render", "render_status_line"),
    ("render_status_line(app, area)", "app", "app"),
    ("render_status_line(app, area)", "area", "area"),
    ("if !enabled {", "enabled", "enabled"),
    ("println!(\"hi\")", "println", "println"),
    ("( master)$", "master", "master"),
    ("regex foo$", "foo", "foo$"),
])
def test_double_click_word_bounds_cover_terminal_text(row, click, expected):
    assert _selected_word(row, _col_of(row, click)) == expected


def test_double_click_on_the_second_cell_of_a_wide_character():
    row = "echo 你好-world done"
    assert _selected_word(row, _col_of(row, "好") + 1) == "你好-world"


@pytest.mark.parametrize("delimiter", ["（", "）", "：", "、", "。", "，"])
def test_double_click_word_bounds_treat_cjk_punctuation_as_delimiters(delimiter):
    row = f"left{delimiter}right"
    assert _selected_word(row, _col_of(row, "left")) == "left"
    assert _selected_word(row, _col_of(row, "right")) == "right"
    assert _selected_word(row, _col_of(row, delimiter)) is None
    assert _selected_word(row, _col_of(row, delimiter) + 1) is None


@pytest.mark.parametrize(("row", "click"), [
    ("tmux|newhoo|fixhoo|newmoo|notification|window_bell|herdr", "|"),
    ("alpha,beta;gamma", ","), ("alpha,beta;gamma", ";"),
    ("render_status_line(app, area)", "("), ("render_status_line(app, area)", ")"),
    ("if !enabled {", "!"), ("if !enabled {", "{"), ("(done).", "("), ("(done).", "."),
])
def test_double_click_word_bounds_ignore_delimiters(row, click):
    assert _selected_word(row, _col_of(row, click)) is None


# ── T1-T9: text inputs (client/shell/text_editor.rs) ────────────────────────────────

_CODES = {"Left": "left", "Right": "right", "Home": "home", "End": "end", "Backspace": "backspace",
          "Delete": "delete", "Enter": "enter", "Esc": "esc"}


def _ed_key(editor, code, mods=0, kind="press", text=None):
    result = editor.handle_key(Key(_CODES.get(code, code), mods, kind, None, text))
    starts = [m.start() for m in regex.finditer(r"\X", editor.text)]
    assert editor.cursor == len(editor.text) or editor.cursor in starts
    return result


@pytest.mark.parametrize(("code", "mods", "text", "cursor", "killed"), [
    ("Left", 0, "one two", 3, ""), ("b", CTRL, "one two", 3, ""),
    ("Right", 0, "one two", 5, ""), ("f", CTRL, "one two", 5, ""),
    ("Home", 0, "one two", 0, ""), ("a", CTRL, "one two", 0, ""),
    ("End", 0, "one two", 7, ""), ("e", CTRL, "one two", 7, ""),
    ("Backspace", 0, "onetwo", 3, ""), ("h", CTRL, "onetwo", 3, ""),
    ("Delete", 0, "one wo", 4, ""), ("d", CTRL, "one wo", 4, ""),
    ("b", ALT, "one two", 0, ""), ("f", ALT, "one two", 7, ""),
    ("u", CTRL, "two", 0, "one "), ("k", CTRL, "one ", 4, "two"),
    ("w", CTRL, "two", 0, "one "), ("Backspace", ALT, "two", 0, "one "),
    ("Backspace", CTRL, "two", 0, "one "), ("d", ALT, "one ", 4, "two"),
    ("y", CTRL, "one two", 4, ""), ("X", 0, "one Xtwo", 5, ""),
])
def test_every_binding_edits_at_the_cursor(code, mods, text, cursor, killed):
    editor = TextEditor("one two")
    editor.cursor = 4
    result = _ed_key(editor, code, mods)
    assert (editor.text, editor.cursor, editor.killed) == (text, cursor, killed)
    assert result == (text != "one two")
    _ed_key(TextEditor(), code, mods)


def test_suggestions_movement_kills_and_yank():
    for code, expected in (("Left", "defaulxt"), ("Right", "defaultx"), ("Home", "xdefault"), ("End", "defaultx")):
        editor = TextEditor("default", True)
        _ed_key(editor, code)
        editor.insert("x")
        assert editor.text == expected
    editor = TextEditor("default", True)
    editor.insert("new")
    assert editor.text == "new"
    for replacement, changed in (("default", False), ("another", True)):
        editor = TextEditor("default", True)
        assert editor.handle_key(Key("x", 0, "press", None, replacement)) is changed
        assert editor.text == replacement and not editor.replace_on_type
    editor = TextEditor("default", True)
    _ed_key(editor, "Backspace")
    assert editor.text == ""
    editor = TextEditor("one two", True)
    _ed_key(editor, "w", CTRL)
    assert editor.text == "one " and not editor.replace_on_type
    _ed_key(editor, "k", CTRL)
    _ed_key(editor, "Backspace")
    _ed_key(editor, "y", CTRL)
    _ed_key(editor, "y", CTRL)
    assert editor.text == "onetwotwo"
    _ed_key(editor, "u", CTRL)
    assert editor.killed == "onetwotwo"
    other = TextEditor()
    _ed_key(other, "y", CTRL)
    assert other.text == ""


def test_unicode_graphemes_and_boundary_changing_edits():
    editor = TextEditor("é中👩‍💻")
    for expected in ("é中", "é", ""):
        _ed_key(editor, "Backspace")
        assert editor.text == expected
    editor = TextEditor("👩💻")
    _ed_key(editor, "Left")
    editor.insert("‍")
    assert editor.cursor == len(editor.text)
    _ed_key(editor, "Backspace")
    assert editor.text == ""
    editor = TextEditor("́x")
    _ed_key(editor, "Home")
    editor.insert("e")
    assert editor.cursor == len("é")
    _ed_key(editor, "Delete")
    assert editor.text == "é"


def test_accepting_trimmed_text_preserves_cursor_and_local_kill_buffer():
    editor = TextEditor("  feature/name  ", True)
    editor.trim_and_accept()
    assert editor.text == "feature/name" and not editor.replace_on_type and editor.cursor == len(editor.text)
    _ed_key(editor, "w", CTRL)
    editor.trim_and_accept()
    _ed_key(editor, "y", CTRL)
    assert editor.text == "feature/name"


def test_words_distinguish_paths_punctuation_and_whitespace():
    editor = TextEditor("src/foo_bar.rs  é中 👩‍💻")
    for expected in ("src/foo_bar.rs  é中 ", "src/foo_bar.rs  ", "src/foo_bar.", "src/foo_bar",
                     "src/", "src", ""):
        _ed_key(editor, "w", CTRL)
        assert editor.text == expected
    editor = TextEditor(" /tmp/foo_bar.rs")
    _ed_key(editor, "Home")
    for expected in (2, 5, 6, 13, 14, 16):
        _ed_key(editor, "f", ALT)
        assert editor.cursor == expected


def test_insertion_normalizes_controls_and_respects_host_text():
    editor = TextEditor("ab")
    _ed_key(editor, "Left")
    editor.insert("中\r\n\r\n\t\x00\x1b\x7fé")
    assert editor.text == "a中   éb"
    editor.handle_key(Key("b", CTRL | ALT, "press", None, "β"))
    assert editor.text == "a中   éβb"
    before = (editor.text, editor.cursor)
    assert editor.handle_key(Key("b", CTRL | ALT, "release", None, "β")) is None
    assert (editor.text, editor.cursor) == before
    assert editor.handle_key(Key("left", 0, "repeat")) is not None


@pytest.mark.parametrize("code", ["enter", "esc"])
def test_enter_and_escape_ignore_generated_text(code):
    editor = TextEditor("default", True)
    assert editor.handle_key(Key(code, 0, "press", None, "printable")) is None
    assert editor.text == "default"


def test_viewport_is_pure_and_grapheme_safe():
    for text in ("abcdefghijklmnopqrstuvwxyz", "é中👩‍💻xyz", "́abc"):
        editor = TextEditor(text)
        for cursor in [m.start() for m in regex.finditer(r"\X", text)] + [len(text)]:
            editor.cursor = cursor
            for width in (0, 1, 2, 3, 8, 80):
                before = (editor.text, editor.cursor)
                visible, col = editor.viewport(width)
                assert sum(grapheme_width(g) for g in regex.findall(r"\X", visible)) <= width
                assert width == 0 or col < width
                assert (editor.text, editor.cursor) == before
    editor = TextEditor("abcdef")
    assert editor.viewport(4) == ("def", 3)
    editor.cursor = 2
    assert editor.viewport(4) == ("abcd", 2)
    editor.cursor = 0
    assert editor.viewport(4) == ("abcd", 0)


# ── N1-N18: the navigator (client/shell/aggregate_navigation.rs + overlays.rs) ──────

def _pane(pid, title="shell", *, cwd="/w/proj", ally=None, reported=None, alive=True, busy=False, fg_cwd=None):
    return {"id": pid, "title": title, "cwd": cwd, "ally": ally, "reported": reported, "alive": alive,
            "busy": busy, "foreground": {"cwd": fg_cwd} if fg_cwd else None, "agent_state": None,
            "status": None, "unseen": False}


def _space(sid, folder, tabs, names=None, name=None):
    return {"id": sid, "folder": folder, "name": name, "tabs": tabs,
            "tab_names": names or [None] * len(tabs), "zoomed": [False] * len(tabs)}


def _split(a, b):
    return ("split", "vertical", 0.5, ("pane", a), ("pane", b))


def _nav_fixture():
    spaces = [_space("s1", "/w/proj", [("pane", "p1"), _split("p2", "p3")], names=[None, "research"]),
              _space("s2", "/w/other", [("pane", "p4")])]
    listing = [_pane("p1", "Last Order", reported={"state": "working", "message": "reading", "seq": 1}),
               _pane("p2", "Last Order", cwd="/w/proj/sub"),
               _pane("p3", "shell", ally="claude"),
               _pane("p4", "shell", cwd="/w/other", fg_cwd="/w/other/src")]
    return spaces, listing


def _labels(rows):
    return [(row["target"], row["label"]) for row in rows]


def test_navigator_lists_every_terminal_with_herdr_labels():
    spaces, listing = _nav_fixture()
    rows = panel_mod.navigator_rows(spaces, listing, "p2")
    assert _labels(rows) == [
        (("space", "s1"), "proj"),
        (("pane", "p1"), "Last Order"),                     # single pane: its name
        (("pane", "p2"), "research · Last Order · 1"),      # tab · pane · N
        (("pane", "p3"), "research · claude · 2"),
        (("space", "s2"), "src"),                           # misaka: the label follows the root pane's job
        (("pane", "p4"), "src"),                            # a lone shell in a one-tab space: the space name
    ]
    p2 = rows[2]
    assert p2["current"] and p2["detail"] == "proj / research / p2" and p2["meta"] == "/w/proj/sub"
    assert rows[3]["agent"] == "claude" and rows[1]["agent"] == "misaka" and rows[5]["agent"] is None
    assert rows[5]["meta"] == "/w/other/src"                 # the foreground job's cwd first
    assert rows[1]["message"] == "reading"


def test_navigator_label_for_unnamed_shell_among_several_tabs():
    spaces = [_space("s1", "/w/proj", [("pane", "p1"), ("pane", "p2")])]
    listing = [_pane("p1"), _pane("p2", ally="codex")]
    assert [row["label"] for row in panel_mod.navigator_rows(spaces, listing, None)][1:] == [
        "terminal · 1", "codex · 2"]


def test_navigator_query_words_and_fields():
    spaces, listing = _nav_fixture()

    def targets(query, state_filter=None):
        rows = panel_mod.navigator_rows(spaces, listing, None, query=query, state_filter=state_filter)
        return [row["target"][1] for row in rows]

    assert targets("claude research") == ["s1", "p3"]        # every word, any order, one field
    assert targets("RESEARCH") == ["s1", "p2", "p3"]           # a tab name keeps its panes
    assert targets("src") == ["s2", "p4"]                      # the space name keeps its panes
    assert targets("other/src") == ["s2", "p4"]                # the foreground cwd
    assert targets("p1") == ["s1", "p1"]                       # the pane id
    assert targets("misaka") == ["s1", "p1", "p2"]             # the agent kind
    assert targets("nothing-here") == []
    assert targets("", "working") == ["s1", "p1"]
    assert targets("src", "working") == []                    # a filter drops a name-only space


def test_navigator_space_row_kept_by_its_own_name_and_branch():
    spaces = [_space("s1", "/w/empty", [])]
    rows = panel_mod.navigator_rows(spaces, [], None, query="empty")
    assert _labels(rows) == [(("space", "s1"), "empty")]
    rows = panel_mod.navigator_rows(spaces, [], None, query="feature", git=lambda folder: {"branch": "feature/x"})
    assert rows[0]["meta"] == "feature/x"


def test_navigator_selection_is_by_target():
    spaces, listing = _nav_fixture()
    rows = panel_mod.navigator_rows(spaces, listing, None)
    assert panel_mod.navigator_selected_index(rows, None) == 1           # the first pane row
    assert panel_mod.navigator_selected_index(rows, ("pane", "p4")) == 5
    assert panel_mod.navigator_selected_index(rows, ("pane", "gone")) is None
    assert panel_mod.navigator_selected_index([], None) is None
    only_space = [{"target": ("space", "s")}]
    assert panel_mod.navigator_selected_index(only_space, None) == 0


def test_navigator_scroll_follows_selection():
    rows = [{"target": ("pane", str(i))} for i in range(30)]
    assert panel_mod.navigator_scroll(rows, 20, 0, 10) == (11, 20)
    assert panel_mod.navigator_scroll(rows, 19, 0, 10) == (10, 20)
    assert panel_mod.navigator_scroll(rows, 5, 15, 10) == (5, 20)
    assert panel_mod.navigator_scroll(rows, 29, 25, 10) == (20, 20)


def test_navigator_popup_geometry():
    assert panel_mod.navigator_popup_rect(hui.Rect(0, 0, 200, 60)) == hui.Rect(42, 9, 116, 42)
    assert panel_mod.navigator_popup_rect(hui.Rect(0, 0, 80, 24)) == hui.Rect(2, 1, 76, 22)
    assert panel_mod.navigator_popup_rect(hui.Rect(0, 0, 80, 10)) is None


def _plain(ansi):
    return "".join(symbol for symbol, _style in __import__("misaka.ui.panel.screen", fromlist=["x"]).cells_from_ansi(ansi))


def test_format_navigator_layout():
    spaces, listing = _nav_fixture()
    rows = panel_mod.navigator_rows(spaces, listing, "p2")
    rect = hui.Rect(0, 0, 80, 16)
    out = panel_mod.format_navigator(rows, ("pane", "p2"), 0, rect, TextEditor())
    lines = [_plain(line) for _y, _x, line in out["rows"]]
    assert lines[0].startswith("┌─ Go to ─")
    assert lines[1].startswith("│ / search agents and terminals") and lines[1].rstrip("│ ").endswith("4 terminals")
    assert set(lines[2][1:-1]) == {"─"}
    assert lines[3].startswith("│ proj")
    assert lines[4].startswith("│ ├─ ● Last Order")
    assert lines[5].startswith("│ ├─ ◆ ○ research · Last Order · 1")
    assert lines[6].startswith("│ └─ ○ research · claude · 2")
    body = lines[4][1:-1]
    assert body.endswith("misaka      working    ")                     # 24 columns: kind + status
    assert lines[8].startswith("│ └─ ○ src ")
    assert lines[8][1:-1].rstrip().endswith("shell")                    # no agent: "shell"
    assert lines[12].startswith("│ proj / research / p2")
    assert lines[13].startswith("│ /w/proj/sub")
    assert lines[14].startswith("│ ↑↓/j/k rows · ←→ workspace")
    assert len(out["hits"]) == 6 and out["hits"][2][1] == ("pane", "p2")
    assert out["caret"] is None and out["track"] is None


def test_format_navigator_search_scroll_and_empty():
    editor = TextEditor("zz")
    out = panel_mod.format_navigator([], None, 0, hui.Rect(0, 0, 60, 12), editor, search_focused=True)
    lines = [_plain(line) for _y, _x, line in out["rows"]]
    assert lines[1].startswith("│ / zz") and "0 terminals" in lines[1]
    assert out["caret"] == (1 + 3 + 2, 1)
    assert lines[3].startswith("│ No matching agents or terminals")
    assert lines[-2].startswith("│ search type · move ↑↓/ctrl+n/p")
    rows = [{"target": ("pane", str(i)), "depth": 1, "label": f"t{i}", "meta": "", "detail": "", "agent": None,
             "state": "idle", "seen": True, "status": True, "current": False, "message": ""} for i in range(20)]
    out = panel_mod.format_navigator(rows, ("pane", "15"), 0, hui.Rect(0, 0, 60, 12), TextEditor())
    assert out["track"] == hui.Rect(58, 3, 1, 5)
    assert out["metrics"] == {"offset_from_bottom": 4, "max_offset_from_bottom": 15, "viewport_rows": 5}
    lines = [_plain(line) for _y, _x, line in out["rows"]]
    assert {lines[y][-2] for y in range(3, 8)} <= {"▕", "▐"}
    filtered = panel_mod.format_navigator(rows, None, 0, hui.Rect(0, 0, 60, 12), TextEditor(), state_filter="idle")
    assert _plain(filtered["rows"][1][2]).startswith("│ / idle")


def test_rename_popup_draws_editor_and_caret():
    editor = TextEditor("tab name")
    editor.cursor = 3
    lines, hits, caret = panel_mod.format_rename_popup("rename tab", editor, hui.Rect(10, 5, 56, 7))
    text = [_plain(line) for _y, _x, line in lines]
    assert text[3].startswith("│ tab name ") and "█" not in text[3]
    assert caret == (10 + 1 + 1 + 3, 5 + 3)
    assert [action for _rect, action in hits] == ["save", "clear", "cancel"]
    long = TextEditor("x" * 80)
    _lines, _hits, caret = panel_mod.format_rename_popup("rename tab", long, hui.Rect(0, 0, 56, 7))
    assert caret == (1 + 1 + 52, 3)                                    # the viewport keeps the caret inside


def test_copy_prompt_bar():
    editor = TextEditor("abc")
    line = panel_mod.format_copy_prompt_bar(1, editor, 60)
    cells = __import__("misaka.ui.panel.screen", fromlist=["x"]).cells_from_ansi(line)
    plain = "".join(symbol for symbol, _s in cells)
    assert plain.startswith(" COPY  /abc ")
    assert plain.endswith("  enter search  esc cancel")
    cursor = cells[8 + 3]                                             # the cell after "abc"
    assert cursor[1][1] is not None and cursor[1][0] != cells[8][1][0]  # drawn inverse
    narrow = "".join(symbol for symbol, _s in __import__("misaka.ui.panel.screen", fromlist=["x"]).cells_from_ansi(
        panel_mod.format_copy_prompt_bar(-1, editor, 40)))
    assert narrow.startswith(" COPY  ?abc") and "enter search" not in narrow


def test_modal_paste_shortcut_and_clipboard_commands():
    assert panel_mod.is_modal_paste_shortcut(Key("v", CTRL), macos=False)
    assert panel_mod.is_modal_paste_shortcut(Key("V", CTRL | SHIFT), macos=False)
    assert panel_mod.is_modal_paste_shortcut(Key("v", SUPER), macos=True)
    assert not panel_mod.is_modal_paste_shortcut(Key("v", SUPER), macos=False)
    assert not panel_mod.is_modal_paste_shortcut(Key("v", CTRL, text="v"), macos=False)
    assert not panel_mod.is_modal_paste_shortcut(Key("v", CTRL | ALT), macos=False)
    assert panel_mod._clipboard_read_commands({}, "darwin") == [["pbpaste"]]
    assert panel_mod._clipboard_read_commands({"WAYLAND_DISPLAY": "w", "DISPLAY": ":0"}, "linux") == [
        ["wl-paste", "--type", "text/plain;charset=utf-8"], ["wl-paste", "--type", "text/plain"],
        ["xclip", "-selection", "clipboard", "-out"], ["xsel", "--clipboard", "--output"]]
    assert panel_mod._clipboard_read_commands({}, "linux") == []


def test_clipboard_read_limits(monkeypatch, tmp_path):
    script = tmp_path / "clip"

    def run(body):
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(0o755)
        monkeypatch.setattr(panel_mod, "_clipboard_read_commands", lambda: [[str(script)]])
        return panel_mod._read_clipboard_text()

    assert run("printf 'héllo'") == "héllo"
    assert run("exit 0") is None
    assert run("printf x; exit 1") is None
    assert run("printf '\\377'") is None
    assert run("head -c 1048577 /dev/zero") is None
    assert run("head -c 1048576 /dev/zero | tr '\\0' a") == "a" * 1048576


# ── S1, M2, K11, D1: sidebar reveal, menu placement, paragraph motion, OSC 52 ──────

def test_list_scroll_start_to_reveal_moves_the_least():
    heights = [1] * 10
    assert hui.list_scroll_start_to_reveal(heights, 4, 0, 2) == 0          # already visible
    assert hui.list_scroll_start_to_reveal(heights, 4, 0, 6) == 3          # just far enough
    assert hui.list_scroll_start_to_reveal(heights, 4, 5, 2) == 2          # above: to the target
    assert hui.list_scroll_start_to_reveal(heights, 4, 0, 9) == 6          # never past the end
    assert hui.list_scroll_start_to_reveal([2, 2, 2, 2], 4, 0, 3) == 2     # tall entries shown whole


def test_sidebar_reveals_the_active_space_once():
    spaces = [{"key": f"s{i}", "label": f"space {i}", "folder": "/w", "active": i == 8,
               "state": "idle", "seen": True, "alive": True} for i in range(12)]
    _lines, _hits, sections = panel_mod.format_sidebar(spaces, [], 26, 20, reveal_space=True)
    state = sections["spaces"]
    assert state["revealed"] and state["scroll"] > 0
    _lines, _hits, sections = panel_mod.format_sidebar(spaces, [], 26, 20, reveal_space=False)
    assert not sections["spaces"]["revealed"] and sections["spaces"]["scroll"] == 0


def test_menu_right_edge_follows_the_launcher():
    screen, labels = hui.Rect(0, 0, 80, 24), ["a" * 20]
    assert hui.menu_popup_rect(screen, hui.Rect(40, 23, 10, 1), labels) == hui.Rect(26, 20, 24, 3)
    assert hui.menu_popup_rect(screen, hui.Rect(2, 23, 10, 1), labels) == hui.Rect(0, 20, 24, 3)
    assert hui.menu_popup_rect(hui.Rect(0, 0, 30, 24), hui.Rect(20, 23, 10, 1), labels).x == 6


def test_paragraph_target_finds_the_nearest_blank_row(monkeypatch):
    term = vt.Terminal(20, 8)
    term.write(b"a\r\nb\r\n\r\nc\r\nd")
    pane = _PaneStub(term)
    assert dm.paragraph_target(pane, 4, -1) == 2
    assert dm.paragraph_target(pane, 0, 1) == 2
    assert dm.paragraph_target(pane, 3, 1) == 5                # past the last line: blank
    assert dm.paragraph_target(pane, 2, 0) is None
    assert dm.paragraph_target(pane, 99, 1) is None
    monkeypatch.setattr(dm, "PARAGRAPH_SCAN_ROWS", 2)          # one row of reach
    assert dm.paragraph_target(pane, 1, -1) is None             # row 0 is text: the cursor stays
    pane.compression.cancel()
    term.close()


def test_osc52_writes_are_captured_and_validated():
    writes = []
    term = vt.Terminal(20, 5, on_clipboard_write=writes.append)
    term.write(b"\x1b]52;c;aGVsbG8=\x07")
    term.write(b"\x1b]52;c;?\x07")                             # a query, not a write
    assert writes == [b"hello"]
    term.close()


# ── P9: toasts queue, the copy box has its own slot (notification_policy.rs, ui.rs) ──

def test_toasts_queue_first_in_first_out_and_time_from_showing():
    queue = panel_mod.ToastQueue()
    queue.push({"text": "one"}, 0.0, 4.0)
    queue.push({"text": "two"}, 1.0, 4.0)
    assert queue.visible["text"] == "one" and queue.visible["deadline"] == 4.0
    assert not queue.tick(3.9, 4.0)
    assert queue.tick(5.0, 4.0)
    assert queue.visible["text"] == "two" and queue.visible["deadline"] == 9.0   # timed from showing
    assert queue.tick(9.0, 4.0) and queue.visible is None


def test_toast_queue_drops_the_oldest_and_replaces_by_pane():
    queue = panel_mod.ToastQueue()
    queue.push({"text": "shown"}, 0.0, 4.0)
    for index in range(panel_mod.MAX_QUEUED_NOTIFICATIONS + 2):
        queue.push({"text": f"q{index}"}, 0.0, 4.0)
    assert [toast["text"] for toast in queue.queue] == [f"q{i}" for i in range(2, 10)]
    queue = panel_mod.ToastQueue()
    queue.push({"text": "a1", "pane": "a"}, 0.0, 4.0)
    queue.push({"text": "b1", "pane": "b"}, 0.0, 4.0)
    queue.push({"text": "a2", "pane": "a"}, 1.0, 4.0)
    assert queue.visible["text"] == "b1"                        # a1 gave way, b1 was next
    assert [toast["text"] for toast in queue.queue] == ["a2"]


def test_copy_feedback_moves_up_over_a_toast():
    area = hui.Rect(0, 0, 60, 20)
    toast_rect, _rows = panel_mod.format_toast("Input not delivered", "x" * 50, "needs_attention", area)
    offset = panel_mod.copy_feedback_offset("copied to clipboard", area, toast_rect)
    assert offset == toast_rect.height
    rect, _rows = panel_mod.format_copy_feedback("copied to clipboard", area, offset)
    assert not panel_mod.rects_overlap(rect, toast_rect)
    small, _rows = panel_mod.format_toast("x", "", "needs_attention", area)
    assert panel_mod.copy_feedback_offset("copied to clipboard", area, small) == 0
    assert panel_mod.copy_feedback_offset("copied to clipboard", area, None) == 0


# ── D3: DECSCUSR cursor shape passthrough (pane/cursor.rs, pane/terminal.rs) ─────────

def _tracker_bytewise(chunks):
    tracker = dm.DecscusrTracker()
    for chunk in chunks:
        for byte in chunk:
            tracker._byte(byte)
    return tracker


def _tracker_state(tracker):
    return (tracker.state, tracker.first, tracker.collecting, tracker.space, tracker.overridden)


@pytest.mark.parametrize("data", [
    b"", b"plain text\n\twithout escapes", b"text\x1b[1 qmore\x1b[0 qend",
    b"\x1b[ q\x1b[2 q\x1b[3 q\x1b[4 q\x1b[5 q\x1b[6 q\x1b[7 q", b"\x1b\x1b[1 q\x1b[2;9 q\x1b[0:4 q",
    b"\x1b[1q\x1b[? q\x1b[12$ q\x1b[1\x00 q\x1b[2\xff q", b"\x1b[12\x1b[5 q\x1b]0;title\x07\x1bPdata\x1b\\",
    b"\x1b[1 q\x1b", b"\x1b[1 q\x1b[", b"\x1b[1 q\x1b[0 ",
])
def test_decscusr_bulk_search_matches_bytewise_control_sequences_and_splits(data):
    for split in range(len(data) + 1):
        chunks = [data[:split], data[split:]]
        tracker = dm.DecscusrTracker()
        for chunk in chunks:
            tracker.observe(chunk)
        assert _tracker_state(tracker) == _tracker_state(_tracker_bytewise(chunks))


def test_decscusr_bulk_search_matches_bytewise_all_byte_values():
    for prefix in (b"", b"\x1b", b"\x1b[", b"\x1b[2", b"\x1b[0 ", b"\x1b[2;"):
        for byte in range(256):
            data = b"\x1b[1 q" + prefix + bytes([byte]) + b" qtext\x1b[0 q\x1b[6 q"
            tracker = dm.DecscusrTracker()
            tracker.observe(data)
            assert _tracker_state(tracker) == _tracker_state(_tracker_bytewise([data]))


def test_decscusr_override_follows_the_last_sequence():
    tracker = dm.DecscusrTracker()
    tracker.observe(b"\x1b[5 q")
    assert tracker.overridden
    tracker.observe(b"\x1b[7 q")                      # out of range: ignored
    assert tracker.overridden
    tracker.observe(b"\x1b[0 q")
    assert not tracker.overridden
    tracker.observe(b"\x1b[ q")                       # no parameter is 0
    assert not tracker.overridden


def test_decscusr_cursor_shape_preserves_blinking_variants():
    shapes = [dm.decscusr_cursor_shape(style, blink)
              for style, blink in ((vt.CURSOR_STYLE_BLOCK, True), (vt.CURSOR_STYLE_BLOCK, False),
                                   (vt.CURSOR_STYLE_UNDERLINE, True), (vt.CURSOR_STYLE_UNDERLINE, False),
                                   (vt.CURSOR_STYLE_BAR, True), (vt.CURSOR_STYLE_BAR, False),
                                   (vt.CURSOR_STYLE_BLOCK_HOLLOW, True), (vt.CURSOR_STYLE_BLOCK_HOLLOW, False))]
    assert shapes == [1, 2, 3, 4, 5, 6, 1, 2]


def test_pane_cursor_shape_comes_from_the_program():
    class _Shaped:
        def __init__(self):
            self.term, self.render, self.decscusr = vt.Terminal(20, 5), vt.RenderState(), dm.DecscusrTracker()

        def feed(self, data):
            self.decscusr.observe(data)
            self.term.write(data)
            self.render.update(self.term)
            return dm._cursor_shape(self)

    pane = _Shaped()
    assert pane.feed(b"hello") == 0                   # never set: the host's default
    assert pane.feed(b"\x1b[6 q") == 6                # steady bar (vim insert mode)
    assert pane.feed(b"\x1b[3 q") == 3                # blinking underline
    assert pane.feed(b"\x1b[0 q") == 0                # handed back
    pane.render.close()
    pane.term.close()


# ── D4: the host window title (config/window_title.rs, terminal_effects.rs) ──────────

def test_sanitizes_and_bounds_rendered_titles():
    assert panel_mod.sanitize_window_title("  herdr\x1b api\x07\n  ") == "herdr api"
    assert panel_mod.sanitize_window_title("\x07\n") is None
    assert len(panel_mod.sanitize_window_title("x" * (panel_mod.MAX_WINDOW_TITLE_CHARS + 1))) == 200


def test_window_title_strips_terminators_and_defaults_to_the_product():
    assert panel_mod.window_title_bytes("host: proj") == b"\x1b]0;host: proj\x07"
    assert panel_mod.window_title_bytes(None) == b"\x1b]0;misaka\x07"
