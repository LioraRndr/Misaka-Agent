"""Markdown headings read the way CommonMark reads them: a ``#`` in fenced code is code, ``#tag`` is prose."""
import re

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?=[ \t\r]|$)")
_FENCE = re.compile(r"^ {0,3}(```|~~~)")
_CLOSING_HASHES = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")


def atx_headings(lines):
    """``(line index, level, title)`` of every ATX heading among ``lines`` outside a fenced block.

    Up to three leading spaces still make a heading; the title drops the optional closing ``#`` run
    and may be empty (a bare ``##`` is a heading with no words).
    """
    fence, out = None, []
    for index, line in enumerate(lines):
        opener = _FENCE.match(line)
        if fence is not None:
            if opener and line.strip().startswith(fence):
                fence = None
        elif opener:
            fence = opener.group(1)
        elif found := _HEADING.match(line):
            rest = line[found.end():].strip()
            out.append((index, len(found.group(1)), _CLOSING_HASHES.sub("", rest).strip()))
    return out
