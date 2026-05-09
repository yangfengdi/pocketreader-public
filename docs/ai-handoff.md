# AI Handoff Notes

This file records the deployment agreement made during initial development so a
future AI session does not need the original chat context.

## Existing Server Application

The same server also runs `other_app`:

```text
Domain: sibling.example.com
Host: 203.0.113.10
Paths:
  /opt/other-app
  /var/lib/other-app
  /etc/other-app
  /var/log/other-app
Systemd:
  other-app-update.service
  other-app-update.timer
  other-app-trigger.service
```

PocketReader must not modify those paths or services.

## Caddy Agreement

Caddy has been converted to a multi-application layout:

```text
/etc/caddy/Caddyfile
/etc/caddy/apps/other-app.caddy
/etc/caddy/apps/pocketreader.caddy
```

PocketReader owns only:

```text
/etc/caddy/apps/pocketreader.caddy
```

Do not edit:

```text
/etc/caddy/Caddyfile
/etc/caddy/apps/other-app.caddy
```

After adding or updating the PocketReader snippet:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
curl -I https://sibling.example.com/
curl -I https://reader.example.com/
```

If PocketReader breaks Caddy validation, rollback by moving the snippet away:

```bash
mv /etc/caddy/apps/pocketreader.caddy \
  /etc/caddy/apps/pocketreader.caddy.disabled
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

## PocketReader Boundaries

PocketReader should use:

```text
/opt/apps/pocketreader
/var/lib/apps/pocketreader
/etc/apps/pocketreader
/var/log/apps/pocketreader
```

Docker Compose maps the backend to:

```text
127.0.0.1:4780:4780
```

The app listens on `0.0.0.0` inside the container, but the host publishes it only
on loopback.

