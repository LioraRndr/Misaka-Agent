<h1 align="center">
  <img src="assets/logo.svg" alt="" width="96" height="96"><br>
  MISAKA
</h1>

<p align="center"><strong>将 DAG 与症候阅读结合、挖掘多元叙事，专为人文社科研究打造的 AI Agent 架构。</strong></p>

<p align="center"><em>比在场更重要的是缺席！御坂御坂敲了敲你的脑袋。</em></p>

<p align="center">
  <a href="LICENSE"><img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/licence-Apache_2.0-blue"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="macOS, Linux and Windows" src="https://img.shields.io/badge/runs_on-macOS_%7C_Linux_%7C_Windows-555">
</p>

<p align="center"><a href="README.md">English</a> · 简体中文 · <a href="README.ja.md">日本語</a></p>

与协调者 **Last Order**（最后之作）一起拆解问题，完善研究计划，把研究的各个分支领域调查任务派发给善于报告-联络-讨论的 **Sisters**（妹妹们），将各位专家的调研报告汇总归纳，阅读和撰写，与评审员完成答辩，将结论无法涵盖的方向转化为新的研究。用图论算法来管理研究分支图，最终报告以研究论文的形式写进你的项目文件夹，每一处引用都可溯源。

<p align="center">
  <img src="assets/tui.png" alt="MISAKA 面板：左侧是空间、会话和 agent，右侧是 Last Order 的窗口" width="820">
</p>

<table>
<tr><td><b>材料没回来，不下结论</b></td><td>专家交回材料之前，Last Order 不替问题下结论，只把它拆成子问题和前提问题，理清它们之间怎样相互牵动。观点从材料里长出来；写最终报告时，她也只是把研究得出的论点编排成文，与主流相左的观点不会被磨平。</td></tr>
<tr><td><b>专家各持其术</b></td><td>每位 Sister 带着自己的专长、技能和模型钻研自己的领域：Claude、GPT、Gemini，或你本机上的模型；Claude Code 和 Codex 也能入队领任务卡。Last Order 不必操心工具怎么用，上下文都留给专家交上来的材料。不需思考手段，便可专精目的。</td></tr>
<tr><td><b>症候阅读</b></td><td>红队 Sister 核对事实、检查推理之外，还读 Last Order 的思考过程，找出结论没有说出口、却在暗中撑着论证的地方。随后的歧路审把这些缺席分开处理：这条线自己补得上的疏漏，就在本节点补齐；被它的前提挡在视野之外的方向，交给 Last Order 决定是否另开一项研究，不开也要写明理由。阿尔都塞在症候阅读里分辨过这两种“没看见”：一种是看漏了，一种是问题式根本不让你看见。</td></tr>
<tr><td><b>一张可能性的图</b></td><td>每个新方向都从 Last Order 的会话里分叉出去，带着此前全部的思考，成为一个有自己团队和红队的节点。图一层一层往下长：同一种可能只开一次，两条线都提出的问题只研究一次；殊途同归的线会汇合，能统合的统合，统合不了的把分歧划清。</td></tr>
<tr><td><b>问题本身也会问错</b></td><td>研究可以得出这样的结论：问题建立在概念混乱或意识形态预设之上，照原样问不下去。这是研究的正当结果；要改动的若是你提的问题，Last Order 会先征得你同意。</td></tr>
<tr><td><b>去翻常识之外的那部分</b></td><td>一问一答，模型给出的多半是它最常说的那一片。每份计划都附一张覆盖表，空着的格子就是事先声明的缺口；覆盖图取自各学科给自己文献编的分类目录，文献扫描能看出一个问题在学术史里的位置。</td></tr>
<tr><td><b>可溯源</b></td><td>引文追得到页：PageIndex 给长文档编出目录，agent 按章节读书、按印刷页码引用，还能查到一段引文在第几页；扫描件用中、英、日文做 OCR，DjVu 也读得了。记忆追得到原话：对话超出模型的容量时，无损上下文管理（LCM）把它压成摘要，每条摘要都能追回原文，项目里的所有 agent 检索同一份记忆。</td></tr>
<tr><td><b>有案可查</b></td><td>计划、任务卡、结论的每一版、批评和出处清单，都是项目里的 Markdown 文件，项目本身是一个 git 仓库。MISAKA 只在你要求、并且看过文件之后才提交；一个论证在批评下怎样一步步改变，都留在历史里。</td></tr>
<tr><td><b>你来掌舵</b></td><td>每份计划都等你点头，点头就是正常聊天。每个分支在面板里有自己的标签页，每个 agent 都在一个你随时能走进去的窗格里。研究可以停下，再接着跑。</td></tr>
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

一次研究，是一张由种种可能长成的图。你的问题是第一个节点，结论放下的每一种可能，一层层长成它下面的节点。

<p align="center">
  <img src="assets/research-graph.zh-CN.svg" alt="一次研究是一张图：你的问题；第 1 层是另一个假说、另一种方法和对问题本身的批判；第 2 层是其中一条放下的路、两条线都提出而只研究一次的问题，以及殊途同归的汇合；最后是报告" width="820">
</p>

1. **每个节点都是一项完整的研究。** Last Order 和你商量计划，你点头才开工。材料回来之前，她只拆问题、不下结论；Sisters 并行做任务卡，每条发现都记下出处，Last Order 读完再写结论。
2. **红队与歧路审。** 红队 Sister 核对事实、检查推理，读出结论没说出口的东西；再开一个新会话做歧路审，把结论放下的可能和留下的缺口分开。Last Order 在本节点逐条回应、补上缺口，改过的结论再交回复审。
3. **研究图一层层长出来。** 只有前提不同、真正的另一种可能，才会从 Last Order 的会话分叉成新节点，带着此前全部的思考，各有自己的 Last Order、Sisters 和红队，一直展开到你选定的深度。两条线都提出的问题只研究一次，同一种可能只开一次，殊途同归的线会汇合，在汇合处对质。
4. **报告。** 所有节点结束后，Last Order 通读全部节点，把研究得出的论点编排成一篇研究论文：有注释、参考文献，附录记下每一条研究线、答案承担的代价和没走的路。初稿先交独立红队审查，再由 Last Order 对每条异议作出裁决，写成终稿。

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

选 pi 作底座，是因为它的内核简单，又有成熟的社区在维护，能直接跟上上游的更新。MISAKA 的图管的是研究的内容和可能：节点是一项做完的研究，边是一次带着思考分叉出去的追问。

## 许可证

[Apache License 2.0](LICENSE)。第三方组件保留各自的许可证，记录在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

基于 MISAKA 再发布或改编时，请保留 [NOTICE](NOTICE) 里的署名：Apache-2.0 要求随发行物一并附上这份署名。

<p align="center"><em>以上，御坂网络通信结束，御坂御坂如此说道。</em></p>
