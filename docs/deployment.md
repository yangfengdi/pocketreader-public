# 部署自己的实例

`reader.example.com` 是示例域名。实际地址只写在服务器配置或仓库外的私有维护目录，不要替换到已跟踪的模板中再提交。

已有服务器的维护者先运行 `git config --get pocketreader.privateDir`，阅读该目录的私有 runbook。若为空，此克隆没有绑定作者的服务器。确认目标、登录方式和隔离边界后再操作。

## 前提与目录

- Linux、Docker Engine + Compose v2、Caddy、SSH 访问和自己的域名。
- 域名解析、HTTPS 端口和证书验证方式已确认。
- 后端只绑定 `127.0.0.1:4780`，公网访问经过 HTTPS 反向代理。
- 一个实例一个容器、一个应用 worker；不要直接增加副本或 Uvicorn workers。
- 共用服务器的其他应用目录、端口和服务写入私有 runbook，只维护本实例的资源。

| 路径 | 用途 |
| --- | --- |
| `/opt/apps/pocketreader` | 源码 |
| `/etc/apps/pocketreader/pocketreader.env` | 私有配置，权限 600 |
| `/var/lib/apps/pocketreader` | 数据库、快照和音频 |
| `/var/log/apps/pocketreader` | 日志目录 |
| `/etc/caddy/apps/pocketreader.caddy` | 本实例代理片段 |

命令需要相应目录权限；下面以 sudo 表示管理员操作，不要求远程 root 登录。

## 首次安装

把自己的 fork 克隆到 `/opt/apps/pocketreader`，然后执行：

```bash
sudo install -d -m 700 /etc/apps/pocketreader
sudo install -d /var/lib/apps/pocketreader /var/log/apps/pocketreader
cd /opt/apps/pocketreader
sudo python3 scripts/init_env.py \
  --output /etc/apps/pocketreader/pocketreader.env \
  --base-url https://reader.example.com \
  --container
```

将上面**命令参数**的示例域名改为自己的。用服务器编辑器查看用户名和随机密码。生成器拒绝覆盖已有 env；更新时不应重新生成。变量含义见 [configuration.md](configuration.md)。

```bash
sudo docker compose up -d --build
sudo docker compose ps
curl -fsS http://127.0.0.1:4780/health
```

将 `deploy/pocketreader.caddy` 复制到服务器 `/etc/caddy/apps/pocketreader.caddy`，只编辑这份服务器副本的域名。

新服务器由管理员配置主 Caddyfile 导入片段，例如 `import /etc/caddy/apps/*.caddy`。共用 Caddy 时先确认现有导入规则，不覆盖主文件和其他应用配置。

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

模板使用 Caddy 默认自动 HTTPS。特殊 ACME challenge 或网络要求按服务器实情配置，并记入私有 runbook。访问自己的 HTTPS 地址，登录、导入短文本并播放；共用服务器还需检查其他应用。

## 扩展和 Podcast

登录自己的实例后打开 `/extension`，把服务地址和自己的 `IMPORT_TOKEN` 填入扩展设置，保存时允许访问该 HTTPS 域名。详见 [browser-extension.md](browser-extension.md)。

在网页复制私有 Feed URL 到自己的 Podcast App。URL 自带访问凭证，不能公开截图或提交到 GitHub；客户端也可能通过其服务器抓取和缓存内容。

## 更新

先在本地完成测试和扫描、提交代码。在服务器按 [operations.md](operations.md)备份数据、env 和代码，记录旧提交号或镜像标识。

若部署目录是你自己的 Git checkout，检查工作区干净、远端正确后：

```bash
cd /opt/apps/pocketreader
git status --short --branch
git pull --ff-only
sudo docker compose up -d --build
curl -fsS http://127.0.0.1:4780/health
```

只有代理配置变更才需要验证和 reload Caddy。发布源码不意味着服务器已经更新。

GitHub 网络不通时，可从已审核提交生成 `git archive`，上传到独立临时发布目录，再按私有 runbook 切换代码。不要打包整个工作区，不要对含有数据或凭证的目录执行 `rsync --delete`。

升级前检查四个必需凭证：`APP_PASSWORD`、`APP_SECRET_KEY`、`FEED_TOKEN`、`IMPORT_TOKEN`。缺失或模板值会使新版启动失败。保留已有有效 token，避免订阅和扩展失效。

## 验证与回滚

- `/health` 为 `{"status":"ok"}`；未登录访问 `/` 跳转 `/login`。
- 登录、短文 TTS、播放正常；已有音频 HEAD 为 200、有效 Range GET 为 206。
- 已有 Feed 和扩展可用，其他共用应用正常。
- 生成中重启会重新排队遗留的 `processing`，不要删除数据库处理“卡住”。

代码回滚使用记录的旧版本和镜像。schema 有变化时确认旧代码兼容；不兼容则停应用后恢复匹配的数据库和音频备份，并先保留现场副本。恢复备份会丢失备份后的新增内容。

代理回滚恢复本实例片段备份，验证整个 Caddy 配置后再 reload，不重写其他实例规则。`sudo docker compose down` 会停止服务并保留绑定挂载的数据；不要一起删除数据目录。
