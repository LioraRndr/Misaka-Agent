"""A multi-byte character split across two body chunks decodes as one character.

Upstream reads the SSE body through ``TextDecoder.decode(value, {stream: true})`` and flushes
it at the end; decoding each chunk on its own raised ``UnicodeDecodeError`` as soon as a CJK
character straddled a chunk boundary.
"""
from types import SimpleNamespace

from misaka.ai.providers.anthropic import _iter_response_lines

LINE = "data: 数据と資料\n".encode()


async def _collect(source):
    return [line async for line in _iter_response_lines(source)]


def _split_inside_a_character():
    cut = LINE.index("数".encode()) + 1          # one byte into a three-byte character
    return [LINE[:cut], LINE[cut:]]


async def test_async_body_keeps_a_character_split_across_chunks():
    async def body():
        for chunk in _split_inside_a_character():
            yield chunk

    assert await _collect(SimpleNamespace(body=body())) == ["data: 数据と資料"]


async def test_sync_body_keeps_a_character_split_across_chunks():
    assert await _collect(SimpleNamespace(body=_split_inside_a_character())) == ["data: 数据と資料"]
