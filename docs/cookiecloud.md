# CookieCloud Setup

These skills authenticate via your existing browser login cookies.

Recommended approach: **CookieCloud** (browser extension + a small local server).

## Start CookieCloud Server (Docker)

From repo root:
```bash
docker compose up -d cookiecloud
```

CookieCloud will listen on `http://127.0.0.1:8088`.

## Configure Browser Extension

In the CookieCloud browser extension settings:
- Server: `http://127.0.0.1:8088`
- UUID / PASSWORD: set your own values

Then trigger a sync/export so the server has an encrypted cookie payload.

## Provide Credentials to Scripts

Set env vars on the host (preferred names):
- `COOKIECLOUD_UUID`
- `COOKIECLOUD_PASSWORD`
- optional: `COOKIECLOUD_SERVER_URL` (default: `http://127.0.0.1:8088`)

Compatibility aliases also work:
- `COOKIECLOUDUUID`
- `COOKIECLOUDPASSWORD`

PowerShell:
```powershell
$env:COOKIECLOUD_UUID="YOUR_UUID"
$env:COOKIECLOUD_PASSWORD="YOUR_PASSWORD"
```

## If You Run a Script in Docker

If a container needs to talk to CookieCloud running on your host:
- Windows/macOS: `COOKIECLOUD_SERVER_URL=http://host.docker.internal:8088`
- Linux: you may need `--add-host=host.docker.internal:host-gateway`

Example:
```bash
docker run --rm \
  -e COOKIECLOUD_SERVER_URL='http://host.docker.internal:8088' \
  -e COOKIECLOUD_UUID='YOUR_UUID' \
  -e COOKIECLOUD_PASSWORD='YOUR_PASSWORD' \
  <image> --help
```

## Optional: Export Cookies to an Env File

The router skill includes a helper to export per-platform cookie env vars:
```bash
uv run skills/favorites-harvester/scripts/cookiecloud_export_env.py \
  http://127.0.0.1:8088 YOUR_UUID YOUR_PASSWORD --env-file favorites.env
```

