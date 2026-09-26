"""Native paths/settings; original LCM_* algorithm configuration, without environment mutation."""
from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager

from ..vendor.config import LCMConfig
from . import storage

_AUXILIARY_CONFIG = contextvars.ContextVar("lcm_auxiliary_config", default=None)


def load_auxiliary_config() -> dict:
    """Read native global settings only, never Hermes or an untrusted project file.

    The auxiliary call binds this snapshot through route resolution and dispatch.
    No config file is created, migrated, or written on this read path.
    """
    import json

    from misaka.config import home

    config = _AUXILIARY_CONFIG.get()
    if config is not None:
        return config
    try:
        settings = json.loads(home.path("settings").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    raw = settings.get("auxiliary", {})
    auxiliary = dict(raw) if isinstance(raw, dict) else {}
    return {**settings, "auxiliary": auxiliary}



@contextmanager
def auxiliary_config():
    token = _AUXILIARY_CONFIG.set(load_auxiliary_config())
    try:
        yield
    finally:
        _AUXILIARY_CONFIG.reset(token)


def get_plugin_auxiliary_tasks():
    # The pinned LCM plugin registers no auxiliary-task defaults. MISAKA has no
    # Hermes plugin-discovery registry; do not discover another install's plugins.
    return ()


def _scoped_key_env(name):
    # Native workers already inherit their role's scrubbed environment. Hermes'
    # profile-secret store is not part of this host.
    return (os.environ.get(name) or "").strip() if name else ""


def database_path(ctx=None) -> str:
    """LCM content belongs to the session's project, never a global home DB."""
    return str(storage.directory(storage.project(ctx)) / "lcm.db")


def _session_host_config(ctx) -> dict:
    """The host config this session reads: settings.json, with the session's own compaction
    threshold (``misaka.core.session_overrides``, a research run's choice) as its
    ``lcm.context_threshold`` -- the same channel, so upstream's precedence and its explicit-choice
    rules (no Codex autoraise over it) treat it exactly as the global setting."""
    config = load_auxiliary_config()
    if ctx is None:
        return config
    from misaka.core import session_overrides

    from . import ingest
    threshold = session_overrides.value(ingest.session_id(ctx), "context_threshold")
    if threshold is None:
        return config
    lcm = config.get("lcm") if isinstance(config.get("lcm"), dict) else {}
    return {**config, "lcm": {**lcm, "context_threshold": float(threshold)}}


def load_config(*, database=None, home=None, ctx=None) -> LCMConfig:
    """Keep upstream algorithm settings; the host owns all content paths."""
    from . import settings
    config = settings.apply(LCMConfig.from_env(host_config=_session_host_config(ctx)))
    if "LCM_EMBEDDING_QUERY_TIMEOUT_S" not in os.environ:
        # Upstream's 3 s deadline also bounds lcm_grep's full-text arm (it interrupts the
        # SQLite query through a progress handler), and a research project's lcm.db runs to
        # tens of megabytes, where that arm regularly overran it and was dropped in silence
        # (2026-09-18, B32). The knob is upstream's own; only misaka's default differs.
        config.embedding_query_timeout_s = 30.0
        config.config_sources["embedding_query_timeout_s"] = "misaka.default"
    if "LCM_RESERVE_TOKENS_FLOOR" not in os.environ:
        # Upstream arms its overflow recovery (forced compaction that may cut into the fresh
        # tail, deterministic truncation when the summariser cannot) only when an assembly
        # cap exists, and the cap exists only with `max_assembly_tokens` or a non-zero
        # reserve floor; upstream ships both at 0. Without it an overflowed Sister retried the
        # identical prompt and died (2026-09-23, card t_9f10b6 on a 272k window). pi's own
        # reserve is 16384 tokens; the knob is upstream's, only misaka's default differs.
        config.reserve_tokens_floor = 16_384
        config.config_sources["reserve_tokens_floor"] = "misaka.default"
    config.database_path = str(database) if database is not None else database_path(ctx)
    directory = str(home) if home is not None else os.path.dirname(config.database_path)
    config.large_output_externalization_path = os.path.join(directory, "lcm-large-outputs")
    config.extraction_output_path = os.path.join(directory, "lcm-extractions")
    return config
