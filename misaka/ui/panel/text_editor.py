"""One-line text input with a cursor: port of herdr ``src/client/shell/text_editor.rs``.

Every single-line field of the panel (rename, the navigator's search, copy mode's search
prompt) edits through this. The cursor moves by grapheme cluster (``regex``'s ``\\X``
stands in for unicode-segmentation), a cut goes to a per-field kill buffer (ctrl+y puts it
back; the system clipboard is not touched), and inserted text is normalised: CR, CRLF, LF
and TAB each become one space, other control characters are dropped. Offsets are string
indices where herdr's are byte offsets; both only ever sit on grapheme boundaries.
"""
import regex

from misaka.ui.panel import pane_input as pin
from misaka.ui.panel.host_input import ALT, CTRL, LOCK_MASK, SHIFT, Key, is_control
from misaka.ui.panel.screen import char_width

_GRAPHEME = regex.compile(r"\X")


def _starts(text):
    return [match.start() for match in _GRAPHEME.finditer(text)]


def graphemes(text):
    return _GRAPHEME.findall(text)


def grapheme_width(grapheme):
    """One cluster's cells (herdr: unicode-width). Measured with the frame buffer's own
    ``char_width`` so the caret lands where screen.py lays the text out."""
    return sum(char_width(ch) for ch in grapheme)


def _text_char(key):
    """input/keybind_help.rs keybind_help_text_char: the character a key types with no
    modifier but Shift -- the kitty shifted alternate when the host reported one. Without
    one, Shift is applied the way the panel's ``key_text`` applies it (misaka's kitty parse
    keeps ``a`` + Shift, where herdr's key would already read ``A``)."""
    mods = key.mods & ~LOCK_MASK
    if mods & ~SHIFT or not key.is_char:
        return None
    if key.shifted is not None:
        try:
            return chr(key.shifted)
        except (ValueError, OverflowError):
            return None
    if mods == SHIFT:
        return pin.encode_key(Key(key.code, key.mods, key.kind), pin.DEFAULT_STATE).decode() or None
    return key.code


def _class(grapheme):
    ch = grapheme[:1] or " "
    if ch.isspace():
        return 0
    if ch.isalnum() or ch == "_":
        return 1
    return 2


class TextEditor:
    def __init__(self, text="", replace_on_type=False):
        self.text, self.cursor, self.replace_on_type, self.killed = "", 0, False, ""
        self.insert(text)
        self.replace_on_type = replace_on_type

    def __str__(self):
        return self.text

    def __len__(self):
        return len(self.text)

    def clear(self):
        self.text, self.cursor, self.replace_on_type = "", 0, False

    def trim_and_accept(self):
        leading = len(self.text) - len(self.text.lstrip())
        self.text = self.text.strip()
        self.cursor = min(max(0, self.cursor - leading), len(self.text))
        self.replace_on_type = False
        self._repair_cursor()

    def _repair_cursor(self):
        """An edit can join clusters across it: snap forward to the next boundary."""
        self.cursor = next((start for start in _starts(self.text) if start >= self.cursor), len(self.text))

    def insert(self, text):
        """Insert at the cursor (replacing everything when replace_on_type); True when the
        content changed."""
        out, index = [], 0
        while index < len(text):
            ch = text[index]
            if ch == "\r":
                if text[index + 1:index + 2] == "\n":
                    index += 1
                out.append(" ")
            elif ch in "\n\t":
                out.append(" ")
            elif not is_control(ch):
                out.append(ch)
            index += 1
        normalized = "".join(out)
        if not normalized:
            return False
        changed = not self.replace_on_type or self.text != normalized
        if self.replace_on_type:
            self.clear()
        self.text = self.text[:self.cursor] + normalized + self.text[self.cursor:]
        self.cursor += len(normalized)
        self._repair_cursor()
        return changed

    def _previous(self):
        starts = [start for start in _starts(self.text[:self.cursor])]
        return starts[-1] if starts else 0

    def _next(self):
        match = _GRAPHEME.match(self.text, self.cursor)
        return self.cursor + (len(match.group()) if match else 0)

    def _word_boundary(self, backward):
        boundary, run = self.cursor, 0
        if backward:
            for match in reversed(list(_GRAPHEME.finditer(self.text[:self.cursor]))):
                current = _class(match.group())
                if run and current != run:
                    break
                run, boundary = current, match.start()
        else:
            for match in _GRAPHEME.finditer(self.text, self.cursor):
                current = _class(match.group())
                if run and current != run:
                    break
                run, boundary = current, match.end()
        return boundary

    def _remove(self, start, end, kill):
        self.replace_on_type = False
        if start == end:
            return
        if kill:
            self.killed = self.text[start:end]
        self.text = self.text[:start] + self.text[end:]
        self.cursor = start
        self._repair_cursor()

    def handle_key(self, key):
        """Apply one key (text_editor.rs handle_key). Returns None when the key is not an
        editing key, else whether the content changed."""
        if key.kind == "release" or key.code in ("enter", "esc"):
            return None
        before = len(self.text)
        changed = False
        mods = key.mods & ~LOCK_MASK
        if key.text:                      # text the host reports is authoritative (AltGr, IME)
            changed = self.insert(key.text)
        else:
            ctrl, alt, plain = mods == CTRL, mods == ALT, mods == 0
            code = key.code
            movement = None
            if (code == "left" and plain) or (code == "b" and ctrl):
                movement = self._previous()
            elif (code == "right" and plain) or (code == "f" and ctrl):
                movement = self._next()
            elif (code == "home" and plain) or (code == "a" and ctrl):
                movement = 0
            elif (code == "end" and plain) or (code == "e" and ctrl):
                movement = len(self.text)
            elif code == "b" and alt:
                movement = self._word_boundary(True)
            elif code == "f" and alt:
                movement = self._word_boundary(False)
            if movement is not None:
                self.cursor, self.replace_on_type = movement, False
            elif (code == "backspace" and plain) or (code == "h" and ctrl):
                if self.replace_on_type:
                    self.clear()
                else:
                    self._remove(self._previous(), self.cursor, False)
            elif (code == "delete" and plain) or (code == "d" and ctrl):
                self._remove(self.cursor, self._next(), False)
            elif code == "u" and ctrl:
                self._remove(0, self.cursor, True)
            elif code == "k" and ctrl:
                self._remove(self.cursor, len(self.text), True)
            elif (code == "w" and ctrl) or (code == "backspace" and (ctrl or alt)):
                self._remove(self._word_boundary(True), self.cursor, True)
            elif code == "d" and alt:
                self._remove(self.cursor, self._word_boundary(False), True)
            elif code == "y" and ctrl:
                changed = self.insert(self.killed)
            elif key.is_char and not mods & ~SHIFT:
                typed = _text_char(key)
                if typed:
                    changed = self.insert(typed)
            else:
                return None
        return changed or len(self.text) != before

    def viewport(self, width):
        """The part of the text a ``width``-cell field shows, keeping the cursor inside it,
        and the cursor's cell offset in that part."""
        if width <= 0:
            return "", 0
        start, cells = self.cursor, 0
        for match in reversed(list(_GRAPHEME.finditer(self.text[:self.cursor]))):
            nxt = cells + grapheme_width(match.group())
            if nxt >= width:
                break
            start, cells = match.start(), nxt
        end, used = self.cursor, cells
        for match in _GRAPHEME.finditer(self.text, self.cursor):
            used += grapheme_width(match.group())
            if used > width:
                break
            end = match.end()
        return self.text[start:end], cells
