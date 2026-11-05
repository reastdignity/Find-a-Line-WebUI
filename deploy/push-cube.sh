#!/usr/bin/env bash
# Find-a-Line: copy a country's cube to the public site, for the highline explorer (#layer,
# administrators only; docs/deployment.md, "Country cubes"). Run on the machine that counted it:
#   deploy/push-cube.sh <ssh-target> <country-id> [<data-folder>]
# The server never counts countries: its web service only reads /data/countries/<id>/cube/ of the
# data volume, so a new or rebuilt cube is copied again (a few MB to tens of MB). The web service
# loads it when the cube.json changes: nothing is restarted.
#
# <ssh-target> is whatever `ssh` takes (a Host of ~/.ssh/config, or user and host joined by an
# at sign); the script holds no address, user, key or port: they come from your ssh configuration
# and agent. Environment:
#   SSH                the ssh program (default ssh; on Windows with Git Bash the OpenSSH of
#                      Windows, which has the agent: SSH=/c/Windows/System32/OpenSSH/ssh.exe)
#   FINDALINE_CONTAINER  a container of the site that mounts the data volume as uid 10001
#                      (default findaline-worker-1)
# <data-folder> is the folder with countries/<id>/cube/ (default: the checkout).
#
# Only cube/ goes: the tiles, the manifest and the logs stay here. The copy is extracted next to
# the old cube and swapped in, and every file's sha256 is compared afterwards.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 <ssh-target> <country-id> [<data-folder>]" >&2
    exit 2
fi
target=$1
id=$2
data=${3:-$(cd "$(dirname "$0")/.." && pwd)}
ssh_cmd=${SSH:-ssh}
container=${FINDALINE_CONTAINER:-findaline-worker-1}

# web.COUNTRY_ID: the id goes into the remote command, so nothing else may pass
if [[ ! $id =~ ^[a-z0-9][a-z0-9_-]{0,63}$ ]]; then
    echo "not a country id: $id" >&2
    exit 2
fi
if [[ ! $container =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    echo "not a container name: $container" >&2
    exit 2
fi
cube=$data/countries/$id/cube
if [[ ! -f $cube/cube.json ]]; then
    echo "no cube at $cube (is the country built? findaline.py country build $id)" >&2
    exit 1
fi

sums() {
    if command -v sha256sum > /dev/null; then sha256sum -- *; else shasum -a 256 -- *; fi
}
# "hash  name" whatever marks binary files (Git Bash's sha256sum, shasum), sorted by name
plain() { sed 's/^\([0-9a-f]*\) [ *]/\1  /' | LC_ALL=C sort -k2; }

dir=/data/countries/$id
echo "Copying $cube to $target ($container:$dir/cube) ..."
# shellcheck disable=SC2029  # the values are checked above and meant to expand here
tar -c -C "$cube" . | "$ssh_cmd" -o BatchMode=yes "$target" \
    "docker exec -i $container sh -c 'set -e; d=$dir; rm -rf \$d/.cube.new; mkdir -p \$d/.cube.new; tar -x -C \$d/.cube.new; test -f \$d/.cube.new/cube.json; rm -rf \$d/.cube.old; if [ -d \$d/cube ]; then mv \$d/cube \$d/.cube.old; fi; mv \$d/.cube.new \$d/cube; rm -rf \$d/.cube.old'"

echo "Checking the copy ..."
local_sums=$(cd "$cube" && sums | plain)
# shellcheck disable=SC2029
remote_sums=$("$ssh_cmd" -n -o BatchMode=yes "$target" \
    "docker exec $container sh -c 'cd $dir/cube && sha256sum -- *'" | plain)
if [[ "$local_sums" != "$remote_sums" ]]; then
    echo "the copy differs from $cube:" >&2
    diff <(echo "$local_sums") <(echo "$remote_sums") >&2 || true
    exit 1
fi
echo "Done: $(echo "$local_sums" | wc -l | tr -d ' ') files, sha256 identical."
