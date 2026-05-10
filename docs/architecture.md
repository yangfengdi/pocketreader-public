# 架构说明

## 总览

PocketReader 是一个小型自托管 FastAPI 应用。它故意避免前端构建系统，使用服务端渲染 HTML、少量原生 JS 和 CSS，降低维护成本。

```text
iPhone / Desktop Browser
        |
        | HTTPS
        v
Caddy: reader.example.com
        |
        | reverse_proxy 127.0.0.1:4780
        v
Docker container: FastAPI + background worker
        |
        +-- SQLite database
        +-- /var/lib/apps/pocketreader/audio 下的 MP3 文件
        +-- edge-tts outbound requests
        +-- ffmpeg / ffprobe
```

浏览器扩展导入链路：

```text
Chrome 中的 AI 网站
        |
        | content script 提取当前页面可见对话
        v
Chrome extension background.js
        |
        | POST /api/browser-capture
        | X-PocketReader-Import-Token: <IMPORT_TOKEN>
        v
PocketReader 后端创建普通 queued item
```

Podcast 链路：

```text
Podcast App
        |
        | GET /feed/<FEED_TOKEN>.xml
        v
RSS Feed
        |
        | enclosure url 指向 /audio/<id>.mp3?token=<FEED_TOKEN>
        v
GET / HEAD / Range GET audio file
```

## 运行组件

- `pocketreader.main`
  - FastAPI 路由。
  - 登录、退出。
  - 文本、文件、URL 导入表单。
  - Chrome 扩展导入 API。
  - 音频下载和 Podcast Feed。
  - 启动一个 background worker。
  - 启动时恢复中断的 `processing` 条目。

- `pocketreader.db`
  - SQLite schema。
  - `items`、`jobs`、`listen_events` 的读写。
  - 使用 `BEGIN IMMEDIATE` 抢占下一个 queued item，避免并发 worker 重复处理。
  - `requeue_interrupted_items()` 在进程启动时把遗留 `processing` 条目重新排队。

- `pocketreader.tts`
  - 按字符上限切分文本。
  - 调用 `edge_tts.Communicate`。
  - 每个 chunk 生成后用 `ffprobe` 校验时长。
  - 多 chunk 使用 `ffmpeg concat` 合并成最终 MP3。
  - 临时输出文件使用 `.mp3` 后缀并显式 `-f mp3`，避免 ffmpeg 无法判断 muxer。

- `pocketreader.importers`
  - 普通文本和 Markdown 清理。
  - URL 抓取和可读文本提取。
  - ChatGPT share page 的 React Router payload 解析。
  - Gemini / Claude share page 的错误识别。
  - Chrome 扩展消息 payload 标准化。

- `browser-extension`
  - Manifest V3 Chrome extension。
  - content script 注入“导入 PocketReader”按钮。
  - 分别对 ChatGPT、Gemini、Claude 写 DOM extractor。
  - background service worker 负责提交到 PocketReader 和打开 options page。

## 数据库

数据库路径：

```text
/var/lib/apps/pocketreader/pocketreader.sqlite3
```

主要表：

- `items`
  - 条目正文、标题、来源、声音、朗读范围。
  - 状态：`queued`、`processing`、`ready`、`error`。
  - 音频路径、时长、文本长度。
  - 播放进度和收听时间。

- `jobs`
  - TTS job 历史。
  - 状态包括 `queued`、`processing`、`done`、`error`、`interrupted`。
  - `interrupted` 表示进程停止时尚未完成，启动恢复机制已重新排队。

- `listen_events`
  - `play`、`pause`、`progress`、`seek`、`ended`。

## TTS 状态流

```text
create item
    |
    v
items.status = queued
jobs.status = queued
    |
    v
worker claim_next_item()
    |
    v
items.status = processing
jobs.status = processing
    |
    +--> success: items.status = ready, jobs.status = done
    |
    +--> exception: items.status = error, jobs.status = error
    |
    +--> process killed/restarted:
            startup requeue_interrupted_items()
            old job = interrupted
            new job = queued
```

这个机制用于处理部署、服务器重启、容器重建、TTS 中途失败等导致的半成品状态。

## 音频存储

每个条目有独立目录：

```text
/var/lib/apps/pocketreader/audio/<item_id>/audio.mp3
```

生成过程中的临时 chunk：

```text
/var/lib/apps/pocketreader/audio/<item_id>/chunks/
```

成功合并后会删除 `chunks/`。如果进程中断，下一次重新生成会先清理旧 `chunks/`。

## Podcast Feed 兼容性

Feed 路径：

```text
/feed/<FEED_TOKEN>.xml
```

音频路径：

```text
/audio/<item_id>.mp3?token=<FEED_TOKEN>
```

为了兼容 Apple Podcasts、Pocket Casts 等客户端：

- RSS 使用 `application/rss+xml; charset=utf-8`。
- channel 包含 `atom:link rel="self"`、`lastBuildDate`、`itunes:author`、`itunes:explicit`。
- item 包含 `guid isPermaLink="false"`、`pubDate`、`itunes:duration`。
- `pubDate` 和 `lastBuildDate` 使用 RFC 2822 格式。
- audio endpoint 支持 `GET`、`HEAD`、Range request。
- `HEAD` 返回 `Content-Type: audio/mpeg`、`Content-Length`、`Accept-Ranges: bytes`。

## 安全模型

- 单用户用户名/密码。
- session cookie 由 `APP_SECRET_KEY` 做 HMAC 签名。
- 音频文件需要有效登录 session 或正确 `FEED_TOKEN`。
- Chrome 扩展导入需要独立的 `IMPORT_TOKEN`。
- Docker 只发布 `127.0.0.1:4780`。
- Caddy 是唯一公网 HTTPS 入口。
- 不要把生产 env 文件提交到仓库。

