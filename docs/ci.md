# 启用 GitHub Actions（可选）

本仓库提供完整的工作流模板 `docs/github-actions-checks.yml.example`，但默认没有启用 GitHub Actions。测试和公开内容检查可以按 CONTRIBUTING.md 在本地执行，Git hooks 仍会在提交/推送前检查。

发布时使用的 GitHub 授权没有 `workflow` 权限，GitHub 拒绝上传 `.github/workflows/` 下的工作流文件，所以模板保存在文档目录中。这个限制不影响克隆、运行或修改应用。

仓库所有者准备启用 CI 时：

1. 确认用于推送的授权允许管理 Actions 工作流。若通过 GitHub CLI 管理 OAuth 授权，可主动执行 `gh auth refresh -h github.com -s workflow` 并完成 GitHub 授权界面的确认。
2. 将模板复制为 `.github/workflows/checks.yml`，提交并推送自己的分支。
3. 在 Actions 页面确认 `Checks` 完成并通过，再根据需要设置分支保护。

```bash
mkdir -p .github/workflows
cp docs/github-actions-checks.yml.example .github/workflows/checks.yml
git add .github/workflows/checks.yml
git commit -m "Enable GitHub Actions checks"
git push
```

模板覆盖 Python 3.12、ffmpeg、Node.js 扩展测试、编译检查、全部可达历史的公开内容检查，以及固定版本和校验和的 Gitleaks 扫描。它不需要应用服务器凭证，不应把生产 env 或服务器访问权限加入 Actions。

实际在 GitHub 运行成功前，不要把模板存在当作远端测试已通过。CI 检查发生在上传之后，不能代替本地推送前的防泄露检查。
