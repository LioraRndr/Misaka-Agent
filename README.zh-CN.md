<h1 align="center">
  <img src="assets/logo.svg" alt="" width="96" height="96"><br>
  MISAKA
</h1>

<p align="center"><strong>为人文社科研究组建的 AI 研究团队。</strong></p>

<p align="center"><em>每个结论都要过红队，出处就摆在它旁边，御坂如此报告。</em></p>

<p align="center">
  <a href="LICENSE"><img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/licence-Apache_2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS, Linux and Windows" src="https://img.shields.io/badge/runs_on-macOS_%7C_Linux_%7C_Windows-555">
</p>

<p align="center"><a href="README.md">English</a> · 简体中文 · <a href="README.ja.md">日本語</a></p>

你提出一个问题。协调者 **Last Order**（最后之作）和你一起定下研究计划，把各部分交给 **Sisters**（妹妹们），也就是由你创建的专家 agent。她们在你的终端里并行工作；每个结论都要经受红队的质疑，结论没有走的路会各自成为新的研究。最终报告以研究论文的形式写进你的项目文件夹，旁边就是它引用的每一份文件。

<p align="center">
  <img src="assets/tui.png" alt="MISAKA 面板：左侧是空间、会话和 agent，右侧是 Last Order 的窗口" width="820">
</p>

<table>
<tr><td><b>经得起红队的结论</b></td><td>每个结论都要面对一位红队 Sister 的质疑。Last Order 逐条作答并留有记录：修改结论、反驳异议，或承认这是答案要承担的代价。</td></tr>
<tr><td><b>没走的路，也去走一遍</b></td><td>结论放下的假说、方法和读法会成为新的研究，各有自己的团队和红队。两条线都提出的问题只研究一次，殊途同归的线会汇合。</td></tr>
<tr><td><b>打得开的证据</b></td><td>每条发现都写明出处和页码。每个结论旁边就放着它引用的文件，agent 能查到一段引文在第几页。</td></tr>
<tr><td><b>论断各归其类</b></td><td>事实、推断、诠释和价值判断各自申明。证据分不出高下时，相互竞争的结论并列保留。</td></tr>
<tr><td><b>按章读书，按页引用</b></td><td>PageIndex 为长文档生成目录，agent 按章节读一本书、按印刷页码引用，并能查到一段引文在第几页。扫描件用英文、中文和日文做 OCR，DjVu 也不例外；文献扫描能看出一个问题在学术史中的位置。</td></tr>
<tr><td><b>不丢一字的记忆</b></td><td>对话超出模型的容量时，无损上下文管理（LCM）会把它摘要，而每条摘要都能追回到原话。项目里的每个 agent 检索的是同一份记忆，按语义回忆可以只用本机的小模型。</td></tr>
<tr><td><b>可以审计的研究记录</b></td><td>计划、任务卡、结论的每一个版本、批评和出处清单都是项目里的 Markdown 文件，项目本身是一个 git 仓库。MISAKA 只在你要求并看过文件后才提交，一个论证在批评下怎样改变，都留在记录里。</td></tr>
<tr><td><b>不同头脑组成的团队</b></td><td>每位 Sister 都有自己的专长、技能和模型：Claude、GPT、Gemini，或你本机上的模型。Claude Code 和 Codex 也能作为队员加入，像 Sister 一样领任务卡。</td></tr>
<tr><td><b>由你掌舵的研究</b></td><td>每份计划都等你点头，点头就是正常聊天。每个分支在面板里有自己的标签页，每个 agent 都在一个你随时能进去的窗格里。研究可以停下，再接着跑。</td></tr>
</table>

## 快速开始

```sh
uv tool install "misaka[providers] @ git+https://github.com/Luciole-Studio/Misaka-Agent.git"

mkdir my-research
cd my-research
misaka setup     # 登录、选模型、创建最初的两位 Sister
misaka           # 打开 MISAKA，输入 /research
```

需要 macOS、Linux 或 Windows（x86_64 或 arm64），装好 [uv](https://docs.astral.sh/uv/)、git、[ripgrep](https://github.com/BurntSushi/ripgrep)、[fd](https://github.com/sharkdp/fd) 和 poppler，以及一个模型服务商：API 密钥，或 ChatGPT、GitHub Copilot 的订阅。Claude 账号也能登录，这部分用量由 Anthropic 按 token 另计为额外用量。请从本仓库安装：PyPI 上的 `misaka` 是另一个无关的项目。

[入门指南](docs/getting-started.zh-CN.md)会一步步带你装好，并跑通第一个研究问题。

## 一次研究怎么进行

> *计划写好啦！只要你点头，御坂御坂马上开工！御坂御坂双手捧着计划书说道。*

一次研究是一张由各种可能组成的图。你的问题是第一个节点，结论放下的可能一层一层成为它下面的节点。

<p align="center">
  <img src="assets/research-graph.zh-CN.svg" alt="一次研究是一张图：你的问题；第 1 层是另一个假说、另一种方法和对问题本身的批判；第 2 层是其中一条放下的路、两条线都提出而只研究一次的问题，以及殊途同归的汇合；最后是报告" width="820">
</p>

1. **每个节点都是一项完整的研究。** Last Order 和你商量计划，你同意后才开工。Sisters 并行处理任务卡，每条发现都记下出处，最后由 Last Order 写出结论。
2. **红队审查。** 红队 Sister 质疑结论，再读一遍，找出它放下的可能和留下的缺口。Last Order 在本节点内逐条回应、补上缺口；修改后的结论再交回复审。
3. **研究图一层层长出来。** 只有前提不同的真正另一种可能，才会开成新节点，各有自己的 Last Order、Sisters 和红队，一层一层展开到你选定的深度。两条线都提出的问题只研究一次，同一个可能只开一次，殊途同归的线会汇合，并在汇合处相互对质。
4. **报告。** 所有节点都结束后，Last Order 通读全部节点，把答案写成一篇研究论文：有注释、参考文献，附录记下每一条研究线索、答案承担的代价和没有走的路。草稿交独立红队审查，Last Order 再在最终报告里对每一条异议作出裁决。

深度、并发、跟进和恢复研究，见[研究指南](docs/guide/research.md)（英文）。

## 你会得到什么

> *引用的每一份材料都已归档，随时可以核查，御坂如此报告。*

所有产出都写进你的项目文件夹：

```text
my-research/
├── final/<run>-final.md     最终报告，连同它承担的代价和没有走的路
├── final/<run>-sources/     报告引用的每一个文件，链接在原处
└── nodes/<node>/            每一项研究
    ├── plan.md              Last Order 的计划，以及为什么选这几位 Sister
    ├── cards/<card>/        每位 Sister 的工作成果，以及红队的批评
    ├── synthesis.md         结论（修改后是 synthesis-2.md）
    └── SOURCES.md           结论引用的每个文件，以及哪些论断以它为依据
```

MISAKA 只在你要求时提交。如果项目是 git 仓库，用 `/commit` 提交，提交前你会先看到文件并确认。

## 常用命令

| 想要 | 输入 |
|---|---|
| 打开 MISAKA | `misaka` |
| 开始一次研究 | `/research`，然后输入你的问题 |
| 查看、停止或恢复研究 | `/research status`、`/research stop`、`/research resume` |
| 单独和一位 Sister 对话 | `/sister 10032` |
| 创建一位 Sister | `misaka create 10036 --desc "实证计量与因果识别"` |
| 索引你的文档 | `misaka doc scan sources/` |
| 选模型、登录 | `/model`、`/login` |
| 查看全部命令 | 对话里输入 `/`，终端里用 `misaka --help` |
| 查看面板的按键 | 先按 `ctrl+b`，再按 `?`（[面板指南](docs/guide/panel.md)） |
| 更新 | `misaka update --apply` |

完整列表见[命令参考](docs/reference/commands.md)（英文）。

## 文档

| 想要 | 阅读 |
|---|---|
| 安装并跑通第一个问题 | [入门指南](docs/getting-started.zh-CN.md) |
| 运行和引导研究 | [研究指南](docs/guide/research.md) |
| 组建团队，加入 Claude Code 或 Codex | [团队指南](docs/guide/team.md) |
| 熟悉面板：标签页、窗格、按键 | [面板指南](docs/guide/panel.md) |
| 登录、选模型、接本地模型 | [模型指南](docs/guide/models.md) |
| 使用你的文档和网络 | [文档与网络](docs/guide/sources.md) |
| 解决问题 | [排障](docs/guide/troubleshooting.md) |
| 查命令或设置 | [命令](docs/reference/commands.md)、[配置](docs/reference/configuration.md) |

[docs/README.md](docs/README.md) 是全部文档的地图，还解释了 MISAKA 用到的各个词。除入门指南外，以上文档目前只有英文版。

## 你的数据与费用

MISAKA 保存的一切都在你自己的机器上：设置、凭据和历史在 `~/.misaka/`，研究产出在你的项目文件夹。提示词只发给你配置的模型服务商。网页搜索发给你配置的搜索服务；没有配置、或配置的服务出错时，改用 Exa、Parallel、Firecrawl 和 Keenable 的免费公共接口（用 `misaka web set keyless_fallback false` 关闭）。文献扫描会把问题的检索词发给 OpenAlex。MISAKA 不发送任何遥测数据。

一次研究会铺得很开：默认最多同时跑四个分支，每个分支最多四位 Sister 同时工作（以机器内存允许为限），所以一次深度研究会发出大量模型调用。想省钱就选小一点的深度；想给所有研究设一个硬上限，在 `~/.misaka/settings.json` 里设置 `research.token_cap`。

## 名字的由来

MISAKA 的名字取自镰池和马的《魔法禁书目录》和《某科学的超电磁炮》。在原作里，妹妹们（Sisters）是「超电磁炮」御坂美琴的克隆体，通过御坂网络共享记忆。

| 原作 | MISAKA |
|---|---|
| **御坂美琴**，所有妹妹的本体 | `MISAKA.md`：每个 agent 在读自己的设定之前，都会先读这份共同身份 |
| **妹妹们**，以编号相称：御坂 10032 号、10033 号…… | 你的专家们，每人有编号、专长和自己的 `SOUL.md` |
| **最后之作**（Last Order），御坂 20001 号，御坂网络的司令塔 | 你与之对话的协调者 |
| **御坂网络**，一位妹妹学到的，其他妹妹也能想起来 | 项目里的对话，其中每个 agent 都能检索 |

本文里那些「御坂如此说道」只是点缀；你的 agent 怎么说话，取决于她们各自的 `SOUL.md`。想让她们也这样说话，在 `SOUL.md` 里加一句就行。

MISAKA 是独立项目，与原作作者及出版方没有任何关联，也未获其认可。

## 基于

MISAKA 的 agent 内核是 [pi](https://github.com/earendil-works/pi) 的 Python 移植，面板移植自 [herdr](https://github.com/herdrdev/herdr)，每个窗格背后是 [ghostty](https://github.com/ghostty-org/ghostty) 的终端库。长对话管理基于 [hermes-lcm](https://github.com/stephenschoettler/hermes-lcm)，文档结构基于 [PageIndex](https://github.com/VectifyAI/PageIndex)；网页工具和技能移植自 [Hermes Agent](https://github.com/NousResearch/hermes-agent)，Office 支持移植自 [FrontierAgent](https://github.com/ApodexAI/FrontierAgent)。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 记录了每一部分的来源。

## 许可证

[Apache License 2.0](LICENSE)。第三方组件保留各自的许可证，记录在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

基于 MISAKA 再发布或改编时，请保留 [NOTICE](NOTICE) 里的署名：Apache-2.0 要求随发行物一并附上这份署名。

<p align="center"><em>以上，御坂网络通信结束，御坂御坂如此说道。</em></p>
