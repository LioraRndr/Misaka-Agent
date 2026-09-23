"""`doc_page_image` renders at most 2x and hands back a JPEG for a text page.

2026-09-23 (card t_9f10b6): scale-3 renders of the same Marion pages, 1.7 MB of PNG each, 26
times over, sat in the context (~25k Codex tokens apiece) and in every LCM checkpoint of a
557 MB transcript. Scale is clamped and the byte cap makes the resize choose JPEG."""
import base64
import io
from types import SimpleNamespace as NS

import pytest
from PIL import Image, ImageDraw, ImageFont

from misaka.core.documents.wiring import documents
from misaka.core.wiring import ToolCollector


def _png(width, height, scanned):
    """A blank page, or a scanned one: noisy paper with lines of type, which PNG cannot compress."""
    if not scanned:
        image = Image.new("RGB", (width, height), "white")
    else:
        paper = Image.effect_noise((width, height), 12).point(lambda v: 225 + min(30, max(0, (v - 128) // 2)))
        image = paper.convert("RGB")
        draw, font = ImageDraw.Draw(image), ImageFont.load_default()
        for y in range(20, height - 20, 22):
            draw.text((30, y), "On the r. of Halstead is Dyne Hall, Henry Sperling, Esq. " * 2, fill=(20, 20, 20), font=font)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


@pytest.mark.parametrize("scale, scanned, mime", [(3.0, True, "image/jpeg"), (1.5, False, "image/png")])
async def test_scale_is_clamped_and_text_pages_become_jpeg(tmp_path, monkeypatch, scale, scanned, mime):
    seen = {}

    def render(pdf_path, page, used_scale):
        seen["scale"] = used_scale
        return _png(1400, 1800, scanned), 10

    monkeypatch.setattr(documents, "_render_page", render)
    monkeypatch.setattr(documents, "_source", lambda doc_id, ctx: (str(tmp_path), str(tmp_path / "book.pdf"), "A Book"))
    collector = ToolCollector()
    documents.register(collector)
    tool = next(t for t in collector.tools if t.name == "doc_page_image")
    result = await tool.execute("call", {"doc_id": "d", "page": 3, "scale": scale}, None, None, NS(cwd=str(tmp_path), model=None))
    assert seen["scale"] == min(scale, documents.PAGE_IMAGE_MAX_SCALE)
    image = next(part for part in result["content"] if getattr(part, "mimeType", None))
    assert image.mimeType == mime
    assert len(base64.b64decode(image.data)) < documents.PAGE_IMAGE_MAX_BYTES
    assert "page 3 of 10" in result["content"][0]["text"]
