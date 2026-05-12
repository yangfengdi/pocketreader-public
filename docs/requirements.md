# 需求说明

## 用户需求

用户经常通过“听”的方式获取信息，希望把文本、Markdown、AI 对话、草稿和批量文件转成音频，在 iPhone 上连续收听。典型场景包括开车、坐车、坐飞机、以及通过“听稿”来审稿。

目标设备优先适配：

```text
iPhone 13 Pro Max
```

## 核心使用场景

1. 电脑导入，手机收听：
   - 在电脑上打开 PocketReader。
   - 粘贴文本，或批量上传 `.txt` / `.md` 文件。
   - 等待 TTS 生成。
   - 在 iPhone 上打开网页或 Podcast App 收听。

2. 手机链接导入：
   - 在手机上拿到公开 URL 或 AI share link。
   - 粘贴到 PocketReader 的链接导入框。
   - 选择“只读 AI 回复”或“用户和 AI 都读”。

3. 浏览器内 AI 对话导入：
   - 在桌面 Chrome 中正常使用 ChatGPT、Gemini 或 Claude。
   - 不需要创建 share link。
   - 点击页面内由扩展注入的“导入 PocketReader”按钮。
   - 检查标题、声音、朗读范围和“每个回合一个独立音频”选项后提交。
   - 如果启用按回合拆分，每一轮一问一答会生成一个独立条目，方便在 Podcast App 中逐条播放。

4. 草稿审阅：
   - 粘贴或上传自己写的稿件。
   - 生成音频。
   - 通过收听发现行文、逻辑或表达问题。

5. 离线准备：
   - 在条目页点“缓存音频”，让浏览器缓存该 MP3。
   - 或把私有 Podcast Feed 添加到支持下载的 Podcast App 中。

## 功能需求

- 单用户登录。
- 导入普通文本和 Markdown。
- 批量上传 `.txt`、`.md`、`.markdown`。
- 导入公开 URL。
- 对 ChatGPT share link 做专门解析。
- 对 Gemini / Claude share link 做明确错误提示，避免把登录壳或 Cloudflare 页面当正文。
- Chrome 扩展导入已登录的 ChatGPT、Gemini、Claude 页面。
- Chrome 扩展导入 AI 对话时默认朗读“问题和 AI 回复”。
- 可选只读 AI 回复。
- Chrome 扩展支持把 ChatGPT、Gemini、Claude 的多回合对话按“每个回合一个独立音频”拆分。
- 拆分条目标题前缀使用 `[1/9]`、`[05/19]`、`[012/109]` 这类编号，确保播客客户端按标题或文本排序时能保持对话顺序。
- Chrome 扩展会把 AI 对话中可读取的 AI 生成文件单独创建为音频条目；文本类文件直接读取，`.docx` 文件由后端解析正文，带明确 Artifact 标记的 Claude Artifact 会按 Markdown 文本处理。
- 文件条目标题前缀使用 `[文件]` 或 `[文件 1/2]`。
- ChatGPT share link 导入保持原有单条音频模式，不提供按回合拆分入口。
- UI 中选择 TTS 声音。
- TTS job 队列化处理。
- 长文本自动切分，避免单次 TTS 生成超过 provider 限制。
- 多 chunk 合并成单个 MP3。
- 保存条目状态和历史。
- 保存播放进度。
- 播放结束后自动进入下一条 ready item。
- 私有 Podcast RSS Feed。
- 音频 URL 支持 `HEAD` 和 Range request，兼容 Podcast 客户端下载。
- 服务重启后自动恢复中断的 `processing` 条目。

## 非目标

- 第一版不做原生 iOS App。
- 不做多用户账号体系。
- 不在远程服务器上登录用户的 ChatGPT/Gemini/Claude 账号。
- 不自动删除旧音频。
- 不做全文搜索。
- 不做复杂权限系统；单用户加 token 已足够。

## 已知限制

- AI 网站 DOM 结构变化时，Chrome 扩展的 snapshot selectors 或后端 `browser_snapshot` 解析器可能需要维护。
- 扩展 reload 后，已经打开的 AI 页面必须刷新；否则旧 content script 会失去 runtime 上下文并显示 `Extension context invalidated`。
- Gemini / Claude share link 后端抓取不稳定，主要推荐 Chrome 扩展导入。
- Pocket Cast 可能有自己的服务端缓存，feed 修改后它不一定像 Apple Podcasts 那样立即显示所有新条目。
- 生产服务器到 GitHub 的网络在某些时间可能超时；部署可以用本地 archive 上传，但仍应在网络恢复后补 `git push`。
