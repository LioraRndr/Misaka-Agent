"""Codex and Copilot OAuth requests give up on a token endpoint that never answers.

They were built with ``httpx.AsyncClient(timeout=None)``, so a stalled endpoint held a
credential refresh -- and every request queued behind its lock -- forever.
"""
import asyncio

import httpx
import pytest

from misaka.ai.utils.oauth import github_copilot, openai_codex


@pytest.fixture
async def silent_endpoint(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    held = []

    async def accept_and_say_nothing(reader, writer):
        held.append(writer)

    server = await asyncio.start_server(accept_and_say_nothing, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        for writer in held:
            writer.close()
        server.close()


async def test_codex_refresh_fails_instead_of_hanging(silent_endpoint, monkeypatch):
    monkeypatch.setattr(openai_codex, "TOKEN_URL", f"{silent_endpoint}/oauth/token")
    monkeypatch.setattr(openai_codex, "REQUEST_TIMEOUT_MS", 200)
    result = await asyncio.wait_for(openai_codex._refresh_access_token("refresh"), 5)
    assert result["type"] == "failed"


async def test_copilot_request_fails_instead_of_hanging(silent_endpoint, monkeypatch):
    monkeypatch.setattr(github_copilot, "REQUEST_TIMEOUT_MS", 200)
    with pytest.raises(httpx.TimeoutException):
        await asyncio.wait_for(github_copilot._fetch_json(f"{silent_endpoint}/copilot_internal/v2/token"), 5)


async def test_copilot_model_policy_reads_as_not_enabled_instead_of_hanging(silent_endpoint, monkeypatch):
    monkeypatch.setattr(github_copilot, "_REQUEST_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(github_copilot, "get_github_copilot_base_url", lambda *_: silent_endpoint)
    assert await asyncio.wait_for(github_copilot._enable_github_copilot_model("token", "model"), 5) is False
