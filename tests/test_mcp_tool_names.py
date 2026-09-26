"""MCP tool names are valid for every provider, and the server behind one stays recoverable.

A server called ``my-server.v2`` used to register ``mcp__my-server.v2__...``; OpenAI-style
function-name validation rejects the dot and 400s the whole request, and a long plugin
server key pushes the name past 64 characters.
"""
import re

from misaka.core import mcp

VALID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def test_names_are_sanitized_and_clamped():
    assert mcp.tool_name("my-server.v2", "get.page") == "mcp__my-server_v2__get_page"
    long_name = mcp.tool_name("plugin-" + "x" * 40, "a_really_long_tool_name_" + "y" * 30)
    assert VALID.match(long_name) and len(long_name) == 64
    assert long_name == mcp.tool_name("plugin-" + "x" * 40, "a_really_long_tool_name_" + "y" * 30)


def test_a_name_that_was_already_valid_is_unchanged():
    # Agent definitions written the Claude Code way name these tools exactly like this.
    assert mcp.tool_name("brave-search", "brave_web_search") == "mcp__brave-search__brave_web_search"
    assert mcp.tool_name("sequential-thinking", "sequentialthinking") == "mcp__sequential-thinking__sequentialthinking"


def test_the_configured_server_is_recovered_from_a_registered_name():
    assert mcp.server_of(mcp.tool_name("my-server.v2", "search")) == "my-server.v2"
    clamped = mcp.tool_name("plugin-" + "z" * 60, "tool")
    assert mcp.server_of(clamped) == "plugin-" + "z" * 60
    assert mcp.server_of("read") is None


def test_a_name_from_another_process_falls_back_to_its_segment():
    assert mcp.server_of("mcp__other_server__tool") == "other_server"


def test_required_server_patterns_match_either_spelling():
    assert mcp.server_matches("my-server", "my-server.v2")
    assert mcp.server_matches("my-server", "my-server_v2")
    assert mcp.server_matches("MY-SERVER", "my-server.v2")
    assert not mcp.server_matches("other", "my-server.v2")


def test_required_server_matching_is_what_it_was_plus_the_sanitized_spelling():
    # Everything the plain comparison matched still matches, and nothing it rejected newly
    # matches except a sanitized spelling of the same name.
    assert mcp.server_matches("github", "github-server")
    assert not mcp.server_matches("gitlab", "github-server")
    assert mcp.server_matches("my-server_v2", "my-server.v2")      # a fork's snapshot name
    assert not mcp.server_matches("搜索", "翻译")
    assert not mcp.server_matches("搜索", "my__server")
    assert mcp.server_matches("搜索", "搜索服务")
