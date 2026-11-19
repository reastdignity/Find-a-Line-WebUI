#!/bin/bash
# The Husarnet sidecar's entry point and healthcheck (husarnet-sidecar.Dockerfile copies it to
# /usr/local/bin/husarnet.sh; compose.yaml: service `husarnet`). README.md of deploy/mirror, "The
# publishing account". Written against Husarnet's nightly daemon 2.0.349 (the 3.0 protocol; its
# sources at that build: core/husarnet/api_server/server.cpp, config_manager.cpp, husarnet_manager.cpp,
# cli/api_claim_command.go).
#
#   husarnet.sh start    the daemon, then the join (a claim) if the device is not joined yet
#   husarnet.sh health   exit 0 only when up and reachable by one of the user's devices (below)
#
# The daemon takes no join code at all (none of its settings is one): the code goes only to the CLI's
# `husarnet claim`, which hands it to Husarnet's dashboard through the daemon (POST
# /api/forward/v3/device/manage/claim, with the API token, which only root here reads; the daemon logs
# the path, not the body). The daemon's output goes nowhere.
#
# The join runs once: when the device is claimed (the dashboard's answer, kept in the state folder) or
# a peer of the user's is on its allow list, the daemon starts without a join and the code is not
# needed (it may be removed from .env after the first join). Neither and no code: the script says so
# in the log and exits 1.
#
# Health, read from GET /api/status (no token needed) with jq:
# - up: live.health.summary true, which the daemon sets from a base server connection AND its event bus
#   connection to Husarnet's control plane; that connection exists only while the control plane is on,
#   and only then does the daemon enforce its allow list (with HUSARNET_ENABLE_CONTROL_PLANE=false it
#   lets every peer through and starts no event bus: config_manager.cpp allowEveryone);
# - a peer of the user's on the allow list: an address of config.dashboard.peers (the devices the
#   dashboard puts there because they share the door's network, the publishing PC) or of
#   config.user_config.local-whitelist, other than Husarnet's own servers, which the daemon always lets
#   in (config.license.api_servers, eb_servers, websetup_host).
set -u

API=${HUSARNET_DAEMON_API_HOST:-127.0.0.1}:${HUSARNET_DAEMON_API_PORT:-16216}   # the daemon's defaults (its settings of these names)

status() {  # the body of the daemon's GET /api/status (no token needed), nothing on failure
    { exec 3<> "/dev/tcp/${API%:*}/${API#*:}"; } 2> /dev/null || return 1   # quiet while the daemon starts
    printf 'GET /api/status HTTP/1.0\r\nHost: %s\r\n\r\n' "$API" >&3
    timeout 5 cat <&3 | tr -d '\r' | sed '1,/^$/d'
    exec 3<&-
}

# jq filters over the status: the user's peers (allowed, not Husarnet's own; addresses compared in
# one written form, since the dashboard's and the licence's lists come as their servers send them)
# and whether it is up
USER_PEERS='def norm: ascii_downcase | split("::") as $p
        | (if ($p | length) == 2
           then ($p[0] | split(":") | map(select(. != ""))) as $a | ($p[1] | split(":") | map(select(. != ""))) as $b
                | $a + [range(8 - ($a | length) - ($b | length)) | "0"] + $b
           else split(":") end)
        | map(("0000" + .)[-4:]) | join(":");
    .result.config as $c
    | ([($c.dashboard.peers // [])[].address] + ($c.user_config["local-whitelist"] // []) | map(select(. != null) | norm))
    - (($c.license.api_servers // []) + ($c.license.eb_servers // []) + [$c.license.websetup_host] | map(select(. != null) | norm))
    | unique | .[]'
UP='.result.live.health.summary == true and .result.live.dashboard_connection == true
    and (.result.live.base_connection.type == "UDP" or .result.live.base_connection.type == "TCP")'
CLAIMED='.result.config.dashboard.is_claimed == true'

case ${1:-} in
    start)
        code=${HUSARNET_JOIN_CODE:-}
        unset HUSARNET_JOIN_CODE HUSARNET_JOINCODE JOINCODE
        husarnet-daemon > /dev/null 2>&1 &
        daemon=$!
        trap 'kill -TERM "$daemon" 2> /dev/null' TERM INT
        s=""
        for _ in $(seq 60); do
            s=$(status) && printf '%s' "$s" | jq -e '.result.version' > /dev/null 2>&1 && break
            s=""
            sleep 1
        done
        if [ -z "$s" ]; then
            echo "husarnet.sh: the daemon's API did not answer; no join" >&2
        elif printf '%s' "$s" | jq -e "$CLAIMED" > /dev/null 2>&1 || [ -n "$(printf '%s' "$s" | jq -r "$USER_PEERS" 2> /dev/null)" ]; then
            echo "husarnet.sh: joined before (claimed, or a peer on the allow list): no join" >&2
        elif [ -n "$code" ]; then
            out=$(timeout 30 husarnet claim "$code" --hostname "${HUSARNET_HOSTNAME:-findaline-mirror-door}" 2>&1)
            if [ $? -ne 0 ] || printf '%s' "$out" | grep -qiE 'error|failed'; then
                echo "husarnet.sh: the join request failed (husarnet claim)" >&2
            fi
            unset out
        else
            echo "husarnet.sh: not joined (not claimed, no peer on the allow list) and no HUSARNET_JOIN_CODE: put the join code into .env for the first join" >&2
            kill -TERM "$daemon" 2> /dev/null
            wait "$daemon"
            exit 1
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
        printf '%s' "$s" | jq -e "$UP" > /dev/null 2>&1 || exit 1
        [ -n "$(printf '%s' "$s" | jq -r "$USER_PEERS" 2> /dev/null)" ]
        ;;
    *)
        echo "usage: husarnet.sh start|health" >&2
        exit 2
        ;;
esac
