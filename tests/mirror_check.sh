#!/usr/bin/env bash
# The mirror stack's checks (deploy/mirror, docs/mirror-hosting/spec.md, section 4 "Tests"): one
# line "PASS|FAIL <id> <what>" per check, "INFO" lines for measurements; the exit code is the
# number of failures (capped at 100).
#
#   tests/mirror_check.sh               build the image, start compose.yaml + compose.test.yaml +
#                                       deploy/mirror/test/compose.check.yaml (a fixture tree in
#                                       volumes, test clients with fixed addresses), run every
#                                       check, the --live checks against the stand-in's published
#                                       port, then remove everything it made
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
# port on 127.0.0.1, default 8792).
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
has() { printf '%s\n' "$1" | grep -qiE "$2"; }
hasnt() { ! printf '%s\n' "$1" | grep -qiE "$2"; }
between() { awk -v v="$1" -v lo="$2" -v hi="$3" 'BEGIN { exit !(v + 0 >= lo + 0 && v + 0 <= hi + 0) }'; }
hostpath() { if command -v cygpath > /dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
now() { date +%s.%N | cut -c1-14; }

# ---------------------------------------------------------------- the live checks (no fixture)

live_checks() {  # <url> [master folder]: from this machine, through the proxy
    local U=${1%/} master=${2:-} ua h c py out
    ua="Find-a-Line/check-live (mirror_check.sh; +https://site.example; contact: someone@example.org)"
    lc() { curl -sS -A "$ua" -m 60 "$@" 2> /dev/null; }
    h=$(lc -D - -o /dev/null "$U/robots.txt" | tr -d '\r')
    eq LV01 "robots.txt: 200 text/plain; charset=utf-8" "$(printf '%s\n' "$h" | head -1 | cut -d' ' -f2) $(printf '%s\n' "$h" | grep -i '^content-type:' | cut -d' ' -f2-)" "200 text/plain; charset=utf-8"
    check LV02 "robots.txt disallows everything" has "$(lc "$U/robots.txt")" '^Disallow: /$'
    check LV03 "headers of an answer: nosniff, Cross-Origin-Resource-Policy, X-Robots-Tag" \
        eval 'has "$h" "^x-content-type-options: nosniff$" && has "$h" "^cross-origin-resource-policy: same-origin$" && has "$h" "^x-robots-tag: noindex$"'
    check LV04 "no Access-Control-*, Retry-After or X-Accel-Buffering towards the visitor; no version in Server" \
        eval 'hasnt "$h" "^access-control-" && hasnt "$h" "^retry-after" && hasnt "$h" "^x-accel-buffering" && hasnt "$h" "^server: [^ ]*/[0-9]"'
    out=$(lc -o /dev/null -w '%{http_code} %{content_type}' "$U/")
    eq LV05 "landing page: 200 text/html; charset=utf-8" "$out" "200 text/html; charset=utf-8"
    check LV06 "the landing page carries the privacy text word for word" \
        eval '[ "$(lc "$U/" | sed -e "s/<[^>]*>//g" | tr -s " \t\r\n" "    " | grep -cF "$PRIVACY")" -ge 1 ]'
    c=""
    for p in /v1/cubes/ /v1/cache/ /v1/cubes/x.bin /v1/tiles/ /outside.txt /v1/tiles/.x /index.html; do
        c="$c $(lc -o /dev/null -w '%{http_code}' "$U$p")"
    done
    eq LV07 "reserved, unknown and dot paths: 404" "$c" " 404 404 404 404 404 404 404"
    eq LV08 "a query string: 400" "$(lc -o /dev/null -w '%{http_code}' "$U/robots.txt?x=1")" 400
    eq LV09 "PUT and DELETE: 405" "$(lc -o /dev/null -w '%{http_code}' -X PUT -d x "$U/robots.txt") $(lc -o /dev/null -w '%{http_code}' -X DELETE "$U/robots.txt")" "405 405"
    h=$(head -c 2048 /dev/zero | tr '\0' x | lc -D - -o /dev/null -X POST --data-binary @- "$U/robots.txt" | tr -d '\r')
    check LV10 "a POST with a 2 KB body is refused by the proxy itself (405 without the mirror's headers)" \
        eval 'has "$h" "^HTTP/[0-9.]+ 405" && hasnt "$h" "^cross-origin-resource-policy"'
    out=$(head -c 4096 /dev/zero | tr '\0' x | lc -o /dev/null -w '%{http_code}' -X GET --data-binary @- "$U/robots.txt")
    eq LV11 "a GET with a 4 KB body: 413 from the proxy (at most 1 KB)" "$out" 413
    # The published datasets (none before the first publish)
    py=$(command -v python3 || command -v python || true)
    local list="$WORK/live-datasets.json"
    out=$(lc -o "$(hostpath "$list")" -D - "$U/v1/datasets.json" | tr -d '\r')
    if ! has "$out" '^HTTP/[0-9.]+ 200'; then
        info "no /v1/datasets.json (status $(printf '%s\n' "$out" | head -1 | cut -d' ' -f2)): LV12-LV15 skipped, as before the first publish"
        return
    fi
    check LV12 "datasets.json: application/json, Cache-Control: no-cache" \
        eval 'has "$out" "^content-type: application/json$" && has "$out" "^cache-control: no-cache$"'
    if [ -z "$py" ]; then result LV13 FAIL "python3 or python is needed to read datasets.json"; return; fi
    # Every product: the served index.json against datasets.json's index_sha256 (and the master's)
    local products bad=0 n=0 path want got tile best=0 size bestpath=""
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
                info "index of $path differs from the master's"
            fi
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
    eq LV13 "every served index.json has the sha256 datasets.json gives${master:+ and the master copy} ($n products)" "$bad" 0
    out=$(lc -D - -o /dev/null -H 'Accept-Encoding: gzip' "$U/v1/tiles/${products%% *}/index.json" | tr -d '\r')
    check LV14 "an index.json is sent gzip-compressed when the client accepts it" has "$out" '^content-encoding: gzip$'
    # The per-address cap through the real proxy: four slow downloads held open, a fifth request
    # refused. Holds only while the proxy does not buffer (X-Accel-Buffering honoured) and the
    # tile is larger than what the sockets on the way hold.
    if [ -z "$bestpath" ]; then info "no tile listed: LV15 skipped"; return; fi
    info "LV15 holds $bestpath ($best bytes) at 64 KB/s"
    local probe
    for _ in 1 2 3; do lc -o /dev/null --limit-rate 64k -m 18 "$U$bestpath" & done
    sleep 8
    probe=$(lc -o /dev/null -w '%{http_code}' "$U/robots.txt")
    lc -o /dev/null --limit-rate 64k -m 12 "$U$bestpath" &
    sleep 3
    out=$(lc -o /dev/null -w '%{http_code} %header{retry-after}' "$U/robots.txt")
    wait
    eq LV15 "through the proxy: a 4th request beside 3 held downloads 200, a 5th beside 4: 429, Retry-After 10" "$probe / $out" "200 / 429 10"
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
    for name in a b c d e t1 t2 inside; do docker rm -f "$PROJECT-$name" > /dev/null 2>&1; done
    docker ps -aq --filter "name=^$PROJECT-start-" | xargs -r docker rm -f > /dev/null 2>&1
    compose down -v --remove-orphans > /dev/null 2>&1
    docker image rm "$PROJECT-files" "$PROJECT-files:orig" > /dev/null 2>&1
    rm -rf "$WORK"
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
    out=$(csh a "printf 'HEAD $T/0_0/1_2.tif HTTP/1.0\r\nHost: m\r\nUser-Agent: $UA\r\n\r\n' | nc proxy 8080")
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
    # Straight to the mirror (a proxy normalises the path itself): to an existing file outside it
    out=$(cx inside --path-as-is -w ' %{http_code}' -A "$UA" "$M/v1/tiles/madeira/../../../etc/passwd")
    out="$out|$(cx inside --path-as-is -w ' %{http_code}' -A "$UA" "$M/v1/tiles/madeira/%2e%2e/%2e%2e/%2e%2e/etc/passwd")"
    check N12 "a ../ and a %2e%2e traversal to /etc/passwd: not served" \
        eval '! printf "%s" "$out" | grep -q "root:" && ! printf "%s" "$out" | grep -qE " 2[0-9][0-9](\||$)"'
    eq Q01 "a query string: 400 (also an empty one, also on the landing page)" \
        "$(code "$P$T/index.json?x=1") $(code "$P/v1/datasets.json?") $(code "$P/?a")" "400 400 400"
    # The mirror's own method rule, straight to it, on a path no file answers
    local m=""
    for method in POST PUT DELETE OPTIONS; do
        m="$m $(cx inside -o /dev/null -w '%{http_code}' -A "$UA" -X "$method" "$M/v1/cubes/")"
    done
    eq M01 "the mirror: POST, PUT, DELETE, OPTIONS: 405" "$m" " 405 405 405 405"
    eq M02 "the mirror: a POST with a 2 KB body: 405 (the body is not read)" \
        "$(head -c 2048 /dev/zero | tr '\0' x | docker exec -i "$PROJECT-inside" curl -s -o /dev/null -w '%{http_code}' -A "$UA" --data-binary @- "$M/v1/cubes/")" 405
}

g_swag() {
    local h out
    h=$(head -c 2048 /dev/zero | tr '\0' x | docker exec -i "$PROJECT-a" curl -s -D - -o /dev/null -A "$UA.swag" --data-binary @- "$P/v1/cubes/" | tr -d '\r')
    check S01 "through the proxy: a POST with a 2 KB body is refused by the proxy itself (405, no mirror header)" \
        eval 'has "$h" "^HTTP/1.1 405" && hasnt "$h" "^cross-origin-resource-policy"'
    h=$(cx a -D - -o /dev/null -A "$UA.swag" -X DELETE "$P$T/0_0/1_2.tif" | tr -d '\r')
    check S02 "through the proxy: DELETE refused by the proxy itself" \
        eval 'has "$h" "^HTTP/1.1 405" && hasnt "$h" "^cross-origin-resource-policy"'
    out=$(head -c 4096 /dev/zero | tr '\0' x | docker exec -i "$PROJECT-a" curl -s -o /dev/null -w '%{http_code}' -A "$UA.swag" -X GET --data-binary @- "$P/robots.txt")
    eq S03 "through the proxy: a GET with a 4 KB body: 413 (at most 1 KB)" "$out" 413
    sleep 1
    check S04 "the proxy writes no access line for the mirror's host" \
        eval '! docker logs "$PROJECT-proxy-1" 2>&1 | grep -q "$MARK"'
}

hold() {  # <client> <seconds>: a slow download held open through the proxy
    docker exec "$PROJECT-$1" curl -s -o /dev/null -A "$UA.hold" --limit-rate 256k -m "$2" "$P$T/0_0/1_3.tif" &
}
probe() { cx "$1" -o /dev/null -w '%{http_code} %header{retry-after}' -A "$UA.probe" "$P$T/0_0/1_2.tif"; }

g_caps() {
    # Holds: 24 MB read at 256 KB/s. The mirror sends a visitor 4 MB/s, so without the
    # proxy's buffering switched off by X-Accel-Buffering the mirror would be done after 6 s
    # (the trusted class after 1.5 s) and the caps would count nothing at the probes (8 s on).
    local i
    for i in 1 2 3 4; do hold a 16; done
    for i in 1 2 3; do hold b 16; hold t1 16; done
    sleep 8
    eq C01 "visitors: an 8th concurrent request (7 held, 3 trusted beside them): 200" "$(probe c)" "200 "
    eq C02 "trusted: a 4th concurrent request from one trusted address: 200" "$(probe t1)" "200 "
    hold b 10
    hold t1 10
    sleep 2
    eq C03 "visitors: a 9th concurrent request (8 held): 429, Retry-After: 10" "$(probe c)" "429 10"
    eq C04 "trusted: a 5th concurrent request from one trusted address: 429, Retry-After: 10" "$(probe t1)" "429 10"
    eq C05 "trusted: another trusted address while the visitors' total is full: 200" "$(probe t2)" "200 "
    wait
    sleep 1
    for i in 1 2 3; do hold d 16; done
    sleep 8
    eq C06 "one visitor address: a 4th concurrent request: 200" "$(probe d)" "200 "
    hold d 10
    sleep 2
    eq C07 "one visitor address: a 5th concurrent request: 429, Retry-After: 10" "$(probe d)" "429 10"
    wait
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

g_rate() {
    local t0 t1 out n200 n429 bad
    sleep 3
    t0=$(now)
    # shellcheck disable=SC2046
    out=$(cx c -w '%{http_code}/%header{retry-after}\n' -A "$UA.rate" $(urls 60 "$P$T/0_0/1_2.tif"))
    t1=$(now)
    n200=$(printf '%s\n' "$out" | grep -c '^200/$')
    n429=$(printf '%s\n' "$out" | grep -c '^429/10$')
    bad=$(printf '%s\n' "$out" | grep -cvE '^(200/|429/10)$')
    info "60 requests back to back from one address in $(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }') s: $n200 x 200, $n429 x 429"
    check Q11 "back to back: the burst of 40 (41 served at once), at most 20 a second more, then 429 with Retry-After: 10" \
        eval '[ "$bad" -eq 0 ] && [ "$n429" -ge 1 ] && [ "$n200" -ge 41 ] && awk -v n="$n200" -v a="$t0" -v b="$t1" "BEGIN { exit !(n <= 42 + 20 * (b - a)) }"'
    # The burst is used up now: the rate itself decides
    # shellcheck disable=SC2046
    out=$(cx c --rate 17/s -w '%{http_code}\n' -A "$UA.rate" $(urls 51 "$P$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    info "51 requests at 17 a second, after the burst: $out"
    eq Q12 "with the burst used up, 17 requests a second: all served" "$out" " 51 200 "
    # shellcheck disable=SC2046
    # The burst used up again (back to back), then 24 a second for 2 s
    # shellcheck disable=SC2046
    cx c -A "$UA.rate" $(urls 50 "$P$T/0_0/1_2.tif") > /dev/null
    # shellcheck disable=SC2046
    out=$(cx c --rate 24/s -w '%{http_code}\n' -A "$UA.rate" $(urls 48 "$P$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    info "with the burst used up, 48 requests at 24 a second: $out"
    check Q13 "24 requests a second: refused (429) beyond 20 a second" has "$out" ' [0-9]+ 429 '
    # shellcheck disable=SC2046
    out=$(cx t1 -w '%{http_code}\n' -A "$UA.rate" $(urls 100 "$P$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    eq Q14 "a trusted address: 100 requests back to back all served (no request rate)" "$out" " 100 200 "
}

g_forged() {
    local out
    sleep 3
    # shellcheck disable=SC2046
    out=$(cx e -H "X-Real-IP: $T1" -H "X-Forwarded-For: $T1" -w '%{http_code}\n' -A "$UA.forged" $(urls 60 "$P$T/0_0/1_2.tif") | sort | uniq -c | tr -s ' \n' ' ')
    info "60 back to back with X-Real-IP and X-Forwarded-For of a trusted address: $out"
    check F01 "a visitor's forged X-Real-IP / X-Forwarded-For is not believed (still limited as a visitor)" has "$out" ' [0-9]+ 429 '
}

g_timeouts() {
    # Straight to the mirror from a client on its network, in parallel (about 55 s)
    local d="$WORK/timeouts"
    mkdir -p "$d"
    csh inside "(printf 'GET /robots.txt HTTP/1.1\r\nHost: m\r\nUser-Agent: $UA.th\r\n'; sleep 12; printf 'Connection: close\r\n\r\n'; sleep 3) | nc findaline-mirror-files 8080" > "$d/h12" 2>&1 &
    csh inside "(printf 'GET /robots.txt HTTP/1.1\r\nHost: m\r\nUser-Agent: $UA.th\r\n'; sleep 7; printf 'Connection: close\r\n\r\n'; sleep 3) | nc findaline-mirror-files 8080" > "$d/h7" 2>&1 &
    # A reader that stops reading: nc's output into a pipe nobody reads for 55 s
    csh inside "(printf 'GET $T/0_0/1_4.tif HTTP/1.1\r\nHost: m\r\nUser-Agent: Find-a-Line/$MARK.send\r\nConnection: close\r\n\r\n'; sleep 55) | nc findaline-mirror-files 8080 | sleep 55" > /dev/null 2>&1 &
    cx inside -o /dev/null -o /dev/null --rate 3/m -w '%{num_connects} ' -A "$UA.ka" "$M/robots.txt" "$M/robots.txt" > "$d/k20" &
    cx inside -o /dev/null -o /dev/null --rate 6/m -w '%{num_connects} ' -A "$UA.ka" "$M/robots.txt" "$M/robots.txt" > "$d/k10" &
    wait
    sleep 1
    check Z01 "headers: a request whose headers stop for 12 s gets no answer (10 s)" eval '! grep -q "^HTTP/1.1" "$d/h12"'
    check Z02 "headers: a pause of 7 s is answered" grep -q '^HTTP/1.1 200' "$d/h7"
    eq Z03 "keep-alive: a second request 20 s later needs a new connection (15 s)" "$(cat "$d/k20")" "1 1 "
    eq Z04 "keep-alive: a second request 10 s later reuses the connection" "$(cat "$d/k10")" "1 0 "
    local line rt b
    line=$(docker exec "$FILES" cat "/var/log/mirror/access-$(docker exec "$FILES" date -u +%F).log" | grep "\"v\":\"$MARK.send\"" | tail -1)
    rt=$(printf '%s' "$line" | sed -n 's/.*"rt":\([0-9.]*\).*/\1/p')
    b=$(printf '%s' "$line" | sed -n 's/.*"b":\([0-9]*\).*/\1/p')
    info "a reader that stops: the mirror's line $line"
    check Z05 "sending: a reader that stops reading is dropped after 30 s without progress (request time 29-48 s, part of the file)" \
        eval 'between "${rt:-0}" 29 48 && [ "${b:-0}" -lt 48000000 ]'
}

g_log() {
    local day file all mine out
    day=$(docker exec "$FILES" date -u +%F)
    file="/var/log/mirror/access-$day.log"
    docker exec "$FILES" /usr/local/bin/mirror-start health
    cx b -o /dev/null -A "Mozilla/5.0 (X11; Linux x86_64)" "$P$T/index.json"
    sleep 1
    all=$(docker exec "$FILES" cat "$file" 2> /dev/null | tail -n "+$((LOG_FROM + 1))")
    mine=$(printf '%s\n' "$all" | grep "\"v\":\"$MARK")
    check L01 "one file a day: access-$day.log (the container's UTC day) holds this run's requests" \
        eval '[ "$(printf "%s\n" "$mine" | grep -c .)" -ge 20 ]'
    out=$(printf '%s\n' "$all" | grep -vcE '^\{"t":"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}\+00:00","s":[0-9]{3},"b":[0-9]+,"rt":[0-9]+\.[0-9]{3},"ds":"([a-z0-9_-]+|-)","a":"[0-9.]+","lim":"(-|rate|conn|trusted)","v":"[0-9A-Za-z.+-]+"\}$')
    eq L02 "every line: exactly the keys t, s, b, rt, ds, a, lim, v, typed" "$out" 0
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
        eval 'printf "%s\n" "$mine" | grep -q "\"v\":\"$MARK.forged\"" && ! printf "%s\n" "$mine" | grep "\"v\":\"$MARK.forged\"" | grep -qv "\"a\":\"$E\""'
    check L09 "the healthcheck's requests are not logged" eval '! printf "%s\n" "$all" | grep -q "\"a\":\"127.0.0.1\""'
    out=$(docker logs "$FILES" 2>&1)
    check L10 "nothing of a request on the container's stdout or stderr" \
        eval '! printf "%s\n" "$out" | grep -qE "/v1/|$MARK|\"$A\"|$A,|client: |limiting"'
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
    local name="$PROJECT-start-$1" envs=()
    shift
    for e in "$@"; do envs+=(-e "$e"); done
    docker rm -f "$name" > /dev/null 2>&1
    docker run -d --name "$name" --read-only --tmpfs /tmp --cap-drop ALL --network none "${envs[@]}" "$PROJECT-files" > /dev/null
    sleep 3
    docker inspect -f '{{.State.Running}} {{.State.ExitCode}}' "$name"
    docker logs "$name" > "$WORK/start-$1.log" 2>&1
    docker rm -f "$name" > /dev/null 2>&1
}

g_start() {
    local ok=(MIRROR_CONTACT=x@example.org MIRROR_SUBNET=172.29.0.0/24)
    eq T01 "four single addresses: starts" "$(start_run good "${ok[@]}" MIRROR_TRUSTED_ADDRESSES=192.0.2.1,192.0.2.2,192.0.2.3,198.51.100.4)" "true 0"
    eq T02 "no trusted address: starts" "$(start_run none "${ok[@]}" MIRROR_TRUSTED_ADDRESSES=)" "true 0"
    local n=3 v
    for v in 0.0.0.0/0 192.0.2.0/24 "192.0.2.1,192.0.2.2,192.0.2.3,192.0.2.4,192.0.2.5" localhost 192.0.2.256 \
        "192.0.2.1," 192.0.2.01 "192.0.2.1,192.0.2.1" 2001:db8::1; do
        eq "T0$n" "MIRROR_TRUSTED_ADDRESSES='$v': refuses to start" "$(start_run "bad$n" "${ok[@]}" "MIRROR_TRUSTED_ADDRESSES=$v")" "false 64"
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
    csh files-1 "cd /var/log/mirror && touch access-$d13.log access-$d14.log access-$d15.log access-notes.log notes.txt"
    docker restart "$FILES" > /dev/null
    wait_healthy || info "not healthy after the restart"
    left=$(csh files-1 'ls /var/log/mirror' | tr '\n' ' ')
    info "after the cleanup: $left"
    check E01 "the cleanup keeps a file 13 days back" eval 'case " $left" in *" access-$d13.log "*) true ;; *) false ;; esac'
    check E02 "the cleanup deletes a file 14 days back" eval 'case " $left" in *" access-$d14.log "*) false ;; *) true ;; esac'
    check E03 "the cleanup deletes a file 15 days back" eval 'case " $left" in *" access-$d15.log "*) false ;; *) true ;; esac'
    check E04 "the cleanup leaves other names alone" eval 'case " $left" in *" access-notes.log "*" notes.txt "*) true ;; *) false ;; esac'
    csh files-1 'rm -f /var/log/mirror/access-notes.log /var/log/mirror/notes.txt'
    # The heartbeat: stale -> unhealthy; the loop renews it; a dead loop -> unhealthy
    csh files-1 "touch -d '2000-01-01 00:00:00' /tmp/mirror/heartbeat"
    check E05 "a stale heartbeat fails the healthcheck" eval '! docker exec "$FILES" /usr/local/bin/mirror-start health'
    sleep 35
    check E06 "the cleanup loop renews the heartbeat (within 30 s)" docker exec "$FILES" /usr/local/bin/mirror-start health
    csh files-1 'kill $(cat /tmp/mirror/cleanup.pid)'
    csh files-1 "touch -d '2000-01-01 00:00:00' /tmp/mirror/heartbeat"
    sleep 35
    check E07 "a dead cleanup loop makes the container unhealthy" eval '! docker exec "$FILES" /usr/local/bin/mirror-start health'
    docker restart "$FILES" > /dev/null
    wait_healthy || info "not healthy after the restart"
}

run_checks() {  # the groups named, against the running stack
    local g
    MARK="chk$RANDOM$RANDOM"
    UA="Find-a-Line/$MARK (highline finder; +https://site.example; contact: someone@example.org)"
    LOG_FROM=$(docker exec "$FILES" sh -c 'cat /var/log/mirror/access-$(date -u +%F).log 2>/dev/null | wc -l')
    PROXY_IP=$(docker inspect "$PROJECT-proxy-1" --format "{{(index .NetworkSettings.Networks \"${PROJECT}_mirror\").IPAddress}}")
    for g in "$@"; do
        [ "$QUIET" = 1 ] || echo "== $g"
        "g_$g"
    done
}

# ---------------------------------------------------------------- the self-test

# <name> @@ <file in deploy/mirror> @@ <sed expression> @@ <groups> @@ <check ids that must FAIL>
VARIANTS=(
    'allow-list off @@ nginx.conf @@ s#location / { return 404; }#location / { autoindex on; }# @@ paths @@ N01 N02 N03 N04 N06 N07 N08'
    'served root / @@ nginx.conf @@ s#location / { return 404; }#location / { root /; }# @@ paths @@ N12'
    'symlinks followed @@ nginx.conf @@ s#disable_symlinks on;#disable_symlinks off;# @@ paths @@ N09 N10'
    'folders not caught @@ nginx.conf @@ /if (-d \$request_filename)/d @@ paths @@ N05'
    'other methods allowed @@ nginx.conf @@ s#!~ ^(GET|HEAD)$)#!~ ^(GET|HEAD|POST|PUT|DELETE|OPTIONS)$)# @@ paths @@ M01 M02'
    'HEAD refused @@ nginx.conf @@ s#!~ ^(GET|HEAD)$)#!~ ^(GET)$)# @@ content @@ R03'
    'query allowed @@ nginx.conf @@ /if (\$request_uri ~ "\?")/d @@ paths @@ Q01'
    'several ranges allowed @@ nginx.conf @@ /if (\$http_range ~ ",")/d; /max_ranges 1;/d @@ content @@ R02'
    'headers off @@ nginx.conf @@ /add_header X-Content-Type-Options/d; /add_header Cross-Origin-Resource-Policy/d; /add_header X-Accel-Buffering/d; s#add_header X-Robots-Tag "noindex" always;#add_header Access-Control-Allow-Origin "*" always;#; s#server_tokens off;#server_tokens on;# @@ content @@ H01 H02 H03 H04 H05 H06 H07'
    'types, charset, caching, gzip off @@ nginx.conf @@ /image\/tiff tif;/d; /application\/json json;/d; /text\/plain md txt;/d; s#charset utf-8;#charset off;#; /add_header Cache-Control/d; s#gzip on;#gzip off;# @@ content @@ P01 P02 P03 P04 P05 P06 P07 P08 P09 P12'
    'caps off @@ nginx.conf @@ /limit_conn visitor_address 4;/d; /limit_conn visitors_all 8;/d; /limit_conn trusted_address 4;/d @@ caps @@ C03 C04 C07'
    'caps one lower @@ nginx.conf @@ s#visitor_address 4;#visitor_address 3;#; s#visitors_all 8;#visitors_all 7;#; s#trusted_address 4;#trusted_address 3;# @@ caps @@ C01 C02 C06'
    'X-Accel-Buffering off @@ nginx.conf @@ /add_header X-Accel-Buffering/d @@ caps @@ C03 C04 C07'
    'byte rates off @@ nginx.conf @@ s#visitor 4000000; trusted 16000000; default 0;#default 0;# @@ bytes @@ B01 B02'
    'trusted list ignored @@ nginx.conf @@ /include \/tmp\/mirror\/trusted.conf;/d @@ caps bytes rate @@ C05 B02 Q14'
    'request rate off @@ nginx.conf @@ /limit_req zone=visitor_rate/d @@ rate forged @@ Q11 Q13 F01'
    'request rate 14 a second @@ nginx.conf @@ s#rate=20r/s#rate=14r/s# @@ rate @@ Q12'
    'request rate 30 a second @@ nginx.conf @@ s#rate=20r/s#rate=30r/s# @@ rate @@ Q13'
    'burst 10 @@ nginx.conf @@ s#burst=40 nodelay#burst=10 nodelay# @@ rate @@ Q11'
    'X-Forwarded-For believed from anyone @@ nginx.conf @@ s#include /tmp/mirror/realip.conf;#set_real_ip_from 0.0.0.0/0;#; s#real_ip_header X-Real-IP;#real_ip_header X-Forwarded-For;#; s#real_ip_recursive off;#real_ip_recursive on;# @@ forged log @@ F01 L08'
    'timeouts long @@ nginx.conf @@ s#client_header_timeout 10s;#client_header_timeout 60s;#; s#send_timeout 30s;#send_timeout 300s;#; s#keepalive_timeout 15s;#keepalive_timeout 75s;# @@ timeouts @@ Z01 Z03 Z05'
    'timeouts short @@ nginx.conf @@ s#client_header_timeout 10s;#client_header_timeout 5s;#; s#keepalive_timeout 15s;#keepalive_timeout 5s;# @@ timeouts @@ Z02 Z04'
    'log on stdout @@ nginx.conf @@ s#access_log /var/log/mirror/access-$mirror_day.log#access_log /dev/stdout# @@ content log @@ L01 L10'
    'log with the path @@ nginx.conf @@ s#"rt":$request_time,#"rt":$request_time,"p":"$uri",# @@ content log @@ L02 L06'
    'log with the whole User-Agent @@ nginx.conf @@ s#"v":"$mirror_version"#"v":"$http_user_agent"# @@ content log @@ L06 L07'
    'log without the refusing limit @@ nginx.conf @@ s#"lim":"$mirror_limit"#"lim":"-"# @@ caps rate log @@ L05'
    'healthcheck logged @@ nginx.conf @@ s#map $mirror_class $mirror_loggable { local 0; default 1; }#map $mirror_class $mirror_loggable { default 1; }# @@ log @@ L09'
    'one log file @@ nginx.conf @@ s#access-$mirror_day.log#access.log# @@ content log @@ L01'
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
        docker build -q -t "$PROJECT-files" "$(hostpath "$ctx")" > /dev/null || return 1
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
        # shellcheck disable=SC2086
        run_checks $groups
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
    local without=""
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
compose down -v --remove-orphans > /dev/null 2>&1
if ! stack_up; then
    echo "FAIL the stack did not start"
    compose logs --no-color 2>&1 | tail -40
    exit 100
fi
info "image: $(docker exec "$FILES" nginx -v 2>&1)"
run_checks container content paths swag caps bytes rate forged timeouts log start
declare -A MAIN=()
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
echo "== live mode against the stand-in (http://127.0.0.1:$PORT)"
sleep 3
live_checks "http://127.0.0.1:$PORT"
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
run_checks cleanup
for id in "${!OUT[@]}"; do MAIN[$id]=${OUT[$id]}; done
echo "== checks: $FAILS failures of ${#MAIN[@]}"
if [ "$MODE" = selftest ]; then
    self_test
fi
echo "== done, failures: $FAILS"
[ "$FAILS" -le 100 ] && exit "$FAILS" || exit 100
