#!/usr/bin/env bash
# Find-a-Line: what only root can read, for the monitoring (docs/monitoring.md, "Host facts";
# docs/deployment.md, section 15). Run as root by findaline-facts.timer every 5 minutes; writes
# /var/lib/findaline-monitoring/facts.json, which Telegraf reads (deploy/monitoring/telegraf.conf):
#   fail2ban            per jail (findaline, sshd; a jail that does not run is left out): banned
#                       now and in total, failed now and in total; numbers only, never an address
#   image_holes_bytes   unallocated bytes of the disk image (deploy/vps.sh --disk-image; left out
#                       without one), as `vps.sh check` counts them
#   updates_pending, updates_security   the packages apt would upgrade, and those of them from the
#                       security pocket; from apt's lists as its daily timer left them (nothing
#                       is downloaded here)
# `facts.sh check` runs `deploy/vps.sh check` instead (findaline-check.timer, daily) and writes
# check.json: the numbers of its ok and FAIL lines (a check that could not run counts as a FAIL).
# Each file is replaced at once (a temporary file renamed), so Telegraf never reads half of one.
set -euo pipefail
# Sourced, vps.sh only defines its functions and settings: image_holes, IMAGE_FILE, DEPLOY
# shellcheck source=SCRIPTDIR/../vps.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../vps.sh"
OUT=${FINDALINE_MONITORING_DIR:-/var/lib/findaline-monitoring}

# stdin into $OUT/$1, atomically, readable by Telegraf
publish() {
    local tmp
    tmp=$(mktemp "$OUT/.$1.XXXXXX")
    cat > "$tmp"
    chmod 644 "$tmp"
    mv -f "$tmp" "$OUT/$1"
}

# The arguments joined by ", "
join() {
    [ $# -gt 0 ] || return 0
    printf '%s' "$1"
    shift
    [ $# -eq 0 ] || printf ', %s' "$@"
}

# The number after "<label>:" in fail2ban-client's status of a jail ($2)
jail_count() {
    local n
    n=$(sed -n "s/.*$1:[[:space:]]*\([0-9][0-9]*\).*/\1/p" <<< "$2" | head -n 1)
    echo "${n:-0}"
}

# '"<jail>": {...}' for a jail that runs, nothing for one that does not
jail() {
    local status
    status=$(fail2ban-client status "$1" 2>/dev/null) || return 0
    printf '"%s": {"banned": %d, "banned_total": %d, "failed": %d, "failed_total": %d}' "$1" \
        "$(jail_count 'Currently banned' "$status")" "$(jail_count 'Total banned' "$status")" \
        "$(jail_count 'Currently failed' "$status")" "$(jail_count 'Total failed' "$status")"
}

facts() {
    local parts=() jails=() name entry upgrades
    parts+=("\"time\": $(date +%s)")
    for name in findaline sshd; do
        entry=$(jail "$name")
        [ -z "$entry" ] || jails+=("$entry")
    done
    parts+=("\"fail2ban\": {$(join "${jails[@]}")}")
    if [ -f "$IMAGE_FILE" ]; then
        parts+=("\"image_holes_bytes\": $(image_holes)")
    fi
    # A simulated upgrade: no lock (unattended-upgrades may hold it) and no cache file written
    # (the unit's file system is read-only); a failure leaves both numbers out, never 0
    if upgrades=$(apt-get -s -q -o Debug::NoLocking=1 -o Dir::Cache::pkgcache= -o Dir::Cache::srcpkgcache= \
            dist-upgrade 2>/dev/null); then
        parts+=("\"updates_pending\": $(grep -c '^Inst ' <<< "$upgrades" || true)")
        parts+=("\"updates_security\": $(grep '^Inst ' <<< "$upgrades" | grep -c -- '-security' || true)")
    else
        echo "apt-get -s dist-upgrade failed: the updates left out" >&2
    fi
    echo "{$(join "${parts[@]}")}" | publish facts.json
}

checks() {
    local out status=0 passed failed
    out=$(bash "$DEPLOY/vps.sh" check 2>&1) || status=$?
    printf '%s\n' "$out"  # the details stay in the journal
    passed=$(grep -c '^   ok: ' <<< "$out" || true)
    failed=$(grep -c '^FAIL: ' <<< "$out" || true)
    if [ "$status" != 0 ] && [ "$failed" = 0 ]; then
        failed=1  # stopped before its checks (STOP: ...)
    fi
    echo "{\"time\": $(date +%s), \"ok\": $passed, \"failed\": $failed}" | publish check.json
}

install -d -m 755 "$OUT"
case ${1:-} in
    "") facts ;;
    check) checks ;;
    *) echo "usage: $0 [check]" >&2; exit 1 ;;
esac
