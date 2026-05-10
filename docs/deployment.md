# 部署说明

## 生产环境

服务器：

```text
203.0.113.10
```

生产域名：

```text
https://reader.example.com
```

同一台服务器上还有已有应用：

```text
https://sibling.example.com
```

PocketReader 部署和运维时必须避免影响 other-app / other_app。

## 隔离规则

不要修改：

```text
/etc/caddy/Caddyfile
/etc/caddy/apps/other-app.caddy
/opt/other-app
/var/lib/other-app
/etc/other-app
/var/log/other-app
other-app-update.service
other-app-update.timer
other-app-trigger.service
```

PocketReader 只拥有：

```text
/opt/apps/pocketreader
/var/lib/apps/pocketreader
/etc/apps/pocketreader
/var/log/apps/pocketreader
/etc/caddy/apps/pocketreader.caddy
```

后端只允许监听宿主机本地端口：

```text
127.0.0.1:4780
```

公网访问必须走 Caddy 反向代理。

## 首次部署

1. 创建目录：

```bash
mkdir -p /opt/apps/pocketreader
mkdir -p /var/lib/apps/pocketreader
mkdir -p /etc/apps/pocketreader
mkdir -p /var/log/apps/pocketreader
```

2. 把仓库内容放到：

```text
/opt/apps/pocketreader
```

3. 创建 env 文件：

```bash
cp /opt/apps/pocketreader/deploy/pocketreader.env.example \
  /etc/apps/pocketreader/pocketreader.env
chmod 600 /etc/apps/pocketreader/pocketreader.env
```

必须设置：

```text
APP_USERNAME=admin
APP_PASSWORD=<app-password>
APP_SECRET_KEY=<random-hex-or-url-safe-token>
FEED_TOKEN=<random-token>
IMPORT_TOKEN=<random-token>
APP_BASE_URL=https://reader.example.com
APP_DATA_DIR=/data
APP_LOG_DIR=/logs
```

4. 启动应用：

```bash
cd /opt/apps/pocketreader
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:4780/health
```

5. 安装 Caddy snippet：

```bash
cp /opt/apps/pocketreader/deploy/pocketreader.caddy \
  /etc/caddy/apps/pocketreader.caddy
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

6. 验证两个域名：

```bash
curl -I https://sibling.example.com/
curl -I https://reader.example.com/
```

预期：

- other-app 通常返回 `401`，表示原应用仍由 Basic Auth 保护。
- pocketreader 未登录时返回 `303` 到 `/login`。

## 常规更新部署

如果服务器上的 `/opt/apps/pocketreader` 是完整 git checkout，优先：

```bash
cd /opt/apps/pocketreader
git pull --ff-only
docker compose up -d --build
curl -fsS http://127.0.0.1:4780/health
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

如果服务器无法从 GitHub 拉取，或本地提交还没有 push，可以从本机打包部署：

```bash
git archive --format=tar.gz -o /tmp/pocketreader-main.tar.gz HEAD
scp /tmp/pocketreader-main.tar.gz root@203.0.113.10:/tmp/pocketreader-main.tar.gz
```

服务器上执行：

```bash
rm -rf /opt/apps/pocketreader.prev
cp -a /opt/apps/pocketreader /opt/apps/pocketreader.prev
rm -rf /opt/apps/pocketreader.release
mkdir -p /opt/apps/pocketreader.release
tar -xzf /tmp/pocketreader-main.tar.gz -C /opt/apps/pocketreader.release
rsync -a --delete /opt/apps/pocketreader.release/ /opt/apps/pocketreader/
rm -rf /opt/apps/pocketreader.release
cd /opt/apps/pocketreader
docker compose up -d --build
curl -fsS http://127.0.0.1:4780/health
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
rm -f /tmp/pocketreader-main.tar.gz
```

部署会重启容器。若有条目正在生成，重启后 `requeue_interrupted_items()` 会自动把旧 `processing` 条目重新排队。

## 部署后验证

```bash
cd /opt/apps/pocketreader
docker compose ps
curl -fsS http://127.0.0.1:4780/health
curl -I https://sibling.example.com/
curl -I https://reader.example.com/
```

验证 Podcast 音频 endpoint：

```bash
TOKEN=$(grep '^FEED_TOKEN=' /etc/apps/pocketreader/pocketreader.env | cut -d= -f2-)
curl -fsS "https://reader.example.com/feed/$TOKEN.xml" >/tmp/pocketreader-feed.xml
curl -I "https://reader.example.com/audio/<item_id>.mp3?token=$TOKEN"
curl -r 0-1023 -I "https://reader.example.com/audio/<item_id>.mp3?token=$TOKEN"
```

预期：

- feed GET 返回 `200`，并成功写入 `/tmp/pocketreader-feed.xml`。
- audio `HEAD` 返回 `200`。
- Range request 返回 `206`。

## 回滚

如果 Caddy snippet 导致 HTTPS 异常：

```bash
mv /etc/caddy/apps/pocketreader.caddy \
  /etc/caddy/apps/pocketreader.caddy.disabled
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

这不会修改 other-app 配置。

如果新应用版本异常，且 `/opt/apps/pocketreader.prev` 存在：

```bash
rsync -a --delete /opt/apps/pocketreader.prev/ /opt/apps/pocketreader/
cd /opt/apps/pocketreader
docker compose up -d --build
curl -fsS http://127.0.0.1:4780/health
```

如果只需要停掉 PocketReader：

```bash
cd /opt/apps/pocketreader
docker compose down
```

数据库和音频仍保留在 `/var/lib/apps/pocketreader`。
