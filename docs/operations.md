# 运维说明

## 常用命令

```bash
cd /opt/apps/pocketreader
docker compose ps
docker compose logs -f --tail=100
docker compose restart
curl -fsS http://127.0.0.1:4780/health
```

查看数据库：

```bash
sqlite3 /var/lib/apps/pocketreader/pocketreader.sqlite3
```

如果宿主机没有 `sqlite3`，可以用 Python：

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("/var/lib/apps/pocketreader/pocketreader.sqlite3")
conn.row_factory = sqlite3.Row
for row in conn.execute("select id,title,status,created_at,updated_at from items order by id desc limit 10"):
    print(dict(row))
PY
```

## 修改登录密码

编辑：

```text
/etc/apps/pocketreader/pocketreader.env
```

修改：

```text
APP_PASSWORD=<new-password>
```

然后重启容器：

```bash
cd /opt/apps/pocketreader
docker compose up -d
```

已有 session cookie 在过期前可能继续有效。若要强制所有会话失效，同时更换 `APP_SECRET_KEY`。

## 轮换 FEED_TOKEN

`FEED_TOKEN` 用于私有 Podcast Feed 和音频 URL：

```text
/feed/<FEED_TOKEN>.xml
/audio/<item_id>.mp3?token=<FEED_TOKEN>
```

编辑 env 文件中的 `FEED_TOKEN` 后重启：

```bash
cd /opt/apps/pocketreader
docker compose up -d
```

旧 feed 地址和旧 tokenized audio URL 会失效。普通重启不会改变 feed 地址，只要 env 文件里的 `FEED_TOKEN` 没变。

## 轮换 IMPORT_TOKEN

`IMPORT_TOKEN` 只用于 Chrome 扩展导入：

```text
POST /api/browser-snapshot
POST /api/browser-snapshot/<capture_id>/create
X-PocketReader-Import-Token: <IMPORT_TOKEN>
```

编辑 env 文件中的 `IMPORT_TOKEN` 后重启：

```bash
cd /opt/apps/pocketreader
docker compose up -d
```

然后在 Chrome 扩展设置页更新 token。更换 `IMPORT_TOKEN` 不影响 Podcast Feed。

## 备份

至少备份：

```text
/var/lib/apps/pocketreader/pocketreader.sqlite3
/var/lib/apps/pocketreader/audio
/etc/apps/pocketreader/pocketreader.env
```

示例：

```bash
tar -czf /root/pocketreader-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  /var/lib/apps/pocketreader \
  /etc/apps/pocketreader/pocketreader.env
```

## 存储

查看空间：

```bash
du -sh /var/lib/apps/pocketreader
du -sh /var/lib/apps/pocketreader/audio
df -h /
```

当前版本不会自动删除音频。通过 UI 删除条目会删除数据库记录和对应音频目录。

## 日志

应用日志：

```bash
cd /opt/apps/pocketreader
docker compose logs --tail=200
docker compose logs -f --tail=100
```

Caddy 日志使用服务器现有 Caddy 行为。PocketReader snippet 没有单独配置 Caddy log file，因为生产服务器的 Caddy systemd sandbox 曾拒绝新增日志文件路径。

## 处理中断恢复

如果部署、重启或崩溃发生在 TTS 生成中，条目可能停在 `processing`。现在应用启动时会自动执行：

```text
db.requeue_interrupted_items()
```

行为：

- 找出所有 `items.status = 'processing'`。
- 把旧未完成 job 标记为 `interrupted`。
- 把 item 状态改回 `queued`。
- 插入新的 queued job。
- worker 自动重新生成。

手动检查：

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("/var/lib/apps/pocketreader/pocketreader.sqlite3")
conn.row_factory = sqlite3.Row
for row in conn.execute("select id,title,status,updated_at from items where status in ('queued','processing') order by id"):
    print(dict(row))
PY
```

如果需要手动重试某个失败条目，打开条目页点击“重新生成”。

## TTS 常见问题

如果错误包含：

```text
Unable to choose an output format
```

检查 `pocketreader/tts.py`：

- 合并临时文件必须保留 `.mp3` 后缀。
- ffmpeg 命令应显式指定 `-f mp3`。

相关测试：

```bash
python -m unittest tests.test_tts
```

## AI Share Link 导入

PocketReader 对 AI share link 有平台专门处理。

- ChatGPT：
  - 从分享页嵌入的 React Router conversation payload 中解析。
  - 跳过 system、tool、thought、code 等记录。
  - 保留 user 和 assistant 文本。
  - 默认 UI 模式只朗读 assistant。

- Gemini：
  - 服务器请求分享页时可能只拿到登录壳，没有正文。
  - 这种情况会创建错误条目并给出明确错误。
  - 推荐使用 Chrome 扩展导入当前登录页面。

- Claude：
  - 服务器请求可能遇到区域限制或 Cloudflare challenge。
  - 这种情况会明确报错。
  - 推荐使用 Chrome 扩展导入当前登录页面。

## Chrome 扩展导入

扩展目录：

```text
browser-extension
```

登录 PocketReader 后可打开：

```text
https://reader.example.com/extension
```

页面会显示扩展需要填写的：

```text
PocketReader 地址
IMPORT_TOKEN
```

扩展面板打开后会先把当前页面快照提交到后端解析。后端会保存原始快照到 `browser_captures`，并把解析结果写入 `browser_parse_runs`。面板状态里会显示消息数、回合数、文件数和 warnings。

扩展面板可选择：

- 朗读范围：默认“问题和 AI 回复”，也可改成“只读 AI 回复”。
- 是否“每个回合生成一个独立音频”。

按回合拆分只适用于扩展直接抓取 ChatGPT / Gemini / Claude 当前页面。通过 PocketReader 网页粘贴 ChatGPT share link 的导入流程保持单条音频模式。

如果 AI 回复里包含可读取的 AI 生成文件，扩展会把每个文件单独提交给后端，后端为每个文件创建独立音频条目。当前主要支持文本类文件、`.docx` 和带明确 DOM 标记的 Claude Artifact。不要用“右侧大块文本”兜底猜测文件；如果 Claude 没有暴露明确 Artifact DOM，应优先增加手动导入入口。

调试扩展导入问题时：

1. 先在网页面板看 `服务器已识别 X 条消息，Y 个回合，Z 个文本文件`。
2. 如果识别数量明显不对，到服务器查 `browser_captures.raw_snapshot_json`。
3. `blocks` 为空时，改扩展的 `snapshotSelectors`。
4. `blocks` 有内容但解析错时，改后端的 `pocketreader/browser_snapshot.py`。

修改扩展代码后：

1. 打开 `chrome://extensions/`。
2. 找到 PocketReader。
3. 点击 reload。
4. 刷新已经打开的 ChatGPT / Gemini / Claude 页面。

如果忘记刷新页面，旧 content script 可能在 console 里报：

```text
Extension context invalidated.
```

处理方式是刷新当前 AI 页面，再重新点“导入 PocketReader”。

列表页和详情页如果存在排队/生成中的条目，会在用户空闲时自动刷新。只要用户最近有点击/输入、正在展开“查看文本”、正在聚焦控件或播放音频，刷新会被推迟，避免把当前打开的控件折回去。

## Podcast 排障

Feed 地址：

```text
https://reader.example.com/feed/<FEED_TOKEN>.xml
```

如果 Podcast App 能看到订阅更新但不显示新单集，检查：

```bash
TOKEN=$(grep '^FEED_TOKEN=' /etc/apps/pocketreader/pocketreader.env | cut -d= -f2-)
curl -fsS "https://reader.example.com/feed/$TOKEN.xml" >/tmp/pocketreader-feed.xml
curl -I "https://reader.example.com/audio/<item_id>.mp3?token=$TOKEN"
curl -r 0-1023 -I "https://reader.example.com/audio/<item_id>.mp3?token=$TOKEN"
```

预期：

```text
feed GET: HTTP 200
audio HEAD: HTTP 200
audio Range: HTTP 206
```

Pocket Casts 可能使用服务端缓存。若 feed 已修复但仍不显示新条目，可以删除订阅后重新添加同一个 feed 地址。

## 回归检查

部署前运行：

```bash
python -m unittest discover -s tests
python -m compileall pocketreader
node --check browser-extension/background.js
node --check browser-extension/content-script.js
node --check browser-extension/options.js
node tests/browser_extension_capture.test.js
```

截至当前文档更新，本地测试覆盖：

- ChatGPT share link 解析 fixture。
- Chrome 扩展 payload 导入。
- Chrome 扩展 snapshot 保存、后端解析、按回合创建。
- Chrome 扩展纯逻辑测试：回合拆分、单边消息告警、重复片段去重。
- `/api/browser-capture` token 鉴权。
- `/api/browser-snapshot` token 鉴权和 Claude 解析回归。
- 音频 `HEAD` 支持。
- Podcast feed 兼容元数据。
- 中断 job 恢复。
- TTS chunk 和 ffmpeg 合并。
