"""The vision extension: a model without vision is read the images a request carries.

2026-10-07: Pi replaces an image with "(image omitted: model does not support images)" for a
model that cannot see, and every image a text-only Sister was handed -- a scanned page, a map, a
screenshot, a pasted chart -- reached her as that sentence. The browser alone could have a
screenshot read by browser.vision_model. Now one vision model, vision.model, reads every image
to such a model, on the request-time context event, without touching Pi's kernel."""
from types import SimpleNamespace as NS

import pytest

from misaka.ai.types import ImageContent, TextContent, ToolResultMessage, UserMessage
from misaka.core.web import vision
from misaka.extensions import vision as extension

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jE1sAAAAASUVORK5CYII="
OTHER = PNG.replace("AAAA", "AAAB", 1)
TEXT_ONLY = NS(input=["text"], id="deepseek-flash")


@pytest.fixture
def reader(monkeypatch):
    """vision.model set, and a vision model that answers with what it was asked about."""
    asked = []

    async def describe(image, question, ctx, selected, **kw):
        asked.append((image["data"], question, selected, kw["setting"]))
        return f"A map of the march, image {len(asked)}."

    monkeypatch.setattr(vision, "describe", describe)
    monkeypatch.setattr(vision, "selected_model", lambda: ("openai/gpt-4o", "vision.model"))
    monkeypatch.setattr(extension, "_kept", {})
    return asked


def _messages(*images, note=""):
    return [UserMessage(content=[TextContent(text="look at this"), ImageContent(data=PNG, mimeType="image/png")],
                        timestamp=1),
            ToolResultMessage(toolCallId="c1", toolName="doc_page_image", isError=False,
                              content=[TextContent(text="[d] page 12 of 40, figure 1" + note),
                                       *[ImageContent(data=data, mimeType="image/png") for data in images]],
                              timestamp=2)]


async def test_a_model_that_can_see_is_sent_the_images_untouched(reader):
    assert await extension.read_images({"messages": _messages(PNG)}, NS(model=NS(input=["text", "image"]))) is None
    assert reader == []


async def test_without_a_vision_model_pi_placeholder_stands(monkeypatch):
    monkeypatch.setattr(vision, "selected_model", lambda: (None, None))
    assert await extension.read_images({"messages": _messages(PNG)}, NS(model=TEXT_ONLY)) is None


async def test_every_image_is_read_to_a_model_that_cannot_see(reader):
    result = await extension.read_images({"messages": _messages(OTHER)}, NS(model=TEXT_ONLY))
    user, tool = result["messages"]
    assert [block.type for block in user.content] == ["text", "text"]
    assert "read to this model by openai/gpt-4o (vision.model) because deepseek-flash cannot see" in user.content[1].text
    assert "A map of the march" in tool.content[1].text
    asked = {data: question for data, question, *_ in reader}            # read side by side, in no set order
    assert "came back from the tool `doc_page_image`, which said: [d] page 12 of 40" in asked[OTHER]
    assert "The user attached the image." in asked[PNG]


async def test_an_image_is_read_once_and_kept(reader, monkeypatch):
    await extension.read_images({"messages": _messages(PNG)}, NS(model=TEXT_ONLY))
    assert len(reader) == 1, "the same image twice in one request is read once"
    monkeypatch.setattr(extension, "_kept", {})                   # a new process: the disk copy answers
    await extension.read_images({"messages": _messages(PNG)}, NS(model=TEXT_ONLY))
    assert len(reader) == 1


async def test_pi_read_tool_note_that_the_image_is_omitted_is_taken_out(reader):
    note = "\n" + extension._omitted_note()
    result = await extension.read_images({"messages": _messages(OTHER, note=note)}, NS(model=TEXT_ONLY))
    assert "will be omitted" not in result["messages"][1].content[0].text


async def test_an_image_the_vision_model_cannot_read_does_not_stop_the_turn(monkeypatch):
    async def describe(*a, **kw):
        raise ValueError("vision.model has no authentication")

    monkeypatch.setattr(vision, "describe", describe)
    monkeypatch.setattr(vision, "selected_model", lambda: ("openai/gpt-4o", "vision.model"))
    monkeypatch.setattr(extension, "_kept", {})
    result = await extension.read_images({"messages": _messages()}, NS(model=TEXT_ONLY))
    assert "could not read" in result["messages"][0].content[1].text and "no authentication" in result["messages"][0].content[1].text


def test_the_extension_is_bundled_for_every_role():
    registered = {}
    extension.activate(None)(NS(on=lambda event, handler: registered.setdefault(event, handler)))
    assert registered == {"context": extension.read_images}


async def test_the_session_keeps_the_pixels(reader):
    """The runner hands extensions a copy; a later request to a model that sees gets the image."""
    from copy import deepcopy
    stored = _messages(OTHER)
    await extension.read_images({"messages": deepcopy(stored)}, NS(model=TEXT_ONLY))
    assert stored[0].content[1].type == "image"


def test_every_session_of_every_role_gets_it(tmp_path):
    from misaka.core.wiring import KINDS
    from misaka.extensions import discover
    for kind in sorted(KINDS):
        names = [entry["name"] if isinstance(entry, dict) else getattr(entry, "name", None)
                 for entry in discover(NS(profile_dir=str(tmp_path / "sister"), kind=kind, workspace=str(tmp_path)))]
        assert "vision" in names, kind
