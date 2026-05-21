# Markdown 朗读转换规则

本文档记录 PocketReader 把 Markdown 转成朗读文本时必须遵守的原则。后续修改 `pocketreader/text.py`、`pocketreader/importers.py`、浏览器扩展或 AI 对话解析时，都应先看这份文档，并补充回归测试。

## 总原则

Markdown 转朗读不是“提取摘要”，而是“去掉格式符号后尽量保留正文”。除非某类内容被明确列为不朗读，否则不能因为它是 Markdown 结构的一部分就删除文字。

应该删除的是格式标记，不是标记包裹的内容。例如：

```markdown
**艺术与品味**
```

朗读文本必须包含：

```text
艺术与品味
```

不能因为 `**...**` 是加粗语法就把“艺术与品味”整段删掉。

## 必须保留的内容

- 标题正文：`# 标题`、`## 标题 ###`、Setext 标题里的“标题”都要保留。
- 加粗、斜体、删除线里的正文：`**文本**`、`_文本_`、`~~文本~~` 都只删除符号。
- 链接显示文字：`[显示文字](https://example.com)` 保留“显示文字”，删除 URL。
- 图片 alt 文本：`![说明](image.png)` 保留“说明”。
- 表格单元格文字：Markdown 表格要转成可朗读的行文本，不能整行删除。
- 行内代码文本：`` `code` `` 删除反引号，保留 `code`。
- 代码块正文：删除三反引号或 `~~~` 围栏和语言标记，保留围栏里的文本。
- 普通列表项正文：删除 `-`、`*`、`+`、checkbox 标记，保留列表项文字。
- 引用正文：删除 `>`，保留引用文字。

## 应删除或跳过的结构符号

- ATX 标题的 `#`。
- Setext 标题下划线和分隔线：`---`、`===`、`***`。
- Markdown 表格分隔行：`| --- | --- |`。
- 表格竖线本身。
- 加粗、斜体、删除线符号。
- 链接 URL 和图片 URL。
- HTML 标签本身。

## 当前实现位置

- `pocketreader/text.py`
  - `markdown_to_speech_text()`：Markdown 到朗读文本的主入口。
  - `markdown_table_line_to_text()`：表格行转朗读文本。
  - `title_from_markdown()`：从 Markdown 推导条目标题。
- `pocketreader/importers.py`
  - `import_markdown()`：网页表单、上传 `.md` 文件、AI 生成文件导入时调用。
  - `render_messages()`：AI 对话消息入库前会对每条消息调用 `markdown_to_speech_text()`。
- `browser-extension/content-script.js`
  - 对 Claude 页面，扩展必须把独立的加粗小标题作为候选块提交给后端。Claude 有时会把 `**艺术与品味**` 渲染成独立 `<strong>` / `<b>` 节点，而不是标准段落；这类节点应作为 AI 正文的一部分，而不是被忽略。

## Claude 独立加粗标题规则

Claude 回复里常见这种 Markdown 写法：

```markdown
**艺术与品味**

"这不是真正的艺术，只是商品。"
```

在 DOM 中，它可能不是 `p` / `h2`，而是一个独立的 `strong` 或 `b` 节点。扩展采集时：

- 如果 `strong` / `b` 是独立块，并且位于 Claude AI 回复上下文中，应作为 `AI` 消息候选提交。
- 如果 `strong` / `b` 位于 `p`、`li`、标题、代码块、按钮、链接、Artifact、用户消息、输入框或 PocketReader 面板内部，不应单独提交，避免重复朗读或误抓 UI。
- 后端收到连续 AI 候选块后，会按 DOM 顺序合并成同一条 AI 回复，因此独立加粗标题应出现在后续段落之前。

## 测试要求

修改 Markdown 朗读转换或 Claude 采集规则时，至少运行：

```bash
python -m unittest tests.test_text
python -m unittest tests.test_browser_capture_api
node --check browser-extension/content-script.js
node tests/browser_extension_capture.test.js
```

如果变更涉及更多导入路径，运行完整测试：

```bash
python -m unittest discover -s tests
node --check browser-extension/background.js
node --check browser-extension/content-script.js
node --check browser-extension/options.js
node tests/browser_extension_capture.test.js
```
