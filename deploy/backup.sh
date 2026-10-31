#!/usr/bin/env bash
# Find-a-Line: back up the public site (docs/deployment.md, "Backups"). Run as root on the host,
# by hand or from findaline-backup.timer, with the settings of /etc/findaline-backup.env:
#   RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE (and the credentials of the repository's service)
#   FINDALINE_IMAGE            the site's image (default findaline:local, compose.yaml)
#   FINDALINE_DATA_VOLUME      the data volume (default findaline_data)
#   FINDALINE_ACCOUNTS_VOLUME  the accounts volume (default findaline_accounts)
#   BACKUP_STAGE               where the consistent copies of the databases go (default below)
# and of /etc/findaline-monitoring.env (the unit reads both; docs/deployment.md, section 15):
#   BACKUP_PING_URL            healthchecks.io's ping URL of the backup check (empty: no ping)
#
# 1. A consistent copy of each SQLite database with SQLite's backup API, which is safe while the
#    site runs (WAL mode). It runs in a throwaway container of the site's image that mounts the
#    volumes, as the containers' user (uid 10001), without network: the volumes' folders under
#    the Docker root (/var/lib/docker, mode 0710) are closed to that uid on the host, and SQLite
#    run as root could leave -wal/-shm files the app can no longer open. Each copy is checked
#    (integrity_check) before it replaces the previous one.
# 2. restic (as root, which can read the volume): the copies and runs/ into the repository
#    (encrypted, deduplicated, off-site), then the old snapshots are forgotten and the
#    repository checked.
# 3. At the end of every run, also a failed one: backup.json for the monitoring (its time, success,
#    the last success, duration, what it added, the repository's size and snapshots; read by
#    Telegraf, deploy/monitoring/telegraf.conf) and the ping of healthchecks.io (its /fail URL
#    after a failure), so a backup that stops running or keeps failing is reported.
# The rest of the cache is downloaded again when needed, the Slovak mirror is a copy anyway.
set -euo pipefail

IMAGE=${FINDALINE_IMAGE:-findaline:local}
DATA_VOLUME=${FINDALINE_DATA_VOLUME:-findaline_data}
ACCOUNTS_VOLUME=${FINDALINE_ACCOUNTS_VOLUME:-findaline_accounts}
STAGE=${BACKUP_STAGE:-/var/backups/findaline}
STATE=${FINDALINE_MONITORING_DIR:-/var/lib/findaline-monitoring}
STARTED=$(date +%s)
ADDED=0
REPO_BYTES=0
SNAPSHOTS=0

# Step 3, from the exit trap: it runs whatever ends the script (set -e, exit 1), with its status
finish() {
    local status=$? success=0 last=0 now tmp
    trap - EXIT
    set +e
    now=$(date +%s)
    if [ "$status" = 0 ]; then
        success=1
        last=$now
    elif [ -f "$STATE/backup.json" ]; then
        # The last success of before: a failure must not reset the age of the last good backup
        last=$(sed -n 's/.*"last_success": *\([0-9]*\).*/\1/p' "$STATE/backup.json")
    fi
    if install -d -m 755 "$STATE" && tmp=$(mktemp "$STATE/.backup.json.XXXXXX"); then
        printf '{"time": %d, "success": %d, "last_success": %d, "seconds": %d, "added_bytes": %d, "repo_bytes": %d, "snapshots": %d}\n' \
            "$now" "$success" "${last:-0}" "$((now - STARTED))" "$ADDED" "$REPO_BYTES" "$SNAPSHOTS" > "$tmp"
        chmod 644 "$tmp"
        mv -f "$tmp" "$STATE/backup.json"
    else
        echo "$STATE/backup.json not written" >&2
    fi
    if [ -n "${BACKUP_PING_URL:-}" ]; then
        local url=$BACKUP_PING_URL
        [ "$success" = 1 ] || url=${url%/}/fail
        curl -fsS -m 10 --retry 3 -o /dev/null "$url" || echo "the ping of healthchecks.io failed" >&2
    fi
    exit "$status"
}
trap finish EXIT

: "${RESTIC_REPOSITORY:?set it in /etc/findaline-backup.env}"
: "${RESTIC_PASSWORD_FILE:?set it in /etc/findaline-backup.env}"

# `docker run -v name:...` would create a missing volume, empty: check that both exist
for volume in "$DATA_VOLUME" "$ACCOUNTS_VOLUME"; do
    docker volume inspect "$volume" >/dev/null || { echo "no Docker volume $volume" >&2; exit 1; }
done
RUNS="$(docker volume inspect --format '{{.Mountpoint}}' "$DATA_VOLUME")/runs"

install -d -m 700 -o 10001 -g 10001 "$STAGE"

# The copies: <stage>/data/... from the data volume, <stage>/accounts/... from the accounts one
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true \
    --user 10001:10001 --entrypoint python \
    --volume "$DATA_VOLUME:/data" --volume "$ACCOUNTS_VOLUME:/accounts" --volume "$STAGE:/stage" \
    "$IMAGE" -c '
import os, shutil, sqlite3, sys

os.umask(0o077)  # the copies hold the sessions (as hashes) and the audit log: root and uid 10001 only
DATABASES = ["data/jobs.sqlite", "data/audit.sqlite", "data/cache/osm/nominatim.sqlite",
             "accounts/accounts.sqlite"]
failed = False
for name in DATABASES:
    source, target = "/" + name, "/stage/" + name
    if not os.path.isfile(source):
        print("not there (yet):", source)
        continue
    os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
    part = target + ".part"
    if os.path.exists(part):
        os.remove(part)
    with sqlite3.connect(source, timeout=60) as db, sqlite3.connect(part) as copy:
        db.backup(copy)
        check = copy.execute("PRAGMA integrity_check").fetchone()[0]
    copy.close()
    db.close()
    if check != "ok":
        print("integrity_check of the copy of", source + ":", check, file=sys.stderr)
        failed = True
        continue
    os.replace(part, target)
    print("copied:", source, os.path.getsize(target), "bytes")
# The layout marker of the cache: without it a restored cache/ (nominatim.sqlite) is refused
if os.path.isfile("/data/cache/LAYOUT"):
    os.makedirs("/stage/data/cache", mode=0o700, exist_ok=True)
    shutil.copyfile("/data/cache/LAYOUT", "/stage/data/cache/LAYOUT")
sys.exit(1 if failed else 0)
'

restic backup --tag findaline --exclude "$RUNS/_viewer" "$STAGE" "$RUNS"
restic forget --tag findaline --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune
restic check

# The numbers of backup.json; the backup is done, so a failure here only leaves them 0. What the
# run added is in the newest snapshot's summary (restic 0.17 and later), the size of the
# repository (compressed and deduplicated, as stored) in `restic stats --mode raw-data`.
numbers=$( { restic snapshots --json --tag findaline --latest 1 && restic stats --json --mode raw-data; } 2>/dev/null \
    | python3 -c '
import json, sys
snapshots, stats = (json.loads(line) for line in sys.stdin.read().splitlines()[-2:])
summary = snapshots[-1].get("summary", {}) if snapshots else {}
print(int(summary.get("data_added", 0)), int(stats.get("total_size", 0)), int(stats.get("snapshots_count", 0)))
' 2>/dev/null) || numbers="0 0 0"
read -r ADDED REPO_BYTES SNAPSHOTS <<< "$numbers"
