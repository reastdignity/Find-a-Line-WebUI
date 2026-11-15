#!/bin/sh
# The fixture tree of tests/mirror_check.sh (test/compose.check.yaml runs it once, as root, with
# the public volume at /f and the log volume at /l). The tile names are grid_tile_name's
# (sources/readers/tilebases.py) and the resolution folders res_name's: "2m", "0.5m";
# tests/test_mirror_deploy.py checks the names below against those functions.
set -eu
cd /f
rm -rf ./* ./.[!.]* 2>/dev/null || true
d=v1/tiles/madeira/dtm/2m
h=v1/tiles/madeira/dtm/0.5m
mkdir -p "$d/0_0" "$d/-1_0" "$h/0_0" v1/cubes v1/cache

head -c 10240 /dev/urandom > "$d/0_0/1_2.tif"           # grid_tile_name(1, 2): a small tile
head -c 10240 /dev/urandom > "$d/-1_0/-3_4.tif"         # grid_tile_name(-3, 4): negative indices
head -c 24000000 /dev/urandom > "$d/0_0/1_3.tif"        # 24 MB: held open by slow readers (caps)
head -c 48000000 /dev/urandom > "$d/0_0/1_4.tif"        # 48 MB: the bytes a second of a request
head -c 16000000 /dev/urandom > "$d/0_0/1_5.tif"        # 16 MB: the visitors' bytes a second
head -c 10240 /dev/urandom > "$h/0_0/0_1.tif"           # grid_tile_name(0, 1) at 0.5 m
head -c 1000 /dev/urandom > "$d/0_0/1_8.tif.part"       # a half-copied tile
head -c 1000 /dev/urandom > "$d/0_0/.1_9.tif"           # a dot-file in a tile's form
echo secret > v1/tiles/madeira/.secret                  # a dot-file
echo 'not served' > "$d/notes.txt"                      # a name outside the patterns
echo 'not served' > outside.txt                         # a file at the root, outside the patterns
echo 'reserved' > v1/cubes/x.bin                        # /v1/cubes/ and /v1/cache/ are reserved
echo 'reserved' > v1/cache/x.bin
mkdir -p "$d/0_0/2_0.tif"                               # a folder with a tile's name
ln -s /etc/passwd "$d/0_0/1_6.tif"                      # a symlink to a file outside the root
ln -s 1_2.tif "$d/0_0/1_7.tif"                          # a symlink to a real tile

# The indexes and the list, as the publish tool writes them (hashes of the files above)
sum() { sha256sum "$1" | cut -d' ' -f1; }
printf '{"partial": false, "tiles": {"1_2": "%s", "-3_4": "%s", "1_3": "%s", "1_4": "%s", "1_5": "%s"}}\n' \
    "$(sum "$d/0_0/1_2.tif")" "$(sum "$d/-1_0/-3_4.tif")" "$(sum "$d/0_0/1_3.tif")" "$(sum "$d/0_0/1_4.tif")" \
    "$(sum "$d/0_0/1_5.tif")" > "$d/index.json"
# Large enough to be compressed (gzip_min_length)
printf '{"partial": false, "tiles": {"0_1": "%s"}, "padding": "%s"}\n' "$(sum "$h/0_0/0_1.tif")" \
    "$(head -c 3000 /dev/zero | tr '\0' 'x')" > "$h/index.json"
printf '# Madeira (test fixture)\n\nNot real data.\n' > v1/tiles/madeira/README.md
printf '{"version": 1, "generated": "2026-11-16T00:00:00Z", "datasets": [{"id": "madeira", "title": "Madeira <test>", "licence": "none", "attribution": "Test & fixture", "source": "https://example.org/terms", "products": [{"path": "madeira/dtm/2m", "tiles": 5, "bytes": 1, "index_sha256": "%s"}, {"path": "madeira/dtm/0.5m", "tiles": 1, "bytes": 1, "index_sha256": "%s"}]}]}\n' \
    "$(sum "$d/index.json")" "$(sum "$h/index.json")" > v1/datasets.json
chmod -R a+rX /f

# The log folder: owned by the mirror's uid, as the README's install step makes it
chown 101:101 /l
chmod 0755 /l
find /l -mindepth 1 -delete
echo "fixture ready"
