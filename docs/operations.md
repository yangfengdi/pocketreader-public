# Operations

## Useful Commands

```bash
cd /opt/apps/pocketreader
docker compose ps
docker compose logs -f --tail=100
docker compose restart
curl -fsS http://127.0.0.1:4780/health
```

## Change Password

Edit:

```text
/etc/apps/pocketreader/pocketreader.env
```

Then run:

```bash
cd /opt/apps/pocketreader
docker compose up -d
```

Existing sessions keep working until their cookie expires unless `APP_SECRET_KEY`
is also changed.

## Rotate Feed Token

Edit `FEED_TOKEN` in the env file and restart the container:

```bash
cd /opt/apps/pocketreader
docker compose up -d
```

Old podcast/audio feed URLs stop working.

## Back Up Data

Back up:

```text
/var/lib/apps/pocketreader/pocketreader.sqlite3
/var/lib/apps/pocketreader/audio
/etc/apps/pocketreader/pocketreader.env
```

## Storage

Check disk usage:

```bash
du -sh /var/lib/apps/pocketreader
df -h /
```

Version 1 does not automatically delete audio. Delete items through the UI to
remove their database row and audio folder.

## Logs

- Application logs:

```bash
cd /opt/apps/pocketreader
docker compose logs --tail=200
```

- Caddy access logs use the existing Caddy logging behavior. The PocketReader
  snippet does not create its own Caddy log file because the Caddy systemd
  sandbox on the production server rejects new log file paths.
