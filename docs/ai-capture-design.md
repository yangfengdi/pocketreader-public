# AI 对话解析设计

## 目标

PocketReader 的浏览器扩展负责从用户已经登录的 AI 页面里读取当前对话，再提交到后端生成音频。这个链路的目标是稳定、可解释，而不是尽可能多地猜测页面内容。

核心需求：

- 支持 ChatGPT、Gemini、Claude 当前对话页。
- 识别 User 与 AI 两类消息，并保持页面顺序。
- 默认朗读“问题和 AI 回复”。
- 可选“只读 AI 回复”。
- 可选“每个回合生成一个独立音频”。
- 拆分回合时，标题必须使用 `[1/3]`、`[2/3]` 这类前缀。
- 如果页面里有明确的 AI 生成文件，文件应单独生成音频。
- 不应把普通 AI 回复、页面侧栏、导航、按钮、历史列表误判为文件。

## 稳定性原则

1. 宁可少抓文件，也不要误抓正文为文件。
2. 每个平台先使用明确消息容器，再使用有限 fallback。
3. 只有同时识别到 User 和 AI，才认为“完整识别问答双方”。
4. 不能用宽泛 selector 抓消息，例如在 Claude 中直接抓 `.markdown`，这会把同一回复里的段落节点重复当成消息。
5. 不能用“右侧大块文本”自动判断文件；Claude 页面右侧可能是 Artifact，也可能是普通对话正文或预览容器。
6. 扩展状态栏必须暴露识别结果，让提交前能看到明显异常，例如“未完整识别问答双方”。

## 回合拆分规则

扩展和后端采用同一逻辑：

```text
User 开始一个新回合
后续 AI 消息归入该回合
遇到下一个 User 时，结束前一个回合
没有 AI 回复的悬空 User 不生成音频
```

例：

```text
User 1
AI 1
User 2
AI 2
User 3
AI 3
```

生成 3 个回合：

```text
[1/3] User 1 + AI 1
[2/3] User 2 + AI 2
[3/3] User 3 + AI 3
```

如果扩展只识别到 AI，没有识别到 User，且用户选择了“问题和 AI 回复”，扩展应停止提交并提示页面没有完整识别。

## ChatGPT 解析规则

优先规则：

- 消息节点：`[data-message-author-role]`
- role 来源：`data-message-author-role`
- 文本来源：消息节点内的 readable child，优先 `.markdown`

fallback：

- User: `[data-testid*='user-message']`、`.font-user-message`
- AI: `[data-testid*='assistant-message']`、`.markdown.prose`、`.markdown`

风险：

- fallback 中 `.markdown` 比较宽，只应在 ChatGPT 缺少 `data-message-author-role` 时使用。

## Gemini 解析规则

User selector：

```text
user-query
[data-test-id='user-query']
[data-testid='user-query']
.query-text
```

AI selector：

```text
model-response
[data-test-id='model-response']
[data-testid='model-response']
.model-response-text
.response-container
message-content
```

Gemini 的 share link 后端抓取不稳定，优先使用浏览器扩展读取已登录页面。

## Claude 解析规则

Claude 是最容易漂移的平台，规则必须更保守。

第一优先级：

```text
User: [data-testid='user-message'], [data-testid*='user-message']
AI:   [data-testid='assistant-message'], [data-testid*='assistant-message']
```

只有当这一组结果同时包含 User 和 AI 时，才使用它。

fallback：

```text
User: .font-user-message
AI:   .font-claude-message
```

禁止：

- 不要用 `.markdown` 作为 Claude 消息 selector。
- 不要用 `[data-is-streaming]` 作为历史消息 selector。
- 不要把右侧任意大块文本自动当作文件。

## AI 生成文件规则

自动文件识别只允许两类来源：

1. 明确文件链接或文件卡片：
   - `a[download]`
   - `a[href]`
   - 带文件名扩展名的 `title`、`aria-label`、文本内容
2. 明确 Artifact 容器：
   - `data-testid` / `class` / `aria-label` / `title` 中包含 `artifact`
   - `data-testid` / `class` 中包含 `canvas`

支持格式：

- 文本类：`.txt`、`.md`、`.csv`、`.json`、`.html`、`.py`、`.js`、`.ts`、`.css`、`.sql` 等。
- `.docx`：扩展读取 base64，后端解析 `word/document.xml`。

不自动支持：

- PDF。
- 图片。
- 表格文件。
- 只有预览但没有可读正文、没有明确 Artifact 标记的 Claude 右侧内容。

这些场景后续应该加“手动把选中文本作为文件导入”的入口，而不是继续扩大自动猜测范围。

## 提交前 UI 反馈

状态栏格式：

```text
已识别 6 条消息，3 个回合
已识别 6 条消息，3 个回合，1 个文本文件
已识别 3 条消息，未完整识别问答双方
```

当用户勾选“每个回合生成一个独立音频”且选择“问题和 AI 回复”时，如果没有完整识别 User 与 AI，扩展应停止提交。

## 回归测试

浏览器扩展纯逻辑测试：

```bash
node tests/browser_extension_capture.test.js
```

覆盖内容：

- 三轮问答应拆成 3 个回合。
- Claude 只抓到 AI 时不能被当作完整问答。
- 同一 AI 回复的父节点和子段落重复抓取时，只保留完整文本。
- 状态栏对单边消息给出“未完整识别问答双方”。

后端测试：

```bash
python -m unittest discover -s tests
```

覆盖内容：

- 浏览器 capture API。
- 按回合拆分。
- 文件独立 item。
- `.docx` 文件解析。
- Podcast、音频 endpoint、队列恢复等。
