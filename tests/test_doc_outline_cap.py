"""``doc_outline`` returns a document's whole heading tree, which has no natural bound. It now
gets the same kind of cap as the workspace index and find/grep: a huge tree is cut, the cut says
how to keep navigating (sections by node or pages, doc_find beyond the cut); an ordinary
outline passes through untouched with its usual reading hint."""
from types import SimpleNamespace as NS

import pytest

from misaka.core.documents.wiring import documents
from misaka.core.wiring import ToolCollector


@pytest.fixture
def outline(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "_owning_root", lambda doc_id, ctx: str(tmp_path))
    monkeypatch.setattr(documents, "_row", lambda doc_id, root: {})
    monkeypatch.setattr(documents, "_ocr_note", lambda row: "")
    collector = ToolCollector()
    documents.register(collector)
    tool = next(t for t in collector.tools if t.name == "doc_outline")

    async def call():
        result = await tool.execute("call", {"doc_id": "d"}, None, None, NS(cwd=str(tmp_path), model=None))
        return result["content"][0]["text"]

    return call


async def test_a_huge_outline_is_cut_with_navigation_advice(outline, monkeypatch):
    monkeypatch.setattr(documents.corpus, "tree_outline",
                        lambda doc_id, workspace: "\n".join(f"{i:05d}  Heading {i} " + "x" * 60 for i in range(20000)))
    text = await outline()
    assert len(text.encode("utf-8")) < documents.OUTLINE_MAX_BYTES + 2048
    assert "00000  Heading 0 " in text and "19999  Heading 19999 " not in text
    assert "limit reached" in text and "doc_find" in text and "pages=<range>" in text


async def test_an_ordinary_outline_passes_through(outline, monkeypatch):
    monkeypatch.setattr(documents.corpus, "tree_outline", lambda doc_id, workspace: "0000  Book I\n0001  Chapter 1\n")
    text = await outline()
    assert "0000  Book I\n0001  Chapter 1" in text
    assert "Use doc_read(doc_id, node=<node-id>) to read a section." in text and "limit reached" not in text
