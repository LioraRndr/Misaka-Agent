"""Text selection in a pane, in screen-buffer coordinates.

Port of herdr ``src/selection.rs``: rows are absolute (0 = the oldest history line, the
live screen follows history), so a selection stays on its text while the pane scrolls or
the program prints more. Lifecycle: a press anchors (nothing shown), a drag activates the
highlight, a release finishes it; a plain click never becomes a selection.
"""
from dataclasses import dataclass


def viewport_top_row(metrics):
    """Absolute row of the first visible line for the pane's scroll metrics."""
    if not metrics:
        return 0
    return max(0, metrics["max_offset_from_bottom"] - metrics["offset_from_bottom"])


def absolute_row(viewport_row, metrics):
    return viewport_top_row(metrics) + viewport_row


def viewport_row(absolute, metrics):
    return absolute - viewport_top_row(metrics)


@dataclass(slots=True)
class Selection:
    pane: str
    anchor: tuple                     # (absolute row, col)
    cursor: tuple                     # (absolute row, col)
    phase: str = "anchored"           # anchored | dragging | done

    @classmethod
    def at(cls, pane, viewport_row_, col, metrics):
        """A potential selection: the press position; nothing is highlighted yet."""
        point = (absolute_row(viewport_row_, metrics), col)
        return cls(pane, point, point)

    @classmethod
    def range(cls, pane, viewport_row_, start_col, end_col, metrics):
        """An active selection over one viewport row (double-click word selection)."""
        row = absolute_row(viewport_row_, metrics)
        return cls(pane, (row, start_col), (row, end_col), "dragging")

    @classmethod
    def lines(cls, pane, anchor_row, cursor_row, end_col):
        """Whole absolute rows from the anchor row to the cursor row (copy mode V)."""
        if anchor_row <= cursor_row:
            return cls(pane, (anchor_row, 0), (cursor_row, end_col), "dragging")
        return cls(pane, (anchor_row, end_col), (cursor_row, 0), "dragging")

    def drag(self, screen_col, screen_row, inner, metrics):
        """Extend to a screen position, clamped to the pane's inner rect; the highlight
        appears once the cursor leaves the anchor cell."""
        col = min(max(screen_col, inner.x), inner.x + max(0, inner.width - 1)) - inner.x
        row = min(max(screen_row, inner.y), inner.y + max(0, inner.height - 1)) - inner.y
        self.cursor = (absolute_row(row, metrics), col)
        if self.cursor != self.anchor:
            self.phase = "dragging"

    def force_dragging(self):
        """The pointer left the anchor cell but clamping put it back: still a drag."""
        if self.phase == "anchored":
            self.phase = "dragging"

    def finish(self):
        """Release: True when this was a real selection (the user dragged)."""
        if self.phase == "dragging":
            self.phase = "done"
            return True
        return False

    @property
    def visible(self):
        return self.phase in ("dragging", "done")

    @property
    def finalized(self):
        return self.phase == "done"

    @property
    def in_progress(self):
        return self.phase in ("anchored", "dragging")

    @property
    def just_click(self):
        return self.phase == "anchored"

    def ordered(self):
        """(start, end) in reading order."""
        return (self.anchor, self.cursor) if self.anchor <= self.cursor else (self.cursor, self.anchor)

    def anchor_screen_pos(self, inner, metrics):
        """The anchor as a clamped screen (row, col), to compare with the pointer."""
        row = viewport_row(self.anchor[0], metrics) + inner.y
        col = self.anchor[1] + inner.x
        return (min(max(row, inner.y), inner.y + max(0, inner.height - 1)),
                min(max(col, inner.x), inner.x + max(0, inner.width - 1)))

    def span(self, viewport_row_, width, metrics):
        """Column range [c0, c1) the selection covers on a viewport row, or None."""
        if not self.visible:
            return None
        row = absolute_row(viewport_row_, metrics)
        (start_row, start_col), (end_row, end_col) = self.ordered()
        if row < start_row or row > end_row:
            return None
        first = start_col if row == start_row else 0
        last = end_col + 1 if row == end_row else width
        return first, min(last, width)


# ── Token under a double-click (herdr app/actions.rs word_bounds_at_column) ─────────────
#
# A row's text is mapped to display cells first, so wide characters and zero-width marks
# use terminal columns; then the spans people expect to copy whole are preferred (a URL,
# a quoted path), and only then a separator-delimited token, trimmed of wrapping
# punctuation. The result is inclusive terminal columns, or None.

_WORD_SEPARATORS = frozenset("|()[]{},;!（）：、。，")
_LEADING_TOKEN_WRAPPERS = frozenset("([{<\"'`")
_TRAILING_TOKEN_WRAPPERS = frozenset(")]}>\"'`.,;:!?")
_TRAILING_URL_PUNCTUATION = frozenset("\"'`.,;:!?")
_URL_CLOSERS = {")": "(", "]": "[", "}": "{"}


def _is_word_separator(ch):
    return ch.isspace() or ch in _WORD_SEPARATORS


def _text_cells(row):
    """text_cells: ``[(ch, start_col, end_col)]``; a zero-width mark shares the previous cell."""
    from misaka.ui.panel import ghostty

    cells, next_col = [], 0
    for ch in row:
        width = ghostty.codepoint_width(ord(ch))
        start_col = max(0, next_col - 1) if width == 0 else next_col
        if width > 0:
            next_col += width
        cells.append((ch, start_col, max(0, next_col - 1)))
    return cells


def _starts_with(cells, start, prefix):
    return all(start + i < len(cells) and cells[start + i][0] == ch for i, ch in enumerate(prefix))


def _trailing_url_closer_is_balanced(cells, start, end, opener, closer):
    balance = 0
    for ch, _s, _e in cells[start:end]:
        if ch == opener:
            balance += 1
        elif ch == closer:
            balance -= 1
    return balance > 0


def _trim_url_edges(cells, start, end):
    while start <= end:
        ch = cells[end][0]
        if ch in _TRAILING_URL_PUNCTUATION:
            trim = True
        elif ch in _URL_CLOSERS:
            trim = not _trailing_url_closer_is_balanced(cells, start, end, _URL_CLOSERS[ch], ch)
        else:
            trim = False
        if not trim:
            break
        if end == 0:
            return None
        end -= 1
    return (start, end) if start <= end else None


def _url_span(cells, clicked):
    start = 0
    while start < len(cells):
        if _starts_with(cells, start, "http://") or _starts_with(cells, start, "https://"):
            end = start
            while end + 1 < len(cells) and not cells[end + 1][0].isspace():
                end += 1
            if start <= clicked <= end:
                span = _trim_url_edges(cells, start, end)
                return span if span is not None and span[0] <= clicked <= span[1] else None
            start = end + 1
        else:
            start += 1
    return None


def _is_escaped(cells, index):
    slashes = 0
    while index > 0 and cells[index - 1][0] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _quoted_path_span(cells, clicked):
    if cells[clicked][0] in "\"'`":
        return None
    for quote in "\"'`":
        opened = None
        for index, (ch, _s, _e) in enumerate(cells):
            if ch != quote or _is_escaped(cells, index):
                continue
            if opened is None:
                opened = index
                continue
            if opened < clicked < index and any(c == "/" for c, _s2, _e2 in cells[opened + 1:index]):
                return opened + 1, index - 1
            opened = None
    return None


def _trim_token_edges(cells, start, end):
    while start <= end and cells[start][0] in _LEADING_TOKEN_WRAPPERS:
        start += 1
    if start < end and cells[end][0] == "$" and cells[end - 1][0] in _TRAILING_TOKEN_WRAPPERS:
        end -= 1
    while start <= end and cells[end][0] in _TRAILING_TOKEN_WRAPPERS:
        if end == 0:
            return None
        end -= 1
    return (start, end) if start <= end else None


def _token_span(cells, clicked):
    if _is_word_separator(cells[clicked][0]):
        return None
    start = end = clicked
    while start > 0 and not _is_word_separator(cells[start - 1][0]):
        start -= 1
    while end + 1 < len(cells) and not _is_word_separator(cells[end + 1][0]):
        end += 1
    span = _trim_token_edges(cells, start, end)
    return span if span is not None and span[0] <= clicked <= span[1] else None


def word_bounds_at_column(row, col):
    """Inclusive terminal columns of the token under ``col`` in ``row`` (a row's text), or
    None: a URL first, then a quoted path containing "/", then a separator-delimited token."""
    cells = _text_cells(row)
    clicked = next((index for index, (_ch, start, end) in enumerate(cells) if start <= col <= end), None)
    if clicked is None:
        return None
    span = _url_span(cells, clicked) or _quoted_path_span(cells, clicked) or _token_span(cells, clicked)
    if span is None:
        return None
    return cells[span[0]][1], cells[span[1]][2]
