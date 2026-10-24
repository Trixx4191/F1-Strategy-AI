# AWS demo

The deployment uses the primary React + FastAPI application, including fresh
simulations, rival analysis, backtesting, CSV export, saved comparisons, and track
replay. Public FastF1 data for the **2024 Bahrain Grand Prix** is bundled as JSON;
the deployed demo does not fetch race data. The initial dashboard shows a real
precomputed 500-iteration simulation across 2,772 strategies. Other seasons and
races remain available in the normal local application when demo mode is off.
Track replay is an illustration of simulated pace, not recorded car positions.

## Build and run

```sh
docker compose -f docker-compose.demo.yml up -d --build
curl -f http://127.0.0.1:8100/api/health
```

This Compose project has its own name, image, and loopback port. It does not
publish on ports 80/443 or join another application's networks. The resource
limits are 1 CPU and 1.5 GiB RAM; check actual free capacity before sharing a VM.
An independent reverse proxy route and HTTPS endpoint must be configured before
external visitors can access it. Do not replace Tidewatch's proxy configuration.
Do not run Compose shutdown commands from Tidewatch's directory or prune shared
Docker resources.

For a host without Docker, build the frontend locally, then package an allowlisted
release. The archive contains public demo data and application code; it excludes
AWS configuration, environment files, Git history, virtual environments, and the
143 MB FastF1 HTTP cache.

```sh
cd frontend
VITE_DEMO_MODE=true npm run build
cd ..
python3 scripts/package_release.py
```

Install `requirements-runtime.txt` in a dedicated Python 3.12 virtual environment,
then start the backend with `F1_DEMO_MODE=true` and `MPLCONFIGDIR` pointing to a
writable directory. It serves the built frontend and API on the same origin:

```sh
F1_DEMO_MODE=true MPLCONFIGDIR=/tmp/f1-matplotlib \
  .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8100 --limit-concurrency 12
```

## Regenerate demo data

With the development requirements installed, run from the repository root:

```sh
PYTHONPATH=. python scripts/prepare_demo.py --with-run
```

This preparation step may access FastF1 upstream services. Runtime demo mode uses
the exported JSON only. No Python pickle or HTTP cache is shipped.

## Deployment status

Public URL: **https://d2s2fm4gy9s0l9.cloudfront.net**

Current release: **`ce6422ec53e1`** — previous UI restored, 24 October 2026.

AWS profile: `sha`; region: `eu-north-1`. The native Python service shares the
existing Lightsail VM with Tidewatch. It has its own
user (`f1strategy`), virtual environment, releases in `/opt/f1-strategy-ai`, data
in `/var/lib/f1-strategy-ai`, and systemd service (`f1-strategy`). The frontend and
API are served on `127.0.0.1:8100`. Its memory limit is 768 MB and CPU limit is
70% of one CPU, with low scheduling priority. nginx allows only one expensive
API request at a time, returning HTTP 429 when busy.

The separate nginx virtual host uses
`ec2-13-62-14-125.eu-north-1.compute.amazonaws.com`; Tidewatch's default IP route
and service configuration were preserved. CloudFront distribution
`E39ENSISPQBR38` supplies the public HTTPS endpoint. The viewer connection uses
HTTPS; CloudFront connects to the public origin using HTTP. API caching is
disabled, including query-string forwarding. This is a small public demo, not
a deployment for private data or sustained multi-user simulation workloads.

No additional VM was created. CloudFront usage can incur additional charges.
Docker is an optional alternative; the shared host uses native systemd services.

## Repeat a deployment

1. Run tests and build the demo frontend, then `python3 scripts/package_release.py`.
2. Copy the archive and `deploy/install-release.sh` to the host using temporary
   Lightsail SSH credentials. Keep SSH limited to your current IP and preserve
   any existing allowlist entries.
3. Run `sudo bash /tmp/install-release.sh /tmp/f1-strategy-demo.tar.gz RELEASE_ID`,
   using the first 12 characters of the archive SHA256 as the release ID. Each
   release ID must be new; the installer does not overwrite an existing release.
4. For nginx changes, install only `deploy/f1-strategy.nginx.conf` as
   `/etc/nginx/sites-available/f1-strategy`, then run `sudo nginx -t` before
   `sudo systemctl reload nginx`. Do not replace the Tidewatch file.
5. Run `python3 scripts/smoke_demo.py https://d2s2fm4gy9s0l9.cloudfront.net`.
   Check Tidewatch's original route and service status again.

The CloudFront creation configuration is recorded in `deploy/cloudfront.json`.
Do not create a second distribution on ordinary code updates; no invalidation
is needed while caching is disabled. If the VM IP changes, update both the origin
hostname and the F1 nginx virtual host.

For rollback, restore `/opt/f1-strategy-ai/current` to the path recorded in
`/opt/f1-strategy-ai/previous-release`, then restart **only** `f1-strategy`.
The virtual environment is shared between F1 releases; dependency changes may
also require reinstalling the previous release's runtime requirements.

## Verification — 23 October 2026

- 122 backend tests passed; the React production build passed.
- Public HTTPS smoke checks passed for the frontend, health, season/race list,
  session geometry and 20-driver timing tower, precomputed run, fresh simulation,
  CSV export, rival analysis/replay, and four PNG plot endpoints.
- Active release: `ce6422ec53e1`.
- Tidewatch retained its original process ID, running since 06:59 UTC, and its
  service/nginx file hashes matched the pre-deployment baseline. Its original
  IP route and health endpoint remained operational.
- F1 service used approximately 140 MB RAM before the final simulation checks.

## PHP advisory check — 24 October 2026

The running Lightsail host was checked over SSH for CVE-2026-109618 and
CVE-2026-109619. No installed PHP packages, PHP executable on PATH, PHP/Apache
processes, or nginx PHP/FastCGI routes were found. A file search under `/opt`,
`/usr/local`, `/usr/bin`, `/usr/sbin`, `/snap`, and `/var/www` found no PHP runtime
or application scripts; the PHP-named files found in snaps were AppArmor policy
abstractions, not runtimes. The `php-crypt-gpg` dpkg entry had status `un`
(not installed).

F1 runs Python/Uvicorn; Tidewatch runs Node.js. Both systemd services and nginx
were active, F1 health returned `ok`, Tidewatch returned HTTP 200, and `nginx -t`
passed. No affected PHP runtime was identified, so no PHP update was needed.
This check covers the shared host at that time, not other account resources or
software installed later. The temporary single-IP SSH rule used for this audit
was removed afterward, preserving the original SSH allowlist.

## UI rollback — 24 October 2026

At the user's request, the UI refresh was reversed. The local frontend files
were restored byte for byte to the pre-refresh version (`4c4554c`), the added UI
notes and checks were removed, and the original demo production build passed.
The prior PHP advisory audit was preserved.

The retained release `ce6422ec53e1` was restored on the existing VM and only
`f1-strategy` was restarted. The public CloudFront page serves the original
Mission Control UI again. F1 health passed, Tidewatch retained its process ID,
all nginx site and Tidewatch unit hashes remained unchanged, and Tidewatch's
original nginx health route remained operational. The temporary deployment
SSH rule was removed after rollback.
