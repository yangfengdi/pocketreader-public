# AI Agent 交接说明

这份文件记录当前项目的关键上下文。未来如果换成另一个编程 Agent，即使没有原始对话记录，也应先阅读本文件和同目录下其他文档，再进行修改或部署。

## 项目目标

PocketReader 是一个个人自用的文本转语音收听系统。核心体验是：

- 电脑上方便导入文本、文件、链接和 AI 对话。
- 手机上方便听、暂停、继续、听下一条。
- 通过私有 Podcast Feed 让 Podcast App 下载和播放。
- 通过 Chrome 扩展从 ChatGPT / Gemini / Claude 当前页面导入对话。

## 生产服务器现状

同一台服务器上已经运行 `other_app` / other-app：

```text
Domain: sibling.example.com
Host: 203.0.113.10
Paths:
  /opt/other-app
  /var/lib/other-app
  /etc/other-app
  /var/log/other-app
Systemd:
  other-app-update.service
  other-app-update.timer
  other-app-trigger.service
```

PocketReader 不得修改这些路径或 systemd 服务。

## Caddy 协议

Caddy 已经是多应用结构：

```text
/etc/caddy/Caddyfile
/etc/caddy/apps/other-app.caddy
/etc/caddy/apps/pocketreader.caddy
```

PocketReader 只维护：

```text
/etc/caddy/apps/pocketreader.caddy
```

不要修改：

```text
/etc/caddy/Caddyfile
/etc/caddy/apps/other-app.caddy
```

修改 PocketReader snippet 后必须执行：

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
curl -I https://sibling.example.com/
curl -I https://reader.example.com/
```

如果 Caddy validation 失败，回滚方式：

```bash
mv /etc/caddy/apps/pocketreader.caddy \
  /etc/caddy/apps/pocketreader.caddy.disabled
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

## PocketReader 拥有的路径

```text
/opt/apps/pocketreader
/var/lib/apps/pocketreader
/etc/apps/pocketreader
/var/log/apps/pocketreader
/etc/caddy/apps/pocketreader.caddy
```

Docker Compose 发布端口：

```text
127.0.0.1:4780:4780
```

容器内部 uvicorn 监听 `0.0.0.0`，但宿主机只暴露 loopback，由 Caddy 代理公网 HTTPS。

## 重要 token

生产 env 文件：

```text
/etc/apps/pocketreader/pocketreader.env
```

重要变量：

- `APP_USERNAME` / `APP_PASSWORD`：网页登录。
- `APP_SECRET_KEY`：签名 session cookie。
- `FEED_TOKEN`：保护 RSS Feed 和音频 URL。
- `IMPORT_TOKEN`：保护 Chrome 扩展导入接口。

不要把真实 token 写入仓库。

`FEED_TOKEN` 与 `IMPORT_TOKEN` 不要混用：

- 更换 `FEED_TOKEN` 会让旧 Podcast Feed 和音频 URL 失效。
- 更换 `IMPORT_TOKEN` 只会让旧扩展提交失效。
- 正常重启不会改变任何 token，除非 env 文件被修改。

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

## 当前生产验证过的行为

最近一次部署后验证过：

- `/health` 返回 `{"status":"ok"}`。
- `https://reader.example.com/` 未登录时返回 `303 /login`。
- `https://sibling.example.com/` 仍返回原来的 `401`。
- 音频 `HEAD` 返回 `200`。
- 音频 Range GET 返回 `206`。
- item 18 曾因部署中断停在 `processing`，已被自动恢复并生成完成。

## GitHub 状态注意

本地开发机曾出现访问 `github.com:443` 超时，导致生产已经通过本地 archive 部署，但本地 git 可能显示：

```text
main...origin/main [ahead N]
```

未来 Agent 接手时应先运行：

```bash
git status --short --branch
git log --oneline -8
```

如果本地仍 ahead，且网络恢复，应补：

```bash
git push origin main
```

不要因为远端落后就回退本地提交；生产可能已经运行本地 ahead 的版本。

## 修改前建议阅读顺序

1. `README.md`
2. `docs/requirements.md`
3. `docs/architecture.md`
4. `docs/deployment.md`
5. `docs/operations.md`
6. `docs/browser-extension.md`
7. `docs/ai-capture-design.md`
8. `docs/markdown-speech.md`
9. 本文件

改代码前运行测试；部署前确认不会触碰 other-app/other-app。
