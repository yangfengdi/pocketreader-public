# Deployment

Production host:

```text
203.0.113.10
```

Production domain:

```text
reader.example.com
```

## Isolation Rules

Do not modify:

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

PocketReader owns only:

```text
/opt/apps/pocketreader
/var/lib/apps/pocketreader
/etc/apps/pocketreader
/var/log/apps/pocketreader
/etc/caddy/apps/pocketreader.caddy
```

## First Deploy

1. Create directories:

```bash
mkdir -p /opt/apps/pocketreader
mkdir -p /var/lib/apps/pocketreader
mkdir -p /etc/apps/pocketreader
mkdir -p /var/log/apps/pocketreader
```

2. Put the repository contents under:

```text
/opt/apps/pocketreader
```

3. Create `/etc/apps/pocketreader/pocketreader.env`:

```bash
cp /opt/apps/pocketreader/deploy/pocketreader.env.example \
  /etc/apps/pocketreader/pocketreader.env
chmod 600 /etc/apps/pocketreader/pocketreader.env
```

Set:

```text
APP_USERNAME=admin
APP_PASSWORD=<app-password>
APP_SECRET_KEY=<random-hex>
FEED_TOKEN=<random-token>
APP_BASE_URL=https://reader.example.com
```

4. Start the app:

```bash
cd /opt/apps/pocketreader
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:4780/health
```

5. Add Caddy snippet:

```bash
cp /opt/apps/pocketreader/deploy/pocketreader.caddy \
  /etc/caddy/apps/pocketreader.caddy
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

6. Verify both domains:

```bash
curl -I https://sibling.example.com/
curl -I https://reader.example.com/
```

## Update Deploy

```bash
cd /opt/apps/pocketreader
git pull --ff-only
docker compose up -d --build
curl -fsS http://127.0.0.1:4780/health
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

## Rollback

If the PocketReader Caddy snippet breaks validation or HTTPS:

```bash
mv /etc/caddy/apps/pocketreader.caddy \
  /etc/caddy/apps/pocketreader.caddy.disabled
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

This leaves other-app untouched.

If the app container is bad:

```bash
cd /opt/apps/pocketreader
docker compose down
```

The database and audio remain under `/var/lib/apps/pocketreader`.

