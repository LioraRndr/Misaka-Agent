"""Allies: other vendors' agents (Claude Code, Codex, ...) working the board as Sisters do.

A Sister is a misaka agent in the misaka engine. An ally is someone else's agent, driven over the
Agent Client Protocol: it is assigned cards, started, messaged and stopped with the same tools, and
its attempt is claimed, settled and reported by the same board. Only the program running the
attempt differs -- ``card`` (the ACP runner) instead of a Sister's session -- and the card's tools
reach the ally through an MCP server, ``bridge``. ``presets`` says which allies this home enables.
"""
