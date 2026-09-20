# AI Agent 交接说明

这份文件记录当前项目的关键上下文。未来如果换成另一个编程 Agent，即使没有原始对话记录，也应先阅读本文件和同目录下其他文档，再进行修改或部署。

## 项目目标

PocketReader 是一个个人自用的文本转语音收听系统。核心体验是：

- 电脑上方便导入文本、文件、链接和 AI 对话。
- 手机上方便听、暂停、继续、听下一条。
- 通过私有 Podcast Feed 让 Podcast App 下载和播放。
- 通过 Chrome 扩展从 ChatGPT / Gemini / Claude 当前页面导入对话。

## 新维护者的起点

先读仓库根目录 `AGENTS.md`、`docs/getting-started.md` 和 `docs/configuration.md`。项目运行不依赖原作者的账号、服务器、其他目录或以前的聊天记录。默认建立自己的实例。

现有实例维护时，用 `git config --get pocketreader.privateDir` 查找本机私有 runbook。那里保存真实地址、SSH 方式、凭证位置、其他应用的保护规则和历史备份。不要把这些内容复制回公开代码、文档、issue 或 PR。

公开部署方法见 `docs/deployment.md`。一个应用进程对应一个 worker；env 持久保存在仓库外。正常重启不轮换 token。首次生成使用 `scripts/init_env.py`，已有实例不能通过覆盖 env 来“修复”启动。

## 已实现的重要机制

- ChatGPT share link 解析：
  - `pocketreader/importers.py`
  - 解析 React Router stream payload。
  - 默认只朗读 AI 回复。

- Gemini / Claude 导入：
  - share link 后端抓取不可靠。
  - 推荐 Chrome 扩展导入当前登录页面。

- Chrome 扩展：
  - 目录：`browser-extension/`
  - 配置页：`options.html`
  - 解析接口：`POST /api/browser-snapshot`
  - 创建接口：`POST /api/browser-snapshot/<capture_id>/create`
  - 旧兼容接口：`POST /api/browser-capture`
  - 登录后的服务器帮助页：`/extension`
  - 支持 ChatGPT、Gemini、Claude 当前页面导入。
  - 架构是“扩展采集候选 DOM blocks，后端保存 raw snapshot 并解析”。
  - 原始快照保存在 `browser_captures`，解析结果保存在 `browser_parse_runs`。
  - 默认朗读“问题和 AI 回复”。
  - 可选“每个回合生成一个独立音频”。
  - ChatGPT 当前页面导入默认按回合拆分，和 Claude 一样生成带编号标题；ChatGPT share link URL 导入仍是单条音频。
  - 拆分标题使用 `[问&答 001]` 或 `[AI答 001]`，同时显示朗读范围和当前回合序号，不再包含回合总数。
  - 同一 AI 会话重复导入时，按 `platform + source_url + reader_mode + turn_index` 做增量创建；同一范围已有非错误状态回合跳过，只创建新增回合。`问&答` 与 `AI答` 是可并存的两个系列。
  - `items.turn_index` 是回合身份字段；旧标题如 `[001]` 或 `[1/2]` 会在相应会话下一次导入时根据原有 `reader_mode` 升级标题并补写该字段。
  - 可读取的 AI 生成文件会被单独导入，标题前缀为 `[文件]` 或 `[文件 1/2]`；Claude Artifact 必须有明确 Artifact DOM 标记，不能靠右侧大块文本猜测。
  - Claude Markdown 小标题，例如 `**艺术与品味**` 渲染成短段落、单独 `strong` / `b`、或“只有一个加粗节点的段落”时，也属于 AI 正文，扩展需要采集；不要因为文本少于 20 字就过滤掉这类结构文本。
  - 扩展 reload 后必须刷新已打开的 AI 页面，否则旧 content script 会报 `Extension context invalidated`。
  - AI 平台解析规则见 `docs/ai-capture-design.md`；不要用宽泛 selector 临时修 Claude，否则容易误抓重复消息或把正文误判为文件。

- Markdown 朗读转换：
  - 规则见 `docs/markdown-speech.md`。
  - 核心原则是“去符号、保正文”：`#`、`**`、表格竖线、链接 URL、代码围栏等格式符号可以去掉，但标题文字、加粗正文、表格单元格、链接显示文字、代码块正文不能被删除。

- TTS：
  - `edge-tts`
  - `ffmpeg`
  - `ffprobe`
  - 默认 chunk 字符上限 1800。

- 中断恢复：
  - 启动时执行 `db.requeue_interrupted_items()`。
  - 遗留 `processing` 条目会变回 `queued`。
  - 旧 job 标记为 `interrupted`。
  - 新 job 继续生成。

- Podcast 兼容：
  - audio endpoint 支持 `HEAD` 和 Range GET。
  - RSS 含 `atom:link`、`lastBuildDate`、`itunes:duration`、`guid isPermaLink=false`。
  - 这是为了兼容 Apple Podcasts 和 Pocket Casts。

## 接手时需要重新验证

- 检查 `git status --short --branch`、远端和已有修改，不假定 GitHub 或生产一定是最新版本。
- 安装依赖并运行 Python 与扩展测试，再做本地浏览器验收。
- `/health`、登录、短文本生成、播放、音频 HEAD/Range 和自己的 Podcast 订阅分别验证。
- 修改扩展后 reload 并刷新已打开的 AI 页面，确认当前平台 DOM 仍可解析。
- 测试数据必须合成；数据库、原始对话和音频不随源码分发。
- SQLite schema 在 `Database.init()` 中维护；变更要验证旧库兼容和回滚。
- 当前没有完整多用户权限、分布式任务领取、自动存储清理或外部 TTS 服务保证。

## 阅读顺序与修改地图

1. `README.md`、`AGENTS.md`、`docs/getting-started.md`
2. `docs/requirements.md`、`docs/architecture.md`
3. UI 改动：`templates/`、`static/`、`main.py`
4. 导入改动：`importers.py`、`browser_snapshot.py`、`browser-extension/`，先读 `docs/ai-capture-design.md`
5. TTS 改动：`tts.py`、`text.py`，先读 `docs/markdown-speech.md`
6. 部署改动：`docs/configuration.md`、`docs/deployment.md`、`docs/operations.md`
7. 提交与公开：`CONTRIBUTING.md`、`SECURITY.md`、`docs/open-source-release.md`

面向新维护者的可复制 AI 任务示例见上手指南。每次交付说明行为变化、测试和限制；不要把某台生产机器的历史验证结果当作其他实例的保证。
