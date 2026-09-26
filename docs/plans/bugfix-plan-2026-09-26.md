# 非上游 BUG 修复计划（2026-09-26）

来源：`docs/audits/code-quality-2026-09-25/findings.md` 中判定为"不来自上游"的 15 个 BUG，外加 2 个"上游就有、翻译后加重"的（Q-123、Q-068）。共 17 项。

**状态（2026-09-26 晚）：15 项已实施，未提交。Q-086（D3）用户决定暂不修；Q-104 实施后用户决定回退（login 与模型选择相关的一律不改，保持 misaka 现状，`provider_display_names.py` 已恢复）。** D1/D2/D4/D5/D6 按建议执行；Q-087 单独实施（D3 只挡住 Q-086）。每项的实际做法写在台账对应行末尾的〔2026-09-26 已修〕里；与本计划不同的地方：Q-054 没有另立共享常量（上游三处本就是字面量，逐行移植）；Q-124 的新测试顺带查出同一渲染器还用了不存在的主题色；Q-114 的额度词是内联的并由测试守同步，而非 import（避免板进程加载 provider 层，约 190 ms）；Q-020 让 setup/update/uninstall 在坏设置下仍能运行。门禁：改动文件 ruff 全过，全量 pytest 3509 passed / 1 skipped（基线 3350；Q-104 回退时删去其 5 个测试）。事后复核又改正了自己引入的 4 处问题：Q-114 第一版把文件 PermissionError 误判为终态并漏判 `Authentication failed`/`invalid token`；Q-087 第一版替换连字符会改掉常见 MCP 服务器的工具名；Q-028 的尺寸缓存会留住图片数据；Q-123 的整读在文件被并发写大时可能拿截断内容去改；二次复核又改正复核本身的 2 处：Q-114 把 `insufficient quota` 改窄了，Q-087 的 `server_matches` 会让两个中文服务器名互相匹配。

门禁沿用现状：改动文件 `ruff check --force-exclude`，相关测试 + 全量 `pytest`。每项都先写能复现的失败测试，再改代码。

调研中顺带更正了一处审计结论：Q-056 不是"彻底零重试"——会话层自动重试（`retry.enabled`，默认开、3 次）仍按错误文本兜底；真正缺的是 provider 层那一道，以及它无视 `retry.provider.maxRetries`。台账已同步更正。

---

## 需要你拍板的 6 个决定

| # | 条目 | 问题 | 建议 |
|---|---|---|---|
| D1 | Q-132 | `/research` 的位置式深度怎么留 | 开头整数只在"单独出现"或"后面紧跟 `--选项`"时才算深度；否则整行是问题。`/research 2`、`start 2 --parallel 1 …` 照旧可用，`/research 2 某问题` 会变成问题"2 某问题"（行为变化，文档同步改） |
| D2 | Q-083 | `auth.json` 是软链/硬链时怎么办 | 允许：软链解析一次后对目标文件做"必须是普通文件、属主是当前用户"的检查；去掉 `st_nlink == 1` 禁令；写入落到解析后的目标上，软链本身保留 |
| D3 | Q-086 | MCP 子进程环境：黑名单还是白名单 | 黑名单（复用现成的 `without_credentials`，保住代理/证书等变量）+ 允许在服务器配置 `env` 里用 `${VAR}` 显式授予某个 key |
| D4 | Q-054 | 缓存保留旋钮统一成哪个名字 | `PI_CACHE_RETENTION`（与 pi 逐行一致；本机与各 `.env`/`settings.json`/`models.json` 都没设过任何一个名字，改名零影响） |
| D5 | Q-020 | 设置项类型错误怎么处理 | 建一张集中的旋钮表；进程入口（`bootstrap.install()`）一次性校验、有错就拒绝启动并列出全部错误；运行期读到坏值只告警一次并用默认值，不再 `SystemExit` |
| D6 | Q-123 | `read` 要不要限大小 | 必须先确认是普通文件；文本改为流式读取（内存有界，照样能报总行数）；图片/Office 另设字节上限 |

其余 11 项没有需要你选的地方，按下文直接做。

---

## 分批

- **第一批（小、独立、低风险）**：Q-124、Q-054、Q-047、Q-110、Q-009、Q-068、Q-003
- **第二批（中等，不改行为语义）**：Q-056、Q-104、Q-114、Q-028
- **第三批（行为变化，等 D1–D6）**：Q-132、Q-083、Q-086+Q-087、Q-020、Q-123

---

## 第一批

### Q-124 office 渲染器少传参数（L）
- 现状：`core/tools/office.py:265` 调 `render_tool_path(raw_path, context.cwd)`，签名是 `(raw_path, theme, cwd)`；每次 TypeError，被 `ui/tui/interactive/components/tool_execution.py:319` 的 catch-all 吞掉。仓库里**没有任何** renderCall/renderResult 测试。
- 修法：改成 `render_tool_path(raw_path, theme_obj, context.cwd)`。
- 防复发：新增一个测试，构造全部内置工具定义（read/write/edit/bash/grep/find/ls/office/powershell/web_fetch/download_file 等），各调一次 `renderCall`/`renderResult`，断言不抛异常。catch-all 保留（UI 不能因扩展渲染器崩），但测试保证我们自己的渲染器不会再悄悄失效。
- 文件：`core/tools/office.py`；新测试 `tests/test_tool_renderers.py`。

### Q-054 缓存保留旋钮一半叫 PI_、一半叫 MISAKA_（L）
- 现状：`core/cache_warmer.py:49`、`ai/providers/pi_messages.py:282` 读 `PI_CACHE_RETENTION`；`ai/providers/_common.py:156` 读 `MISAKA_CACHE_RETENTION`（anthropic/bedrock/openai_* 都经它）。pi 0.87.1 全部用 `PI_CACHE_RETENTION`。
- 修法（按 D4）：`_common.resolve_cache_retention` 改读 `PI_CACHE_RETENTION`，与上游逐行一致；cache_warmer 与 pi_messages 本就一致。三处共用一个常量。
- 测试：设 `PI_CACHE_RETENTION=long`（进程环境与 per-request `env` 两种），断言三条路径都得到 long。

### Q-047 Anthropic 兜底分支逐块解码 UTF-8（L）
- 现状：`ai/providers/anthropic.py:1007-1033` 的 body 分支对每块 `chunk.decode("utf-8")`；上游 `anthropic-messages.js:253-276` 用 `new TextDecoder()` + `decode(value, {stream: true})` + 末尾 `decode()` 刷新。这是移植时漏掉的。
- 修法：按上游逐行移植：`codecs.getincrementaldecoder("utf-8")()`，每块 `decode(chunk, final=False)`，结束 `decode(b"", final=True)`。异步/同步两个分支都改。
- 测试：把 `"数据"` 的 UTF-8 字节从中间切成两块喂给替身 body，断言行内容正确、不抛 `UnicodeDecodeError`。

### Q-110 terminate_orphaned_group 漏了漂移容忍（M）
- 现状：`core/platform/processes.py:178` 仍是 `current != leader_identity`，并把"不等"解释为"PID 已复用、进程组已不存在"直接返回 True。调用点：`core/network/dispatch.py:159`（回收卡住的 worker）、`ui/panel/daemon.py:1336`（接管 blocked 卡）。全仓库其余身份比较已在 B56 改成 `same_identity`，这是唯一漏网。该函数**没有任何测试**。
- 修法：改为 `not processes.same_identity(current, leader_identity)`。
- 测试（放进 `tests/test_process_identity_drift.py`）：起一个自带进程组的 `sleep 60`（`start_new_session=True`），
  1. 用偏移 1 s 的身份调用 → 返回 True **且进程已被杀**；
  2. 另起一个，用偏移 3600 s 的身份调用 → 返回 True、**不发信号**（PID 复用语义），测试自己清理。

### Q-009 剪贴板：事件循环上同步整张抓图，还抓两次（M）
- 现状：`utils/clipboard_image.py:288` 先 `clipboard.has_image()`（`clipboard_native.py:32` 同步 `ImageGrab.grabclipboard()`），再 `await get_image_binary()` 又抓一次。上游 `Clipboard.hasImage()` 是原生的轻量类型查询，Python 替身没有等价物。
- 修法：`read_clipboard_image_via_native_clipboard` 不再调 `has_image()`，直接 `await get_image_binary()`（它在线程里抓图，无图返回 None）。加 `# MISAKA fork:` 注释说明偏离上游的原因。`has_image` 保留在协议里（其他实现可能廉价），但本路径不用。
- 测试：替身剪贴板记录 grab 次数，断言粘贴一次只抓一次，且抓图不在事件循环线程。

### Q-068 codex / Copilot 的 OAuth 请求没有超时（L）
- 现状：`ai/utils/oauth/openai_codex.py:120,153,186,244` 与 `github_copilot.py:92,206` 用 `httpx.AsyncClient(timeout=None)`。仓库里其他 OAuth 流程（xai、kimi、meta、radius）统一是 `REQUEST_TIMEOUT_MS = 30 * 1000`，anthropic 用 30 s。上游 Node fetch 有 undici 约 300 s 的隐式上限，httpx 的 None 是真正无限。
- 修法：两个模块各加 `REQUEST_TIMEOUT_MS = 30 * 1000`，六处改用它。设备码轮询是逐次短请求，整体期限仍由设备码过期时间控制，不受影响。
- 测试：用会挂住的 `httpx.MockTransport`（或故意不响应的本地 socket）断言刷新在超时后抛错而不是永久等待。

### Q-003 workspace 的 Markdown 标题识别（L）
- 现状：`workspace.py:52-63`（`_artifact_node`）与 `76-83`（`_project_file`）各写一份"`#` 开头即标题"，不识别代码块；一份有条数/长度上限，一份没有。仓库里已有正确实现：`core/research/workflow.py:1175-1190` 的 `_headings`（识别 ``` 与 ~~~ 围栏）。
- 修法：把 `_FENCE`/`_HEADING`/`_headings` 抽到共享位置（如 `misaka/utils/markdown.py`，返回 `(行号, 级别, 标题)`），workflow 与 workspace 三处都用它；`_project_file` 也套用 `_ARTIFACT_MAX_HEADINGS`/`_ARTIFACT_MAX_TITLE_CHARS` 上限。
- 测试：扩展 `tests/test_workspace_artifact_outline.py`，PROJECT.md 与 artifact 里放 fenced code 中的 `# comment` 和 `#hashtag`，断言不进大纲；超长/超多标题被截断。

---

## 第二批

### Q-056 Gemini/Vertex 的 provider 层重试（M）
- 现状：`google.py:168-169`、`google_vertex.py:409-410` 把 SDK 自带重试关成 1 次（理由是外层 `retry_google_request` 负责），但两处调用 `google.py:286`、`google_vertex.py:158` 都没包它。上游 0.87.1 `google-generative-ai.js:49`、`google-vertex.js:52` 都是 `await retryGoogleRequest(() => client.models.generateContentStream(params), options)`。
- 已验证：`provider_error_status` 能从真实的 `google.genai.errors.ClientError(429)`/`ServerError(503)` 取到状态码，`is_retryable_provider_error` 对 429/503 为真、400 为假——重试策略本身可用，只差把调用包进去。
- 修法：两处按上游逐行改为 `google_stream = await retry_google_request(lambda: client.aio.models.generate_content_stream(**_prepare_sdk_params(params)), options)`。建连阶段的中止：用现成的 `ai/utils/abort.race_with_abort_signal` 包住这次 await（因为 `_prepare_sdk_params` 会剥掉 SDK 不认识的 `abortSignal`），标 `# MISAKA fork:`。
- 行为说明：默认 `retry.provider.maxRetries` 未设，provider 层仍是 0 次，与 OpenAI 系一致；用户设了之后 Gemini 才开始照它重试。会话层自动重试不变。
- 测试：替身 client 前两次抛 `ServerError(503)`、第三次成功；`maxRetries=2` 时成功、`maxRetries=0` 时失败；建连中途中止立即返回 aborted。

### Q-104 /login 选不到 8 个 API-key provider（M）
- 现状：`ui/tui/interactive/interactive_mode.py:255-263 isApiKeyLoginProvider` 按 `core/provider_display_names.py` 的手抄表判断，表来自 pi 0.74.0；模型目录已同步到 0.87.1。pi 在 0.74.0 之后、0.80.0 之前删掉了这套（0.74.0 仍有该文件，0.80.0 已无），改为遍历 `modelRuntime.getProviders()`、看 `provider.auth.apiKey`/`auth.oauth`（0.87.1 `interactive-mode.js:4692-4722`）。
- 已验证：MISAKA 的 `modelRegistry.getProviders()` 已经返回带 `auth` 元数据的 42 个 provider，缺失的 8 个 `auth.apiKey` 均为真。
- 修法：按上游 0.87.1 逐行移植 `getLoginProviderOptions`（含 `status` 字段与按名字排序）；删掉 `isApiKeyLoginProvider`；`provider_display_names.py` 只剩 `model_registry.py:2085` 一处兜底用，改为用 provider 自己的 `name`，然后删除整个文件（`__all__`/测试引用一并清）。
- 测试：`getLoginProviderOptions("api_key")` 含 nvidia/baseten/meta/ant-ling/zai-coding-cn/qwen-token-plan×3；OAuth 项不变；与上游同样的排序。

### Q-114 卡片失败分类过宽（L）
- 现状：`core/platform/tasks.py:1243-1270` 的 `auth_or_quota` 含裸 `api[ _-]?key`、`billing`、`authentication`，命中即终态不重试。原因文本来源有五种：Sister 会话错误（`network/sister_runtime.py:1105`）、`supervisor: …`（`:1152`）、`finalizer: …`（`network/todo.py:560`）、`TypeName: msg`（`network/dispatch.py:279`）、pane 崩溃尾巴（`ui/panel/daemon.py:1565`，已显式传 `crash`）。仓库里**没有**任何分类器测试。
- 修法：
  1. 来源已知的调用点显式传 `failure_kind`：supervisor/finalizer/dispatch 异常一律 `crash`（除非异常本身是 provider 认证错误类型），不再交给正则猜。
  2. 正则只对"provider 报回来的错误文本"生效，并收紧为 provider 形状：`invalid (x-)?api[ _-]?key`、`incorrect api key`、`authentication_error`、`permission_error`、`\b(401|403)\b`、`No API key for provider`、`No configured authentication`；额度类直接复用 `ai/utils/retry.py` 的 `NON_RETRYABLE_PROVIDER_LIMIT_ERROR_PATTERN`（单一来源）。去掉裸 `billing`/`authentication`/`api key`。
  3. `protocol` 这个词同样收紧为本仓库自己的措辞（`without settling`、`bad schema` 等），不再匹配任意含 "protocol" 的文本。
- 测试：表驱动——真实的 Anthropic 401 body、OpenAI `insufficient_quota`、Gemini "Resource has been exhausted (e.g. check quota)"（应可重试）、`KeyError: 'api_key'`（crash）、"Brave API key is not configured; fell back to ddgs"（failure）、"MCP protocol version mismatch"（crash/failure，不是 protocol_violation）。

### Q-028 预算把图片 base64 当 token（M）
- 现状：`agent/request_budget.py:46-88` 以"整段上下文 JSON 的 UTF-8 字节数"作 token 上界，图片 data 原样计入；`allowance()` 与 `reserve()` 各序列化一次。无测试。`read` 已把图片缩到 ≤2000×2000。
- 修法：
  1. `context_token_upper_bound` 序列化前把每个 image block 的 `data` 换成占位，另按尺寸加一个保守的每图上界：用 Pillow 只读头部取宽高，`ceil(w*h/750) + 85`（覆盖 Anthropic 的 w·h/750、Gemini 按 768 平铺、OpenAI 分块的最坏情况）；读不出尺寸时取固定 6,400。
  2. `reserve()` 复用 `allowance()` 算出的上界，只序列化一次。
- 测试：含一张 400 KB PNG 的上下文，上界从约 40 万降到数千；纯文本上下文结果不变；`reserve` 与 `allowance` 对同一上下文只序列化一次（计数替身）。

---

## 第三批（等 D1–D6）

### Q-132 `/research` 吞掉问题开头的数字（M）→ D1
- 现状：`core/research/wiring/research.py:58-119` 把开头第一个整数当深度。`/research 1968 …` 报错；`/research 3 main causes …` 静默改题。现有测试钉住 `/research 2`（`tests/test_skill_command_delivery.py:333`）与 `start 2 --parallel 1 …`（`tests/test_research_sister_parallel.py:50`）；文档 `docs/guide/research.md:18` 与 `USAGE` 写的是 `/research [DEPTH] … QUESTION`。
- 修法（D1 建议）：开头整数仅在"整行只有它"或"下一个词以 `--` 开头"时才是深度；否则不消费，整行进问题。`USAGE` 与 `docs/guide/research.md` 改为"深度用 `--depth N`；单独的 `/research N` 表示先定深度、下一条消息给问题"。
- 测试：`/research 1968 student movements in Japan` → 问题完整；`/research 3 main causes …` → 问题完整、深度默认；`/research 2` 与 `start 2 --parallel 1 …` 行为不变。

### Q-083 auth.json 软链/硬链即全部凭据失效（M）→ D2
- 现状：`core/auth_storage.py:135-156` 用 `lstat`+`S_ISREG`+`st_nlink != 1` 拒绝+`O_NOFOLLOW`，来自 MISAKA 加固提交 2c26e43；上游 pi 新旧版都没有这些检查；`utils/paths.get_file_revision` 的 docstring 恰好说明这些检查会让正常的 dotfiles 软链、备份硬链"永远失效"。写入走 `atomic.write_text`（临时文件 + `os.replace`），直接放开会把软链替换成普通文件。
- 修法（D2 建议）：
  1. 路径先 `os.path.realpath` 一次；对**目标**做 `S_ISREG` 与 `st_uid == os.getuid()` 检查（这才是真正的安全属性），拒绝 FIFO/目录/他人文件；
  2. 去掉 `st_nlink` 禁令；
  3. 读取对解析后的路径仍用 `O_NOFOLLOW` 并比对前后 `(dev, ino)`，防打开瞬间被换；
  4. 写入对解析后的目标做原子替换（临时文件放在目标所在目录），软链本身保留；硬链接会被原子替换断开——在 docstring 里写明。
- 测试：auth.json 是指向 tmp 另一处文件的软链 → 能读、能写、软链仍在且目标被更新；auth.json 有第二个硬链接 → 能读写；指向 FIFO/目录的软链 → 明确报错；空文件仍按现有语义报错。

### Q-086 + Q-087 MCP 子进程环境与工具名（M/L）→ D3
- Q-086 现状：`core/mcp.py:213-221` `env = dict(os.environ)`；`config/env.py:128` 把 `.env` 全部装入 `os.environ`。Hermes 用白名单（`tools/mcp_tool_config.py:74-129`）；MISAKA 自己的 `core/web/config.without_credentials` 已给 DDGS/浏览器用（已验证在 web 作用域之外也能调用，能剔除 `*_API_KEY`、保留 `HTTPS_PROXY`）。本机没有配置任何 MCP 服务器。
- Q-086 修法（D3 建议）：
  1. 把"凭据形变量"的判定（`_SECRET_NAME_SUFFIXES`、公开/端点名单、`provider_variables()`）从 `core/web/config.py` 挪到中性模块（如 `misaka/utils/child_env.py`），web 模块改为从那里 import，免得 MCP 反向依赖 web；
  2. MCP stdio 子进程的基础环境 = `without_credentials(os.environ)` + MISAKA 角色变量 + 服务器配置里的 `env`；
  3. 配置 `env` 的值支持 `${VAR}` 引用（从进程环境/`.env` 取），让用户显式授予某个 key，而不用把密钥抄进 settings.json；
  4. 模块 docstring 写明规则。
- Q-087 现状：`core/mcp.py:437-438` 原样拼 `mcp__{server}__{tool}`。Hermes `tools/mcp_tool_schema.py:134-172`：非 `[A-Za-z0-9_]` 一律换 `_`，超过 64 字符截断并加 8 位 sha256 后缀。**连带影响**：`core/subagent/child.py:938-962` 靠 `split("__")` 从工具名反解服务器名，再与 `MISAKA_REQUIRED_MCP_SERVERS` 里的原始名比较——只改注册名会让这里对不上。
- Q-087 修法：逐行移植 Hermes 的 `sanitize_mcp_name_component` 与 `mcp_prefixed_tool_name`；`child.py` 的比较两边都过同一个 sanitize；更稳妥的是让 `McpPart` 直接提供"已注册的服务器名"，child 不再从工具名反解（被截断的名字已无法反解）。
- 测试：服务器名 `my-server.v2`、超长工具名 → 名字合法且 ≤64；required-server 等待逻辑对带连字符的名字仍生效；子进程环境里没有 `ANTHROPIC_API_KEY`，有 `HTTPS_PROXY`，`env: {"FOO_API_KEY": "${FOO_API_KEY}"}` 时只放行这一个。
- 顺带（可选，属上游继承的 Q-121）：同一个 `child_env` 也可以用于模型的 bash，但 `.env` 同时承担给技能脚本传密钥的职责，需要"模型凭据/技能凭据"分名单，另起一项，不并入本批。

### Q-020 setting() 运行期 SystemExit（M）→ D5
- 现状：`config/product.py:51-72` 类型不符即 `raise SystemExit`，而它在面板守护进程、研究驱动、TUI 运行中随时被读（全仓 29 处调用、27 个键）。三个进程入口（CLI、子代理 child、research node）都会先调 `cli/bootstrap.install()`。
- 修法（D5 建议）：
  1. `product.py` 增加 `KNOBS = {(section, key): (default, cast)}`，收录现有 27 个键；调用点可继续传默认值（有两处是动态默认：`network.max_concurrent_per_sister` 用 host 上限、ddgs 的 `http_timeout` 用请求超时），表里只登记类型；
  2. 新增 `validate_settings()`：按表检查 `settings.json`，收集全部错误，`bootstrap.install()` 调用它，有错就 `SystemExit` 并一次列全；
  3. 运行期 `setting()` 遇坏值：告警一次（按 section.key.value 去重，写 warnings log，不走 stderr）并返回默认值；
  4. 加一条棘轮测试：代码里出现的 `setting("x","y", …)` 必须在 `KNOBS` 里。
- 测试：坏值时启动拒绝并列出全部错误；运行中改坏文件，下一次读取返回默认值且只告警一次，进程不退出。

### Q-123 read/edit 不查文件类型、无上限（M，部分继承）→ D6
- 现状：`core/tools/read.py:93-98` 的 `access()` 直接 `open()`（FIFO 当场卡死；上游用的是 `access(R_OK)` 系统调用）；`read_bytes()` 整读；图片先做头部 mime 探测（同样会卡在 FIFO）。`edit.py:139-146` 的 `access()` 连开两次；中止时 `_drain_worker` 等线程结束且持有路径变更锁，所以 FIFO 上的 edit 按 Esc 也回不来。`edit_diff.py:568-581` 的 TUI 预览同理。
- 修法（D6 建议）：
  1. 三处的 `access` 改为：`os.stat`（跟随软链）后要求 `S_ISREG`，否则给模型明确的错误（"不是普通文件"）；权限检查用 `os.access`，与上游一致；这一步放在 mime 探测之前；
  2. `read` 文本路径改为流式：按行读取，只保留 offset/limit 与 `truncate_head` 需要的部分，同时计数总行数——内存有界，输出格式不变；
  3. 图片与 Office 渲染设字节上限（图片输入另设上限（如 50 MB；`image_resize.DEFAULT_MAX_BYTES` 是缩放后的输出目标，不是输入上限），Office 渲染另设一个），超出就给出说明而不读取；
  4. `edit` 保持"整读"语义（要应用编辑），加一个大小上限并在超出时拒绝。
- 测试：FIFO 上 `read`/`edit` 立即返回错误、无线程残留（复用本次审计的复现脚本）；`/dev/zero` 立即报"不是普通文件"；1 GB 稀疏文件带 offset/limit 读取时内存不随文件增长；正常文件输出与现在逐字一致（快照对比）。

---

## 顺序与工作量

- 第一批约半天：7 项都是几行到几十行，各带测试。
- 第二批约一天：Q-104 与 Q-114 改动面稍大（删表、改调用点）。
- 第三批取决于 D1–D6；Q-020 与 Q-086 各需半天，Q-123 的流式读取约半天。
- 每批单独提交；每项提交信息里写 `Q-xxx`，并在审计台账对应行标注"已修 + 提交号"。
