# PocketReader

PocketReader 是一个个人自用的“稍后收听”服务。它把文本、Markdown、文件、公开链接、AI 对话内容转成 MP3，并提供网页播放、离线缓存和私有 Podcast Feed，方便在 iPhone 上连续收听。

当前生产地址：

```text
https://reader.example.com
```

## 核心能力

- 在电脑或手机网页里导入普通文本和 Markdown。
- 一次上传多个 `.txt` / `.md` / `.markdown` 文件。
- 导入公开 URL，并对部分 AI share link 做专门解析。
- 通过 Chrome 扩展从已登录的 ChatGPT、Gemini、Claude 页面直接抓取当前对话。
- Chrome 扩展可把 AI 多回合对话拆成“每个回合一个独立音频”，并在标题前加 `[1/9]` 这类顺序编号。
- Chrome 扩展会把对话中可读取的 AI 生成文本文件、`.docx` 和带明确 Artifact 标记的 Claude Artifact 单独导入为音频条目，标题使用 `[文件]` 或 `[文件 1/2]` 前缀。
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
- 扩展 reload 后必须刷新已经打开的 AI 页面；否则页面里残留的旧 content script 可能显示 `Extension context invalidated`。
- 服务器保存 SQLite 数据库和 MP3 文件，目前没有自动清理策略。
- 生产服务器上还运行着 `sibling.example.com`，PocketReader 必须与它隔离部署。

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
  ai-handoff.md               给未来 AI Agent 的交接注意事项
tests/                        回归测试
```

## 本地开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
APP_USERNAME=admin \
APP_PASSWORD=CHANGE_ME \
APP_SECRET_KEY=dev-secret \
FEED_TOKEN=dev-feed-token \
IMPORT_TOKEN=dev-import-token \
APP_BASE_URL=http://127.0.0.1:4780 \
.venv/bin/uvicorn pocketreader.main:app --host 127.0.0.1 --port 4780
```

打开：

```text
http://127.0.0.1:4780
```

常用检查：

```bash
python -m unittest discover -s tests
python -m compileall pocketreader
node --check browser-extension/background.js
node --check browser-extension/content-script.js
node --check browser-extension/options.js
node tests/browser_extension_capture.test.js
```

## 生产部署概要

生产环境目录：

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

TTS 方案沿用 `../pte_speaking` 的方向：

- 使用 `edge-tts` 调用 Microsoft Edge TTS。
- 使用 `ffprobe` 检查每个 chunk 和最终 MP3 的时长。
- 使用 `ffmpeg` 合并多个 MP3 chunk。
- 默认 `TTS_MAX_CHARS_PER_CHUNK=1800`，显著低于免费 API 单次生成 10 分钟 MP3 的实用限制。
- 如果生成过程中进程被重启，启动时会自动把遗留的 `processing` 条目重新排队。

## 安全说明

- 不要提交 `/etc/apps/pocketreader/pocketreader.env`。
- 不要把服务器 root 密码写入仓库或文档。
- App 登录密码、`APP_SECRET_KEY`、`FEED_TOKEN`、`IMPORT_TOKEN` 都只放在服务器 env 文件中。
- `FEED_TOKEN` 保护 Podcast Feed 和 tokenized audio URLs。
- `IMPORT_TOKEN` 只给 Chrome 扩展导入接口使用。
- 更换 `FEED_TOKEN` 会让旧 feed 地址和旧音频 token URL 失效；普通重启不会失效。
