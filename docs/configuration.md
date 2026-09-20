# 配置说明

应用从进程环境读取配置：本地启动用 Uvicorn `--env-file .env`，Compose 用服务器 `/etc/apps/pocketreader/pocketreader.env`。`get_settings()` 不自动寻找 env 文件。

用 `python3 scripts/init_env.py` 创建本地配置；`--output`、`--base-url`、`--container` 用于生产容器。生成器只创建新文件，权限 600，不输出秘密值、不覆盖已有文件。

| 变量 | 用途和默认值 |
| --- | --- |
| `APP_USERNAME` | 登录用户名，默认 `admin` |
| `APP_PASSWORD` | 必填，网页密码，无默认值 |
| `APP_SECRET_KEY` | 必填，session 签名密钥，无默认值 |
| `FEED_TOKEN` | 必填，RSS 和 tokenized 音频访问，无默认值 |
| `IMPORT_TOKEN` | 必填，扩展导入鉴权，无默认值 |
| `APP_BASE_URL` | 默认 `http://127.0.0.1:4780`；部署时是自己的 HTTPS 根地址 |
| `APP_DATA_DIR` | 本地默认 `data`；容器 `/data`，绑定服务器持久目录 |
| `APP_LOG_DIR` | 本地默认 `logs`；容器 `/logs` |
| `DEFAULT_VOICE` | 默认 `zh-CN-XiaoxiaoNeural`；选择见 `pocketreader/config.py` |
| `TTS_MAX_CHARS_PER_CHUNK` | 默认 1800，代码下限 500 |
| `TTS_RETRIES` | 默认 3，下限 0 |

必需凭证为空或使用 `CHANGE_ME`、`replace-with-…`、`<…>` 模板值时拒绝启动。代码不会判断每个用户自选密码的强度；建议使用生成器或密码管理器生成独立随机值。

## 轮换影响

- 改 `APP_PASSWORD` 改变网页密码；现有 session 可能持续到到期。
- 同时改 `APP_SECRET_KEY` 使旧 session 失效，需重新登录。
- 改 `FEED_TOKEN` 使旧 Feed 与带 token 的音频 URL 失效，需重新订阅。
- 改 `IMPORT_TOKEN` 影响扩展导入，需更新各浏览器设置。
- 持久 env 不变时，普通更新和重启不轮换 token。

env 修改后用 `docker compose up -d --force-recreate` 重新读取容器环境；`docker compose restart` 不重新加载 env。本地 `.env` 改动也需重启 Uvicorn。

## 私有资料存放

`.env`、`.env.*`、`*.env`、`.local/`、`.private/`、数据、日志、私钥和备份归档由 `.gitignore` 排除。`deploy/pocketreader.env.example` 只放模板。

维护资料放在仓库外，用 `git config --local pocketreader.privateDir /absolute/private/path` 记录本机位置。目录权限 700、凭证文件 600，并独立安全备份。权限不是加密，不能防止同一用户下运行的程序读取。

私有目录不能设为 remote 或打包给贡献者。Docker build context 另有 `.dockerignore` 限制，构建公开源码不需要真实配置。
