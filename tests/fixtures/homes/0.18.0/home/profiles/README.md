# MISAKA profiles

One directory per role: personality, skills, sub-agent types and MCP servers live here, never
in the source tree. A role directory overlays the home above it -- what a role does not
define, it shares with every other role.

    last_order/        Last Order, the coordinator
      SOUL.md          her voice -- OPTIONAL; shared duties and role charter are kept
      settings.json    what she holds of her own: "defaultProvider"/"defaultModel" (the model
                       she starts on; /model Ctrl+S writes it), "mcpServers", "web"
      skills/          skills only she sees
      subagents/       sub-agent types only she sees
    sisters/<id>/      one per Sister, same layout (`misaka create <id>` builds it)

In the home, shared by every role:

    ../MISAKA.md       identity every role loads before its own SOUL.md
    ../settings.json   every other setting, and the fallback model
    ../skills/         skills every role sees
    ../subagents/      sub-agent types every role sees

An MCP server entry has the shape Hermes uses:

    "mcpServers": {"camofox": {"command": "npx", "args": ["-y", "camofox-mcp"]}}

Skills resolve project -> role -> shared -> external, first match winning. The project
layer is a `skills/` folder in whatever directory MISAKA runs in.

Providers and credentials are shared by every role too: `/login` writes
`../credentials/auth.json`, `/model` writes `../settings.json`, and `../models.json` is where you
declare a provider the built-in catalog does not carry (a local proxy, a private gateway).
