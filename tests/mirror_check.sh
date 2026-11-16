#!/usr/bin/env bash
# The mirror stack's checks (deploy/mirror, docs/mirror-hosting/spec.md, section 4 "Tests"): one
# line "PASS|FAIL <id> <what>" per check, "INFO" lines for measurements; the exit code is the
# number of failures (capped at 100).
#
#   tests/mirror_check.sh               build the image, start compose.yaml + compose.test.yaml +
#                                       deploy/mirror/test/compose.check.yaml (a fixture tree in
#                                       volumes, test clients with fixed addresses), run every
#                                       check, the --live checks against the stand-in's published
#                                       port, then the publishing door (publish/compose.yaml +
#                                       test/compose.door-check.yaml, an SSH client in a container,
#                                       key pairs made at run time), then remove everything it made
#   tests/mirror_check.sh --self-test   the same, then each behaviour switched off in a variant of
#                                       the config (nginx.conf, start.sh, the landing page, the SWAG
#                                       conf) and the checks that must FAIL then: a check that
#                                       passes with its behaviour broken is a defect
#   tests/mirror_check.sh --live <url> [--master <folder>]
#                                       what needs no fixture, from this machine, against a running
#                                       mirror through its proxy (https://<host>); with --master,
#                                       every served index.json is also compared with the master's
#   --keep                              leave the test stack running (with the first two forms)
#
# Needs Docker with compose, bash, curl, awk and sha256sum on the host; --live also python3 (or
# python) for the JSON. On Windows run it with Git's bash (not WSL's), Docker Desktop on PATH.
# Settings (environment): MIRROR_CHECK_PROJECT (the compose project and the prefix of every Docker
# object it makes, default mirror-check), MIRROR_CHECK_SUBNET and MIRROR_CHECK_FRONT_SUBNET (two
# free /24 networks, defaults 172.29.142.0/24 and 172.29.143.0/24), MIRROR_CHECK_PORT (the stand-in's
# port on 127.0.0.1, default 8792), MIRROR_CHECK_DOOR_PORT (the door's, default 8793).
set -u
export MSYS_NO_PATHCONV=1

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$HERE")
MIRROR="$REPO/deploy/mirror"
CURL_IMAGE=curlimages/curl:8.23.0@sha256:3fb7e13e5d179a845c97d78204f3f1064d1907037f26a3ebf91710571151fd93
PROJECT=${MIRROR_CHECK_PROJECT:-mirror-check}
SUBNET=${MIRROR_CHECK_SUBNET:-172.29.142.0/24}
FRONT=${MIRROR_CHECK_FRONT_SUBNET:-172.29.143.0/24}
PORT=${MIRROR_CHECK_PORT:-8792}
DOOR_PORT=${MIRROR_CHECK_DOOR_PORT:-8793}
CONTACT='abuse@example.org <check&co>'
CONTACT_HTML='abuse@example.org &lt;check&amp;co&gt;'
PRIVACY="An installation that downloads from the project's data server shows it its address and which tiles it asks for. The server writes down the time, the address, the dataset (not the tile), the size, whether the request was served or refused, how long it took, and the Find-a-Line version of each request. It keeps this for 14 days, to hold the service within its limits, and uses it for nothing else. To never contact the data server, set FINDALINE_MIRROR_URL to empty; the regions it serves then use coarser data."

declare -A OUT=()
FAILS=0
QUIET=0

result() {  # <id> PASS|FAIL <text>
    OUT[$1]=$2
    [ "$2" = PASS ] || FAILS=$((FAILS + 1))
    [ "$QUIET" = 1 ] || echo "$2 $1 $3"
}
check() {  # <id> <text> <command...>: PASS when the command succeeds
    local id=$1 text=$2
    shift 2
    if "$@"; then result "$id" PASS "$text"; else result "$id" FAIL "$text"; fi
}
eq() {  # <id> <text> <got> <want>
    if [ "$3" = "$4" ]; then result "$1" PASS "$2 (got $3)"; else result "$1" FAIL "$2 (got '$3', want '$4')"; fi
}
info() { [ "$QUIET" = 1 ] || echo "INFO $*"; }
skip() {  # <id> <why>: a check that could not run here (not a PASS; the acceptance needs it run)
    OUT[$1]=SKIP
    [ "$QUIET" = 1 ] || echo "SKIP $1 $2"
}
TAGS=" base hold probe rate forged swag th ka day send refuse local dsprobe dsserved "
tag() {  # <tag>: its number (the log's "v" holds only version-shaped tokens: <MARK>.<number>)
    local before=${TAGS%% $1 *}
    printf '%s' "$before" | wc -w | tr -d ' '
}
ua() {  # [tag]: this run's User-Agent; the log's "v" is "<MARK>.<tag's number>", e.g. "8.4321.4"
    printf 'Find-a-Line/%s (highline finder; +https://site.example; contact: someone@example.org)' "$MARK.$(tag "${1:-base}")"
}
has() { printf '%s\n' "$1" | grep -qiE "$2"; }
hasnt() { ! printf '%s\n' "$1" | grep -qiE "$2"; }
between() { awk -v v="$1" -v lo="$2" -v hi="$3" 'BEGIN { exit !(v + 0 >= lo + 0 && v + 0 <= hi + 0) }'; }
hostpath() { if command -v cygpath > /dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
# The host's curl on Windows is a native program: /dev/null is NUL there
if command -v cygpath > /dev/null 2>&1; then NULLDEV=NUL; else NULLDEV=/dev/null; fi
now() { date +%s.%N | cut -c1-14; }

# ---------------------------------------------------------------- the live checks (no fixture)

live_checks() {  # <url> [master folder]: from this machine, through the proxy
    local U=${1%/} master=${2:-} ua h c py out
    ua="Find-a-Line/check-live (mirror_check.sh; +https://site.example; contact: someone@example.org)"
    lc() { curl -sS -A "$ua" -m 60 "$@" 2> /dev/null; }
    h=$(lc -D - -o "$NULLDEV" "$U/robots.txt" | tr -d '\r')
    eq LV01 "robots.txt: 200 text/plain; charset=utf-8" "$(printf '%s\n' "$h" | head -1 | cut -d' ' -f2) $(printf '%s\n' "$h" | grep -i '^content-type:' | cut -d' ' -f2-)" "200 text/plain; charset=utf-8"
    check LV02 "robots.txt disallows everything" has "$(lc "$U/robots.txt")" '^Disallow: /$'
    check LV03 "headers of an answer: nosniff, Cross-Origin-Resource-Policy, X-Robots-Tag" \
        eval 'has "$h" "^x-content-type-options: nosniff$" && has "$h" "^cross-origin-resource-policy: same-origin$" && has "$h" "^x-robots-tag: noindex$"'
    check LV04 "no Access-Control-*, Retry-After or X-Accel-Buffering towards the visitor; no version in Server" \
        eval 'hasnt "$h" "^access-control-" && hasnt "$h" "^retry-after" && hasnt "$h" "^x-accel-buffering" && hasnt "$h" "^server: [^ ]*/[0-9]"'
    out=$(lc -o "$NULLDEV" -w '%{http_code} %{content_type}' "$U/")
    eq LV05 "landing page: 200 text/html; charset=utf-8" "$out" "200 text/html; charset=utf-8"
    check LV06 "the landing page carries the privacy text word for word" \
        eval '[ "$(lc "$U/" | sed -e "s/<[^>]*>//g" | tr -s " \t\r\n" "    " | grep -cF "$PRIVACY")" -ge 1 ]'
    c=""
    for p in /v1/cubes/ /v1/cache/ /v1/cubes/x.bin /v1/tiles/ /outside.txt /v1/tiles/.x /index.html; do
        c="$c $(lc -o "$NULLDEV" -w '%{http_code}' "$U$p")"
    done
    eq LV07 "reserved, unknown and dot paths: 404" "$c" " 404 404 404 404 404 404 404"
    eq LV08 "a query string: 400" "$(lc -o "$NULLDEV" -w '%{http_code}' "$U/robots.txt?x=1")" 400
    eq LV09 "PUT and DELETE: 405" "$(lc -o "$NULLDEV" -w '%{http_code}' -X PUT -d x "$U/robots.txt") $(lc -o "$NULLDEV" -w '%{http_code}' -X DELETE "$U/robots.txt")" "405 405"
    h=$(head -c 2048 /dev/zero | tr '\0' x | lc -D - -o "$NULLDEV" -X POST --data-binary @- "$U/robots.txt" | tr -d '\r')
    check LV10 "a POST with a 2 KB body is refused by the proxy itself (405 without the mirror's headers)" \
        eval 'has "$h" "^HTTP/[0-9.]+ 405" && hasnt "$h" "^cross-origin-resource-policy"'
    h=$(head -c 4096 /dev/zero | tr '\0' x | lc -D - -o "$NULLDEV" -X GET --data-binary @- "$U/robots.txt" | tr -d '\r')
    check LV11 "a GET with a 4 KB body: 413 from the proxy itself (at most 1 KB, without the mirror's headers)" \
        eval 'has "$h" "^HTTP/[0-9.]+ 413" && hasnt "$h" "^cross-origin-resource-policy"'
    # The published datasets (none before the first publish)
    local list="$WORK/live-datasets.json"
    out=$(lc -o "$(hostpath "$list")" -D - "$U/v1/datasets.json" | tr -d '\r')
    if ! has "$out" '^HTTP/[0-9.]+ 200'; then
        skip LV12-LV15 "no /v1/datasets.json (status $(printf '%s\n' "$out" | head -1 | cut -d' ' -f2)): nothing published yet; the index and cap checks wait for the first publish"
        return
    fi
    check LV12 "datasets.json: application/json, Cache-Control: no-cache" \
        eval 'has "$out" "^content-type: application/json$" && has "$out" "^cache-control: no-cache$"'
    py=""
    for c in python3 python; do
        if command -v "$c" > /dev/null 2>&1 && "$c" -c '' > /dev/null 2>&1; then py=$c; break; fi
    done
    if [ -z "$py" ]; then result LV13 FAIL "python3 or python is needed to read datasets.json"; return; fi
    # Every product: the served index.json against datasets.json's index_sha256 (and the master's)
    local products bad=0 n=0 path want got tile best=0 size bestpath="" gz=0 big=0
    products=$("$py" -I -c 'import json,sys
for d in json.load(open(sys.argv[1], encoding="utf-8"))["datasets"]:
    for p in d["products"]:
        print(p["path"], p["index_sha256"])' "$(hostpath "$list")" | tr -d '\r') || { result LV13 FAIL "datasets.json could not be read"; return; }
    while read -r path want; do
        [ -n "$path" ] || continue
        n=$((n + 1))
        lc -o "$(hostpath "$WORK/live-index.json")" "$U/v1/tiles/$path/index.json"
        got=$(sha256sum "$WORK/live-index.json" | cut -d' ' -f1)
        if [ "$got" != "$want" ]; then bad=$((bad + 1)); info "index of $path: $got, datasets.json says $want"; fi
        if [ -n "$master" ]; then
            if [ "$got" != "$(sha256sum "$master/$path/index.json" 2> /dev/null | cut -d' ' -f1)" ]; then
                bad=$((bad + 1))
                info "index of $path differs from the master copy"
            fi
        fi
        # An index above gzip's minimum is sent compressed
        if [ "$(wc -c < "$WORK/live-index.json")" -gt 2048 ]; then
            big=$((big + 1))
            lc -D - -o "$NULLDEV" -H 'Accept-Encoding: gzip' "$U/v1/tiles/$path/index.json" | tr -d '\r' \
                | grep -qi '^content-encoding: gzip$' && gz=$((gz + 1))
        fi
        # The largest of the first 20 tiles the index lists with data: the held downloads of LV15
        for tile in $("$py" -I -c 'import json,sys
keys = [k for k, v in json.load(open(sys.argv[1], encoding="utf-8"))["tiles"].items() if v][:20]
for k in keys:
    i, j = (int(x) for x in k.split("_"))
    print(f"{i // 10}_{j // 10}/{i}_{j}.tif")' "$(hostpath "$WORK/live-index.json")" | tr -d '\r'); do
            size=$(lc -I "$U/v1/tiles/$path/$tile" | tr -d '\r' | grep -i '^content-length:' | cut -d' ' -f2)
            if [ "${size:-0}" -gt "$best" ]; then best=$size; bestpath="/v1/tiles/$path/$tile"; fi
        done
    done <<< "$products"
    check LV13 "every served index.json has the sha256 datasets.json gives${master:+ and the master copy} ($n products, $bad wrong)" \
        eval '[ "$n" -ge 1 ] && [ "$bad" -eq 0 ]'
    if [ "$big" -ge 1 ]; then
        eq LV14 "an index.json above 2 KB is sent gzip-compressed when the client accepts it ($big such)" "$gz" "$big"
    else
        skip LV14 "no index.json above 2 KB"
    fi
    # The per-address cap through the real proxy: slow downloads held open, then one request more.
    # It shows the proxy honours X-Accel-Buffering only when the tile is larger than what the
    # sockets and buffers on the way hold (several MB): a small tile is sent into them at once
    # and the mirror's connection ends whatever the proxy does.
    if [ -z "$bestpath" ]; then skip LV15 "no tile listed with data"; return; fi
    info "LV15 holds $bestpath ($best bytes) at 64 KB/s"
    local probe
    for _ in 1 2 3; do lc -o "$NULLDEV" --limit-rate 64k -m 18 "$U$bestpath" & done
    sleep 8
    probe=$(lc -o "$NULLDEV" -w '%{http_code}' "$U/robots.txt")
    lc -o "$NULLDEV" --limit-rate 64k -m 12 "$U$bestpath" &
    sleep 3
    out=$(lc -o "$NULLDEV" -w '%{http_code} %header{retry-after}' "$U/robots.txt")
    wait
    eq LV15 "through the proxy: a request beside 3 held downloads 200, beside 4: 429, Retry-After 10 (held: $best bytes)" "$probe / $out" "200 / 429 10"
}

# ---------------------------------------------------------------- the stack

compose() {
    docker compose -p "$PROJECT" --project-directory "$(hostpath "$MIRROR")" --env-file "$(hostpath "$WORK/env")" \
        -f "$(hostpath "$MIRROR/compose.yaml")" -f "$(hostpath "$MIRROR/compose.test.yaml")" \
        -f "$(hostpath "$MIRROR/test/compose.check.yaml")" "$@"
}
write_env() {  # [swag conf]: the stack's settings
    {
        echo "MIRROR_ROOT=/nonexistent-mirror-root"
        echo "MIRROR_CONTACT=$CONTACT"
        echo "MIRROR_TRUSTED_ADDRESSES=$T1,$T2"
        echo "MIRROR_SUBNET=$SUBNET"
        echo "MIRROR_MEMORY=128m"
        echo "MIRROR_TEST_FRONT_SUBNET=$FRONT"
        echo "MIRROR_TEST_PORT=$PORT"
        [ -z "${1:-}" ] || echo "MIRROR_CHECK_SWAG_CONF=$(hostpath "$1")"
    } > "$WORK/env"
}
wait_healthy() {
    local s
    for _ in $(seq 90); do
        s=$(docker inspect -f '{{.State.Health.Status}}' "$FILES" 2> /dev/null)
        [ "$s" = healthy ] && return 0
        sleep 1
    done
    return 1
}
clients_up() {
    local name ip
    for pair in "a $A" "b $B" "c $C" "d $D" "e $E" "t1 $T1" "t2 $T2"; do
        name=${pair% *}
        ip=${pair#* }
        docker run -d --name "$PROJECT-$name" --network "${PROJECT}_front" --ip "$ip" --entrypoint sleep \
            "$CURL_IMAGE" 86400 > /dev/null || return 1
    done
    docker run -d --name "$PROJECT-inside" --network "${PROJECT}_mirror" --ip "$INSIDE" --entrypoint sleep \
        "$CURL_IMAGE" 86400 > /dev/null
}
teardown() {
    [ "$KEEP" = 1 ] && { info "left running: project $PROJECT, http://127.0.0.1:$PORT"; return; }
    remove_stack
    door_down
    rm -rf "$WORK"
}
remove_stack() {  # every container, network, volume and image of the project
    for name in a b c d e t1 t2 inside; do docker rm -f "$PROJECT-$name" > /dev/null 2>&1; done
    docker ps -aq --filter "name=^$PROJECT-start-" | xargs -r docker rm -f > /dev/null 2>&1
    compose down -v --remove-orphans > /dev/null 2>&1
    docker image rm "$PROJECT-files" "$PROJECT-files:orig" > /dev/null 2>&1
    docker image prune -f --filter "label=mirror-check=$PROJECT" > /dev/null 2>&1
}
stack_up() {
    write_env
    compose build --quiet files || return 1
    docker tag "$PROJECT-files" "$PROJECT-files:orig"
    compose up -d --wait --wait-timeout 180 > "$WORK/up.log" 2>&1 || { cat "$WORK/up.log"; return 1; }
    clients_up || return 1
    wait_healthy
}

cx() { local c=$1; shift; docker exec "$PROJECT-$c" curl -s "$@"; }   # curl in a client container
csh() { docker exec "$PROJECT-$1" sh -c "$2"; }

# ---------------------------------------------------------------- the checks, by group

g_content() {
    local h out
    out=$(cx a -o /dev/null -w '%{http_code} %{content_type} %{size_download}' -A "$UA" "$P$T/0_0/1_2.tif")
    eq P01 "a tile: 200 image/tiff, all its bytes" "$out" "200 image/tiff 10240"
    eq P02 "a tile with negative indices (grid_tile_name(-3, 4)): 200" \
        "$(cx a -o /dev/null -w '%{http_code} %{content_type}' -A "$UA" "$P$T/-1_0/-3_4.tif")" "200 image/tiff"
    eq P03 "a tile at 0.5m (res_name(0.5)): 200" \
        "$(cx a -o /dev/null -w '%{http_code} %{content_type}' -A "$UA" "$P$H/0_0/0_1.tif")" "200 image/tiff"
    h=$(cx a -D - -o /dev/null -A "$UA" "$P$T/index.json" | tr -d '\r')
    check P04 "index.json: 200 application/json, Cache-Control: no-cache" \
        eval 'has "$h" "^HTTP/1.1 200" && has "$h" "^content-type: application/json$" && has "$h" "^cache-control: no-cache$"'
    h=$(cx a -D - -o /dev/null -A "$UA" -H 'Accept-Encoding: gzip' "$P$H/index.json" | tr -d '\r')
    out="$(csh a "curl -s --compressed -A '$UA' $P$H/index.json | sha256sum") $(csh a "curl -s -H 'Accept-Encoding: identity' -A '$UA' $P$H/index.json | sha256sum")"
    check P05 "index.json gzip-compressed when accepted, the same JSON once unpacked" \
        eval 'has "$h" "^content-encoding: gzip$" && [ "${out%% *}" = "$(printf "%s" "$out" | cut -d" " -f4)" ]'
    h=$(cx a -D - -o /dev/null -A "$UA" "$P/v1/datasets.json" | tr -d '\r')
    check P06 "datasets.json: 200 application/json, Cache-Control: no-cache" \
        eval 'has "$h" "^HTTP/1.1 200" && has "$h" "^content-type: application/json$" && has "$h" "^cache-control: no-cache$"'
    eq P07 "a dataset's README.md: 200 text/plain; charset=utf-8" \
        "$(cx a -o /dev/null -w '%{http_code} %{content_type}' -A "$UA" "$P/v1/tiles/madeira/README.md")" "200 text/plain; charset=utf-8"
    eq P08 "robots.txt: 200 text/plain; charset=utf-8, disallows all" \
        "$(cx a -o /dev/null -w '%{http_code} %{content_type}' -A "$UA" "$P/robots.txt") $(cx a -A "$UA" "$P/robots.txt" | tr -d '\n')" \
        "200 text/plain; charset=utf-8 User-agent: *Disallow: /"
    eq P09 "the landing page: 200 text/html; charset=utf-8" \
        "$(cx a -o /dev/null -w '%{http_code} %{content_type}' -A "$UA" "$P/")" "200 text/html; charset=utf-8"
    out=$(cx a -A "$UA" "$P/")
    check P10 "the landing page carries the privacy text word for word" \
        eval '[ "$(printf "%s" "$out" | sed -e "s/<[^>]*>//g" | tr -s " \t\r\n" "    " | grep -cF "$PRIVACY")" -ge 1 ]'
    check P11 "the landing page names MIRROR_CONTACT, HTML-escaped" \
        eval 'printf "%s" "$out" | grep -qF "$CONTACT_HTML" && ! printf "%s" "$out" | grep -qF "<check&co>"'
    h=$(cx a -D - -o /dev/null -A "$UA" "$P$T/0_0/1_2.tif" | tr -d '\r')
    check P12 "a tile: Cache-Control: max-age=86400, ETag, Last-Modified" \
        eval 'has "$h" "^cache-control: max-age=86400$" && has "$h" "^etag: " && has "$h" "^last-modified: "'
    check H01 "X-Content-Type-Options: nosniff" has "$h" '^x-content-type-options: nosniff$'
    check H02 "Cross-Origin-Resource-Policy: same-origin" has "$h" '^cross-origin-resource-policy: same-origin$'
    check H03 "X-Robots-Tag: noindex" has "$h" '^x-robots-tag: noindex$'
    check H04 "no Access-Control-* header, no Retry-After on a 200" eval 'hasnt "$h" "^access-control-" && hasnt "$h" "^retry-after"'
    h=$(cx a -D - -o /dev/null -A "$UA" "$P$T/0_0/9_9.tif" | tr -d '\r')
    check H05 "a 404 carries nosniff, Cross-Origin-Resource-Policy and X-Robots-Tag too" \
        eval 'has "$h" "^HTTP/1.1 404" && has "$h" "^x-content-type-options: nosniff$" && has "$h" "^cross-origin-resource-policy: same-origin$" && has "$h" "^x-robots-tag: noindex$"'
    # Asked of the mirror itself (a proxy never passes the upstream's Server and X-Accel-* on)
    h=$(cx inside -D - -o /dev/null -A "$UA" "$M/robots.txt" | tr -d '\r')
    eq H06 "the mirror's own Server header: nginx, no version" "$(printf '%s\n' "$h" | grep -i '^server:' | cut -d' ' -f2-)" "nginx"
    check H07 "the mirror sends X-Accel-Buffering: no" has "$h" '^x-accel-buffering: no$'
    eq R01 "one byte range: 206 with 100 bytes" \
        "$(cx a -o /dev/null -w '%{http_code} %{size_download}' -A "$UA" -H 'Range: bytes=0-99' "$P$T/0_0/1_2.tif")" "206 100"
    eq R02 "several ranges: 416 (also with a space)" \
        "$(cx a -o /dev/null -w '%{http_code}' -A "$UA" -H 'Range: bytes=0-9,20-29' "$P$T/0_0/1_2.tif") $(cx a -o /dev/null -w '%{http_code}' -A "$UA" -H 'Range: bytes=0-9, 20-29' "$P$T/0_0/1_2.tif")" "416 416"
    # HEAD: its status, its Content-Length and no body, read raw
    # (nc stops at the end of its input: the sleep keeps it reading the answer)
    out=$(csh a "(printf 'HEAD $T/0_0/1_2.tif HTTP/1.0\r\nHost: m\r\nUser-Agent: $UA\r\n\r\n'; sleep 3) | nc proxy 8080")
    info "HEAD, raw: $(printf '%s' "$out" | head -3 | tr -d '\r' | tr '\n' '|')"
    check R03 "HEAD: 200, Content-Length 10240, no body" eval '
        printf "%s" "$out" | head -1 | grep -q "^HTTP/1.1 200" &&
        printf "%s" "$out" | tr -d "\r" | grep -qi "^content-length: 10240$" &&
        [ "$(printf "%s" "$out" | awk "BEGIN { RS = \"\r\n\r\n\" } NR > 1 { printf \"%s\", \$0 }" | wc -c)" -eq 0 ]'
}

g_paths() {
    local out
    code() { cx a -o /dev/null -w '%{http_code}' -A "$UA" "$@"; }
    eq N01 "a dot-file in a tile's form: 404" "$(code "$P$T/0_0/.1_9.tif")" 404
    eq N02 "a dot-file: 404" "$(code "$P/v1/tiles/madeira/.secret")" 404
    eq N03 "a .part file: 404" "$(code "$P$T/0_0/1_8.tif.part")" 404
    eq N04 "a folder, with and without its slash: 404" "$(code "$P$T/0_0/") $(code "$P$T/0_0") $(code "$P/v1/tiles/")" "404 404 404"
    eq N05 "a folder named like a tile: 404, not a redirect" "$(code "$P$T/0_0/2_0.tif")" 404
    eq N06 "a file beside the tiles outside the patterns: 404" "$(code "$P$T/notes.txt")" 404
    eq N07 "a file at the root outside the patterns: 404" "$(code "$P/outside.txt")" 404
    eq N08 "/v1/cubes/ and /v1/cache/ (reserved): 404" \
        "$(code "$P/v1/cubes/x.bin") $(code "$P/v1/cache/x.bin") $(code "$P/v1/cubes/")" "404 404 404"
    out=$(cx a -w ' %{http_code}' -A "$UA" "$P$T/0_0/1_6.tif")
    check N09 "a symlink with a tile's name to a file outside the root (/etc/passwd): 404, not served" \
        eval '[ "${out##* }" = 404 ] && ! printf "%s" "$out" | grep -q "root:"'
    eq N10 "a symlink to a real tile: 404" "$(code "$P$T/0_0/1_7.tif")" 404
    eq N11 "a tile that does not exist: 404" "$(code "$P$T/0_0/2_2.tif")" 404
    # Straight to the mirror (a proxy normalises the path itself). Taken as it is written, the
    # first path leads from the served root (/srv/public) to the system's /etc/passwd, which
    # exists; normalised, the second and third lead to /etc/passwd inside the served root, where
    # the fixture has a file ("fixture-inside")
    out=$(cx inside --path-as-is -w ' %{http_code}' -A "$UA" "$M/v1/tiles/madeira/dtm/2m/../../../../../../../etc/passwd")
    out="$out|$(cx inside --path-as-is -w ' %{http_code}' -A "$UA" "$M/v1/tiles/madeira/dtm/2m/../../../../../etc/passwd")"
    out="$out|$(cx inside --path-as-is -w ' %{http_code}' -A "$UA" "$M/v1/tiles/madeira/%2e%2e/%2e%2e/%2e%2e/etc/passwd")"
    info "traversals: $(printf '%s' "$out" | tr '\n' ' ' | head -c 200)"
    check N12 "../ and %2e%2e traversals to an existing /etc/passwd, outside and inside the root: not served" \
        eval '! printf "%s" "$out" | grep -qE "root:|fixture-inside" && ! printf "%s" "$out" | grep -qE " 2[0-9][0-9](\||$)"'
    eq Q01 "a query string: 400 (also an empty one, also on the landing page)" \
        "$(code "$P$T/index.json?x=1") $(code "$P/v1/datasets.json?") $(code "$P/?a")" "400 400 400"
    # The mirror's own method rule, straight to it, on a path no file answers
    local m=""
    for method in POST PUT DELETE OPTIONS; do
        m="$m $(cx inside -o /dev/null -w '%{http_code}' -A "$UA" -X "$method" "$M/v1/cubes/")"
    done
    eq M01 "the mirror: POST, PUT, DELETE, OPTIONS: 405" "$m" " 405 405 405 405"
    eq M02 "the mirror: a POST with a body (500 bytes): 405" \
        "$(head -c 500 /dev/zero | tr '\0' x | docker exec -i "$PROJECT-inside" curl -s -o /dev/null -w '%{http_code}' -A "$UA" --data-binary @- "$M/v1/cubes/")" 405
}

g_swag() {
    local h out
    h=$(head -c 2048 /dev/zero | tr '\0' x | docker exec -i "$PROJECT-a" curl -s -D - -o /dev/null -A "$(ua swag)" --data-binary @- "$P/v1/cubes/" | tr -d '\r')
    check S01 "through the proxy: a POST with a 2 KB body is refused by the proxy itself (405, no mirror header)" \
        eval 'has "$h" "^HTTP/1.1 405" && hasnt "$h" "^cross-origin-resource-policy"'
    h=$(cx a -D - -o /dev/null -A "$(ua swag)" -X DELETE "$P$T/0_0/1_2.tif" | tr -d '\r')
    check S02 "through the proxy: DELETE refused by the proxy itself" \
        eval 'has "$h" "^HTTP/1.1 405" && hasnt "$h" "^cross-origin-resource-policy"'
    h=$(head -c 4096 /dev/zero | tr '\0' x | docker exec -i "$PROJECT-a" curl -s -D - -o /dev/null -A "$(ua swag)" -X GET --data-binary @- "$P/robots.txt" | tr -d '\r')
    check S03 "through the proxy: a GET with a 4 KB body: 413 from the proxy itself (at most 1 KB, no mirror header)" \
        eval 'has "$h" "^HTTP/1.1 413" && hasnt "$h" "^cross-origin-resource-policy"'
    sleep 1
    check S04 "the proxy writes no access line for the mirror's host" \
        eval '! docker logs "$PROJECT-proxy-1" 2>&1 | grep -q "$MARK"'
}

hold() {  # <client> <seconds>: a slow download held open through the proxy
    docker exec "$PROJECT-$1" curl -s -o /dev/null -A "$(ua hold)" --limit-rate 256k -m "$2" "$P$T/0_0/1_3.tif" &
}
probe() { cx "$1" -o /dev/null -w '%{http_code} %header{retry-after}' -A "$(ua probe)" "$P$T/0_0/1_2.tif"; }

g_caps() {
    # Holds: 24 MB read at 256 KB/s, cut at 30 s. The mirror sends a visitor 4 MB/s, so without
    # X-Accel-Buffering the proxy's buffering would let the mirror finish after 6 s (the trusted
    # class after 1.5 s) and the caps would count nothing at the probes (10 s on). With it a hold
    # stays open for (24 MB - the buffers on the way) / 256 KB/s, beyond the 30 s: every probe
    # comes 10-16 s after its holds began, which leaves over 10 s for slow docker exec calls.
    local i
    for i in 1 2 3 4; do hold a 30; done
    for i in 1 2 3; do hold b 30; done
    for i in 1 2; do hold t1 30; done
    sleep 10
    eq C01 "visitors: an 8th concurrent request (7 held, 2 trusted beside them): 200" "$(probe c)" "200 "
    hold b 24
    sleep 2
    eq C03 "visitors: a 9th concurrent request (8 held): 429, Retry-After: 10" "$(probe c)" "429 10"
    eq C08 "trusted: a request while the visitors' total is full: 200" "$(probe t2)" "200 "
    hold t1 22
    sleep 2
    eq C02 "trusted: the class's 4th concurrent request (3 held): 200" "$(probe t1)" "200 "
    hold t1 20
    sleep 2
    eq C04 "trusted: a 5th concurrent request from an address holding 4: 429, Retry-After: 10" "$(probe t1)" "429 10"
    eq C05 "trusted: the class's 4 together, a 5th from another trusted address: 429, Retry-After: 10" "$(probe t2)" "429 10"
    wait
    sleep 1
    for i in 1 2 3; do hold d 30; done
    sleep 10
    eq C06 "one visitor address: a 4th concurrent request: 200" "$(probe d)" "200 "
    hold d 24
    sleep 2
    eq C07 "one visitor address: a 5th concurrent request: 429, Retry-After: 10" "$(probe d)" "429 10"
    wait
}

refusal_rate() {  # <id> <what> <code> <curl options> <path>: one address, straight to the mirror
    local id=$1 what=$2 code=$3 out burst slow
    sleep 3
    out=$(csh inside "curl -s $4 -w '%{http_code}\n' -A '$(ua refuse)' $(urls 60 "$M$5") | sort | uniq -c | tr -s ' \n' ' '; echo '|'; sleep 0.2; curl -s $4 --rate 17/s -w '%{http_code}\n' -A '$(ua refuse)' $(urls 34 "$M$5") | sort | uniq -c | tr -s ' \n' ' '")
    burst=${out%%|*}
    slow=$(printf '%s' "${out#*|}" | tr -d '\n')
    info "$what: 60 back to back: $burst; then 34 at 17 a second: $slow"
    check "$id" "$what: beyond the request rate 429 (from one address), at 17 a second none" \
        eval 'printf "%s" "$burst" | grep -qE " [0-9]+ 429 " && printf "%s" "$burst" | grep -qE " [0-9]+ $code " && [ "$slow" = " 34 $code " ]'
}

g_refusals() {
    # Every answer passes the per-address request rate, refusals too (else one address writes the
    # log without a bound)
    refusal_rate X01 "a path outside the served names (404)" 404 "" "/nothing"
    refusal_rate X02 "a query string (400)" 400 "" "/v1/datasets.json?x"
    refusal_rate X03 "another method (405)" 405 "-X DELETE" "/robots.txt"
    refusal_rate X04 "several byte ranges (416)" 416 "-H 'Range: bytes=0-1,3-4'" "$T/0_0/1_2.tif"
}

g_bytes() {
    local s
    s=$(cx e -o /dev/null -w '%{speed_download} %{time_total}' -A "$UA" "$P$T/0_0/1_5.tif")
    info "a visitor's 16 MB tile: bytes a second, seconds = $s"
    check B01 "a visitor's request: 3.4-4.4 MB/s (limit 4 MB/s)" between "${s%% *}" 3400000 4400000
    s=$(cx t2 -o /dev/null -w '%{speed_download} %{time_total}' -A "$UA" "$P$T/0_0/1_4.tif")
    info "a trusted address's 48 MB tile: bytes a second, seconds = $s"
    check B02 "a trusted request: 13.6-17.6 MB/s (limit 16 MB/s)" between "${s%% *}" 13600000 17600000
}

urls() {  # <count> <url>: curl arguments for <count> requests of <url>
    local i
    for i in $(seq "$1"); do printf -- '-o /dev/null %s ' "$2"; done
}

paced() {  # <client> <rate> <count>: the burst used up, 0.2 s, then <count> requests at <rate>: "<n> <status> ..."
    csh "$1" "curl -s -A '$(ua rate)' $(urls 50 "$P$T/0_0/1_2.tif") > /dev/null; sleep 0.2; curl -s --rate $2 -w '%{http_code}\n' -A '$(ua rate)' $(urls "$3" "$P$T/0_0/1_2.tif")" \
        | sort | uniq -c | tr -s ' \n' ' '
}

g_rate() {
    local t0 t1 out n200 n429 bad
    sleep 3
    t0=$(now)
    # shellcheck disable=SC2046
    out=$(cx c -w '%{http_code}/%header{retry-after}\n' -A "$(ua rate)" $(urls 60 "$P$T/0_0/1_2.tif"))
    t1=$(now)
    n200=$(printf '%s\n' "$out" | grep -c '^200/$')
    n429=$(printf '%s\n' "$out" | grep -c '^429/10$')
    bad=$(printf '%s\n' "$out" | grep -cvE '^(200/|429/10)$')
    info "60 requests back to back from one address in $(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }') s: $n200 x 200, $n429 x 429"
    check Q11 "back to back: the burst of 40 (41 served at once), at most 20 a second more, then 429 with Retry-After: 10" \
        eval '[ "$bad" -eq 0 ] && [ "$n429" -ge 1 ] && [ "$n200" -ge 41 ] && awk -v n="$n200" -v a="$t0" -v b="$t1" "BEGIN { exit !(n <= 42 + 20 * (b - a)) }"'
    # With the burst used up (50 back to back, in the same shell, then 0.2 s), the rate decides
    out=$(paced c 17/s 51)
    info "51 requests at 17 a second, the burst used up: $out"
    eq Q12 "with the burst used up, 17 requests a second: all served" "$out" " 51 200 "
    # 40 a second (twice the rate): a client that reaches more than 20 a second at all meets 429
    out=$(paced c 40/s 80)
    info "80 requests at 40 a second, the burst used up: $out"
    check Q13 "40 requests a second: refused (429) beyond 20 a second" has "$out" ' [0-9]+ 429 '
    # shellcheck disable=SC2046
    out=$(cx t1 -w '%{http_code}\n' -A "$(ua rate)" $(urls 100 "$P$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    eq Q14 "a trusted address: 100 requests back to back all served (no request rate)" "$out" " 100 200 "
}

g_forged() {
    local out
    sleep 3
    # shellcheck disable=SC2046
    out=$(cx e -H "X-Real-IP: $T1" -H "X-Forwarded-For: $T1" -w '%{http_code}\n' -A "$(ua forged)" $(urls 60 "$P$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    info "60 back to back with X-Real-IP and X-Forwarded-For of a trusted address: $out"
    check F01 "a visitor's forged X-Real-IP / X-Forwarded-For is not believed (still limited as a visitor)" has "$out" ' [0-9]+ 429 '
    # X-Real-IP 127.0.0.1 from a sender on the project's network never buys the healthcheck's
    # class (no limit, not logged): it is decided on the connection's own address
    sleep 3
    # shellcheck disable=SC2046
    out=$(cx inside -H "X-Real-IP: 127.0.0.1" -w '%{http_code}\n' -A "$(ua local)" $(urls 60 "$M$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    info "60 back to back with X-Real-IP: 127.0.0.1: $out"
    check F02 "X-Real-IP 127.0.0.1 is not the healthcheck's class (limited and logged)" \
        eval 'has "$out" " [0-9]+ 429 " && [ "$(new_log_lines | grep -c "\"v\":\"$MARK.$(tag local)\"")" -ge 41 ]'
}

g_timeouts() {
    # Straight to the mirror from a client on its network, in parallel (about 55 s)
    local d="$WORK/timeouts"
    mkdir -p "$d"
    csh inside "(printf 'GET /robots.txt HTTP/1.1\r\nHost: m\r\nUser-Agent: $(ua th)\r\n'; sleep 12; printf 'Connection: close\r\n\r\n'; sleep 3) | nc findaline-mirror-files 8080" > "$d/h12" 2>&1 &
    csh inside "(printf 'GET /robots.txt HTTP/1.1\r\nHost: m\r\nUser-Agent: $(ua th)\r\n'; sleep 7; printf 'Connection: close\r\n\r\n'; sleep 3) | nc findaline-mirror-files 8080" > "$d/h7" 2>&1 &
    # A reader that stops reading: nc's output into a pipe nobody reads for 55 s
    csh inside "(printf 'GET $T/0_0/1_4.tif HTTP/1.1\r\nHost: m\r\nUser-Agent: $(ua send)\r\nConnection: close\r\n\r\n'; sleep 55) | nc findaline-mirror-files 8080 | sleep 55" > /dev/null 2>&1 &
    cx inside -o /dev/null -o /dev/null --rate 3/m -w '%{num_connects} ' -A "$(ua ka)" "$M/robots.txt" "$M/robots.txt" > "$d/k20" &
    cx inside -o /dev/null -o /dev/null --rate 6/m -w '%{num_connects} ' -A "$(ua ka)" "$M/robots.txt" "$M/robots.txt" > "$d/k10" &
    wait
    sleep 1
    check Z01 "headers: a request whose headers stop for 12 s gets no answer (10 s)" eval '! grep -q "^HTTP/1.1" "$d/h12"'
    check Z02 "headers: a pause of 7 s is answered" grep -q '^HTTP/1.1 200' "$d/h7"
    eq Z03 "keep-alive: a second request 20 s later needs a new connection (15 s)" "$(cat "$d/k20")" "1 1 "
    eq Z04 "keep-alive: a second request 10 s later reuses the connection" "$(cat "$d/k10")" "1 0 "
    local line rt b
    line=$(new_log_lines | cut -d' ' -f2- | grep "\"v\":\"$MARK.$(tag send)\"" | tail -1)
    rt=$(printf '%s' "$line" | sed -n 's/.*"rt":\([0-9.]*\).*/\1/p')
    b=$(printf '%s' "$line" | sed -n 's/.*"b":\([0-9]*\).*/\1/p')
    info "a reader that stops: the mirror's line $line"
    check Z05 "sending: a reader that stops reading is dropped after 30 s without progress (request time 29-48 s, part of the file)" \
        eval 'between "${rt:-0}" 29 48 && [ "${b:-0}" -lt 48000000 ]'
}

log_counts() {  # every day's file of the log with its line count: "<name> <lines>"
    docker exec "$FILES" sh -c 'for f in /var/log/mirror/access-*.log; do [ -f "$f" ] && echo "${f##*/} $(wc -l < "$f")"; done' 2> /dev/null
}
new_log_lines() {  # the log's lines written since run_checks began, from every day's file: "<name> <line>"
    local name count from
    while read -r name count; do
        [ -n "$name" ] || continue
        from=$(printf '%s\n' "$LOG_FROM" | awk -v n="$name" '$1 == n { print $2 }')
        docker exec "$FILES" cat "/var/log/mirror/$name" | tail -n "+$((${from:-0} + 1))" | sed "s|^|$name |"
    done <<< "$(log_counts)"
}

g_log() {
    local lines all mine out p v
    docker exec "$FILES" /usr/local/bin/mirror-start health
    docker exec "$FILES" /usr/local/bin/mirror-start health
    cx b -o /dev/null -A "Mozilla/5.0 (X11; Linux x86_64)" "$P$T/index.json"
    # ds only of the served names; v only of version-shaped tokens (the code review's inputs)
    for p in "/v1/tiles/$(head -c 300 /dev/zero | tr '\0' a)-john-smith-192-168-1-20/x" \
        "/v1/tiles/madeira-dtm-2m-0_0-1_2-tif/x" "/v1/tiles/madeira/x" "/v1/tiles/madeira/dtm/2m/0_0/1_2.tif.x"; do
        cx d -o /dev/null -A "$(ua dsprobe)" "$P$p"
    done
    cx d -o /dev/null -A "$(ua dsserved)" "$P$T/0_0/9_9.tif"
    for v in 203.0.113.77 203.0.113.dev7x madeira.dtm.2m.0.0.1.2 1.2.3.4.5 1234.1.0 0.2.0rc1 1.0.0.dev3 0.1.0+ip203x0x113x7 unknown; do
        cx d -o /dev/null -A "Find-a-Line/$v (x)" "$P/robots.txt"
    done
    sleep 1
    lines=$(new_log_lines)
    all=$(printf '%s\n' "$lines" | cut -d' ' -f2-)
    mine=$(printf '%s\n' "$all" | grep "\"v\":\"$MARK\.")
    info "this run's lines: $(printf '%s\n' "$mine" | grep -c .); refusals by limit: $(printf '%s\n' "$mine" | grep '"s":429,' | sed -n 's/.*"lim":"\([^"]*\)".*/\1/p' | sort | uniq -c | tr -s ' \n' ' ')"
    # A line's time is when its request ended, its file the one open when it began: a request
    # running across midnight UTC has a time of the next day in the day before's file
    out=$(printf '%s\n' "$lines" | grep . | awk '{ split($1, f, /[-.]/); day = f[2] "-" f[3] "-" f[4]; t = substr($2, 7, 10); hm = substr($2, 18, 8)
        if (t != day && !(t > day && hm < "00:10:00")) bad++ } END { print bad + 0 }')
    check L01 "one file a day: each of this run's $(printf '%s\n' "$mine" | grep -c .) lines in access-<its UTC day>.log" \
        eval '[ "$(printf "%s\n" "$mine" | grep -c .)" -ge 20 ] && [ "$out" -eq 0 ] && printf "%s\n" "$lines" | grep -q "^access-[0-9-]*\.log "'
    out=$(printf '%s\n' "$all" | grep . | grep -vcE '^\{"t":"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}\+00:00","s":[0-9]{3},"b":[0-9]+,"rt":[0-9]+\.[0-9]{3},"ds":"([a-z0-9_-]+|-)","a":"[0-9.]+","lim":"(-|rate|conn|trusted)","v":"[0-9A-Za-z.+-]+"\}$')
    check L02 "every line: exactly the keys t, s, b, rt, ds, a, lim, v, typed ($out other lines)" \
        eval '[ "$out" -eq 0 ] && printf "%s\n" "$all" | grep -q .'
    check L03 "the dataset of a tile's line, \"-\" for other paths" \
        eval 'printf "%s\n" "$mine" | grep -q "\"s\":200,\"b\":10240,.*\"ds\":\"madeira\"" && printf "%s\n" "$mine" | grep -q "\"s\":200,\"b\":26,.*\"ds\":\"-\""'
    check L04 "the visitor's address as the proxy passed it" \
        eval 'printf "%s\n" "$mine" | grep -q "\"a\":\"$A\"" && ! printf "%s\n" "$all" | grep -q "\"a\":\"${PROXY_IP:-none}\""'
    check L05 "the refusing limit: conn, trusted, rate; \"-\" when served" \
        eval '(for w in conn trusted rate; do printf "%s\n" "$mine" | grep -q "\"s\":429,.*\"lim\":\"$w\"" || exit 1; done) && printf "%s\n" "$mine" | grep -q "\"s\":200,.*\"lim\":\"-\""'
    check L06 "never the path, the query or the rest of the User-Agent" \
        eval '! printf "%s\n" "$all" | grep -qE "/v1/|\.tif|\?|highline|someone@|site\.example|Mozilla|X11"'
    check L07 "a User-Agent without Find-a-Line/<version>: \"other\"" \
        eval 'printf "%s\n" "$all" | grep -q "\"a\":\"$B\",\"lim\":\"-\",\"v\":\"other\""'
    check L08 "a forged X-Real-IP is logged under the sender's own address" \
        eval 'printf "%s\n" "$mine" | grep -q "\"v\":\"$MARK.$(tag forged)\"" && ! printf "%s\n" "$mine" | grep "\"v\":\"$MARK.$(tag forged)\"" | grep -qv "\"a\":\"$E\""'
    check L09 "the healthcheck's requests are not logged" \
        eval '! printf "%s\n" "$all" | grep "\"a\":\"127.0.0.1\"" | grep -q "\"v\":\"other\""'
    out=$(printf '%s\n' "$all" | grep "\"v\":\"$MARK.$(tag dsprobe)\"")
    check L11 "ds: \"-\" for paths outside the served names (a 300-letter name with an address, a tile's path folded into one name); the dataset for a served one" \
        eval '[ "$(printf "%s\n" "$out" | grep -c .)" -eq 4 ] && ! printf "%s\n" "$out" | grep -qv "\"ds\":\"-\"" && printf "%s\n" "$all" | grep "\"v\":\"$MARK.$(tag dsserved)\"" | grep -q "\"s\":404,.*\"ds\":\"madeira\""'
    out=$(printf '%s\n' "$all" | grep "\"a\":\"$D\"" | grep -v "\"v\":\"$MARK\." | sed -n 's/.*"v":"\([^"]*\)".*/\1/p' | sort | uniq -c | tr -s ' \n' ' ')
    info "versions logged for client d: $out"
    check L12 "v: 0.2.0rc1 -> 0.2.0rc, 1.0.0.dev3 -> 1.0.0.dev, 0.1.0+ip... -> 0.1.0, unknown kept; an address, 203.0.113.dev7x, a tile in dots -> \"other\"" \
        eval '(for v in 0.2.0rc 1.0.0.dev 0.1.0 unknown; do case "$out" in *" $v "*) ;; *) exit 1 ;; esac; done) && case "$out" in *203*|*madeira*|*1.2.3.4*|*1234.*|*rc1*|*dev3*|*ip*) false ;; *) printf "%s" "$out" | grep -qE " 5 other " ;; esac'
    out=$(docker logs --since "$RUN_START" "$FILES" 2>&1 | grep -E "/v1/|$MARK|$A[^0-9]|client: |limiting")
    [ -z "$out" ] || info "on the container's stdout or stderr: $(printf '%s\n' "$out" | head -3)"
    check L10 "nothing of a request on the container's stdout or stderr" eval '[ -z "$out" ]'
}

g_container() {
    local i out
    i=$(docker inspect "$FILES" --format '{{.HostConfig.ReadonlyRootfs}}|{{.HostConfig.CapDrop}}|{{.HostConfig.SecurityOpt}}|{{.Config.User}}|{{json .HostConfig.PortBindings}}|{{.HostConfig.Init}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}|{{.HostConfig.PidsLimit}}|{{.HostConfig.RestartPolicy.Name}}|{{.HostConfig.LogConfig.Type}} {{index .HostConfig.LogConfig.Config "max-size"}}|{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}')
    info "inspect: $i"
    eq K01 "read-only root file system" "$(echo "$i" | cut -d'|' -f1)" true
    eq K02 "the root cannot be written, the tmpfs can" \
        "$(csh files-1 'touch /etc/x 2>/dev/null && echo w || echo ro') $(csh files-1 'touch /tmp/x && rm /tmp/x && echo w')" "ro w"
    eq K03 "all capabilities dropped; none effective" \
        "$(echo "$i" | cut -d'|' -f2) $(csh files-1 'grep CapEff /proc/1/status' | tr -d '\t ')" "[ALL] CapEff:0000000000000000"
    check K04 "no-new-privileges" eval 'echo "$i" | cut -d"|" -f3 | grep -q "no-new-privileges:true"'
    eq K05 "runs as uid 101" "$(echo "$i" | cut -d'|' -f4) $(csh files-1 'id -u')" "101:101 101"
    eq K06 "init: true" "$(echo "$i" | cut -d'|' -f6)" true
    eq K07 "the public folder cannot be written, the log folder can" \
        "$(csh files-1 'touch /srv/public/x 2>/dev/null && echo w || echo ro') $(csh files-1 'touch /var/log/mirror/.w && rm /var/log/mirror/.w && echo w')" "ro w"
    eq K08 "memory limited, swap equal" "$(echo "$i" | cut -d'|' -f7)=$(echo "$i" | cut -d'|' -f8)" "134217728=134217728"
    # The memory limit holds: a process asking for 200 MB is killed, one asking for 32 MB is not,
    # and the container stays up and healthy
    out="$(csh files-1 'dd if=/dev/zero of=/dev/null bs=32M count=1 2>/dev/null; echo $?') $(csh files-1 'dd if=/dev/zero of=/dev/null bs=200M count=1 2>/dev/null; echo $?')"
    sleep 1
    check K14 "the memory limit holds: 32 MB served, 200 MB killed (137), the container still healthy ($out)" \
        eval '[ "$out" = "0 137" ] && [ "$(docker inspect -f "{{.State.Running}}" "$FILES")" = true ] && docker exec "$FILES" /usr/local/bin/mirror-start health'
    # 90 processes asked for at once; the cgroup counts the forks it refused (read by a builtin)
    out=$(csh files-1 'for k in $(seq 90); do sleep 5 & done' 2>&1 | grep -c "can't fork")
    sleep 6
    info "forks refused of 90 processes asked for: $out"
    check K09 "pids limited to 64, and the limit holds (90 processes asked for, forks refused)" \
        eval '[ "$(echo "$i" | cut -d"|" -f9)" = 64 ] && [ "${out:-0}" -ge 1 ]'
    eq K10 "no published port" "$(echo "$i" | cut -d'|' -f5)" "{}"
    eq K11 "its only network: the project's own, internal" \
        "$(echo "$i" | cut -d'|' -f12)$(docker network inspect "${PROJECT}_mirror" --format '{{.Internal}}')" "${PROJECT}_mirror true"
    eq K12 "restart unless-stopped, json-file log with a size cap" "$(echo "$i" | cut -d'|' -f10-11)" "unless-stopped|json-file 1m"
    # No way out: the mirror cannot reach an address or a name that a container on an ordinary
    # network (the control) does reach from this host
    out="$(cx a -o /dev/null -m 8 -w '%{http_code}' http://1.1.1.1/) $(cx a -o /dev/null -m 8 -w '%{http_code}' http://example.com/)"
    info "the control on an ordinary network: http://1.1.1.1/ and http://example.com/ answered $out"
    check K13 "no route out: 1.1.1.1 and example.com unreachable from the mirror, reachable by the control" \
        eval 'case "$out" in *000*) false ;; esac && ! csh files-1 "wget -q -T 5 -O /dev/null http://1.1.1.1/" 2>/dev/null && ! csh files-1 "wget -q -T 5 -O /dev/null http://example.com/" 2>/dev/null'
}

start_run() {  # <name> <env...>: the image's start with these settings; prints "<running> <exit code>"
    local tag=$1 name="$PROJECT-start-$1" envs=()
    shift
    for e in "$@"; do envs+=(-e "$e"); done
    docker rm -f "$name" > /dev/null 2>&1
    docker run -d --name "$name" --read-only --tmpfs /tmp --tmpfs /var/log/mirror:uid=101,gid=101 --cap-drop ALL --network none "${envs[@]}" "$PROJECT-files" > /dev/null
    sleep 3
    docker inspect -f '{{.State.Running}} {{.State.ExitCode}}' "$name"
    docker logs "$name" > "$WORK/start-$tag.log" 2>&1
    docker rm -f "$name" > /dev/null 2>&1
}

g_start() {
    local ok=(MIRROR_CONTACT=x@example.org MIRROR_SUBNET=172.29.0.0/24)
    eq T01 "four single addresses: starts" "$(start_run good "${ok[@]}" MIRROR_TRUSTED_ADDRESSES=192.0.2.1,192.0.2.2,192.0.2.3,198.51.100.4)" "true 0"
    eq T02 "no trusted address: starts" "$(start_run none "${ok[@]}" MIRROR_TRUSTED_ADDRESSES=)" "true 0"
    local n=3 v
    for v in 0.0.0.0/0 192.0.2.0/24 "192.0.2.1,192.0.2.2,192.0.2.3,192.0.2.4,192.0.2.5" localhost 192.0.2.256 \
        "192.0.2.1," 192.0.2.01 "192.0.2.1,192.0.2.1" 2001:db8::1; do
        eq "$(printf "T%02d" "$n")" "MIRROR_TRUSTED_ADDRESSES='$v': refuses to start" "$(start_run "bad$n" "${ok[@]}" "MIRROR_TRUSTED_ADDRESSES=$v")" "false 64"
        n=$((n + 1))
    done
    eq T12 "MIRROR_SUBNET 0.0.0.0/0: refuses to start" "$(start_run subnet MIRROR_CONTACT=x@example.org MIRROR_SUBNET=0.0.0.0/0)" "false 64"
    eq T13 "MIRROR_CONTACT empty: refuses to start" "$(start_run contact MIRROR_SUBNET=172.29.0.0/24 MIRROR_CONTACT=)" "false 64"
    check T14 "a refusal says why" grep -q 'is not a single IPv4 address; not starting' "$WORK/start-bad3.log"
}

g_cleanup() {
    # Files dated 13, 14 and 15 days back (the container's UTC day) and two other names; the loop
    # runs its cleanup at start, so a restart runs it now
    local days d13 d14 d15 left
    days=$(csh files-1 'n=$(date -u +%s); for k in 13 14 15; do date -u -d "@$((n - k * 86400))" +%F; done' | tr '\n' ' ')
    read -r d13 d14 d15 <<< "$days"
    csh files-1 "cd /var/log/mirror && touch access-$d13.log access-$d14.log access-$d15.log access-notes.log notes.txt access-2000-13-45.log access-0000-00-00.log"
    docker restart "$FILES" > /dev/null
    wait_healthy || info "not healthy after the restart"
    left=$(csh files-1 'ls /var/log/mirror' | tr '\n' ' ')
    info "after the cleanup: $left"
    check E01 "the cleanup keeps a file 13 days back" eval 'case " $left" in *" access-$d13.log "*) true ;; *) false ;; esac'
    check E02 "the cleanup deletes a file 14 days back" eval 'case " $left" in *" access-$d14.log "*) false ;; *) true ;; esac'
    check E03 "the cleanup deletes a file 15 days back" eval 'case " $left" in *" access-$d15.log "*) false ;; *) true ;; esac'
    check E04 "the cleanup leaves other names alone, also impossible dates (2000-13-45, 0000-00-00)" \
        eval 'for n in access-notes.log notes.txt access-2000-13-45.log access-0000-00-00.log; do case " $left" in *" $n "*) ;; *) exit 1 ;; esac; done'
    csh files-1 'cd /var/log/mirror && rm -f access-notes.log notes.txt access-2000-13-45.log access-0000-00-00.log'
    # The heartbeat: stale -> unhealthy; the loop renews it; a dead loop -> unhealthy
    csh files-1 "touch -d '2000-01-01 00:00:00' /tmp/mirror/heartbeat"
    check E05 "a stale heartbeat fails the healthcheck" eval '! docker exec "$FILES" /usr/local/bin/mirror-start health'
    # A new day as the loop sees it (the clock is not changed): nginx first made to write into a
    # file named for another day (a reload of the test's own), and that day set as the one in
    # effect; the loop must name today's file and reload, after which a request lands in today's
    # file, no longer in the other
    local day n_old n_new
    day=$(csh files-1 'date -u +%F')
    csh files-1 'echo "access_log /var/log/mirror/access-2000-01-02.log mirror;" > /tmp/mirror/log.conf && kill -HUP $(cat /tmp/nginx.pid)'
    sleep 3
    cx a -o /dev/null -A "$(ua day)" "$P/robots.txt"
    csh files-1 'echo 2000-01-02 > /tmp/mirror/log.day'
    sleep 35
    check E06 "the cleanup loop renews the heartbeat (within 30 s)" docker exec "$FILES" /usr/local/bin/mirror-start health
    cx a -o /dev/null -A "$(ua day)" "$P/robots.txt"
    sleep 1
    n_old=$(csh files-1 "grep -c '\"v\":\"$MARK.$(tag day)\"' /var/log/mirror/access-2000-01-02.log")
    n_new=$(csh files-1 "grep -c '\"v\":\"$MARK.$(tag day)\"' /var/log/mirror/access-$day.log")
    info "a new day: lines in the other day's file $n_old, in today's $n_new; the day in effect $(csh files-1 'cat /tmp/mirror/log.day')"
    check E08 "a new day: the loop names today's file and reloads nginx; the next line lands there, not in the other day's" \
        eval '[ "$(csh files-1 "cat /tmp/mirror/log.day")" = "$day" ] && [ "$n_old" = 1 ] && [ "$n_new" = 1 ]'
    # A reload that fails (today's file made a folder, so nginx cannot open it) is not taken as
    # the switch: the day in effect stays, and the next turn tries again
    csh files-1 "cd /var/log/mirror && mv access-$day.log access-$day.log.moved && mkdir access-$day.log && echo 2000-01-03 > /tmp/mirror/log.day"
    sleep 35
    check E09 "a failed reload at a new day is not taken as the switch (the day in effect stays)" \
        eval '[ "$(csh files-1 "cat /tmp/mirror/log.day")" = 2000-01-03 ]'
    csh files-1 "cd /var/log/mirror && rmdir access-$day.log && mv access-$day.log.moved access-$day.log"
    sleep 35
    check E10 "the next turn tries again and switches" eval '[ "$(csh files-1 "cat /tmp/mirror/log.day")" = "$day" ]'
    csh files-1 'rm -f /var/log/mirror/access-2000-01-02.log'
    csh files-1 'kill $(cat /tmp/mirror/cleanup.pid)'
    csh files-1 "touch -d '2000-01-01 00:00:00' /tmp/mirror/heartbeat"
    sleep 35
    check E07 "a dead cleanup loop makes the container unhealthy" eval '! docker exec "$FILES" /usr/local/bin/mirror-start health'
    docker restart "$FILES" > /dev/null
    wait_healthy || info "not healthy after the restart"
}

run_checks() {  # the groups named, against the running stack
    local g
    MARK="8.$((RANDOM % 900 + 100))"
    UA=$(ua)
    LOG_FROM=$(log_counts)
    RUN_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    PROXY_IP=$(docker inspect "$PROJECT-proxy-1" --format "{{(index .NetworkSettings.Networks \"${PROJECT}_mirror\").IPAddress}}")
    for g in "$@"; do
        [ "$QUIET" = 1 ] || echo "== $g"
        "g_$g"
    done
}

# ---------------------------------------------------------------- the publishing door (publish/)

DOOR="$MIRROR/publish"
DOOR_COMPOSE=""     # a variant's compose.yaml (the self-test); empty: the real one
DOOR_OVERLAY=""     # a variant's test layer (the self-test); empty: test/compose.door-check.yaml
SSH_OPTS=(-o Port=2222 -o IdentitiesOnly=yes -o UserKnownHostsFile=/root/known_hosts
    -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=10)

door_compose() {
    docker compose -p "$PROJECT-door" --project-directory "$(hostpath "$DOOR")" --env-file "$(hostpath "$WORK/door.env")" \
        -f "$(hostpath "${DOOR_COMPOSE:-$DOOR/compose.yaml}")" \
        -f "$(hostpath "${DOOR_OVERLAY:-$MIRROR/test/compose.door-check.yaml}")" "$@"
}
as_root() {  # <volume> <command>: a shell as root in the door's image, the volume at /v
    docker run --rm -i --user 0 --network none -v "$1:/v" --entrypoint sh "$PROJECT-door-sftp:orig" -c "$2"
}
door_up() {
    {
        echo "MIRROR_ROOT=/nonexistent-mirror-root"
        echo "PUBLISH_KEYS=/nonexistent-keys"
        echo "PUBLISH_ADDRESS=127.0.0.1"
        echo "PUBLISH_PORT=$DOOR_PORT"
        echo "DOOR_ROOT_VOLUME=$PROJECT-door-root"
        echo "DOOR_KEYS_VOLUME=$PROJECT-door-keys"
    } > "$WORK/door.env"
    docker volume create "$PROJECT-door-root" > /dev/null && docker volume create "$PROJECT-door-keys" > /dev/null || return 1
    door_compose build --quiet sftp || return 1
    docker tag "$PROJECT-door-sftp" "$PROJECT-door-sftp:orig"
    docker build -q --label "mirror-check=$PROJECT" -t "$PROJECT-sshclient" -f "$(hostpath "$MIRROR/test/sshclient.Dockerfile")" \
        "$(hostpath "$MIRROR/test")" > /dev/null || return 1
    # The host key, made once (owned by the account, mode 600), as the README's install step does
    as_root "$PROJECT-door-keys" 'ssh-keygen -q -t ed25519 -N "" -C door -f /v/ssh_host_ed25519_key &&
        chown 1000:1000 /v/ssh_host_ed25519_key && chmod 600 /v/ssh_host_ed25519_key && : > /v/authorized_keys &&
        chmod 644 /v/authorized_keys' || return 1
    # The mirror folder: staging, public, trash for the account; logs for uid 101 (0750), with a line
    as_root "$PROJECT-door-root" 'install -d -o 1000 -g 1000 -m 0755 /v/staging /v/public /v/public/v1 /v/public/v1/tiles /v/trash &&
        install -d -o 101 -g 101 -m 0750 /v/logs' || return 1
    docker run --rm --user 101:101 --network none -v "$PROJECT-door-root:/v" --entrypoint sh "$PROJECT-door-sftp:orig" \
        -c 'umask 022; echo "{\"t\":\"2000-01-01T00:00:00+00:00\"}" > /v/logs/access-2000-01-01.log' || return 1
    door_compose up -d --wait --wait-timeout 120 sftp > "$WORK/door-up.log" 2>&1 || { cat "$WORK/door-up.log"; return 1; }
    # The client and its key pairs, made now in the client container (never on disk here)
    docker run -d --name "$PROJECT-sshc" --network "$PROJECT-door_publish" "$PROJECT-sshclient" > /dev/null || return 1
    docker exec "$PROJECT-sshc" sh -c 'ssh-keygen -q -t ed25519 -N "" -C check -f /root/k && ssh-keygen -q -t ed25519 -N "" -C wrong -f /root/wrong' || return 1
    docker exec "$PROJECT-sshc" cat /root/k.pub | as_root "$PROJECT-door-keys" 'cat > /v/authorized_keys' || return 1
    DOOR_HOSTKEY=$(as_root "$PROJECT-door-keys" 'cat /v/ssh_host_ed25519_key.pub')
    docker exec "$PROJECT-sshc" sh -c "echo '[sftp]:2222 $DOOR_HOSTKEY' > /root/known_hosts"
}
door_down() {
    docker rm -f "$PROJECT-sshc" > /dev/null 2>&1
    [ -f "$WORK/door.env" ] && door_compose down -v --remove-orphans > /dev/null 2>&1
    docker volume rm "$PROJECT-door-root" "$PROJECT-door-keys" > /dev/null 2>&1
    docker image rm "$PROJECT-door-sftp" "$PROJECT-door-sftp:orig" "$PROJECT-sshclient" > /dev/null 2>&1
}

dssh() {  # <ssh arguments...>: through the door; prints "<exit status>|<output, stdout and stderr>"
    local out rc
    out=$(docker exec "$PROJECT-sshc" timeout 25 ssh "${SSH_OPTS[@]}" -o "IdentityFile=${KEY:-/root/k}" "$@" 2>&1)
    rc=$?
    printf '%s|%s' "$rc" "$out"
}
dsftp() {  # <batch>: an sftp batch through the door; "<exit status>|<output>"
    local out rc
    out=$(printf '%s\n' "$1" | docker exec -i "$PROJECT-sshc" timeout 25 sftp "${SSH_OPTS[@]}" -o IdentityFile=/root/k -b - publish@sftp 2>&1)
    rc=$?
    printf '%s|%s' "$rc" "$out"
}
esc() { printf '%s' "$1" | sed 's/[^A-Za-z0-9_.,:/@-]/\\&/g'; }   # rclone's escaping (shell_type unix)
refused() {  # <id> <what> <request>: the gate refuses it (status not 0, "refused", no hash)
    local r
    r=$(dssh publish@sftp "$3")
    if [ "${r%%|*}" != 0 ] && printf '%s' "$r" | grep -q 'refused' && ! printf '%s' "$r" | grep -qE '[0-9a-f]{64}'; then
        result "$1" PASS "the gate refuses $2"
    else
        result "$1" FAIL "the gate refuses $2 (got: $(printf '%s' "${r#*|}" | head -c 160 | tr '\n' ' '))"
    fi
}

g_door() {
    local r out sum name="we ird;name \$x'q.bin" before after i
    docker exec "$PROJECT-sshc" sh -c 'head -c 200000 /dev/urandom > /root/a.bin'
    sum=$(docker exec "$PROJECT-sshc" sha256sum /root/a.bin | cut -d' ' -f1)
    r=$(dsftp "ls /mirror")
    check D01 "the right key logs in over SFTP and sees the mirror folder" eval '[ "${r%%|*}" = 0 ] && printf "%s" "$r" | grep -q "/mirror/staging"'
    r=$(KEY=/root/wrong dssh publish@sftp "sha256sum /mirror/logs/access-2000-01-01.log")
    check D02 "a wrong key is refused" eval '[ "${r%%|*}" = 255 ] && printf "%s" "$r" | grep -q "Permission denied"'
    r=$(dssh -v -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive publish@sftp true)
    check D03 "no password or keyboard-interactive login offered (publickey only)" \
        eval '[ "${r%%|*}" = 255 ] && printf "%s" "$r" | grep -q "Authentications that can continue: publickey$" && ! printf "%s" "$r" | grep -qE "can continue: .*(password|keyboard)"'
    r=$(dssh publish@sftp id)
    check D04 "a command (id) is refused" eval '[ "${r%%|*}" != 0 ] && printf "%s" "$r" | grep -q refused && ! printf "%s" "$r" | grep -q "uid="'
    r=$(dssh publish@sftp)
    check D05 "no command (a shell) is refused" eval '[ "${r%%|*}" != 0 ] && printf "%s" "$r" | grep -q refused'
    refused D06 "df" "df /mirror"
    r=$(dssh -tt publish@sftp "sha256sum /mirror/logs/access-2000-01-01.log")
    check D07 "no TTY" eval 'printf "%s" "$r" | grep -q "PTY allocation request failed"'
    r=$(dssh -W 1.1.1.1:80 publish@sftp)
    out=$(dssh -o ExitOnForwardFailure=yes -R 9000:127.0.0.1:22 -N publish@sftp)
    check D08 "no forwarding: -W and -R refused" \
        eval '[ "${r%%|*}" != 0 ] && printf "%s" "$r" | grep -qiE "prohibited|open failed" && [ "${out%%|*}" != 0 ] && printf "%s" "$out" | grep -qi "forwarding failed"'
    # Files written through the door; hashes asked as rclone asks them
    r=$(dsftp "mkdir /mirror/staging/x
put /root/a.bin /mirror/staging/x/a.bin
put /root/a.bin \"/mirror/staging/x/$name\"")
    info "files put through the door: status ${r%%|*}"
    # Links over SFTP are refused (sftp-server -P symlink,hardlink)
    r=$(dsftp "symlink /mirror/staging/x/a.bin /mirror/staging/x/s.bin")
    out=$(dsftp "ln /mirror/staging/x/a.bin /mirror/staging/x/h.bin")
    info "a symlink over SFTP: ${r%%|*} $(printf '%s' "${r#*|}" | tail -1); a hard link: ${out%%|*} $(printf '%s' "${out#*|}" | tail -1)"
    check D32 "a symlink made over SFTP is refused" \
        eval '[ "${r%%|*}" != 0 ] && ! as_root "$PROJECT-door-root" "test -L /v/staging/x/s.bin"'
    check D33 "a hard link made over SFTP is refused" \
        eval '[ "${out%%|*}" != 0 ] && ! as_root "$PROJECT-door-root" "test -e /v/staging/x/h.bin"'
    # Links the host's owner could make (the account cannot): the gate resolves them
    as_root "$PROJECT-door-root" 'cd /v/staging/x && ln -s /etc/passwd out.bin && ln -s /dev/zero zero.bin &&
        ln -s /mirror/staging/x/a.bin in.bin && chown -h 1000:1000 out.bin zero.bin in.bin'
    r=$(dssh publish@sftp "sha256sum $(esc /mirror/staging/x/a.bin)")
    eq D09 "sha256sum of a file under the folder through the gate: the local sha256" "$(printf '%s' "${r#*|}" | cut -d' ' -f1)" "$sum"
    r=$(dssh publish@sftp "sha256sum $(esc "/mirror/staging/x/$name")")
    eq D10 "sha256sum of \"$name\" (escaped as rclone does): the local sha256" "$(printf '%s' "${r#*|}" | cut -d' ' -f1)" "$sum"
    r=$(dssh publish@sftp "sha256sum $(esc /mirror/staging/x/in.bin)")
    eq D11 "sha256sum through a symlink that stays in the folder: the local sha256" "$(printf '%s' "${r#*|}" | cut -d' ' -f1)" "$sum"
    refused D12 "a path outside the folder (/etc/passwd)" "sha256sum /etc/passwd"
    refused D13 "/mirror/../etc/passwd" "sha256sum /mirror/../etc/passwd"
    refused D14 "a ../ inside the folder's path" "sha256sum /mirror/staging/x/../../../etc/passwd"
    refused D15 "a symlink out of the folder (to /etc/passwd)" "sha256sum /mirror/staging/x/out.bin"
    refused D16 "a symlink to a device (/dev/zero)" "sha256sum /mirror/staging/x/zero.bin"
    refused D17 "a folder" "sha256sum /mirror/staging/x"
    refused D18 "a path with a line break" "sha256sum /mirror/staging/x/a.bin"$'\n'"id"
    refused D19 "a very long argument (5000 characters)" "sha256sum /mirror/staging/x/$(head -c 5000 /dev/zero | tr '\0' a)"
    refused D20 "two paths" "sha256sum /mirror/staging/x/a.bin /etc/passwd"
    refused D21 "shell syntax (; and \$())" "sha256sum /mirror/staging/x/a.bin;id"
    refused D22 "shell syntax (\$())" "sha256sum \$(id)"
    refused D23 "an option" "sha256sum -c /mirror/staging/x/a.bin"
    # The keys cannot be written; the account's login still works with them
    r=$(dsftp "put /root/a.bin /keys/authorized_keys")
    out=$(dsftp "put /root/a.bin /keys/host/ssh_host_ed25519_key")
    info "writing the keys through the door: ${r%%|*} $(printf '%s' "${r#*|}" | tail -1); ${out%%|*} $(printf '%s' "${out#*|}" | tail -1)"
    check D24 "the account cannot write authorized_keys or the host key" \
        eval '[ "${r%%|*}" != 0 ] && [ "${out%%|*}" != 0 ] && i=$(dsftp "ls /mirror") && [ "${i%%|*}" = 0 ]'
    # The publish tool's swap: staging/x to public/v1/tiles/x is a rename (the inodes kept)
    before=$(as_root "$PROJECT-door-root" 'cd /v/staging/x && ls -i | sort -k2 | tr -s " \n" "  "')
    r=$(dsftp "-mkdir /mirror/public/v1
-mkdir /mirror/public/v1/tiles
rename /mirror/staging/x /mirror/public/v1/tiles/x")
    info "the rename: status ${r%%|*} $(printf '%s' "${r#*|}" | tail -1)"
    after=$(as_root "$PROJECT-door-root" 'cd /v/public/v1/tiles/x && ls -i | sort -k2 | tr -s " \n" "  "')
    info "inodes before: $before; after: $after"
    check D25 "a folder moved from staging/x to public/v1/tiles/x keeps its inodes (a rename)" \
        eval '[ "${r%%|*}" = 0 ] && [ -n "$before" ] && [ "$before" = "$after" ]'
    # The file server's uid reads what the door wrote, from public mounted read-only
    out=$(docker run --rm --user 101:101 --network none --mount "type=volume,src=$PROJECT-door-root,dst=/srv/public,volume-subpath=public,readonly" \
        --entrypoint sh "$PROJECT-door-sftp:orig" -c 'sha256sum /srv/public/v1/tiles/x/a.bin | cut -d" " -f1; touch /srv/public/w 2>/dev/null && echo written')
    eq D26 "uid 101, public mounted read-only, reads a file the door wrote (and cannot write)" "$out" "$sum"
    r=$(dsftp "get /mirror/logs/access-2000-01-01.log /root/log.txt")
    check D27 "the account reads a log file uid 101 wrote (logs 0750, group 101)" \
        eval '[ "${r%%|*}" = 0 ] && docker exec "$PROJECT-sshc" grep -q 2000-01-01 /root/log.txt'
    # The container
    i=$(docker inspect "$PROJECT-door-sftp-1" --format '{{.HostConfig.ReadonlyRootfs}}|{{.HostConfig.CapDrop}}|{{.HostConfig.SecurityOpt}}|{{.Config.User}}|{{.HostConfig.GroupAdd}}|{{.HostConfig.Memory}}={{.HostConfig.MemorySwap}}|{{.HostConfig.PidsLimit}}|{{range $p, $b := .HostConfig.PortBindings}}{{$p}}>{{range $b}}{{.HostIp}}:{{.HostPort}}{{end}} {{end}}|{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}|{{.HostConfig.RestartPolicy.Name}}')
    info "the door's container: $i"
    eq D28 "the door's container: read-only, no capability, no new privileges, uid 1000 with group 101, memory = swap, pids, restart" \
        "$(echo "$i" | cut -d'|' -f1-7,10)" "true|[ALL]|[no-new-privileges:true]|1000:1000|[101]|134217728=134217728|128|unless-stopped"
    eq D29 "the port on the address given only; its own network, not the mirror's" "$(echo "$i" | cut -d'|' -f8-9)" \
        "2222/tcp>127.0.0.1:$DOOR_PORT |$PROJECT-door_publish "
    out=$(docker exec "$PROJECT-door-sftp-1" /usr/sbin/sshd -T -f /etc/ssh/sshd_config 2>&1 | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permittty|permituserrc|disableforwarding|allowtcpforwarding|forcecommand|permitrootlogin|authenticationmethods) ' | sort | tr '\n' ';')
    eq D30 "sshd's effective settings" "$out" "allowtcpforwarding no;authenticationmethods publickey;disableforwarding yes;forcecommand /usr/local/bin/gate;kbdinteractiveauthentication no;passwordauthentication no;permitrootlogin no;permittty no;permituserrc no;"
    # The host key survives a recreate (the client pins it: StrictHostKeyChecking)
    door_compose up -d --no-build --force-recreate --wait --wait-timeout 120 sftp > /dev/null 2>&1
    r=$(dsftp "ls /mirror")
    out=$(docker exec "$PROJECT-sshc" ssh-keyscan -p 2222 -t ed25519 sftp 2> /dev/null | grep -v '^#' | cut -d' ' -f2-)
    info "after the recreate: login ${r%%|*}; host key $out"
    check D31 "the host key is the same after the container is recreated" \
        eval '[ "${r%%|*}" = 0 ] && [ "$out" = "$(printf "%s" "$DOOR_HOSTKEY" | cut -d" " -f1-2)" ]'
}

# ---------------------------------------------------------------- the self-test

# <name> @@ <file in deploy/mirror> @@ <sed expression> @@ <groups> @@ <check ids that must FAIL>
VARIANTS=(
    'allow-list off @@ nginx.conf @@ s#location / { try_files /.none =404; }#location / { autoindex on; }# @@ paths @@ N01 N02 N03 N04 N06 N07 N08'
    'served root / @@ nginx.conf @@ s#location / { try_files /.none =404; }#location / { root /; }# @@ paths @@ N12'
    'refusals before the limits @@ nginx.conf @@ s#rewrite ^ /__refused/\([0-9]*\)? last;#return \1;#; s#location / { try_files /.none =404; }#location / { return 404; }# @@ refusals @@ X01 X02 X03 X04'
    'symlinks followed @@ nginx.conf @@ s#disable_symlinks on;#disable_symlinks off;# @@ paths @@ N09 N10'
    'folders redirected @@ nginx.conf @@ /error_page 301 =404/d @@ paths @@ N05'
    'other methods allowed @@ nginx.conf @@ s#!~ ^(GET|HEAD)$)#!~ ^(GET|HEAD|POST|PUT|DELETE|OPTIONS)$)# @@ paths @@ M01 M02'
    'HEAD refused @@ nginx.conf @@ s#!~ ^(GET|HEAD)$)#!~ ^(GET)$)# @@ content @@ R03'
    'query allowed @@ nginx.conf @@ /if (\$request_uri ~ "\\?")/d @@ paths @@ Q01'
    'several ranges allowed @@ nginx.conf @@ /if (\$http_range ~ ",")/d; /max_ranges 1;/d @@ content @@ R02'
    'headers off @@ nginx.conf @@ /add_header X-Content-Type-Options/d; /add_header Cross-Origin-Resource-Policy/d; /add_header X-Accel-Buffering/d; s#add_header X-Robots-Tag "noindex" always;#add_header Access-Control-Allow-Origin "*" always;#; s#server_tokens off;#server_tokens on;# @@ content @@ H01 H02 H03 H04 H05 H06 H07'
    'types, charset, caching, gzip off @@ nginx.conf @@ /image\/tiff tif;/d; /application\/json json;/d; /text\/plain md txt;/d; s#charset utf-8;#charset off;#; /add_header Cache-Control/d; s#gzip on;#gzip off;# @@ content @@ P01 P02 P03 P04 P05 P06 P07 P08 P09 P12'
    'caps off @@ nginx.conf @@ /limit_conn visitor_address 4;/d; /limit_conn visitors_all 8;/d; /limit_conn trusted_address 4;/d; /limit_conn trusted_all 4;/d @@ caps @@ C03 C04 C05 C07'
    'an address: 3 at once @@ nginx.conf @@ s#visitor_address 4;#visitor_address 3;# @@ caps @@ C06'
    'all visitors: 7 at once @@ nginx.conf @@ s#visitors_all 8;#visitors_all 7;# @@ caps @@ C01'
    'a trusted address: 3 at once @@ nginx.conf @@ s#trusted_address 4;#trusted_address 3;# @@ caps @@ C02'
    'the trusted class: 3 at once @@ nginx.conf @@ s#trusted_all 4;#trusted_all 3;# @@ caps @@ C02'
    'the trusted class without its total @@ nginx.conf @@ /limit_conn trusted_all 4;/d @@ caps @@ C05'
    'X-Accel-Buffering off @@ nginx.conf @@ /add_header X-Accel-Buffering/d @@ caps @@ C03 C04 C05 C07'
    'byte rates off @@ nginx.conf @@ s#visitor 4000000; trusted 16000000; default 0;#default 0;# @@ bytes @@ B01 B02'
    'trusted list ignored @@ nginx.conf @@ /include \/tmp\/mirror\/trusted.conf;/d @@ caps bytes rate @@ C08 B02 Q14'
    'request rate off @@ nginx.conf @@ /limit_req zone=visitor_rate/d @@ rate forged refusals @@ Q11 Q13 F01 F02 X01 X02 X03 X04'
    'request rate 14 a second @@ nginx.conf @@ s#rate=20r/s#rate=14r/s# @@ rate refusals @@ Q12 X01 X02 X03 X04'
    'request rate 50 a second @@ nginx.conf @@ s#rate=20r/s#rate=50r/s# @@ rate @@ Q13'
    'local decided after X-Real-IP @@ nginx.conf @@ s#geo $realip_remote_addr $mirror_local#geo $remote_addr $mirror_local# @@ forged @@ F02'
    'ds of any path @@ nginx.conf @@ s#^    map $uri $mirror_dataset {#&\n        "~^/v1/tiles/(?<ds>[a-z0-9_-]+)/"  $ds;# @@ log @@ L11'
    'v of any token @@ nginx.conf @@ s#^    map $http_user_agent $mirror_version {#&\n        "~^Find-a-Line/(?<v>[0-9A-Za-z.+-]{1,32})"  $v;# @@ log @@ L12'
    'burst 10 @@ nginx.conf @@ s#burst=40 nodelay#burst=10 nodelay# @@ rate @@ Q11'
    'X-Forwarded-For believed from anyone @@ nginx.conf @@ s#include /tmp/mirror/realip.conf;#set_real_ip_from 0.0.0.0/0;#; s#real_ip_header X-Real-IP;#real_ip_header X-Forwarded-For;#; s#real_ip_recursive off;#real_ip_recursive on;# @@ forged log @@ F01 L08'
    'header timeout 60 s @@ nginx.conf @@ s#client_header_timeout 10s;#client_header_timeout 60s;# @@ timeouts @@ Z01'
    'send timeout 300 s @@ nginx.conf @@ s#send_timeout 30s;#send_timeout 300s;# @@ timeouts @@ Z05'
    'keep-alive 75 s @@ nginx.conf @@ s#keepalive_timeout 15s;#keepalive_timeout 75s;# @@ timeouts @@ Z03'
    'timeouts short @@ nginx.conf @@ s#client_header_timeout 10s;#client_header_timeout 5s;#; s#keepalive_timeout 15s;#keepalive_timeout 5s;# @@ timeouts @@ Z02 Z04'
    'log on stdout @@ start.sh @@ s#access_log $LOGS/access-$1.log#access_log /dev/stdout# @@ content log @@ L01 L10'
    'log with the path @@ nginx.conf @@ s#"rt":$request_time,#"rt":$request_time,"p":"$uri",# @@ content log @@ L02 L06'
    'log with the whole User-Agent @@ nginx.conf @@ s#"v":"$mirror_version"#"v":"$http_user_agent"# @@ content log @@ L06 L07'
    'log without the refusing limit @@ nginx.conf @@ s#"lim":"$mirror_limit"#"lim":"-"# @@ caps rate log @@ L05'
    'healthcheck logged @@ nginx.conf @@ s#map $mirror_class $mirror_loggable { local 0; default 1; }#map $mirror_class $mirror_loggable { default 1; }# @@ log @@ L09'
    'one log file @@ start.sh @@ s#access-$1.log#access.log# @@ content log @@ L01'
    'no new file at a new day @@ start.sh @@ s#^    log_conf "$_today"$#    true# @@ cleanup @@ E08'
    'no reload at a new day @@ start.sh @@ s#kill -HUP "$_master" 2> /dev/null || return 0#true# @@ cleanup @@ E08'
    'a failed reload taken as the switch @@ start.sh @@ s#if \[ -f "$LOGS/access-$_today.log" \] && \[ -n "$_after" \] && \[ "$_after" != "$_before" \]; then#if true; then# @@ cleanup @@ E09'
    'impossible dates cleaned @@ start.sh @@ /Only a real date/{n;d} @@ cleanup @@ E04'
    'error log at info @@ nginx.conf @@ s#error_log /dev/stderr crit;#error_log /dev/stderr info;# @@ paths caps log @@ L10'
    'no privacy text @@ landing/index.html @@ /for 14 days, to hold the service/d @@ content @@ P10'
    'contact not put in @@ start.sh @@ s#sed "s|@MIRROR_CONTACT@|$_replacement|g" "$TEMPLATE"#cat "$TEMPLATE"# @@ content @@ P11'
    'trusted list not checked @@ start.sh @@ s#is_ipv4 "$_address" || die#true || die#; s#\[ $_count -le $MAX_TRUSTED \] || die#true || die#; s#case $_seen in#case nothing in#; s#,\* | \*, | \*,,\*) die#nothing) die# @@ start @@ T03 T04 T05 T06 T07 T08 T09 T10 T11'
    'subnet and contact not checked @@ start.sh @@ s#\[ "$_bits" -ge 16 \] && \[ "$_bits" -le 29 \] || die#true || die#; s#\[ -n "$_contact" \] || die#true || die# @@ start @@ T12 T13'
    'cleanup deletes nothing @@ start.sh @@ s#rm -f -- "$_file"#true# @@ cleanup @@ E02 E03'
    'heartbeat touched once @@ start.sh @@ s#^        touch "$RUN/heartbeat"$#        [ -f "$RUN/heartbeat" ] || touch "$RUN/heartbeat"# @@ cleanup @@ E06'
    'logs kept 15 days @@ start.sh @@ s#KEEP_DAYS=14#KEEP_DAYS=15# @@ cleanup @@ E02'
    'healthcheck without the heartbeat @@ start.sh @@ s#\[ $(($(date -u +%s) - _beat)) -le $HEARTBEAT_MAX_AGE \]#true# @@ cleanup @@ E05 E07'
    'SWAG conf without its refusals @@ swag/findaline-mirror.subdomain.conf @@ /if ($request_method/,/^    }/d; s#client_max_body_size 1k;#client_max_body_size 0;#; /access_log off;/d @@ swag @@ S01 S02 S03 S04'
    # The publishing door ("keys writable" last: it lets the account overwrite the host key)
    'gate runs any command @@ publish/gate.sh @@ s#^set -u$#set -u; [ -n "${SSH_ORIGINAL_COMMAND-}" ] \&\& exec sh -c "$SSH_ORIGINAL_COMMAND"# @@ door @@ D04 D06 D12 D13 D14 D18 D19 D20 D21 D22 D23'
    'gate reads the path as text only @@ publish/gate.sh @@ s#resolved=$(readlink -f -- "$path" 2> /dev/null) || refuse#resolved=$path#; /\[ -f "$resolved" \] && \[ ! -L "$resolved" \] || refuse/d @@ door @@ D15 D16 D17'
    'password login on @@ publish/sshd_config @@ s#^PasswordAuthentication no#PasswordAuthentication yes#; s#^KbdInteractiveAuthentication no#KbdInteractiveAuthentication yes#; s#^AuthenticationMethods publickey#AuthenticationMethods any# @@ door @@ D03 D30'
    'TTY allowed @@ publish/sshd_config @@ s#^PermitTTY no#PermitTTY yes# @@ door @@ D07 D30'
    'forwarding allowed @@ publish/sshd_config @@ s#^DisableForwarding yes#DisableForwarding no#; s#^AllowTcpForwarding no#AllowTcpForwarding yes# @@ door @@ D08 D30'
    'files only for the owner @@ publish/gate.sh @@ s#sftp-server -u 022#sftp-server -u 077# @@ door @@ D26'
    'links allowed over SFTP @@ publish/gate.sh @@ s# -P symlink,hardlink## @@ door @@ D32 D33'
    'a shell without a command @@ publish/gate.sh @@ s#^request=${SSH_ORIGINAL_COMMAND-}$#&; [ -n "$request" ] || exec /bin/sh -c "echo a shell"# @@ door @@ D05'
    'escapes not removed @@ publish/gate.sh @@ /^        path=\$(printf/s#.*#        path=$escaped# @@ door @@ D10'
    'not in the log group @@ publish/compose.yaml @@ /group_add:/d @@ door @@ D27 D28'
    'the port on every address @@ publish/compose.yaml @@ s#"${PUBLISH_ADDRESS:?[^}]*}:#"# @@ door @@ D29'
    'a new host key at each start @@ publish/Dockerfile @@ s#^ENTRYPOINT .*#ENTRYPOINT ssh-keygen -q -t ed25519 -N "" -f /tmp/hk \&\& sed "s|^HostKey .*|HostKey /tmp/hk|" /etc/ssh/sshd_config > /tmp/c \&\& exec /usr/sbin/sshd -D -e -f /tmp/c# @@ door @@ D31'
    'two mounts (staging and public) @@ test/compose.door-check.yaml @@ s#- {type: volume, source: root, target: /mirror}#&\n      - {type: tmpfs, target: /mirror/public, tmpfs: {mode: 01777}}# @@ door @@ D25'
    'keys writable @@ test/compose.door-check.yaml @@ s#read_only: true#read_only: false# @@ door @@ D24'
)

field() {  # <spec> <n>: the n-th field (1-based) of a VARIANTS entry
    local rest=$1 n=$2 value
    while :; do
        value=${rest%% @@ *}
        [ "$n" -eq 1 ] && { printf '%s' "$value"; return; }
        [ "$value" = "$rest" ] && return
        rest=${rest#* @@ }
        n=$((n - 1))
    done
}

variant() {  # <file> <sed expression>: the variant built and the stack recreated with it
    local file=$1 expr=$2 src="$MIRROR/$1" ctx="$WORK/variant"
    rm -rf "$ctx"
    mkdir -p "$ctx"
    sed -e "$expr" "$src" > "$ctx/patched"
    if cmp -s "$src" "$ctx/patched"; then echo "SELFTEST-BROKEN the expression changed nothing in $file: $expr"; return 1; fi
    DOOR_COMPOSE=""
    DOOR_OVERLAY=""
    case $file in
        publish/* | test/compose.door-check.yaml)
            case $file in
                publish/compose.yaml) DOOR_COMPOSE="$ctx/patched" ;;
                publish/Dockerfile)
                    docker build -q --label "mirror-check=$PROJECT" -t "$PROJECT-door-sftp" -f "$(hostpath "$ctx/patched")" \
                        "$(hostpath "$DOOR")" > /dev/null || return 1
                    ;;
                test/compose.door-check.yaml) DOOR_OVERLAY="$ctx/patched" ;;
            esac
            [ "$file" = publish/Dockerfile ] || docker tag "$PROJECT-door-sftp:orig" "$PROJECT-door-sftp"
            case $file in
                publish/gate.sh | publish/sshd_config)
                    local to=/usr/local/bin/gate
                    [ "$file" = publish/sshd_config ] && to=/etc/ssh/sshd_config
                    printf 'FROM %s\nCOPY --chmod=0755 patched %s\n' "$PROJECT-door-sftp:orig" "$to" > "$ctx/Dockerfile"
                    docker build -q --label "mirror-check=$PROJECT" -t "$PROJECT-door-sftp" "$(hostpath "$ctx")" > /dev/null || return 1
                    ;;
            esac
            door_compose up -d --no-build --force-recreate --wait --wait-timeout 120 sftp > "$WORK/variant-up.log" 2>&1 || {
                echo "SELFTEST-BROKEN the door did not come up with the variant:"; tail -5 "$WORK/variant-up.log"; return 1; }
            return 0
            ;;
    esac
    if [ "$file" = swag/findaline-mirror.subdomain.conf ]; then
        write_env "$ctx/patched"
        docker tag "$PROJECT-files:orig" "$PROJECT-files"
    else
        write_env
        local target
        case $file in
            nginx.conf) target=/etc/nginx/nginx.conf ;;
            start.sh) target=/usr/local/bin/mirror-start ;;
            landing/index.html) target=/usr/share/findaline-mirror/index.html.in ;;
        esac
        printf 'FROM %s\nCOPY --chmod=0755 patched %s\n' "$PROJECT-files:orig" "$target" > "$ctx/Dockerfile"
        docker build -q --label "mirror-check=$PROJECT" -t "$PROJECT-files" "$(hostpath "$ctx")" > /dev/null || return 1
    fi
    compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 files proxy > "$WORK/variant-up.log" 2>&1 || {
        # A variant that cannot start (the healthcheck) is reported, the stack restored
        echo "SELFTEST-BROKEN the stack did not come up with the variant:"; tail -5 "$WORK/variant-up.log"; return 1; }
    wait_healthy
}

self_test() {
    local spec name file expr groups ids id bad=0 ok=0 seen=" "
    for spec in "${VARIANTS[@]}"; do
        name=$(field "$spec" 1); file=$(field "$spec" 2); expr=$(field "$spec" 3)
        groups=$(field "$spec" 4); ids=$(field "$spec" 5)
        echo "== self-test: $name ($file)"
        if ! variant "$file" "$expr"; then
            bad=$((bad + 1))
            echo "FAIL self-test '$name': the variant could not be run"
            continue
        fi
        OUT=()
        QUIET=1
        local fails_before=$FAILS
        # shellcheck disable=SC2086
        run_checks $groups
        FAILS=$fails_before     # a variant's failures are expected; only the comparison below counts
        QUIET=0
        for id in $ids; do
            seen="$seen$id "
            case "${OUT[$id]:-none}" in
                FAIL) ok=$((ok + 1)); echo "PASS self-test '$name': $id fails" ;;
                PASS) bad=$((bad + 1)); echo "FAIL self-test '$name': $id still passes with the behaviour off" ;;
                *) bad=$((bad + 1)); echo "FAIL self-test '$name': $id did not run" ;;
            esac
        done
    done
    # Back to the real config
    write_env
    docker tag "$PROJECT-files:orig" "$PROJECT-files"
    compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 files proxy > /dev/null 2>&1
    DOOR_COMPOSE=""
    DOOR_OVERLAY=""
    docker tag "$PROJECT-door-sftp:orig" "$PROJECT-door-sftp"
    local without=""""
    for id in "${!MAIN[@]}"; do
        case "$seen" in *" $id "*) ;; *) without="$without $id" ;; esac
    done
    echo "INFO checks with no variant (their control is inside the check: exact values, a positive control beside a negative one):$(printf '%s\n' $without | sort | tr '\n' ' ')"
    echo "== self-test: $ok controls FAIL as they must, $bad wrong"
    FAILS=$((FAILS + bad))
}

# ---------------------------------------------------------------- main

MODE=full
KEEP=0
LIVE_URL=""
MASTER=""
while [ $# -gt 0 ]; do
    case $1 in
        --self-test) MODE=selftest ;;
        --live) MODE=live; LIVE_URL=${2:?--live needs an address}; shift ;;
        --master) MASTER=${2:?--master needs a folder}; shift ;;
        --keep) KEEP=1 ;;
        -h | --help) sed -n '2,27p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

WORK=$(mktemp -d)
if [ "$MODE" = live ]; then
    echo "== live: $LIVE_URL"
    live_checks "$LIVE_URL" "$MASTER"
    rm -rf "$WORK"
    echo "== done, failures: $FAILS"
    [ "$FAILS" -le 100 ] && exit "$FAILS" || exit 100
fi

case $SUBNET in *.0/24) ;; *) echo "MIRROR_CHECK_SUBNET must be a /24 ending in .0" >&2; exit 2 ;; esac
case $FRONT in *.0/24) ;; *) echo "MIRROR_CHECK_FRONT_SUBNET must be a /24 ending in .0" >&2; exit 2 ;; esac
F=${FRONT%.0/24}
A=$F.10 B=$F.11 C=$F.12 D=$F.13 E=$F.14 T1=$F.20 T2=$F.21
INSIDE=${SUBNET%.0/24}.30
FILES="$PROJECT-files-1"
P=http://proxy:8080
M=http://findaline-mirror-files:8080
T=/v1/tiles/madeira/dtm/2m
H=/v1/tiles/madeira/dtm/0.5m
trap teardown EXIT

echo "== the stack: project $PROJECT, mirror network $SUBNET, visitors' network $FRONT, port $PORT"
write_env
remove_stack
if ! stack_up; then
    echo "FAIL the stack did not start"
    compose logs --no-color 2>&1 | tail -40
    exit 100
fi
info "image: $(docker exec "$FILES" nginx -v 2>&1)"
# MIRROR_CHECK_GROUPS: only these groups (for working on the script), no live and no cleanup run
if [ -n "${MIRROR_CHECK_GROUPS:-}" ]; then
    case " $MIRROR_CHECK_GROUPS " in *" door "*) door_down; door_up || exit 100 ;; esac
    # shellcheck disable=SC2086
    run_checks $MIRROR_CHECK_GROUPS
    echo "== done, failures: $FAILS"
    exit 0
fi
run_checks container content paths swag caps bytes rate refusals forged timeouts log start
declare -A MAIN=()
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
echo "== live mode against the stand-in (http://127.0.0.1:$PORT)"
sleep 3
live_checks "http://127.0.0.1:$PORT"
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
run_checks cleanup
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
echo "== the publishing door: project $PROJECT-door, port $DOOR_PORT"
door_down
if door_up; then
    run_checks door
else
    result D00 FAIL "the publishing door did not start"
    door_compose logs --no-color 2>&1 | tail -20
fi
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
echo "== checks: $FAILS failures of ${#MAIN[@]}"
if [ "$MODE" = selftest ]; then
    self_test
fi
echo "== done, failures: $FAILS"
[ "$FAILS" -le 100 ] && exit "$FAILS" || exit 100
