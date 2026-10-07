"""A stdio MCP server does not inherit MISAKA's API keys (issue #10, the key-channel report).

MISAKA loads the home's .env -- search keys, the OpenAlex key -- into its environment, and every
MCP server started with all of it. A server now gets Hermes' safe names, the proxy and certificate
variables, and its own configured env, where ${VAR} takes a value from the environment."""
from misaka.core import mcp

ENVIRON = {"PATH": "/usr/bin", "HOME": "/home/u", "LANG": "C.UTF-8", "LC_CTYPE": "UTF-8", "XDG_CACHE_HOME": "/c",
           "HTTPS_PROXY": "http://127.0.0.1:7890", "no_proxy": "localhost", "SSL_CERT_FILE": "/ca.pem",
           "MISAKA_HOME": "/m", "OPENAI_API_KEY": "sk-secret", "EXA_API_KEY": "exa-secret",
           "GITHUB_TOKEN": "ghp-secret", "MISAKA_USAGE_DB": "/m/board.db", "Path": "C:\\Windows", "SystemRoot": "C:\\Windows"}


def test_a_server_gets_the_safe_names_and_no_key():
    env = mcp.inherited_env(ENVIRON)
    assert {"PATH", "HOME", "LANG", "LC_CTYPE", "XDG_CACHE_HOME", "HTTPS_PROXY", "no_proxy", "SSL_CERT_FILE",
            "MISAKA_HOME", "SystemRoot"} <= set(env)
    assert not {"OPENAI_API_KEY", "EXA_API_KEY", "GITHUB_TOKEN", "MISAKA_USAGE_DB"} & set(env)


def test_a_key_a_server_needs_is_named_in_its_env():
    env = mcp.configured_env({"GITHUB_TOKEN": "${GITHUB_TOKEN}", "MODE": "x-${MISSING}", "N": 3}, ENVIRON)
    assert env == {"GITHUB_TOKEN": "ghp-secret", "MODE": "x-${MISSING}", "N": "3"}
