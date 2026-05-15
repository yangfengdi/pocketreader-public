# AI 对话采集与解析设计

## 总目标

PocketReader 需要把 ChatGPT、Gemini、Claude 中的 AI 对话导入为可朗读音频。这个功能面向个人使用，但要求稳定、可调试、可接手。

核心需求：

- 支持 ChatGPT、Gemini、Claude 当前对话页。
- 支持 ChatGPT share link 的旧导入方式。
- 默认朗读“问题和 AI 回复”，用户可选择“只读 AI 回复”。
- 浏览器扩展支持“每个回合生成一个独立音频”。
- 拆分回合时，标题必须用 `[1/3]`、`[05/19]`、`[012/109]` 这种前缀，保证播客客户端按顺序播放。
- 如果 AI 对话里有明确生成的文本文件或 Claude Artifact，每个文件要单独生成一个音频。
- 不要把普通 AI 回复、历史列表、侧栏、按钮、导航误判为消息或文件。

## 架构决策

当前架构采用“扩展采集，后端解析”：

```text
AI 网站页面
  |
  | Chrome content script 采集页面快照
  v
Chrome background.js
  |
  | POST /api/browser-snapshot
  v
PocketReader 保存原始快照并解析
  |
  | POST /api/browser-snapshot/<capture_id>/create
  v
PocketReader 创建 queued items
```

这样做的原因：

- DOM 解析规则经常变化，放在扩展里不方便测试和复盘。
- 服务器保存原始快照后，即使第一次解析错了，也可以用同一份原始样本反复调试解析逻辑。
- 扩展仍运行在用户已登录的 AI 页面里，能看到服务器无法直接抓取的内容；但扩展尽量只做采集和轻量标注，不负责最终判断。

## 数据持久化

数据库新增两张表：

- `browser_captures`
  - 保存扩展提交的原始页面快照。
  - 字段包括 `platform`、`source_url`、`page_title`、`extension_version`、`raw_snapshot_json`、`created_at`。
- `browser_parse_runs`
  - 保存每一次解析结果。
  - 字段包括 `capture_id`、`parser_version`、`result_json`、`error`、`created_at`。

后续调试某个失败案例时，优先查这两张表，而不是重新问用户截图：

```bash
sqlite3 /var/lib/apps/pocketreader/pocketreader.sqlite3
SELECT id, platform, source_url, page_title, created_at
FROM browser_captures
ORDER BY id DESC
LIMIT 20;

SELECT parser_version, result_json
FROM browser_parse_runs
WHERE capture_id = <id>
ORDER BY id DESC
LIMIT 1;
```

## 接口

扩展解析当前页面：

```http
POST /api/browser-snapshot
X-PocketReader-Import-Token: <IMPORT_TOKEN>
```

payload 结构：

```json
{
  "platform": "claude",
  "url": "https://claude.ai/chat/...",
  "title": "页面标题",
  "extension_version": "0.1.7",
  "snapshot": {
    "page": {"platform": "claude", "url": "...", "host": "claude.ai", "title": "..."},
    "blocks": [
      {
        "index": 0,
        "tag": "div",
        "path": "main > div[data-testid=\"user-message\"]",
        "role_hint": "User",
        "kind_hint": "message",
        "attrs": {"data-testid": "user-message", "class": "..."},
        "rect": {"top": 120, "left": 80, "width": 600, "height": 120},
        "text": "用户问题"
      }
    ],
    "files": [
      {"filename": "outline.md", "body": "# Outline\n\n..."}
    ]
  }
}
```

接口返回：

```json
{
  "capture_id": 123,
  "parse_run_id": 456,
  "parser_version": "2026-05-13.1",
  "title": "页面标题",
  "summary": {
    "message_count": 6,
    "turn_count": 3,
    "file_count": 0,
    "has_user_messages": true,
    "has_ai_messages": true
  },
  "warnings": []
}
```

根据保存的快照创建条目：

```http
POST /api/browser-snapshot/<capture_id>/create
X-PocketReader-Import-Token: <IMPORT_TOKEN>
```

payload：

```json
{
  "title": "标题",
  "reader_mode": "all",
  "split_by_turn": true,
  "include_user_question": true,
  "voice": "zh-CN-XiaoxiaoNeural"
}
```

旧接口 `POST /api/browser-capture` 保留，用于兼容旧扩展或测试，但新的扩展流程不再依赖它。

## 快照采集规则

扩展采集的是“候选块”，不是最终消息列表。每个候选块带：

- 可读文本 `text`。
- DOM 顺序 `index`。
- 轻量 role hint：`User`、`AI` 或空。
- 轻量 kind hint：`message`、`file`、`artifact`。
- 关键属性：`data-testid`、`class`、`aria-label`、`title`、`href` 等。

扩展不发送 AI 账号 cookie。能下载的文本文件或 `.docx` 会由扩展读取正文或 base64 后放入 `snapshot.files`，因为这些链接通常依赖用户浏览器会话，服务器无法直接获取。

扩展提交快照前必须检查当前 AI 页面是否仍在生成回复。如果检测到 `data-is-streaming` 为真，或页面上有 `Stop generating` / `停止生成` / `停止回答` 等按钮，应拒绝导入并提示用户等待生成完成。否则系统只能保存当时已经渲染出来的半截回答，后端无法从服务器侧补齐未显示的内容。

## 后端解析原则

1. 后端才是最终解析者。
2. `role_hint` 只是提示，后端会结合 `data-testid`、`class`、tag、平台规则重新判断。
3. 文件识别必须有明确文件证据，例如文件扩展名、download/file/attachment 标记，或明确 artifact/canvas 标记。
4. 禁止用“右侧大块文本”“文本很长”“看起来像文章”推断文件。
5. 同一 role 的父节点和子节点重复时，只保留更完整的一份。
6. 只有同时识别到 User 和 AI，才认为完整识别问答双方。
7. Claude 打开的 Artifact 文档有时不会进入 `snapshot.files`，而是以普通 `message` block 混在快照里。后端应识别“artifact 标题块 + 后续完整文档内容块”的结构，把它提升为文件，并把该文档内容块及其子段落从普通对话消息中排除。

## 回合拆分规则

后端规则：

```text
User 开始一个新回合
后续 AI 消息归入该回合
遇到下一个 User 时，结束前一个回合
没有 AI 回复的悬空 User 不生成音频
```

示例：

```text
User 1
AI 1
User 2
AI 2
User 3
AI 3
```

生成：

```text
[1/3] User 1 + AI 1
[2/3] User 2 + AI 2
[3/3] User 3 + AI 3
```

如果用户选择“每个回合生成一个独立音频”且朗读范围是“问题和 AI 回复”，但后端没有识别到 User，创建接口会返回 400，避免生成只有回答、标题也不对的错误条目。

## ChatGPT 规则

页面内扩展优先采集：

- `[data-message-author-role]`
- `[data-testid*='user-message']`
- `[data-testid*='assistant-message']`

后端识别：

- `data-message-author-role=user` -> `User`
- `data-message-author-role=assistant` -> `AI`
- `data-testid` 含 `user-message` -> `User`
- `data-testid` 含 `assistant-message` -> `AI`

ChatGPT share link 仍走网页 URL 导入，解析逻辑在 `pocketreader/importers.py` 的 `extract_chatgpt_share()`。

## Gemini 规则

扩展采集：

- User: `user-query`、`[data-test-id='user-query']`、`[data-testid='user-query']`、`.query-text`
- AI: `model-response`、`[data-test-id='model-response']`、`[data-testid='model-response']`、`.model-response-text`、`.response-container`、`message-content`

Gemini share link 在服务器未登录环境下通常拿不到正文，因此优先使用扩展。

## Claude 规则

Claude DOM 最容易变化，规则要保守。

扩展采集：

- User: `[data-testid='user-message']`、`[data-testid*='user-message']`、`.font-user-message`
- AI: `[data-testid='assistant-message']`、`[data-testid*='assistant-message']`、`.font-claude-message`
- Claude 折叠用户消息：Claude 有时会把很长的用户问题显示成窄宽度、`line-clamp`、`text-[8px]` 的预览块，而不是标准 `user-message` 容器。扩展和后端都要把这类带明显提问语气的块识别成 `User`，否则会把下一条 AI 回复并入上一轮。
- AI fallback：如果明确 AI selector 没有覆盖当前 Claude 版本，扩展会在 `main` 对话区域内采集可见的 `p`、`li`、标题、代码块等正文节点，并排除 user message、折叠用户消息、nav、aside、composer、PocketReader 面板和常见 UI 文案；这些 fallback 节点只作为 `AI` 候选提交给后端。
- 文件/Artifact：明确包含 `artifact`、`canvas`、`file`、`attachment`、`download` 的节点。

禁止：

- 不要用 `.markdown` 作为 Claude 消息 selector。
- 不要用 `[data-is-streaming]` 当历史消息 selector。
- 不要用“右侧面板大块文本”当文件 fallback。

如果 Claude 页面出现“识别 0 条消息”，优先检查保存到 `browser_captures.raw_snapshot_json` 的 blocks 是否为空。如果 blocks 有内容但解析为空，改后端 `pocketreader/browser_snapshot.py`；如果 blocks 本身为空，再改扩展 selector。

如果 Claude 页面只识别到 User、没有 AI，通常说明当前 Claude 版本的 AI 回复没有暴露 `assistant-message` 或 `.font-claude-message`。这时应优先维护 `content-script.js` 里的 `addClaudeFallbackTextNodes()`，但仍要限制在 `main` 区域，并继续排除 user message 和 UI 区域。

## AI 生成文件规则

自动文件识别只允许：

1. 明确文件链接或文件卡片：
   - `a[download]`
   - `a[href]`
   - 文件名扩展名出现在 `title`、`aria-label`、文本内容、URL 中
   - 节点属性包含 `file`、`download`、`attachment`
2. 明确 Claude Artifact：
   - `data-testid` / `class` / `aria-label` / `title` 中包含 `artifact`
   - `data-testid` / `class` 中包含 `canvas`
3. 已打开的 Claude 文档面板：
   - 面板或内容区包含 `document`、`preview`、`editor`、`markdown`、`code` 等标记。
   - 或存在 `.cm-content`、`.ProseMirror`、`contenteditable`、`textarea`、toolbar / tablist / copy / download 控件。
   - 如果 Claude 把文档正文渲染成 `.standard-markdown` 或 `.progressive-markdown`，扩展只允许在侧边面板、弹层、Artifact、Canvas、Document、Preview、Editor 等明确容器里采集，不能采集主对话区的普通 Markdown 回复。
   - 必须排除普通 Claude 回复区域，避免把聊天回复当成文件。
4. Claude snapshot 后端兜底：
   - 如果快照里出现短的 `artifact` 标题块，例如 `Ai时代的家庭教育Document · MD`，且其后紧跟大型 Markdown 文档块，后端会创建 `Ai时代的家庭教育.md` 文件条目。
   - 同一文档的重复父节点和子段落只保留最长正文。
   - 被提升为文件的文档正文块会从普通对话消息中排除，避免同一篇文章在“对话音频”和“文件音频”里重复朗读。

支持格式：

- 文本类：`.txt`、`.md`、`.csv`、`.json`、`.html`、`.py`、`.js`、`.ts`、`.css`、`.sql` 等。
- `.docx`：扩展读取 base64，后端解析 `word/document.xml`。

暂不自动支持：

- PDF。
- 图片。
- 表格文件。
- 没有明确 artifact/file 标记的右侧预览内容。

这些场景以后应加“手动把选中文本作为文件导入”的入口，而不是扩大自动猜测范围。

## 测试要求

修改 AI 解析逻辑后必须跑：

```bash
node --check browser-extension/background.js
node --check browser-extension/content-script.js
node --check browser-extension/options.js
node tests/browser_extension_capture.test.js
python -m unittest discover -s tests
```

重点回归：

- Claude 三回合问答能生成 3 个拆分条目。
- 普通 Claude 回复不会被识别为文件。
- 只识别到 AI、没有 User 时，不能在“问题和 AI 回复”模式下创建拆分音频。
- 文件 payload 仍能独立生成音频。
