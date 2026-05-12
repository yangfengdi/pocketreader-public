# Chrome 扩展说明

PocketReader Capture 是一个本地加载的 Chrome extension。它在用户已经登录的 AI 网站页面里提取当前对话文本，然后提交给 PocketReader。

支持页面：

```text
https://chatgpt.com/*
https://chat.openai.com/*
https://gemini.google.com/*
https://claude.ai/*
```

这个扩展不取代 ChatGPT share link 导入。ChatGPT share link 仍可通过网页的 URL 导入表单处理。扩展主要解决 Gemini / Claude 这类服务器无法稳定抓取正文的问题。

## 安装

1. 打开 Chrome 扩展页面：

```text
chrome://extensions/
```

2. 开启 Developer mode。
3. 点击 Load unpacked。
4. 选择仓库中的目录：

```text
browser-extension
```

5. 打开扩展 options page，填写：

```text
PocketReader 地址: https://reader.example.com
IMPORT_TOKEN: /etc/apps/pocketreader/pocketreader.env 中的 IMPORT_TOKEN
```

登录 PocketReader 后也可以从网页查看这些值：

```text
https://reader.example.com/extension
```

## 使用

1. 在 Chrome 中正常打开 ChatGPT、Gemini 或 Claude 对话页。
2. 点击页面右下角的“导入 PocketReader”按钮。
3. 检查标题、朗读范围和声音。
4. 点击“提交导入”。

扩展发送给服务器的数据包括：

- 平台名。
- 当前页面 URL。
- 标题。
- 朗读范围。
- 选择的声音。
- 提取出的 user / AI messages。
- AI 生成文件的文件名、文本内容，或小型 `.docx` 文件的 base64 数据。

扩展不会把 AI 账号 cookie 发给 PocketReader。

## 更新扩展代码后

修改 `browser-extension/` 下文件后，Chrome 不会自动加载新代码。需要：

1. 打开 `chrome://extensions/`。
2. 找到 PocketReader Capture。
3. 点击 reload。
4. 刷新已打开的 ChatGPT / Gemini / Claude 页面。

如果没有刷新页面，旧 content script 会继续留在页面里，但它已经无法调用新的扩展 runtime。此时 Chrome console 可能出现：

```text
Extension context invalidated.
```

扩展会尽量显示“请刷新当前 AI 页面后再导入”的提示，但根本处理方式仍然是刷新当前 AI 页面。

如果“扩展设置”按钮无响应，重点检查：

- `browser-extension/background.js` 中是否处理 `POCKETREADER_OPEN_OPTIONS`。
- `browser-extension/content-script.js` 是否通过 `chrome.runtime.sendMessage` 请求打开设置页。
- 不要在 content script 中直接调用 `chrome.runtime.openOptionsPage()`；某些 Chrome 环境中这个函数不存在。

## 维护提取逻辑

每个平台的 DOM selector 写在：

```text
browser-extension/content-script.js
```

对应函数：

- `extractChatGPTMessages`
- `extractGeminiMessages`
- `extractClaudeMessages`

如果某个 AI 网站改版导致导入为空或混入 UI 文案，优先只改对应平台 extractor。

扩展会先清理不可见节点、按钮、图标、脚本、输入框等，再做去重。服务端还会再次标准化 role 和文本。

平台解析规则和稳定性约束集中记录在：

```text
docs/ai-capture-design.md
```

修改 ChatGPT / Gemini / Claude selector 前，先阅读该文档，并补充 `tests/browser_extension_capture.test.js` 中的回归用例。

## 后端接口

```text
POST /api/browser-capture
X-PocketReader-Import-Token: <IMPORT_TOKEN>
```

Payload 示例：

```json
{
  "platform": "gemini",
  "url": "https://gemini.google.com/...",
  "title": "Conversation title",
  "reader_mode": "all",
  "split_by_turn": true,
  "include_user_question": true,
  "voice": "zh-CN-XiaoxiaoNeural",
  "messages": [
    {"role": "User", "text": "Question"},
    {"role": "AI", "text": "Answer"}
  ],
  "files": [
    {"filename": "outline.md", "body": "# Outline\n\nText"},
    {"filename": "draft.docx", "data_base64": "..."}
  ]
}
```

服务端行为：

- 校验 `IMPORT_TOKEN`。
- 标准化 role：`human/user/you` -> `User`，`assistant/model/ai/claude` -> `AI`。
- 根据 `reader_mode` 选择只保留 AI 回复或完整对话。
- `split_by_turn=false` 时，创建一个普通 `queued` item。
- `split_by_turn=true` 时，按 User 消息开始新回合、后续 AI 消息归入同一回合的规则拆成多个 item；只生成包含 AI 回复的回合。
- 拆分后每个标题最前面加编号，例如 `[1/9]`、`[05/19]`、`[012/109]`。
- `include_user_question=true` 时，每个拆分条目包含提问和回答；为 `false` 时只保留 AI 回复。
- 如果 payload 中有 `files`，服务端会为每个可读取文件创建独立 item。
- 文件标题使用 `[文件]` 或 `[文件 1/2]` 前缀，`source_type` 为 `browser:<platform>:file`。
- 交给同一个 TTS worker 生成音频。

## 按回合拆分

浏览器扩展面板里有“每个回合生成一个独立音频”checkbox。它只影响扩展直接抓取 ChatGPT、Gemini、Claude 当前页面的导入，不影响 PocketReader 网页里通过 ChatGPT share link 粘贴导入的流程。

扩展的默认朗读范围是“问题和 AI 回复”。如果用户明确选择“只读 AI 回复”，服务端会在拆分时把 `include_user_question` 当作 `false` 处理，每个音频只保留回答。

## AI 生成文件

扩展会在 ChatGPT、Gemini、Claude 的 AI 回复区域里寻找文件链接、文件卡片或 Claude Artifact。当前自动读取：

- 文本类文件：`.txt`、`.md`、`.csv`、`.json`、`.html`、`.py`、`.js`、`.ts`、`.css`、`.sql` 等。
- 小型 `.docx` 文件：扩展下载后发给服务端，服务端用标准 docx XML 解析正文。
- Claude Artifact：如果页面 DOM 中存在明确 Artifact 标记，扩展会把它当作 Markdown 文本文件提交。

如果 AI 网站只暴露不可下载的内部 `sandbox:` 链接、Artifact 没有明确 DOM 标记，或文件是 PDF/图片/表格这类当前无法抽取正文的格式，扩展会跳过该文件。不要用“右侧大块文本”兜底猜测文件；这已经导致过普通回复被误判为文件。后续要支持更多格式，应在 `browser-extension/content-script.js` 的文件提取逻辑和 `pocketreader/importers.py` 的文件解析逻辑里扩展。
