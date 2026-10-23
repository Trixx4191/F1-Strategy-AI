#!/usr/bin/env bash
# Run on the inspected Ubuntu host with sudo. Only manages F1-owned paths.
set -euo pipefail
archive=${1:?Usage: install-release.sh ARCHIVE RELEASE_ID}
release_id=${2:?Supply an immutable release ID}
[[ "$release_id" =~ ^[a-zA-Z0-9-]+$ ]] || exit 2
base=/opt/f1-strategy-ai
release="$base/releases/$release_id"
[[ ! -e "$release" ]] || { echo 'Release already exists; use a new release ID.' >&2; exit 2; }
if [[ ! -x /usr/bin/python3 ]] || ! /usr/bin/python3 -c 'import ensurepip' 2>/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-venv
fi
id f1strategy >/dev/null 2>&1 || useradd --system --home-dir /var/lib/f1-strategy-ai --shell /usr/sbin/nologin f1strategy
install -d "$release" /var/lib/f1-strategy-ai/{cache,raw,processed,outputs,matplotlib}
chown -R f1strategy:f1strategy /var/lib/f1-strategy-ai
tar -xzf "$archive" -C "$release"
for directory in cache raw processed; do
  ln -s "/var/lib/f1-strategy-ai/$directory" "$release/data/$directory"
done
ln -s /var/lib/f1-strategy-ai/outputs "$release/outputs"
[[ -d "$base/venv" ]] || python3 -m venv "$base/venv"
OPENBLAS_NUM_THREADS=1 "$base/venv/bin/pip" install --only-binary=:all: -r "$release/requirements-runtime.txt"
# Keep the previous release available for an explicit rollback.
if [[ -L "$base/current" ]]; then
  readlink "$base/current" > "$base/previous-release"
fi
ln -sfn "$release" "$base/current-next"
mv -Tf "$base/current-next" "$base/current"
install -m 644 "$release/deploy/f1-strategy.service" /etc/systemd/system/f1-strategy.service
systemctl daemon-reload
systemctl enable --now f1-strategy
systemctl restart f1-strategy
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8100/api/health; then
    echo
    echo 'F1 service healthy; nginx activation is a separate validated step.'
    exit 0
  fi
  sleep 2
done
systemctl status f1-strategy --no-pager
exit 1
