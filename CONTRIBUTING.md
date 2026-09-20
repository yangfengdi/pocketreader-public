# 开发与贡献

先读[上手指南](docs/getting-started.md)和 [AGENTS.md](AGENTS.md)。修改自己的 fork 并使用功能分支。代码、必要测试和文档一起提交；PR 描述触发条件、修改后行为、验证结果和兼容影响。

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q pocketreader scripts
node --check browser-extension/background.js
node --check browser-extension/content-script.js
node --check browser-extension/options.js
node tests/browser_extension_capture.test.js
node tests/browser_extension_settings.test.js
python3 scripts/check_public_content.py
git diff --check
```

测试使用合成数据和临时目录，不连接生产服务器。ffmpeg 存在时验证短音频合并，缺失时该测试会跳过；跳过不能当作音频功能通过。交互、真实 TTS 和 AI 站点 DOM 需要额外本地浏览器验收。

## 重要约束

- 一个 SQLite 库一个应用 worker；目前没有分布式队列互斥。
- 增量身份包含来源、URL、朗读范围和回合序号，不能只按标题去重。
- 分享链接单条导入和扩展按回合导入有不同语义。
- 保留原始快照便于重新解析，不把生产会话当公开 fixture。
- schema 变化验证旧库兼容和回滚；Markdown 保正文；音频保 HEAD、Range 和 Podcast 兼容。

## 提交前检查

首次 clone 执行 `sh scripts/install_hooks.sh`。Git 不会自动安装仓库 hooks；CI 也不能阻止内容首次上传，本地检查不可省略。

推送前还必须安装 [Gitleaks v8](https://github.com/gitleaks/gitleaks)，macOS 可用 `brew install gitleaks`，其他平台使用其官方安装方式。`sh scripts/check_secrets.sh` 扫描所有本地可达提交；缺少工具或扫描失败会阻止 push。非 PATH 安装可用本地 `git config pocketreader.gitleaksPath /absolute/path/to/gitleaks` 指定。

`pre-commit` 扫完整暂存区；`pre-push` 扫正在推送的引用及其历史。可在本机 `pocketreader.privateDir` 指向的目录维护 `private-values.txt`，每行一个已知私有值，错误输出不显示值。

检查器拦截私有路径、非示例 IP、部分凭证格式和本机已知值，不是完整秘密扫描或代码安全审计。发布前还需 Gitleaks 等通用扫描、diff 与历史审查，包括邮箱、私有域名、口令、会话内容。

保留 [MIT 许可](LICENSE) 声明，第三方代码与资源遵守各自许可。

GitHub Actions 当前以待启用模板提供，启用步骤和权限要求见 [docs/ci.md](docs/ci.md)。不要将本地测试通过表述成 GitHub Actions 已通过。
