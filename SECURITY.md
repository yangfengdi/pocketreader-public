# 安全与隐私

PocketReader 面向单用户可信使用，不是开放注册平台。源码公开不意味着实例数据公开，也不意味着完成了全面安全审计。

## 数据去向

- 文本、来源 URL、原始快照、解析结果和音频留在自己实例的数据目录。
- TTS 把待朗读文本发送给 Microsoft Edge TTS，并非完全离线。
- 扩展发送页面对话和可读取文件，不发送 AI 账号 cookie；对话本身仍可能敏感。
- 当前扩展通过 Chrome `storage.sync` 保存地址、导入 token 和偏好，可能经 Chrome 账号同步。它们不在 Git 仓库中；共享浏览器配置前应清除设置。
- Podcast 客户端可能通过服务器抓取和缓存内容。带 token 的 Feed / 音频 URL 本身就是访问凭证。
- 删除条目不保证关联原始快照和所有备份一并删除；数据保留由实例维护者负责。

## 维护边界

- 各实例使用独立强密码和随机 token，启用 HTTPS，后端仅绑定 loopback。
- 持久 env 不放进源码或镜像，私钥和备份不上传 Git。
- 登录缺少专门的防暴力尝试限速；URL 抓取不能作为强隔离的内网访问边界。面向不可信用户开放前应补入口访问控制、限速、SSRF 防护和权限审查。
- 账号或 import token 的持有者应视为可信，不向陌生人提供共享账号。
- 升级依赖验证兼容性，不能因为源码公开就假设第三方依赖没有漏洞。

## 发现泄露

不在公开 issue 中粘贴口令、完整 Feed URL、原始对话或可直接访问真实实例的操作步骤。实例事实联系所有者私下处理，通用 bug 提供最小脱敏复现。

真实凭证进入 Git 时先撤销或轮换，再清理历史及其他克隆。只删除当前文件不能删除历史；强推也不保证清除 GitHub 缓存或别人手中的副本。见 [GitHub 官方清理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
