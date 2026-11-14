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
# Only the cube goes: cube.json, area.geojson and the build folder cube.json names
# (countcube.build: build-<UTC start>-<random>/ with lines_<L>.npy and spots_<L>.npy; never an
# earlier build's folder still here), or for a cube built before the build folders (no "arrays"
# in cube.json) its lines_<L>.npy and spots_<L>.npy beside it. The tiles, the manifest and the
# logs stay here. The copy is extracted next to the old cube and swapped in, and the sha256 of
# every file copied is compared afterwards. Code older than the build folders does not find the
# arrays of a cube built since (its layer answers errors): update the server's code first.
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

# The files that go, relative to the cube folder; every name checked, as they go into the remote
# command: cube.json's "arrays" must be countcube.BUILD_PATTERN, the arrays countcube.ARRAY_FILES.
files=(cube.json)
if [[ -f $cube/area.geojson ]]; then files+=(area.geojson); fi
arrays=$(grep -o '"arrays": *"[^"]*"' "$cube/cube.json" | head -n 1 | sed 's/^"arrays": *"\(.*\)"$/\1/' || true)
if [[ -n $arrays ]]; then
    if [[ ! $arrays =~ ^build-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{8}$ ]]; then
        echo "$cube/cube.json names no build folder: $arrays" >&2
        exit 1
    fi
    folder=$arrays/
else  # a cube built before the build folders: the arrays beside cube.json
    folder=
fi
for level in 1 2 4 8; do
    for mode in lines spots; do
        if [[ -f $cube/$folder${mode}_$level.npy ]]; then files+=("$folder${mode}_$level.npy"); fi
    done
done
if [[ ! ${files[${#files[@]} - 1]} =~ \.npy$ ]]; then
    echo "no arrays in $cube/$folder (cube.json names a build folder that is not there?)" >&2
    exit 1
fi

sums() {
    if command -v sha256sum > /dev/null; then sha256sum -- "$@"; else shasum -a 256 -- "$@"; fi
}
# "hash  name" whatever marks binary files (Git Bash's sha256sum, shasum), sorted by name
plain() { sed 's/^\([0-9a-f]*\) [ *]/\1  /' | LC_ALL=C sort -k2; }

dir=/data/countries/$id
echo "Copying ${#files[@]} files of $cube (cube.json, ${folder:-the arrays beside it}) to $target ($container:$dir/cube) ..."
# shellcheck disable=SC2029  # the values are checked above and meant to expand here
tar -c -C "$cube" "${files[@]}" | "$ssh_cmd" -o BatchMode=yes "$target" \
    "docker exec -i $container sh -c 'set -e; d=$dir; rm -rf \$d/.cube.new; mkdir -p \$d/.cube.new; tar -x -C \$d/.cube.new; test -f \$d/.cube.new/cube.json; rm -rf \$d/.cube.old; if [ -d \$d/cube ]; then mv \$d/cube \$d/.cube.old; fi; mv \$d/.cube.new \$d/cube; rm -rf \$d/.cube.old'"

echo "Checking the copy ..."
local_sums=$(cd "$cube" && sums "${files[@]}" | plain)
# shellcheck disable=SC2029
remote_sums=$("$ssh_cmd" -n -o BatchMode=yes "$target" \
    "docker exec $container sh -c 'cd $dir/cube && sha256sum -- ${files[*]}'" | plain)
if [[ "$local_sums" != "$remote_sums" ]]; then
    echo "the copy differs from $cube:" >&2
    diff <(echo "$local_sums") <(echo "$remote_sums") >&2 || true
    exit 1
fi
echo "Done: $(echo "$local_sums" | wc -l | tr -d ' ') files, sha256 identical."
