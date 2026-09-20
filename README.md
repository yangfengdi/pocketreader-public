# PocketReader

PocketReader 是一个个人自用的“稍后收听”服务。它把文本、Markdown、文件、公开链接、AI 对话内容转成 MP3，并提供网页播放、离线缓存和私有 Podcast Feed，方便在 iPhone 上连续收听。

代码采用 [MIT 许可证](LICENSE)，可以 fork 后自己修改，也可以交给 AI 编程助手继续开发。每个使用者配置自己的实例、服务器和凭证，项目没有公共托管服务或通用登录账号。

| 你想做什么 | 先读哪里 |
| --- | --- |
| 第一次运行、接手父辈或他人的代码 | [上手指南](docs/getting-started.md) |
| 让 AI 修改功能 | [AGENTS.md](AGENTS.md)、[AI 交接](docs/ai-handoff.md)、[贡献说明](CONTRIBUTING.md) |
| 部署自己的实例 | [部署说明](docs/deployment.md)、[配置表](docs/configuration.md) |
| 备份、更新和排障 | [运维说明](docs/operations.md) |
| 公开自己的 fork | [安全与隐私](SECURITY.md)、[发布检查](docs/open-source-release.md) |

## 核心能力

- 在电脑或手机网页里导入普通文本和 Markdown。
- 一次上传多个 `.txt` / `.md` / `.markdown` 文件。
- 导入公开 URL，并对部分 AI share link 做专门解析。
- 通过 Chrome 扩展从已登录的 ChatGPT、Gemini、Claude 页面采集当前对话快照，后端保存原始快照并解析。
- Chrome 扩展可把 AI 多回合对话拆成“每个回合一个独立音频”；标题使用 `[问&答 001]` 或 `[AI答 001]`，直接标明朗读范围和当前回合序号。ChatGPT 当前页面导入默认也走这套编号拆分逻辑，和 Claude 保持一致。
- 同一个 AI 对话以相同朗读范围再次导入时，已存在的回合会被跳过，只为新增回合创建音频；切换朗读范围会生成另一套可并存的音频。
- Chrome 扩展会把对话中可读取的 AI 生成文本文件、`.docx` 和带明确 Artifact 标记的 Claude Artifact 单独导入为音频条目，标题使用 `[文件]` 或 `[文件 1/2]` 前缀。
- Markdown 转朗读时只删除格式符号，保留标题、加粗正文、表格单元格、链接显示文字、代码块正文等实际内容。
- 在网页 UI 中选择多个 TTS 声音。
- 长文本会被切分成安全长度的小段，逐段生成 MP3，再合并成单个音频文件。
- 保存条目的创建时间、生成时间、首次收听、最近收听、完成时间和播放进度。
- 支持 iPhone 网页播放、暂停、继续、倍速、后退/前进 15 秒、自动进入下一条。
- 支持在条目页缓存单个音频，便于离线收听。
- 暴露私有 Podcast RSS Feed，使用长随机 token 保护。

## 当前产品决策

- 第一版是 Web/PWA，不做原生 iOS App。
- 单用户自用，用户名/密码登录即可。
- Chrome 扩展导入 AI 对话时默认朗读“问题和 AI 回复”，也可以选择只读 AI 回复。
- ChatGPT share link 保持单条音频导入模式。
- ChatGPT share link 保留后端解析能力。
- Gemini / Claude 的 share 页面经常不把正文返回给服务器，更推荐使用 Chrome 扩展在浏览器里抓取已登录页面正文。
- AI 页面导入采用“扩展采集、后端解析”：原始快照保存在 `browser_captures`，解析记录保存在 `browser_parse_runs`，方便后续调试和重新解析。
- 扩展 reload 后必须刷新已经打开的 AI 页面；否则页面里残留的旧 content script 可能显示 `Extension context invalidated`。
- 服务器保存 SQLite 数据库和 MP3 文件，目前没有自动清理策略。
- 每个安装者独立部署；共用服务器的隔离规则只记录在本地私有 runbook 中。

## 仓库结构

```text
pocketreader/                 FastAPI 应用包
  main.py                     HTTP 路由、worker 生命周期、Podcast Feed
  db.py                       SQLite schema 和数据访问
  tts.py                      edge-tts 生成、切分、ffmpeg 合并
  importers.py                文本、Markdown、URL、AI link、浏览器捕获内容导入
  text.py                     文本清理和 TTS 切分工具
  templates/                  服务端渲染 HTML
  static/                     CSS、JS、PWA manifest、service worker
browser-extension/            Chrome 扩展，用于 AI 页面内一键导入
deploy/
  pocketreader.caddy          生产 Caddy snippet
  pocketreader.env.example    环境变量模板
docs/
  requirements.md             需求和使用场景
  architecture.md             架构、数据流和关键机制
  deployment.md               部署、更新和回滚
  operations.md               日常运维、排障和 token 管理
  browser-extension.md        Chrome 扩展安装和维护
  ai-capture-design.md        AI 对话解析规则和稳定性约束
  markdown-speech.md          Markdown 朗读转换规则
  ai-handoff.md               给未来 AI Agent 的交接注意事项
tests/                        回归测试
```

## 本地开发

需要 Python 3.12+、ffmpeg（含 ffprobe）；Node.js 用于扩展测试。Docker 的基准版本是 Python 3.12，没有 npm 构建步骤。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
python3 scripts/init_env.py
sh scripts/install_hooks.sh
.venv/bin/uvicorn pocketreader.main:app --env-file .env --host 127.0.0.1 --port 4780 --workers 1
```

打开 <http://127.0.0.1:4780>。账号和随机密码在本地 `.env` 中，用编辑器在本机查看；不要把内容粘贴到 issue 或截图中。该文件被 Git 忽略。初始化脚本不会覆盖已有配置，也不会打印密码。

先导入一小段不敏感的文本，确认生成并播放正常。网页能打开不代表外部 TTS 服务一定可用。

```bash
.venv/bin/python -m unittest discover -s tests
node tests/browser_extension_capture.test.js
node tests/browser_extension_settings.test.js
python3 scripts/check_public_content.py
```

## 生产部署概要

Compose 默认目录（不是作者服务器的访问授权）：

```text
/opt/apps/pocketreader
/var/lib/apps/pocketreader
/etc/apps/pocketreader
/var/log/apps/pocketreader
```

Docker 只在宿主机 loopback 暴露后端：

```text
127.0.0.1:4780
```

公网 HTTPS 由 Caddy 反向代理：

```text
/etc/caddy/apps/pocketreader.caddy
```

完整部署和回滚流程见 [docs/deployment.md](docs/deployment.md)。

## TTS 实现说明

本项目运行不依赖作者的其他仓库：

- 使用 `edge-tts` 调用 Microsoft Edge TTS。
- 使用 `ffprobe` 检查每个 chunk 和最终 MP3 的时长。
- 使用 `ffmpeg` 合并多个 MP3 chunk。
- 默认 `TTS_MAX_CHARS_PER_CHUNK=1800`，降低长文单次请求失败的风险。
- 如果生成过程中进程被重启，启动时会自动把遗留的 `processing` 条目重新排队。

## 安全说明

- 不要提交 `/etc/apps/pocketreader/pocketreader.env`。
- 不要把服务器 root 密码写入仓库或文档。
- App 登录密码、`APP_SECRET_KEY`、`FEED_TOKEN`、`IMPORT_TOKEN` 都只放在服务器 env 文件中。
- `FEED_TOKEN` 保护 Podcast Feed 和 tokenized audio URLs。
- `IMPORT_TOKEN` 只给 Chrome 扩展导入接口使用。
- 更换 `FEED_TOKEN` 会让旧 feed 地址和旧音频 token URL 失效；普通重启不会失效。

## 现有实例升级注意

现在必须显式设置 `APP_PASSWORD`、`APP_SECRET_KEY`、`FEED_TOKEN`、`IMPORT_TOKEN`。缺失或模板占位值会使启动失败；不再提供固定默认密码或启动时临时生成的 token。升级前检查私有 env，保留现有有效 token，避免订阅和扩展失效。

扩展不再内置作者的域名，默认使用本地地址。已有扩展设置保留；自定义 HTTPS 实例在设置页点“保存”时授权该域名，然后刷新 AI 页面。

本项目是单用户个人工具，没有公开注册、多租户或分布式任务队列。`edge-tts` 会把待朗读文本发送给 Microsoft Edge TTS，不是完全离线语音引擎，也没有第三方服务可用性承诺。其他限制见 [SECURITY.md](SECURITY.md)。

## 自动检查

本地 Git hooks 检查提交和推送内容。GitHub Actions 以[待启用模板](docs/ci.md)提供，尚未启用；拥有工作流权限后可按说明开启。
