# CookieCloud Setup

These skills authenticate via your existing browser login cookies.

Recommended approach: **CookieCloud** (browser extension + a small local server).

## Links

- CookieCloud (GitHub): https://github.com/easychen/CookieCloud
- Docker image: `easychen/cookiecloud`
- Browser extension: search `CookieCloud` in your browser’s extension store (Chrome / Edge)

Config screenshot (sanitized mock):

![CookieCloud extension settings](images/cookiecloud-extension-settings.svg)

## Start CookieCloud Server (Docker)

From repo root:
```bash
docker compose up -d cookiecloud
```

CookieCloud will listen on `http://127.0.0.1:8088`.

The included `docker-compose.yml` mounts CookieCloud data to `./.cookiecloud-data/` (gitignored).

## Configure Browser Extension

In the CookieCloud browser extension settings:
- Server: `http://127.0.0.1:8088`
- UUID / PASSWORD: set your own values

Then trigger a sync/export so the server has an encrypted cookie payload.

## Verify CookieCloud Has Data

After you click Sync/Upload in the extension, the server should return JSON that contains an `encrypted` field:

```bash
curl 'http://127.0.0.1:8088/get/<YOUR_UUID>'
```

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

If you use this repo’s `docker-compose.yml`, the services run in the same Docker network.
Inside containers, CookieCloud is reachable at:
- `http://cookiecloud:8088`

The `runner` / `media-audio-download` services set `COOKIECLOUD_SERVER_URL=http://cookiecloud:8088` automatically.

## Optional: Export Cookies to an Env File

The router skill includes a helper to export per-platform cookie env vars:
```bash
docker compose run --rm runner python skills/favorites-harvester/scripts/cookiecloud_export_env.py \
  http://cookiecloud:8088 YOUR_UUID YOUR_PASSWORD --env-file favorites.env
```
