#!/bin/bash
# The Husarnet sidecar's entry point and healthcheck (compose.yaml: service `husarnet`, the image
# husarnet/husarnet, mounted read-only at /door/husarnet.sh). README.md of deploy/mirror, "The
# publishing account".
#
#   husarnet.sh start    the daemon, then the join
#   husarnet.sh health   exit 0 only when joined and up (below)
#
# Why not the image's own entry point (husarnet-docker, v2.0.180): it hands the join code to the
# daemon in its environment, and the daemon then shows it to every process of the network namespace
# without its API token, which `sftp` shares: GET /api/status carries it under user_settings.joinCode
# and GET /api/logs/get in two lines ("Overriding user setting joinCode=...", "Sending join request
# to websetup (joincode: ...)"); only the POST calls need the token (core/api_server/server.cpp). So
# the daemon starts without the code, its log verbosity is raised to warnings (2) through the API,
# and only then the CLI hands it the code (POST /api/join, with the token, which only root here
# reads): the code is then in neither answer. The daemon's output goes nowhere (as the image's
# entry point does without HUSARNET_DEBUG, which would print the code to Docker's log).
#
# Why not the image's healthcheck: it runs `husarnet daemon wait daemon; exit 0`, healthy as soon
# as the API answers. And the daemon's is_joined is true even for a refused join code (websetup's
# init-response "invalid code" counts as the reply it waits for). Joined and up here: a base server
# connection, is_joined, and at least one address on the whitelist besides Husarnet's websetup
# server: one the dashboard put there because a peer shares the door's network, the publishing PC.
set -u

API=127.0.0.1:${HUSARNET_DAEMON_API_PORT:-16216}   # the daemon's default port (its setting of that name)

status() {  # the daemon's GET /api/status (no token needed), nothing on failure
    exec 3<> "/dev/tcp/${API%:*}/${API#*:}" || return 1
    printf 'GET /api/status HTTP/1.0\r\nHost: %s\r\n\r\n' "$API" >&3
    timeout 5 cat <&3
    exec 3<&-
}

case ${1:-} in
    start)
        code=${HUSARNET_JOIN_CODE:-}
        unset HUSARNET_JOIN_CODE HUSARNET_JOINCODE JOINCODE
        if [ -z "$code" ]; then
            echo "husarnet.sh: HUSARNET_JOIN_CODE is empty" >&2
            exit 1
        fi
        husarnet-daemon > /dev/null 2>&1 &
        daemon=$!
        trap 'kill -TERM "$daemon" 2> /dev/null' TERM INT
        up=0
        for _ in $(seq 60); do
            if timeout 5 husarnet daemon logs settings > /dev/null 2>&1; then up=1; break; fi
            sleep 1
        done
        if [ "$up" = 1 ] && timeout 10 husarnet daemon logs verbosity 2 > /dev/null 2>&1; then
            timeout 30 husarnet join "$code" "${HUSARNET_HOSTNAME:-findaline-mirror-door}" > /dev/null 2>&1 ||
                echo "husarnet.sh: the join request failed" >&2
        else
            echo "husarnet.sh: the daemon's API did not answer; no join" >&2
        fi
        unset code
        wait "$daemon"
        rc=$?
        # After a TERM the first wait returns at once: wait for the daemon's end
        kill -0 "$daemon" 2> /dev/null && { wait "$daemon"; rc=$?; }
        exit "$rc"
        ;;
    health)
        s=$(status) || exit 1
        websetup=$(printf '%s\n' "$s" | sed -n 's/^ *"websetup_address": "\(.*\)",*$/\1/p')
        printf '%s\n' "$s" | grep -q '"base": true' || exit 1
        printf '%s\n' "$s" | grep -q '"is_joined": true' || exit 1
        peers=$(printf '%s\n' "$s" | sed -n '/^        "whitelist": \[/,/\]/p' | grep -o 'fc94:[0-9a-f:]*' | grep -vxF "$websetup")
        [ -n "$websetup" ] && [ -n "$peers" ]
        ;;
    *)
        echo "usage: husarnet.sh start|health" >&2
        exit 2
        ;;
esac
