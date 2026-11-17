#!/usr/bin/env bash
# Fill the status page's history for the days before monitoring started.
# Gathers the evidence on this Mac and runs app.backfill in the backend
# container. Re-runnable; pass --dry-run to only print the estimate.
set -euo pipefail

CONTAINER="${CONTAINER:-wololo-backend}"
TUNNEL_LOG="${TUNNEL_LOG:-$HOME/Library/Logs/edilson-cloudflared-tunnel.log}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"; docker exec "$CONTAINER" rm -f /tmp/backfill-tunnel.log /tmp/backfill-cloudflare.json >/dev/null 2>&1 || true' EXIT

args=()
if [[ -f "$TUNNEL_LOG" ]]; then
  docker cp "$TUNNEL_LOG" "$CONTAINER:/tmp/backfill-tunnel.log"
  args+=(--tunnel-log /tmp/backfill-tunnel.log)
else
  echo "No tunnel log at $TUNNEL_LOG; skipping it" >&2
fi

if [[ -n "${CLOUDFLARE_API_TOKEN:-}" || -f "$HOME/.config/cloudflare/analytics-token" ]]; then
  python3 -I "$SCRIPT_DIR/cloudflare-status-evidence.py" > "$work/cloudflare.json"
  docker cp "$work/cloudflare.json" "$CONTAINER:/tmp/backfill-cloudflare.json"
  args+=(--cloudflare /tmp/backfill-cloudflare.json)
else
  echo "No Cloudflare token; skipping Cloudflare analytics" >&2
fi

docker exec "$CONTAINER" python -m app.backfill "${args[@]}" "$@"
