"""Host terminal bytes -> input events: keys, mouse, paste, focus.

Port of herdr ``src/input/parse.rs`` (key sequences: kitty CSI u, modifyOtherKeys, xterm
modified specials, legacy) and of the host-input framer in ``src/raw_input.rs``
(``RawInputByteFramer``: sequence boundaries, bracketed paste, the idle flush with its
mouse-report recovery, control strings discarded after a timeout) plus the flush timing
of ``src/client/input.rs`` (``idle_flush_timeout_ms``). The panel never looks at raw bytes
again: every mode handler receives ``Key``/``Mouse``/``Paste``/``Focus`` values, and the
pane encoder (``pane_input``) turns a ``Key`` back into bytes for the protocol the pane
negotiated.

The framer works on decoded text instead of bytes: every sequence it has to recognise is
ASCII, so character counts equal byte counts there, and an incomplete UTF-8 character
simply stays inside the incremental decoder (herdr's "waiting for UTF-8 continuation
bytes"). The host-reply families herdr also frames (OSC 10/11 palette replies, cell-size
and colour-scheme reports) are not ported: the panel sends none of those queries while
it runs.
"""
import codecs
import sys
import time
from dataclasses import dataclass

SHIFT, ALT, CTRL, SUPER, HYPER, META = 1, 2, 4, 8, 16, 32
LOCK_MASK = 64 | 128                 # caps / num lock bits (kitty): never part of a binding

# raw_input.rs RAW_INPUT_IDLE_FLUSH_TIMEOUT_MS / MOUSE_ACTIVE_ESCAPE_SEQUENCE_FLUSH_TIMEOUT_MS
RAW_INPUT_IDLE_FLUSH_TIMEOUT = 0.010
MOUSE_ACTIVE_ESCAPE_SEQUENCE_FLUSH_TIMEOUT = 0.150
MAX_DISCARDED_CONTROL_TAIL_BYTES = 128
MAX_ORPHANED_SGR_MOUSE_TAIL_BYTES = 32
# platform::capabilities().preserve_legacy_doubled_escape_input: macOS keeps ``ESC ESC ...``
# together (Option-as-Meta sends Alt+Esc / Alt+arrow that way); elsewhere a doubled ESC is
# two events.
PRESERVE_LEGACY_DOUBLED_ESCAPE_INPUT = sys.platform == "darwin"
# terminal_setup.rs query_host_escape_disambiguation
KEYBOARD_PROBE = b"\x1b[?u\x1b[c"
KEYBOARD_PROBE_TIMEOUT = 0.250
MAX_BUFFERED_HOST_INPUT = 64 * 1024


@dataclass(frozen=True, slots=True)
class Key:
    """One key event. ``code`` is the character itself for character keys, otherwise a
    name: enter, tab, backtab, backspace, esc, up, down, left, right, home, end, pageup,
    pagedown, insert, delete, f1..f35, modifier (a bare shift/ctrl/alt press under the kitty
    protocol), media. ``mods`` are the kitty modifier bits (SHIFT .. META, plus lock bits)."""
    code: str
    mods: int = 0
    kind: str = "press"              # press | repeat | release
    shifted: int | None = None       # kitty alternate (shifted) codepoint, when reported
    text: str | None = None          # kitty associated text, when reported

    @property
    def is_char(self):
        return len(self.code) == 1

    def matches(self, code, mods=0):
        """Binding match: the lock bits never count (herdr terminal_key_matches_combo)."""
        return self.code == code and (self.mods & ~LOCK_MASK) == mods


@dataclass(frozen=True, slots=True)
class Mouse:
    """``kind``: press, release, drag (motion with a button held), move, wheel_up,
    wheel_down, wheel_left, wheel_right. ``button``: 0 left, 1 middle, 2 right (a report
    that names no button -- an X10 release -- is a left release, as herdr reads it).
    ``x``/``y`` are zero-based screen cells."""
    kind: str
    button: int
    x: int
    y: int
    mods: int = 0


@dataclass(frozen=True, slots=True)
class Paste:
    text: str


@dataclass(frozen=True, slots=True)
class Focus:
    gained: bool


_ESC = "\x1b"
_PASTE_START, _PASTE_END = "\x1b[200~", "\x1b[201~"
_CSI_FINALS = frozenset(chr(code) for code in range(0x40, 0x7F))

# parse.rs parse_legacy_special_sequence (the Alt+arrow rows are covered by parse_key's
# generic ESC-prefix rule).
_LEGACY = {
    "\x1b[A": "up", "\x1bOA": "up", "\x1b[B": "down", "\x1bOB": "down",
    "\x1b[C": "right", "\x1bOC": "right", "\x1b[D": "left", "\x1bOD": "left",
    "\x1b[H": "home", "\x1bOH": "home", "\x1b[1~": "home", "\x1b[7~": "home",
    "\x1b[F": "end", "\x1bOF": "end", "\x1b[4~": "end", "\x1b[8~": "end",
    "\x1b[5~": "pageup", "\x1b[6~": "pagedown", "\x1b[2~": "insert", "\x1b[3~": "delete",
    "\x1bOM": "enter",
    "\x1bOP": "f1", "\x1b[11~": "f1", "\x1bOQ": "f2", "\x1b[12~": "f2",
    "\x1bOR": "f3", "\x1b[13~": "f3", "\x1bOS": "f4", "\x1b[14~": "f4",
    "\x1b[15~": "f5", "\x1b[17~": "f6", "\x1b[18~": "f7", "\x1b[19~": "f8",
    "\x1b[20~": "f9", "\x1b[21~": "f10", "\x1b[23~": "f11", "\x1b[24~": "f12",
}
_SS3_KEYPAD = {"p": "0", "q": "1", "r": "2", "s": "3", "t": "4", "u": "5", "v": "6",
               "w": "7", "x": "8", "y": "9", "n": ".", "l": ",", "m": "-", "k": "+",
               "j": "*", "o": "/"}
_XTERM_LETTERS = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end",
                  "P": "f1", "Q": "f2", "R": "f3", "S": "f4"}
_XTERM_TILDES = {"2": "insert", "3": "delete", "5": "pageup", "6": "pagedown",
                 "11": "f1", "12": "f2", "13": "f3", "14": "f4", "15": "f5",
                 "17": "f6", "18": "f7", "19": "f8", "20": "f9", "21": "f10", "23": "f11",
                 "24": "f12"}
_KITTY_NAMED = {8: "backspace", 127: "backspace", 9: "tab", 13: "enter", 57414: "enter", 27: "esc",
                57417: "left", 57418: "right", 57419: "up", 57420: "down", 57421: "pageup",
                57422: "pagedown", 57423: "home", 57424: "end", 57425: "insert", 57426: "delete",
                57427: "kpbegin", 57358: "capslock", 57359: "scrolllock", 57360: "numlock",
                57361: "printscreen", 57362: "pause", 57363: "menu"}
_KITTY_KEYPAD = {57399: "0", 57400: "1", 57401: "2", 57402: "3", 57403: "4", 57404: "5",
                 57405: "6", 57406: "7", 57407: "8", 57408: "9", 57409: ".", 57410: "/",
                 57411: "*", 57412: "-", 57413: "+", 57415: "=", 57416: ","}
_EVENT_KINDS = {"1": "press", "2": "repeat", "3": "release"}
_CTRL_PUNCT = {0: " ", 27: "[", 28: "\\", 29: "]", 30: "^", 31: "_"}
# parse.rs matching_control_associated_text: WezTerm's report-all mode attaches the key's own
# legacy control code as associated text.
_MATCHING_CONTROL_TEXT = {("enter", "13"), ("backspace", "8"), ("tab", "9"), ("esc", "27")}


# ── One sequence -> one event (parse.rs) ──────────────────────────────────────────────

def _u8(text):
    """``text.parse::<u8>()``: decimal digits only, 0..255, else None."""
    if not text or not text.isascii() or not text.isdigit():
        return None
    value = int(text)
    return value if value <= 255 else None


def _u32(text):
    if not text or not text.isascii() or not text.isdigit():
        return None
    value = int(text)
    return value if value <= 0xFFFFFFFF else None


def _char(codepoint):
    """``char::from_u32``: no surrogates, nothing past U+10FFFF."""
    if codepoint is None or codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
        return None
    return chr(codepoint)


def is_control(ch):
    """Rust ``char::is_control``: the Cc category (C0, DEL, C1)."""
    code = ord(ch)
    return code < 0x20 or 0x7F <= code <= 0x9F


def _modifiers(text):
    """``modifier_text.parse::<u8>().ok()?.checked_sub(1)?`` as kitty modifier bits."""
    value = _u8(text)
    if value is None or value == 0:
        return None
    return value - 1


def _split_modifier_and_event(part):
    modifier, sep, event = part.partition(":")
    if sep and modifier:
        return modifier, event
    return part, None


def _event_kind(value):
    return _EVENT_KINDS.get("1" if value is None else value)


def _kitty_code(codepoint):
    """kitty_codepoint_to_keycode."""
    if codepoint in _KITTY_NAMED:
        return _KITTY_NAMED[codepoint]
    if codepoint in _KITTY_KEYPAD:
        return _KITTY_KEYPAD[codepoint]
    if 57364 <= codepoint <= 57375:
        return f"f{codepoint - 57364 + 1}"
    if 57376 <= codepoint <= 57398:
        return f"f{codepoint - 57376 + 13}"
    if 57428 <= codepoint <= 57440:
        return "media"
    if 57441 <= codepoint <= 57454:
        return "modifier"
    return _char(codepoint)


def _associated_text(value):
    """parse_kitty_associated_text: colon-separated codepoints, none of them a control."""
    text = []
    for part in value.split(":"):
        ch = _char(_u32(part))
        if ch is None or is_control(ch):
            return None
        text.append(ch)
    return "".join(text) or None


def _parse_kitty(seq):
    if not (seq.startswith("\x1b[") and seq.endswith("u")) or len(seq) < 4:
        return None
    fields = seq[2:-1].split(";")
    if len(fields) > 3:
        return None
    key_part = fields[0]
    modifier_part = fields[1] if len(fields) > 1 and fields[1] else "1"
    raw_text = fields[2] if len(fields) > 2 else None
    modifier_text, event_type = _split_modifier_and_event(modifier_part)
    mods = _modifiers(modifier_text)
    if mods is None:
        return None
    key_fields = key_part.split(":")
    codepoint = _u32(key_fields[0])
    if codepoint is None:
        return None
    shifted = _u32(key_fields[1]) if len(key_fields) > 1 and key_fields[1] else None
    code = _kitty_code(codepoint)
    if code is None:
        return None
    text = None
    if raw_text is not None:
        text = _associated_text(raw_text)
        if text is None and (code, raw_text) not in _MATCHING_CONTROL_TEXT:
            return None
    kind = _event_kind(event_type)
    if kind is None:
        return None
    # Kitty permits the shifted alternate only while Shift is active.
    if len(code) == 1 and shifted is not None and shifted != codepoint and _char(shifted) is not None:
        mods |= SHIFT
    return Key(code, mods, kind, shifted, text)


def _parse_modify_other(seq):
    if not (seq.startswith("\x1b[27;") and seq.endswith("~")):
        return None
    modifier_part, sep, codepoint_part = seq[5:-1].partition(";")
    if not sep:
        return None
    mods = _modifiers(modifier_part)
    codepoint = _u32(codepoint_part)
    if mods is None or codepoint is None:
        return None
    code = _kitty_code(codepoint)
    return Key(code, mods) if code else None


def _split_xterm_modifier_and_event(part):
    """split_xterm_modifier_and_event: a third field is associated text (Alacritty on macOS
    reports Cocoa function-key markers there); it must be valid and is then ignored."""
    modifier_and_event, sep, associated = part.partition(";")
    if sep and _associated_text(associated) is None:
        return None
    return _split_modifier_and_event(modifier_and_event if sep else part)


def _parse_xterm_modified(seq):
    """parse_xterm_modified_special_sequence."""
    if not seq.startswith("\x1b["):
        return None
    body = seq[2:]
    if body.startswith("1;") and body[-1:].isascii() and body[-1:].isalpha():
        split = _split_xterm_modifier_and_event(body[2:-1])
        if split is None:
            return None
        mods = _modifiers(split[0])
        code = _XTERM_LETTERS.get(body[-1])
        if mods is None or code is None:
            return None
        kind = _event_kind(split[1])
        return Key(code, mods, kind) if kind else None
    if not body.endswith("~"):
        return None
    code_part, sep, modifier_part = body[:-1].partition(";")
    if not sep:
        return None
    split = _split_xterm_modifier_and_event(modifier_part)
    if split is None:
        return None
    mods = _modifiers(split[0])
    code = _XTERM_TILDES.get(code_part)
    if mods is None or code is None:
        return None
    kind = _event_kind(split[1])
    return Key(code, mods, kind) if kind else None


def _parse_ctrl_char(ch):
    value = ord(ch)
    if 1 <= value <= 26:
        return Key(chr(value + 96), CTRL)
    if value in _CTRL_PUNCT:
        return Key(_CTRL_PUNCT[value], CTRL)
    return None


def parse_key(seq):
    """One complete input sequence (str) to a Key, or None when it is not a key."""
    if seq in _LEGACY:
        return Key(_LEGACY[seq])
    if seq == "\x1b[Z":
        return Key("backtab", SHIFT)
    if len(seq) == 3 and seq.startswith("\x1bO") and seq[2] in _SS3_KEYPAD:
        return Key(_SS3_KEYPAD[seq[2]])
    for parser in (_parse_kitty, _parse_modify_other, _parse_xterm_modified):
        key = parser(seq)
        if key is not None:
            return key
    if seq == "\r":
        return Key("enter")
    if seq == "\t":
        return Key("tab")
    if seq == "\x1b":
        return Key("esc")
    if seq == "\x7f":
        return Key("backspace")
    if seq == "\x1b\x7f":
        return Key("backspace", ALT)
    if seq.startswith("\x1b") and len(seq) >= 2:
        # Alt + key: ESC prefix. herdr takes ESC + one character; MISAKA also reads ESC + a
        # whole sequence (\x1b\x1b[5~ is Alt+PageUp), which terminals using Option-as-Meta send.
        inner = parse_key(seq[1:])
        if inner is None or len(seq) > 2 and not seq[1:].startswith("\x1b["):
            return None
        return Key(inner.code, inner.mods | ALT, inner.kind, inner.shifted)
    if len(seq) == 1:
        ctrl = _parse_ctrl_char(seq)
        if ctrl is not None:
            return ctrl
        return Key(seq, SHIFT if "A" <= seq <= "Z" else 0)
    return None


def _mouse_cb(cb):
    """raw_input.rs parse_mouse_cb: ``(kind, button, mods)`` or None."""
    button_number = (cb & 0b11) | ((cb & 0b1100_0000) >> 4)
    dragging = bool(cb & 0b10_0000)
    if button_number <= 2:
        kind, button = ("drag" if dragging else "press"), button_number
    elif button_number == 3 and not dragging:
        kind, button = "release", 0
    elif dragging and button_number in (3, 4, 5, 8, 9):
        kind, button = "move", 3        # extended-button drags keep their position as motion
    elif button_number in (4, 5, 6, 7) and not dragging:
        kind, button = ("wheel_up", "wheel_down", "wheel_left", "wheel_right")[button_number - 4], button_number - 4
    else:
        return None
    mods = (SHIFT if cb & 4 else 0) | (ALT if cb & 8 else 0) | (CTRL if cb & 16 else 0)
    return kind, button, mods


def _parse_sgr_mouse(seq):
    if not seq.startswith("\x1b[<") or seq[-1:] not in ("M", "m"):
        return None
    parts = seq[3:-1].split(";")
    if len(parts) < 3:
        return None
    cb = _u8(parts[0])
    column, row = _u32(parts[1]), _u32(parts[2])
    if cb is None or column is None or row is None or not 1 <= column <= 0xFFFF or not 1 <= row <= 0xFFFF:
        return None
    decoded = _mouse_cb(cb)
    if decoded is None:
        return None
    kind, button, mods = decoded
    if seq[-1] == "m" and kind == "press":
        kind = "release"
    return Mouse(kind, button, column - 1, row - 1, mods)


def _parse_default_mouse(seq):
    if len(seq) != 6 or not seq.startswith("\x1b[M"):
        return None
    cb, column, row = ord(seq[3]) - 32, ord(seq[4]) - 33, ord(seq[5]) - 33
    if not 0 <= cb <= 255 or column < 0 or row < 0:
        return None
    decoded = _mouse_cb(cb)
    if decoded is None:
        return None
    kind, button, mods = decoded
    return Mouse(kind, button, column, row, mods)


def parse_mouse(seq):
    """An SGR (1006) or X10 mouse report to a Mouse, or None."""
    return _parse_sgr_mouse(seq) or _parse_default_mouse(seq)


def parse_sequence(seq):
    """One complete sequence to its event (Key, Mouse, Focus) or None for noise."""
    if seq == "\x1b[I":
        return Focus(True)
    if seq == "\x1b[O":
        return Focus(False)
    return parse_mouse(seq) or parse_key(seq)


# ── Sequence boundaries (raw_input.rs) ────────────────────────────────────────────────

def _find_csi_final(buffer, finals):
    for index in range(2, len(buffer)):
        if buffer[index] in finals:
            return index + 1
    return None


def _control_string_family(buffer):
    head = buffer[:2]
    if head == "\x1b]":
        return "osc"
    if head in ("\x1bP", "\x1b_", "\x1b^", "\x1bX"):
        return "st"
    return None


def _control_string_terminator(buffer, family):
    st = buffer.find("\x1b\\")
    st = st + 2 if st >= 0 else None
    if family == "st":
        return st
    bel = buffer.find("\x07")
    bel = bel + 1 if bel >= 0 else None
    ends = [end for end in (st, bel) if end is not None]
    return min(ends) if ends else None


def _complete_escape_sequence_len(buffer):
    """complete_escape_sequence_len: the length of the sequence at the head of ``buffer``
    (which starts with ESC), or None while it is incomplete."""
    if len(buffer) == 1:
        return None
    if buffer.startswith("\x1b\x1b[<"):
        mouse_len = _find_csi_final(buffer[1:], "Mm")
        if mouse_len is not None and _parse_sgr_mouse(buffer[1:1 + mouse_len]) is not None:
            return 1
    if len(buffer) >= 7 and buffer.startswith("\x1b\x1b[M") and _parse_default_mouse(buffer[1:7]) is not None:
        return 1
    if buffer.startswith("\x1b\x1b"):
        inner = _complete_escape_sequence_len(buffer[1:])
        return None if inner is None else inner + 1
    if buffer.startswith("\x1b["):
        if buffer.startswith("\x1b[<"):
            return _find_csi_final(buffer, "Mm")
        if buffer.startswith("\x1b[M"):
            return 6 if len(buffer) >= 6 else None
        return _find_csi_final(buffer, _CSI_FINALS)
    family = _control_string_family(buffer)
    if family is not None:
        return _control_string_terminator(buffer, family)
    if buffer.startswith("\x1bO"):
        return 3 if len(buffer) >= 3 else None
    return 2                             # ESC + one character: Alt+key


def _incomplete_sgr_mouse(buffer):
    return buffer.startswith("\x1b[<") and all(ch.isdigit() and ch.isascii() or ch == ";" for ch in buffer[3:])


def _incomplete_default_mouse(buffer):
    return buffer.startswith("\x1b[M") and len(buffer) < 6


def _bounded_incomplete_escape(buffer):
    """starts_with_bounded_incomplete_escape_sequence."""
    if len(buffer) >= MAX_DISCARDED_CONTROL_TAIL_BYTES:
        return False
    if buffer in (_ESC, "\x1bO"):
        return True
    if not buffer.startswith("\x1b["):
        return False
    return all(0x20 <= ord(ch) <= 0x3F for ch in buffer[2:])


def _known_escape_introducer(buffer):
    return len(buffer) > 1 and buffer[1] in "[O]P_^X\x1b"


def _incomplete_orphaned_sgr_mouse_tail(buffer):
    if len(buffer) > MAX_ORPHANED_SGR_MOUSE_TAIL_BYTES:
        return False
    if len(buffer) < 3 and "[<".startswith(buffer):
        return True
    return buffer.startswith("[<") and all(ch.isdigit() and ch.isascii() or ch == ";" for ch in buffer[2:])


def _complete_orphaned_sgr_mouse_tail_len(buffer):
    """discard_complete_orphaned_sgr_mouse_tail: the length of a whole ``[<...M`` report
    left behind by an ESC that was already released, or 0."""
    ends = [index for index in (buffer.find("M"), buffer.find("m")) if index >= 0]
    if not ends:
        return 0
    length = min(ends) + 1
    if length > MAX_ORPHANED_SGR_MOUSE_TAIL_BYTES or _parse_sgr_mouse(_ESC + buffer[:length]) is None:
        return 0
    return length


def _plausible_sgr_mouse_prefix(report):
    """plausible_sgr_mouse_prefix: rejects continuations that can never become a report."""
    if not report.startswith("\x1b[<"):
        return False
    fields = report[3:].split(";")
    for index, digits in enumerate(fields):
        last = index == len(fields) - 1
        if index > 2:
            return False
        if not digits:
            return last
        if not (digits.isascii() and digits.isdigit()):
            return False
        value = int(digits)
        if value > 0xFFFF or (index == 0 and value > 255):
            return False
        if not last and ((index == 0 and _mouse_cb(value) is None) or (index == 1 and value == 0)):
            return False
    return True


def _classify_sgr_mouse_continuation(prefix, tail):
    """classify_sgr_mouse_continuation: ("incomplete", 0) | ("complete", n) | ("invalid", 0)."""
    tail = tail[:max(0, MAX_DISCARDED_CONTROL_TAIL_BYTES - len(prefix))]
    final_index = next((i for i, ch in enumerate(tail) if not (ch.isascii() and ch.isdigit()) and ch != ";"), None)
    payload = tail if final_index is None else tail[:final_index]
    report = prefix + payload
    if not _plausible_sgr_mouse_prefix(report):
        return "invalid", 0
    if final_index is not None:
        if _parse_sgr_mouse(report + tail[final_index]) is not None:
            return "complete", final_index + 1
        return "invalid", 0
    if len(report) >= MAX_DISCARDED_CONTROL_TAIL_BYTES:
        return "invalid", 0
    return "incomplete", 0


_OSC_TAIL_CHARS = frozenset("0123456789;:/#?._-+rgbRGB\x1b")


def _plausible_control_string_tail(family, buffer):
    if family == "osc":
        return all(ch in _OSC_TAIL_CHARS for ch in buffer)
    return buffer.endswith(_ESC)


class HostInput:
    """Turns stdin chunks into events: herdr's ``RawInputByteFramer`` driven by the idle
    flush of its stdin reader. ``feed`` frames what arrived; when ``deadline()`` passes with
    no more input, ``flush()`` decides what a partial sequence was. ``mouse_capture``: the
    panel has host mouse reporting on, so a lone ESC, a bare ``ESC [`` or a partial mouse
    report gets the longer grace period (a mouse report split across reads is otherwise
    indistinguishable from Escape followed by typing). ``escape_disambiguation``: the host
    confirmed the kitty disambiguate flag, so Escape and Alt chords arrive as CSI u and a
    partial escape sequence is never released by timeout."""

    def __init__(self, *, mouse_capture=True, escape_disambiguation=False):
        self.mouse_capture = mouse_capture
        self.escape_disambiguation = escape_disambiguation
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buffer = ""
        self._paste = None               # text collected since the paste opener, or None
        self._mouse_prefix = None        # timed_out_mouse_prefix
        self._lone_escape_recently_flushed = False
        self._discard_until = None       # "osc" | "st": an incomplete control string's tail
        self._discarded_tail_bytes = 0
        self._flush_at = None            # when the next idle flush is due
        self._flushes = 0                # idle flushes since the last read (herdr does at most two)

    # ── timing (client/input.rs unix_stdin_reader_loop) ──

    def _idle_timeout(self):
        buffer = self._buffer
        if self.mouse_capture and (buffer in (_ESC, "\x1b[") or _incomplete_sgr_mouse(buffer)
                                   or _incomplete_default_mouse(buffer)):
            return MOUSE_ACTIVE_ESCAPE_SEQUENCE_FLUSH_TIMEOUT
        return RAW_INPUT_IDLE_FLUSH_TIMEOUT

    def deadline(self):
        """When ``flush`` should run for the buffered partial input, or None."""
        return self._flush_at

    def feed(self, data, now=None):
        now = time.monotonic() if now is None else now
        if len(data) == 1 and data[0] > 127 and not self._buffer and self._paste is None:
            text = "\x1b" + chr(data[0] - 128)   # 8-bit meta: Alt+key as one high byte
        else:
            text = self._decoder.decode(bytes(data))
        self._buffer += text
        events = self._events(self._drain())
        self._flushes = 0
        self._flush_at = now + self._idle_timeout() if self._buffer else None
        return events

    def flush(self, now=None):
        """The idle flush (raw_input.rs flush_timeout); called when ``deadline`` has passed.
        A flush that could decide nothing gets one more short window, then the framer waits
        for the next read, as herdr's reader does."""
        now = time.monotonic() if now is None else now
        had_pending = bool(self._buffer)
        chunks = self._flush_timeout()
        self._flushes += 1
        held = had_pending and not chunks
        if self._buffer and held and self._flushes < 2:
            self._flush_at = now + RAW_INPUT_IDLE_FLUSH_TIMEOUT
        else:
            self._flush_at = None
        return self._events(chunks)

    # ── framing ──

    def _drain(self):
        """drain_available_chunks: complete chunks off the head of the buffer."""
        chunks = []
        while True:
            if self._paste is not None:
                cut = self._buffer.find(_PASTE_END)
                if cut < 0:
                    keep = len(_PASTE_END) - 1          # a terminator split across reads
                    self._paste += self._buffer[:-keep] if len(self._buffer) > keep else ""
                    self._buffer = self._buffer[-keep:] if len(self._buffer) > keep else self._buffer
                    break
                chunks.append(Paste(self._paste + self._buffer[:cut]))
                self._paste, self._buffer = None, self._buffer[cut + len(_PASTE_END):]
                continue
            if self._mouse_prefix is not None:
                verdict, length = _classify_sgr_mouse_continuation(self._mouse_prefix, self._buffer)
                if verdict == "incomplete":
                    break
                if verdict == "complete":
                    self._buffer = self._buffer[length:]
                self._mouse_prefix = None
            if self._lone_escape_recently_flushed:
                if _incomplete_orphaned_sgr_mouse_tail(self._buffer):
                    break
                length = _complete_orphaned_sgr_mouse_tail_len(self._buffer)
                self._lone_escape_recently_flushed = False
                if length:
                    self._buffer = self._buffer[length:]
                    continue
            if self._discard_until is not None:
                end = _control_string_terminator(self._buffer, self._discard_until)
                if end is None:
                    break
                self._buffer = self._buffer[end:]
                self._discard_until, self._discarded_tail_bytes = None, 0
                continue
            if not PRESERVE_LEGACY_DOUBLED_ESCAPE_INPUT and self._buffer.startswith("\x1b\x1b"):
                chunks.append(_ESC)
                self._buffer = self._buffer[1:]
                continue
            if (self.escape_disambiguation and self._buffer[:1] == _ESC and len(self._buffer) > 1
                    and not _known_escape_introducer(self._buffer)):
                self._buffer = self._buffer[1:]
                continue
            if not self._buffer:
                break
            if self._buffer.startswith(_PASTE_START):
                self._paste, self._buffer = "", self._buffer[len(_PASTE_START):]
                continue
            if self._buffer[0] == _ESC:
                length = _complete_escape_sequence_len(self._buffer)
                if length is None:
                    break
            else:
                length = 1
            chunks.append(self._buffer[:length])
            self._buffer = self._buffer[length:]
        return chunks

    def _retain_timed_out_mouse_prefix(self, prefix):
        self._mouse_prefix = (prefix if len(prefix) < MAX_DISCARDED_CONTROL_TAIL_BYTES
                              and _plausible_sgr_mouse_prefix(prefix) else None)

    def _flush_timeout(self):
        chunks = self._drain()
        # Idle is not evidence that a mouse report has ended: the continuation stays bounded
        # and is released if it cannot complete a valid report.
        if self._mouse_prefix is not None:
            return chunks
        buffer = self._buffer
        if self._discard_until is not None:
            keep_split_st = buffer.endswith(_ESC)
            keep = _plausible_control_string_tail(self._discard_until, buffer)
            self._discarded_tail_bytes += len(buffer)
            self._buffer = ""
            if keep and self._discarded_tail_bytes <= MAX_DISCARDED_CONTROL_TAIL_BYTES:
                if keep_split_st:
                    self._buffer = _ESC
            else:
                self._discard_until, self._discarded_tail_bytes = None, 0
            return chunks
        if not buffer or self._paste is not None:
            return chunks                 # nothing held, or waiting for the paste terminator
        if self.escape_disambiguation and _bounded_incomplete_escape(buffer):
            return chunks
        if self._lone_escape_recently_flushed and buffer.startswith("[<"):
            self._buffer = ""
            self._retain_timed_out_mouse_prefix(_ESC + buffer)
            self._lone_escape_recently_flushed = False
            return chunks
        if _incomplete_sgr_mouse(buffer):
            self._buffer = ""
            self._retain_timed_out_mouse_prefix(buffer)
            return chunks
        family = _control_string_family(buffer)
        if family is not None and _control_string_terminator(buffer, family) is None:
            # Host control strings take precedence over legacy Alt forms like Alt+], so a
            # later tail of the string cannot leak in as typing.
            self._discard_until, self._discarded_tail_bytes = family, 0
            self._buffer = ""
            return chunks
        if buffer == _ESC:
            self._lone_escape_recently_flushed = True
            self._buffer = ""
            chunks.append(_ESC)
            return chunks
        if parse_key(buffer) is not None:
            self._buffer = ""
            chunks.append(buffer)
            return chunks
        self._lone_escape_recently_flushed = False
        self._buffer = ""                 # an incomplete sequence nobody finished
        return chunks

    @staticmethod
    def _events(chunks):
        events = []
        for chunk in chunks:
            event = chunk if isinstance(chunk, Paste) else parse_sequence(chunk)
            if event is not None:
                events.append(event)
        return events


# ── Keyboard enhancement probe (terminal_setup.rs query_host_escape_disambiguation) ─────

def _host_control_string_end(buffer, offset):
    """host_control_string_end: None if no control string starts at ``offset``; -1 while it
    is unterminated; else its end."""
    if buffer[offset:offset + 1] != b"\x1b":
        return None
    if buffer[offset:offset + 2] == b"\x1b]":
        allow_bel = True
    elif buffer[offset + 1:offset + 2] in (b"P", b"_", b"^", b"X"):
        allow_bel = False
    else:
        return None
    for index in range(offset + 2, len(buffer)):
        if allow_bel and buffer[index] == 0x07:
            return index + 1
        if buffer[index:index + 2] == b"\x1b\\":
            return index + 2
    return -1


def consume_keyboard_probe_responses(buffer, state):
    """consume_host_keyboard_probe_responses: remove the ``CSI ? flags u`` and primary-DA
    replies from ``buffer`` (a bytearray of input read while probing), leaving every other
    byte for the framer. ``state`` collects ``flags`` and ``primary_device_attributes``."""
    offset = 0
    while offset < len(buffer):
        if buffer[offset:].startswith(b"\x1b[200~"):
            end = buffer.find(b"\x1b[201~", offset + 6)
            if end < 0:
                break
            offset = end + 6
            continue
        end = _host_control_string_end(buffer, offset)
        if end is not None:
            if end < 0:
                break
            offset = end
            continue
        if not buffer[offset:].startswith(b"\x1b[?"):
            offset += 1
            continue
        start, end = offset, offset + 3
        while end < len(buffer) and (48 <= buffer[end] <= 57 or buffer[end] == 59):
            end += 1
        if end == len(buffer):
            break
        body = bytes(buffer[start + 3:end])
        recognized = False
        if buffer[end] == ord("u") and body and body.isdigit():
            if not state.get("primary_device_attributes"):
                state["flags"] = int(body)
            recognized = True
        elif buffer[end] == ord("c") and body:
            state["primary_device_attributes"] = True
            recognized = True
        if recognized:
            del buffer[start:end + 1]
        else:
            offset += 1


def escape_disambiguation_confirmed(state):
    """host_escape_disambiguation_confirmed: the host answered DA and reported flag 1."""
    return bool(state.get("primary_device_attributes")) and bool((state.get("flags") or 0) & 1)
