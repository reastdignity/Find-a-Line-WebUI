#!/bin/sh
# The mirror's entry point (docs/mirror-hosting/spec.md, A.1, A.5, A.7, A.9), run as uid 101 on a
# read-only root with /tmp a tmpfs; compose.yaml runs it under `init: true`, which reaps the
# cleanup loop's children.
#
#   mirror-start serve   (the default) write what nginx includes into /tmp/mirror, start the
#                        cleanup loop, then nginx in the foreground
#   mirror-start check   the same files, then `nginx -t` (the settings checked without serving)
#   mirror-start health  the healthcheck: robots.txt on the loopback and a fresh heartbeat
#   mirror-start cleanup [cap]  one pass of the cleanup now, with another size cap (bytes) if
#                        given: the check script's hook
#
# Settings (compose.yaml passes them from .env):
#   MIRROR_TRUSTED_ADDRESSES  at most four single IPv4 addresses, comma-separated (the site's
#                             server); empty for none. Anything else (a network such as 0.0.0.0/0,
#                             a fifth address, a word) refuses to start: a network would take
#                             every visitor out of the visitors' total.
#   MIRROR_SUBNET             the project's network; X-Real-IP is believed from it
#   MIRROR_CONTACT            the contact for abuse and takedown, shown on the landing page
#
# The log: nginx writes one file a day, access-YYYY-MM-DD.log (UTC days); log.conf names today's
# file. The loop: every HEARTBEAT_SECONDS (and at each midnight) it touches the heartbeat the
# healthcheck reads (a dead loop makes the container unhealthy); when the day has changed it writes
# log.conf for the new day and reloads nginx, and tries again at its next turn until the reload
# worked (a request still running then is written into the file of the day it began); every
# CLEANUP_SECONDS (and at start) it deletes each log file named for a real day KEEP_DAYS or more
# days back.
set -eu

RUN=/tmp/mirror
LOGS=/var/log/mirror
TEMPLATE=/usr/share/findaline-mirror/index.html.in
KEEP_DAYS=14
# The log folder's size bound (U45): provisionally 2 GB, the user decides the number
LOG_CAP_BYTES=2000000000
CLEANUP_SECONDS=3600
HEARTBEAT_SECONDS=30
HEARTBEAT_MAX_AGE=120
MAX_TRUSTED=4

die() {
    echo "findaline-mirror: $*; not starting" >&2
    exit 64
}

# A single IPv4 address in dotted decimal, no leading zeros
is_ipv4() {
    case $1 in
        *[!0-9.]* | .* | *. | *..* | '') return 1 ;;
    esac
    _ifs=$IFS
    IFS=.
    # shellcheck disable=SC2086
    set -- $1
    IFS=$_ifs
    [ $# -eq 4 ] || return 1
    for _octet in "$@"; do
        case $_octet in '' | 0?*) return 1 ;; esac
        [ ${#_octet} -le 3 ] && [ "$_octet" -le 255 ] || return 1
    done
}

trusted_conf() {
    _list=$(printf '%s' "${MIRROR_TRUSTED_ADDRESSES:-}" | tr -d ' \t')
    : > "$RUN/trusted.conf"
    [ -n "$_list" ] || return 0
    case $_list in
        ,* | *, | *,,*) die "MIRROR_TRUSTED_ADDRESSES has an empty entry" ;;
    esac
    _count=0
    _seen=,
    _old=$IFS
    IFS=,
    for _address in $_list; do
        IFS=$_old
        is_ipv4 "$_address" || die "MIRROR_TRUSTED_ADDRESSES: '$_address' is not a single IPv4 address"
        case $_seen in *",$_address,"*) die "MIRROR_TRUSTED_ADDRESSES names '$_address' twice" ;; esac
        _seen="$_seen$_address,"
        _count=$((_count + 1))
        [ $_count -le $MAX_TRUSTED ] || die "MIRROR_TRUSTED_ADDRESSES: more than $MAX_TRUSTED addresses"
        echo "$_address trusted;" >> "$RUN/trusted.conf"
    done
    IFS=$_old
}

realip_conf() {
    _subnet=${MIRROR_SUBNET:-}
    _address=${_subnet%/*}
    _bits=${_subnet#*/}
    [ "$_subnet" != "$_address" ] && is_ipv4 "$_address" || die "MIRROR_SUBNET: '$_subnet' is not an IPv4 network"
    case $_bits in '' | *[!0-9]* | 0?*) die "MIRROR_SUBNET: '$_subnet' has no prefix length" ;; esac
    # The project's own network: a /16 at most (Docker's pools), never the whole internet
    [ "$_bits" -ge 16 ] && [ "$_bits" -le 29 ] || die "MIRROR_SUBNET: the prefix length must be 16 to 29"
    echo "set_real_ip_from $_subnet;" > "$RUN/realip.conf"
}

landing_page() {
    _contact=${MIRROR_CONTACT:-}
    [ -n "$_contact" ] || die "MIRROR_CONTACT is empty: the landing page names a contact for abuse and takedown"
    [ ${#_contact} -le 200 ] || die "MIRROR_CONTACT is longer than 200 characters"
    _newline='
'
    case $_contact in *"$_newline"* | *"$(printf '\r')"*) die "MIRROR_CONTACT has a line break" ;; esac
    # HTML-escaped, then escaped for sed's replacement
    _html=$(printf '%s' "$_contact" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' \
        -e 's/"/\&quot;/g' -e "s/'/\&#39;/g")
    _replacement=$(printf '%s' "$_html" | sed -e 's/[\\|&]/\\&/g')
    mkdir -p "$RUN/site"
    sed "s|@MIRROR_CONTACT@|$_replacement|g" "$TEMPLATE" > "$RUN/site/index.html"
}

# The access_log line for the day's file (UTC), included by nginx.conf
log_conf() {
    echo "access_log $LOGS/access-$1.log mirror if=\$mirror_loggable;" > "$RUN/log.conf.new"
    mv "$RUN/log.conf.new" "$RUN/log.conf"
}

# A new day: log.conf names its file and nginx reloads. log.day (the day in effect) changes only
# when the reload worked (new workers, the day's file there); otherwise the next turn tries again
switch_day() {
    _today=$(date -u +%F)
    _master=$(cat /tmp/nginx.pid 2> /dev/null) || return 0
    _before=$(pgrep -P "$_master" nginx | sort | tr '\n' ' ')
    log_conf "$_today"
    kill -HUP "$_master" 2> /dev/null || return 0
    sleep 2
    _after=$(pgrep -P "$_master" nginx | sort | tr '\n' ' ')
    if [ -f "$LOGS/access-$_today.log" ] && [ -n "$_after" ] && [ "$_after" != "$_before" ]; then
        echo "$_today" > "$RUN/log.day"
    fi
}

prepare() {
    mkdir -p "$RUN"
    log_conf "$(date -u +%F)"
    date -u +%F > "$RUN/log.day"
    trusted_conf
    realip_conf
    landing_page
}

# The day of a log file's name, only when the name is access-<a real date>.log (else fails)
log_day() {
    _name=${1##*/access-}
    _name=${_name%.log}
    case $_name in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
        *) return 1 ;;
    esac
    [ "$(date -u -d "$_name 00:00:00" +%F 2> /dev/null)" = "$_name" ] || return 1
    printf '%s' "$_name"
}

# The size bound: while the access-<day>.log files together are above the cap, the oldest day's
# file goes (the glob is in name order, which is day order); today's file never goes, and when it
# alone is above the cap it is emptied in place: nginx writes it with O_APPEND, so it goes on at
# the new end, without a reload or a restart (the heartbeat is untouched)
cap_logs() {
    _cap=$1
    _today=$(date -u +%F)
    _total=0
    for _file in "$LOGS"/access-*.log; do
        [ -f "$_file" ] && log_day "$_file" > /dev/null || continue
        _total=$((_total + $(stat -c %s "$_file")))
    done
    for _file in "$LOGS"/access-*.log; do
        [ "$_total" -gt "$_cap" ] || break
        [ -f "$_file" ] && log_day "$_file" > /dev/null || continue
        [ "${_file##*/}" = "access-$_today.log" ] && continue
        _size=$(stat -c %s "$_file")
        rm -f -- "$_file"
        _total=$((_total - _size))
    done
    if [ "$_total" -gt "$_cap" ] && [ -f "$LOGS/access-$_today.log" ]; then
        : > "$LOGS/access-$_today.log"
    fi
}

# Deletes each access-YYYY-MM-DD.log whose day is KEEP_DAYS or more days back (UTC), then applies
# the size bound
cleanup() {
    _now=$(date -u +%s)
    _cutoff=$(date -u -d "@$((_now - KEEP_DAYS * 86400))" +%Y%m%d)
    for _file in "$LOGS"/access-*.log; do
        [ -f "$_file" ] || continue
        _day=${_file##*/access-}
        _day=${_day%.log}
        case $_day in
            [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
            *) continue ;;
        esac
        # Only a real date (2000-13-45 or 0000-00-00 are left alone)
        [ "$(date -u -d "$_day 00:00:00" +%F 2> /dev/null)" = "$_day" ] || continue
        if [ "$(printf '%s' "$_day" | tr -d -)" -le "$_cutoff" ]; then
            rm -f -- "$_file"
        fi
    done
    cap_logs "${1:-$LOG_CAP_BYTES}"
}

cleanup_loop() {
    _last=0
    while :; do
        _now=$(date -u +%s)
        if [ $((_now - _last)) -ge $CLEANUP_SECONDS ]; then
            cleanup
            _last=$_now
        fi
        if [ "$(date -u +%F)" != "$(cat "$RUN/log.day")" ]; then
            switch_day
        fi
        touch "$RUN/heartbeat"
        # Wake at midnight too, so the new day's file starts within a second of it
        _left=$((86400 - $(date -u +%s) % 86400 + 1))
        [ $_left -lt $HEARTBEAT_SECONDS ] && sleep $_left || sleep $HEARTBEAT_SECONDS
    done
}

health() {
    wget -q -O /dev/null http://127.0.0.1:8080/robots.txt || return 1
    _beat=$(stat -c %Y "$RUN/heartbeat" 2>/dev/null) || return 1
    [ $(($(date -u +%s) - _beat)) -le $HEARTBEAT_MAX_AGE ]
}

case "${1:-serve}" in
    serve)
        prepare
        cleanup_loop </dev/null >/dev/null &
        echo $! > "$RUN/cleanup.pid"
        echo "findaline-mirror: starting ($(wc -l < "$RUN/trusted.conf") trusted addresses)"
        exec nginx -g 'daemon off;'
        ;;
    check)
        prepare
        exec nginx -t -q
        ;;
    cleanup)
        # One pass of the cleanup now, with another cap if given (tests/mirror_check.sh's hook)
        cleanup "${2:-$LOG_CAP_BYTES}"
        ;;
    health)
        health
        ;;
    *)
        echo "usage: mirror-start [serve|check|health|cleanup [cap]]" >&2
        exit 2
        ;;
esac
