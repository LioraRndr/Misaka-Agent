"""Settings for the GUI, done the way ``misaka setup`` and ``misaka web`` do them, minus the terminal.

Each call is one short-lived process (``python -m misaka.ui.gui.settings_worker``): a JSON
request on stdin, one marked JSON line back. A process per call keeps the model registry,
the web scope and the extension discovery these use out of the long-lived GUI server, the
same reason chats run in their own processes. The writes go through the same functions the
wizard calls -- credential store, SettingsManager, role pins, roster, the web config
writer -- so the GUI and the terminal can never disagree about where a setting lives.

``login`` is the one conversational call: it streams events (the browser link, a device
code, a question) as marked lines and reads answers back on stdin until the sign-in ends.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import shlex
import sys
import threading
from types import SimpleNamespace

MARK = "@@misaka-gui@@"
_OUT = sys.stdout


def send(payload: dict) -> None:
    _OUT.write(MARK + json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    _OUT.flush()


# ---- environment and overview ---------------------------------------------------------

TOOLS = (("git", "项目仓库与结果提交", True), ("rg", "文本检索（ripgrep）", True),
         ("fd", "文件查找", True), ("pdftotext", "读取 PDF 文本（poppler）", True),
         ("ocrmypdf", "扫描版 PDF 的文字识别（只有图片型 PDF 才需要）", False))


def _extras_command(extras: list[str]) -> dict:
    from misaka.cli import update
    try:
        install = update.describe()
        command = update.adding_extras(install, extras)
    except Exception:  # noqa: BLE001 - a guess at the install command is not worth failing for
        command, install = None, None
    if command is None:
        from misaka.cli.update import REPO_URL
        return {"command": f"pip install 'misaka[{','.join(extras)}] @ git+{REPO_URL}'", "after_exit": True}
    return {"command": shlex.join(command), "after_exit": getattr(install, "installer", "") in ("uv tool", "pipx")}


def op_overview(_params: dict) -> dict:
    import platform

    from misaka.cli.setup import Wizard, _install_command
    from misaka.config import CFG, VERSION, current_config, profiles
    from misaka.config import env as env_file
    from misaka.config.product import setting
    from misaka.core.documents.pageindex import available as pageindex_available
    from misaka.core.research import runs
    from misaka.core.skills import layers as skill_layers
    from misaka.extensions import coverage
    from misaka.utils.tools_manager import find_tool

    tools = []
    for binary, purpose, required in TOOLS:
        present = find_tool(binary) is not None
        tools.append({"name": binary, "purpose": purpose, "required": required, "present": present,
                      "install": "" if present else _install_command(binary)})
    cfg = current_config()
    try:
        stored = env_file.read()
    except Exception:  # noqa: BLE001
        stored = {}
    roles_root = os.path.expanduser(CFG["roles_root"])
    external = os.path.expanduser("~/.agents/skills")
    external_names = sorted(e.name for e in os.scandir(external) if e.is_dir() and not e.name.startswith(".")) \
        if os.path.isdir(external) else None
    has_outline = pageindex_available()
    return {
        "version": VERSION, "python": platform.python_version(), "python_ok": sys.version_info >= (3, 12),
        "platform": sys.platform, "tools": tools,
        "office": Wizard._importable("docx", "openpyxl", "pptx"),
        "pageindex": has_outline, "pageindex_install": None if has_outline else _extras_command(["pageindex"]),
        "provider": cfg.get("provider", ""), "model": cfg.get("default_model", ""),
        "plan_approval": bool(setting("research", "plan_approval", True, bool)),
        "limits": dict(runs.DEFAULT_LIMITS),
        "openalex": {"name": coverage.KEY_ENV, "stored": bool(stored.get(coverage.KEY_ENV)),
                     "shell": bool(os.environ.get(coverage.KEY_ENV)), "url": "https://openalex.org/rest-api",
                     "file": str(env_file.path())},
        "paths": {"soul": profiles.shared_soul(), "roles": roles_root,
                  "shared_skills": str(skill_layers.shared_skills_dir()), "external_skills": external,
                  "external_names": external_names},
    }


# ---- models and credentials -----------------------------------------------------------

def _runtime(read_only=True):
    from misaka.cli.auth import _create_runtime
    return _create_runtime(read_only=read_only)


def _profile_for(target):
    from misaka.config import current_config
    cfg = current_config()
    if not target:
        return None
    if target == "last_order":
        return os.path.join(cfg["roles_root"], "last_order")
    from misaka.core.network import roster
    if target not in roster.roster_names(root=cfg["profiles_root"]):
        raise ValueError("没有这位 Sister")
    return os.path.join(cfg["profiles_root"], target)


def op_models_overview(_params: dict) -> dict:
    from misaka.cli.auth import _missing_sdk_extras
    from misaka.cli.setup import FEATURED_PROVIDERS
    from misaka.config import current_config, profiles
    from misaka.core.network import roster

    cfg = current_config()
    registry = _runtime().registry
    known = sorted({model.provider for model in registry.getAll()})
    oauth_ids = {p.id for p in registry.getOAuthProviders()}
    providers = []
    for provider in [*[p for p in FEATURED_PROVIDERS if p in known], *[p for p in known if p not in FEATURED_PROVIDERS]]:
        status = registry.getProviderAuthStatus(provider)
        try:
            extras = _missing_sdk_extras(registry, provider)
        except Exception:  # noqa: BLE001
            extras = []
        providers.append({"id": provider, "name": registry.getProviderDisplayName(provider),
                          "oauth": provider in oauth_ids, "featured": provider in FEATURED_PROVIDERS,
                          "configured": bool(status.configured or status.source), "source": status.source or "",
                          "extras": extras, "extras_install": _extras_command(extras) if extras else None})
    targets = [{"key": None, "label": "全局默认", "hint": "没有单独设置模型的角色都使用它", "pinned": ""},
               {"key": "last_order", "label": "Last Order", "hint": "研究协调者",
                "pinned": profiles.pinned_model(os.path.join(cfg["roles_root"], "last_order")) or ""}]
    for sid in roster.roster_names(root=cfg["profiles_root"]):
        targets.append({"key": sid, "label": f"Sister {sid}", "hint": "研究助手",
                        "pinned": profiles.pinned_model(os.path.join(cfg["profiles_root"], sid)) or ""})
    return {"providers": providers, "targets": targets,
            "global": {"provider": cfg.get("provider", ""), "model": cfg.get("default_model", "")}}


def op_models(params: dict) -> dict:
    from misaka.cli.setup import Wizard
    from misaka.config import current_config
    provider = str(params.get("provider") or "")
    registry = _runtime().registry
    cfg = current_config()
    current = cfg["default_model"] if cfg["provider"] == provider else None
    models = Wizard._model_choices([m for m in registry.getAll() if m.provider == provider], current)
    if params.get("configured_only"):
        models = Wizard._model_choices([m for m in registry.getAll() if registry.hasConfiguredAuth(m)], None)
    return {"models": [{"provider": m.provider, "id": m.id, "name": m.name or m.id,
                        "reasoning": bool(getattr(m, "reasoning", False)),
                        "contextWindow": getattr(m, "contextWindow", None)} for m in models]}


def op_set_key(params: dict) -> dict:
    provider, key = str(params.get("provider") or ""), str(params.get("key") or "").strip()
    if not provider or not key:
        raise ValueError("请选择服务商并填写 API Key")
    runtime = _runtime(read_only=False)
    if provider not in {m.provider for m in runtime.registry.getAll()}:
        raise ValueError("未知的服务商")
    runtime.storage.set(provider, {"type": "api_key", "key": key})
    return {"message": f"已保存 {provider} 的 API Key"}


def op_logout(params: dict) -> dict:
    provider = str(params.get("provider") or "")
    runtime = _runtime(read_only=False)
    runtime.storage.remove(provider)
    return {"message": f"已移除 {provider} 保存的登录信息（环境变量中的密钥不受影响）"}


def op_set_default(params: dict) -> dict:
    from misaka.config import profiles
    from misaka.core.settings_manager import SettingsManager
    provider, model = str(params.get("provider") or ""), str(params.get("model") or "")
    target = params.get("target") or None
    profile = _profile_for(target)
    if not provider and not model and profile:
        _clear_pin(profile)
        return {"message": "已改为跟随全局默认模型"}
    if not provider or not model:
        raise ValueError("请选择模型")
    if _runtime().registry.find(provider, model) is None:
        raise ValueError(f"{provider}/{model} 不在模型目录中")
    if profile:
        profiles.persist_role_default_model(profile, f"{provider}/{model}", strict=True)
    else:
        SettingsManager.create(params.get("workspace") or os.getcwd()).setDefaultModelAndProvider(provider, model)
    return {"message": f"默认模型已保存：{provider} / {model}"}


def _clear_pin(profile: str) -> None:
    from filelock import FileLock

    from misaka.config import profiles
    from misaka.utils import atomic
    path = profiles.settings_path(profile)
    if not os.path.exists(path):
        return
    with FileLock(path + ".lock"):
        data = profiles.role_settings(profile, strict=True)
        data.pop("defaultProvider", None)
        data.pop("defaultModel", None)
        atomic.write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def op_verify(params: dict) -> dict:
    from misaka.ai.stream import complete_simple
    from misaka.ai.types import Context, SimpleStreamOptions, UserMessage
    provider, model_id = str(params.get("provider") or ""), str(params.get("model") or "")
    registry = _runtime().registry

    async def ping() -> str:
        model = registry.find(provider, model_id)
        if model is None:
            raise RuntimeError(f"{provider}/{model_id} 不在模型目录中")
        auth = await registry.getApiKeyAndHeaders(model)
        if not auth.get("ok"):
            raise RuntimeError(auth.get("error") or "没有找到可用的凭证")
        reply = await complete_simple(
            model, Context(messages=[UserMessage(content="Reply with the single word OK.", timestamp=0)]),
            SimpleStreamOptions(apiKey=auth.get("apiKey"), headers=auth.get("headers"), maxTokens=16))
        if reply.stopReason == "error":
            raise RuntimeError(reply.errorMessage or "请求失败")
        return "".join(getattr(part, "text", "") for part in reply.content)
    text = asyncio.run(ping())
    return {"message": f"{provider} 已回复：{text.strip()[:40] or '（空回复）'}"}


# ---- browser and device sign-in ---------------------------------------------------------

def op_login(params: dict) -> dict:
    """The wizard's ``_oauth``, with the browser as the terminal.

    Answers arrive on stdin from a daemon thread, never through ``to_thread``: a login
    whose callback server wins the race would otherwise leave a worker blocked on stdin
    that ``asyncio.run`` then waits for forever (see the wizard's docstring).
    """
    from misaka.ai.auth.oauth_bridge import callbacks_for_interaction
    from misaka.cli.setup import _open_browser

    provider = str(params.get("provider") or "")
    registry = _runtime(read_only=False).registry
    if provider not in {p.id for p in registry.getOAuthProviders()}:
        raise ValueError("这个服务商不支持浏览器登录")

    async def run() -> None:
        loop = asyncio.get_running_loop()
        waiting: dict[str, asyncio.Future] = {}

        def reader() -> None:
            for line in sys.stdin:
                try:
                    answer = json.loads(line)
                except ValueError:
                    continue
                future = waiting.get(str(answer.get("id")))
                if future is not None:
                    loop.call_soon_threadsafe(lambda f=future, v=answer.get("value"): f.done() or f.set_result(v))
        threading.Thread(target=reader, daemon=True).start()
        counter = iter(range(1, 10_000))

        async def ask(request) -> str:
            key = f"q{next(counter)}"
            kind = getattr(request, "type", "text")
            options = [{"id": o.id, "label": o.label} for o in (getattr(request, "options", None) or [])]
            future = loop.create_future()
            waiting[key] = future
            send({"event": "prompt", "id": key, "kind": kind, "message": str(getattr(request, "message", "")),
                  "options": options})
            try:
                value = await future
            finally:
                waiting.pop(key, None)
                send({"event": "prompt_done", "id": key})
            if value is None:
                raise RuntimeError("已取消登录")
            return str(value)

        def notify(event) -> None:
            kind = getattr(event, "type", "")
            if kind == "auth_url":
                opened = _open_browser(str(event.url))
                send({"event": "auth_url", "url": str(event.url), "opened": opened,
                      "instructions": str(getattr(event, "instructions", "") or "")})
            elif kind == "device_code":
                send({"event": "device_code", "url": str(event.verificationUri), "code": str(event.userCode)})
            else:
                send({"event": "message", "message": str(getattr(event, "message", ""))})

        interaction = SimpleNamespace(signal=None, prompt=ask, notify=notify)
        owned = (registry.getRegisteredProviderConfig(provider) is not None
                 or registry.getRegisteredNativeProvider(provider) is not None)
        if owned:
            await registry.login(provider, "oauth", interaction)
        else:
            await registry.authStorage.login(provider, callbacks_for_interaction(interaction))

    asyncio.run(run())
    return {"message": f"{provider} 已登录"}


# ---- roles ------------------------------------------------------------------------------

ROLE_FILES = ("DESCRIBE.md", "SOUL.md")


def op_sisters(_params: dict) -> dict:
    from misaka.config import CFG, profiles
    from misaka.core.network import roster
    root = CFG["profiles_root"]
    items = []
    for sid in roster.roster_names(root=root):
        desc, _body = roster.describe(sid, root)
        try:
            counts = roster.card_counts(sid)
        except Exception:  # noqa: BLE001 - a missing board is zero cards
            counts = {}
        items.append({"id": sid, "description": desc or "", "model": profiles.pinned_model(os.path.join(root, sid)) or "",
                      "cards": counts, "path": os.path.join(root, sid)})
    next_id = 10032
    while any(str(next_id) == item["id"] for item in items):
        next_id += 1
    return {"sisters": items, "next_id": str(next_id), "roles_root": os.path.expanduser(CFG["roles_root"])}


def op_create_sister(params: dict) -> dict:
    from misaka.core.network import roster
    sid = str(params.get("id") or "").strip()
    ok, message = roster.create_sister(sid, specialty=(params.get("specialty") or None),
                                       model=(params.get("model") or None))
    if not ok:
        raise ValueError(message)
    return {"message": f"已添加 Sister {sid}"}


def op_remove_sister(params: dict) -> dict:
    from misaka.core.network import roster
    ok, message = roster.remove_sister(str(params.get("id") or ""))
    if not ok:
        raise ValueError(message)
    return {"message": message}


def _role_file(params: dict) -> str:
    from misaka.config import CFG, profiles
    name = params.get("file")
    if name not in ROLE_FILES and name != "SHARED_SOUL":
        raise ValueError("只能编辑 DESCRIBE.md、SOUL.md 或共享身份")
    if name == "SHARED_SOUL":
        return profiles.shared_soul()
    role = str(params.get("role") or "")
    if role == "last_order":
        if name != "SOUL.md":
            raise ValueError("Last Order 只有 SOUL.md")
        return os.path.join(os.path.expanduser(CFG["roles_root"]), "last_order", "SOUL.md")
    _profile_for(role)
    return os.path.join(CFG["profiles_root"], role, name)


def op_read_role_file(params: dict) -> dict:
    path = _role_file(params)
    try:
        with open(path, encoding="utf-8-sig") as f:
            return {"path": path, "content": f.read()}
    except FileNotFoundError:
        return {"path": path, "content": ""}


def op_write_role_file(params: dict) -> dict:
    from misaka.utils import atomic
    path = _role_file(params)
    content = params.get("content")
    if not isinstance(content, str) or len(content) > 200_000:
        raise ValueError("内容为空或过长")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic.write_text(path, content)
    return {"message": f"已保存 {os.path.basename(path)}"}


# ---- research and project ---------------------------------------------------------------

def op_set_research(params: dict) -> dict:
    from misaka.config import env as env_file
    from misaka.core.settings_manager import SettingsManager
    from misaka.extensions import coverage
    messages = []
    if "plan_approval" in params:
        value = bool(params["plan_approval"])

        def mutate(section: dict) -> None:
            section["plan_approval"] = value
        SettingsManager.forRole(None).updateSection("research", mutate)
        messages.append("计划审批：" + ("需要确认" if value else "自动执行"))
    if params.get("openalex_key"):
        env_file.write({coverage.KEY_ENV: str(params["openalex_key"]).strip()})
        messages.append("已保存 OpenAlex Key")
    if params.get("openalex_remove"):
        env_file.write({}, remove=(coverage.KEY_ENV,))
        messages.append("已移除 OpenAlex Key")
    return {"message": "；".join(messages) or "没有改动"}


def op_init_project(params: dict) -> dict:
    from misaka.core.platform import cards
    folder = os.path.abspath(os.path.expanduser(str(params.get("folder") or "")))
    if not params.get("folder"):
        raise ValueError("请填写项目文件夹")
    if not os.path.isdir(folder):
        if not params.get("create"):
            raise ValueError("文件夹不存在")
        os.makedirs(folder, exist_ok=True)
    lines = [str(line) for line in cards.init_project(folder)]
    return {"message": f"项目已就绪：{folder}", "lines": lines, "folder": folder}


# ---- web tools --------------------------------------------------------------------------

@contextlib.contextmanager
def _web_scope():
    from misaka.cli import web as web_cli
    from misaka.core.web import registry
    from misaka.core.web.scope import WebScope, current_scope
    with WebScope(None).activate():
        result = asyncio.run(web_cli._discover([]))
        try:
            registry.ensure_backends_registered()
            registry.replace_extension_providers(result.extensions)
            current_scope().browser_providers = {name: provider for extension in result.extensions
                                                 for name, provider in getattr(extension, "browserProviders", {}).items()}
            yield
        finally:
            result.runtime.invalidate()


def _kind(key: str) -> dict:
    from misaka.cli.web_setup import CHOICES
    from misaka.core.web import config
    if key in config._BOOL_KEYS or tuple(key.split(".")) in config._NESTED_BOOL_KEYS or key == "vault.enabled":
        return {"type": "bool"}
    if key in CHOICES:
        return {"type": "choice", "choices": list(CHOICES[key])}
    if key.startswith("provider_tier."):
        return {"type": "choice", "choices": ["auto", "free", "paid"]}
    if key in config._LIST_KEYS or tuple(key.split(".")) in config._NESTED_LIST_KEYS:
        return {"type": "list"}
    if key in {"vault.onepassword", "vault.bitwarden", "browser.controller_command", "browser.controller_capabilities"} \
            or key.startswith("http_timeout."):
        return {"type": "json"}
    return {"type": "text"}


def _shown(key):
    from misaka.cli.web_setup import _sensitive, _value
    from misaka.core.web import config
    value = _value(key)
    if value is None:
        return None, False
    if _sensitive(key):
        return "已设置（隐藏）", True
    return config.redact_secrets(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)), False


def op_web_overview(_params: dict) -> dict:
    from misaka.cli import web as web_cli
    from misaka.cli import web_setup
    from misaka.core.web import config, dispatch, registry
    with _web_scope():
        providers = []
        for p in registry.list_providers(include_disabled=True):
            rows = []
            for row in web_cli._provider_rows(p):
                rows.append({"name": row.get("name", p.display_name), "tag": row.get("tag", ""), "badge": row.get("badge", ""),
                             "web_tier": row.get("web_tier"), "post_setup": row.get("post_setup"),
                             "env_vars": [{"key": v["key"], "prompt": v.get("prompt", v["key"]), "url": v.get("url", "")}
                                          for v in row.get("env_vars", [])]})
            providers.append({"name": p.name, "display": p.display_name, "search": bool(p.supports_search()),
                              "extract": bool(p.supports_extract()), "disabled": config.provider_disabled(p.name),
                              "ready": bool(registry.provider_is_ready(p)), "tier": config.provider_tier(p.name), "rows": rows})
        resolved = {}
        for label, resolve in (("search", dispatch.resolve_provider), ("extract", dispatch.resolve_extractor)):
            provider, backend, error = resolve()
            resolved[label] = {"backend": backend or "", "error": str(error or ""),
                               "ready": bool(provider is not None and registry.provider_is_ready(provider))}
        own = config.own_section()
        browser = config.web_config().get("browser") or {}
        from misaka.core.web.browser.providers import providers as browser_providers
        services = {}
        for name, provider in browser_providers().items():
            services[name] = [{"name": r.get("name", name), "tag": r.get("tag", ""),
                               "env_vars": [{"key": v["key"], "prompt": v.get("prompt", v["key"])} for v in r.get("env_vars", [])]}
                              for r in web_cli._provider_rows(provider)]
        services["camofox"] = [{"name": "Camofox", "tag": "", "env_vars": [{"key": k, "prompt": k} for k in ("CAMOFOX_URL", "CAMOFOX_API_KEY", "CAMOFOX_USER_ID")]}]
        groups = []
        for title, keys in web_setup.groups().items():
            fields = []
            for key in keys:
                shown, hidden = _shown(key)
                fields.append({"key": key, "value": shown, "hidden": hidden, **_kind(key)})
            groups.append({"title": title, "fields": fields})
        credentials = [{"name": n, "set": s, "source": src} for n, s, src in config.credential_status()]
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                web_cli._status()
        except Exception as error:  # noqa: BLE001 - a broken config is shown, not raised
            buffer.write(f"\n{config.redact_secrets(str(error))}")
        return {"providers": providers, "resolved": resolved,
                "selected": {k: own.get(k) for k in ("backend", "search_backend", "extract_backend")},
                "keyless": bool(config.keyless_tier_enabled()),
                "browser": {"enabled": browser.get("enabled"), "cloud_provider": browser.get("cloud_provider"),
                            "engine": browser.get("engine"), "lightpanda_path": browser.get("lightpanda_path") or "",
                            "cdp": bool(browser.get("cdp_url"))},
                "browser_services": services, "groups": groups, "credentials": credentials,
                "status": config.redact_secrets(buffer.getvalue()), "path": config.config_label()}


def _web_commit(changes: dict, remove=()) -> dict:
    """``web_setup.save`` without its confirmation prompt: validate the merged layers, then write."""
    from misaka.cli.web_setup import _sensitive, _validate
    from misaka.core.settings_manager import deep_merge_settings
    from misaka.core.web import config, dispatch, registry
    from misaka.core.web.scope import current_scope
    from dataclasses import replace
    changes = {str(k): str(v) for k, v in changes.items()}
    for key, value in changes.items():
        if _sensitive(key) and value:
            config.remember_secret(value)
    own = config.own_section()
    for key in remove:
        parts = key.split(".")
        parent = own if len(parts) == 1 else own.get(parts[0], {})
        if isinstance(parent, dict):
            parent.pop(parts[-1], None)
    for key, value in changes.items():
        config._set_value(own, key, value)
    shared = config.load_config() if current_scope().profile_dir else {}
    prospective = deep_merge_settings(shared, own)
    _validate(prospective)
    warnings = []
    with replace(current_scope(), config=prospective, config_error=None).activate():
        for label, resolve in (("搜索", dispatch.resolve_provider), ("网页提取", dispatch.resolve_extractor)):
            provider, backend, error = resolve()
            if error or not registry.provider_is_ready(provider):
                warnings.append(f"{label}：{backend or '未选择'} 在本机尚未就绪，可能缺少凭证或安装。")
    config.update_config(changes, remove=tuple(remove))
    return {"message": "已保存。账号可用性与网络连通性没有测试。", "warnings": warnings}


def op_web_save(params: dict) -> dict:
    changes = params.get("changes") or {}
    remove = params.get("remove") or []
    if not isinstance(changes, dict) or not isinstance(remove, list):
        raise ValueError("参数格式不正确")
    with _web_scope():
        return _web_commit(changes, tuple(str(k) for k in remove))


def op_web_provider(params: dict) -> dict:
    """``misaka web setup <provider>`` as one form: capabilities, tier row, its credentials."""
    from misaka.cli import web as web_cli
    from misaka.core.web import config, registry
    name = str(params.get("name") or "")
    capability = params.get("capability") or "both"
    with _web_scope():
        if not name:
            caps = ("search", "extract") if capability == "both" else (capability,)
            changes = {f"{cap}_backend": "" for cap in caps}
            if capability == "both":
                changes["backend"] = ""
            return _web_commit(changes)
        provider = registry.get_provider(name, include_disabled=True)
        if provider is None:
            raise ValueError("未知的联网服务")
        if config.provider_disabled(name):
            raise ValueError("这个服务已停用，请先启用")
        rows = web_cli._provider_rows(provider)
        index = int(params.get("row") or 0)
        row = rows[index] if 0 <= index < len(rows) else rows[0]
        supported = [cap for cap in ("search", "extract") if getattr(provider, f"supports_{cap}")()]
        selected = supported if capability == "both" else [capability]
        if not selected or any(cap not in supported for cap in selected):
            raise ValueError(f"{name} 只支持：{'、'.join(supported) or '无'}")
        changes = {f"{cap}_backend": name for cap in selected}
        tier = params.get("tier") or row.get("web_tier")
        if tier:
            changes[f"provider_tier.{name}"] = tier
        if tier == "free":
            changes["keyless_fallback"] = "true"
        values = params.get("env") or {}
        for variable in row.get("env_vars", []):
            value = str(values.get(variable["key"]) or "").strip()
            if value:
                changes["env." + variable["key"]] = value
        result = _web_commit(changes)
        if row.get("post_setup") == "ddgs" and not registry.provider_is_ready(provider):
            result["warnings"].append("ddgs 尚未安装：可在「联网 → 安装可选工具」中安装。")
        return result


def op_web_enable(params: dict) -> dict:
    from misaka.core.web import config, registry
    name = str(params.get("name") or "")
    with _web_scope():
        if registry.get_provider(name, include_disabled=True) is None:
            raise ValueError("未知的联网服务")
        config.set_provider_enabled(name, bool(params.get("enabled")))
    return {"message": ("已启用 " if params.get("enabled") else "已停用 ") + name}


def op_web_browser(params: dict) -> dict:
    """The wizard's browser-connection menu as one form."""
    from urllib.parse import urlsplit

    from misaka.core.web import config
    mode = params.get("mode")
    with _web_scope():
        if mode == "off":
            return _web_commit({"browser.enabled": "false"})
        changes = {"browser.enabled": "true", "browser.controller_command": "[]",
                   "browser.cdp_url": "", "env.BROWSER_CDP_URL": "", "browser.cloud_provider": mode}
        if mode != "cdp" and os.environ.get("BROWSER_CDP_URL"):
            raise ValueError("环境变量 BROWSER_CDP_URL 会覆盖这里的设置，请先在启动环境中取消它。")
        if mode == "local":
            engine = params.get("engine") or "auto"
            if engine not in ("auto", "chrome", "lightpanda"):
                raise ValueError("未知的浏览器引擎")
            changes["browser.engine"] = engine
            if engine == "lightpanda":
                path = params.get("lightpanda_path") or (config.web_config().get("browser") or {}).get("lightpanda_path")
                if not path:
                    raise ValueError("Lightpanda 需要可执行文件路径")
                changes.update({"browser.lightpanda_path": path, "browser.headed": "false", "browser.use_real_profile": "false"})
        elif mode == "cdp":
            endpoint = str(params.get("cdp_url") or "")
            if not endpoint:
                raise ValueError("CDP 需要填写地址")
            if urlsplit(endpoint).scheme not in {"http", "https", "ws", "wss"} or not urlsplit(endpoint).hostname:
                raise ValueError("CDP 地址必须是 http(s) 或 ws(s)")
            changes["browser.cdp_url"] = endpoint
        else:
            for key, value in (params.get("env") or {}).items():
                if str(value).strip():
                    changes["env." + str(key)] = str(value).strip()
        return _web_commit(changes)


OPS = {name[3:]: fn for name, fn in globals().items() if name.startswith("op_") and callable(fn)}


def main() -> int:
    try:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", newline="\n")
        line = sys.stdin.readline()
        request = json.loads(line or "{}")
        op = OPS.get(request.get("op"))
        if op is None:
            raise ValueError("未知设置操作")
        params = request.get("params") or {}
        if request.get("workspace") and os.path.isdir(request["workspace"]):
            os.chdir(request["workspace"])
            params.setdefault("workspace", request["workspace"])
        # Whatever a library prints is not the reply; only marked lines are.
        with contextlib.redirect_stdout(sys.stderr):
            data = op(params)
        send({"ok": True, "data": data})
    except BaseException as error:  # noqa: BLE001 - every failure reaches the GUI as text
        if isinstance(error, KeyboardInterrupt):
            raise
        message = str(error) or type(error).__name__
        try:
            from misaka.core.web import config
            message = config.redact_secrets(message)
        except Exception:  # noqa: BLE001
            pass
        send({"ok": False, "error": message})
    sys.stdout.flush()
    os._exit(0)   # a login's stdin reader thread must not hold the exit


if __name__ == "__main__":
    raise SystemExit(main())
