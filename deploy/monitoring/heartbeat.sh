#!/usr/bin/env bash
# Find-a-Line: the heartbeat of the monitoring (docs/monitoring.md, G1; docs/deployment.md,
# section 15). Run every minute by findaline-heartbeat.timer: asks the site through nginx on this
# host (https://<site>/ resolved to 127.0.0.1, so its certificate is checked too) and, when it
# answers 200, pings HEARTBEAT_URL (a check of healthchecks.io; /etc/findaline-monitoring.env,
# given by the unit). healthchecks.io reports a missing ping to ntfy itself: the server, nginx or
# the site down, or this timer stopped, which Grafana on the same server could not report. The
# site's name is the host of FINDALINE_PUBLIC_URL in the checkout's findaline.env.
set -euo pipefail
REPO=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)

site=$(sed -n 's#^FINDALINE_PUBLIC_URL=https://\([^/]*\).*#\1#p' "$REPO/findaline.env" | tail -n 1)
[ -n "$site" ] || { echo "no FINDALINE_PUBLIC_URL=https://... in $REPO/findaline.env" >&2; exit 1; }
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 --resolve "$site:443:127.0.0.1" "https://$site/") || true
if [ "$code" != 200 ]; then
    echo "https://$site/ answered ${code:-nothing}: no ping" >&2
    exit 1
fi
# Not configured yet (setup lists it among its TODOs): nothing to ping, and nothing to log
[ -n "${HEARTBEAT_URL:-}" ] || exit 0
curl -fsS -m 10 --retry 2 -o /dev/null "$HEARTBEAT_URL"
