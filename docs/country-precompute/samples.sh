#!/usr/bin/env bash
# The samples of docs/country-precompute.md (2026-11-02): one search each, measured by
# tools/perf_country.py profile into $OUT/samples.json, one at a time under the exclusive test lock
# (their times are measured). A sample already in samples.json is skipped, so the script can be
# started again. The options are the recorded ones; an --area file must exist at its path
# (the Lauterbrunnen polygon: docs/country-precompute/lauterbrunnen.geojson).
# Usage: OUT=<scratch>/samples DATA=<scratch>/data bash docs/country-precompute/samples.sh
set -u
MAIN="${MAIN:-$(git rev-parse --show-toplevel)}"
PY="${PY:-python}"
OUT="${OUT:?the folder of samples.json}"
DATA="${DATA:?a data folder (its cache may be a link to the real one)}"
mkdir -p "$OUT/logs"
done_already() { "$PY" -c "import json,os,sys; p=sys.argv[1]; d=json.load(open(p)) if os.path.exists(p) else {}; sys.exit(0 if sys.argv[2] in d else 1)" "$OUT/samples.json" "$1"; }
# prof NAME TENSION(-|m:kN,...) [findaline options...]
prof() {
  local name=$1 tension=$2; shift 2
  if done_already "$name"; then echo "--- $name: in samples.json already"; return; fi
  local extra=(); [ "$tension" != "-" ] && extra=(--tension-by-length "$tension")
  echo "=== $name $(date '+%H:%M:%S')"
  "$PY" "$MAIN/tools/test_lock.py" run --exclusive --owner cp-sample -- \
    "$PY" -X utf8 "$MAIN/tools/perf_country.py" profile --lean --out "$OUT" --name "$name" "${extra[@]}" -- \
    "$@" --no-html --data-dir "$DATA" > "$OUT/logs/$name.log" 2>&1
  tail -n 1 "$OUT/logs/$name.log"
}

prof ch-alps-S-1m - --lat 46.550 --lon 7.882 --radius 4000 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof ch-alps-S-2m - --lat 46.550 --lon 7.882 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 60
prof ch-alps-S-5m - --lat 46.550 --lon 7.882 --radius 4000 --min-length 30 --max-length 300 --resolution 5 --slope-threshold 60
prof ch-plateau-S-1m - --lat 47.200 --lon 7.700 --radius 2500 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof pl-jura-S-1m - --lat 50.190 --lon 19.735 --radius 4000 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof pl-jura-S-2m - --lat 50.190 --lon 19.735 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 60
prof pl-niz-S-1m - --lat 52.740 --lon 15.355 --radius 2500 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof pl-tatry-S-1m - --lat 49.235 --lon 20.000 --radius 4000 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof pl-tatry-S-2m - --lat 49.235 --lon 20.000 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 60
prof pl-tatry-S-5m - --lat 49.235 --lon 20.000 --radius 4000 --min-length 30 --max-length 300 --resolution 5 --slope-threshold 60
prof ut-sevier-S-1m - --lat 39.350 --lon -112.550 --radius 2500 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof ut-wasatch-S-1m - --lat 40.570 --lon -111.680 --radius 4000 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof ut-zion-S-1m - --lat 37.260 --lon -112.950 --radius 4000 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60
prof ut-zion-S-2m - --lat 37.260 --lon -112.950 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 60
prof ut-zion-S-5m - --lat 37.260 --lon -112.950 --radius 4000 --min-length 30 --max-length 300 --resolution 5 --slope-threshold 60
prof ch-alps-M-2m 300:2.5,1500:6,5000:15 --lat 46.550 --lon 7.882 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60  # rebuilt from its output: its run was lost while saving
prof ch-alps-M-5m 300:2.5,1500:6,5000:15 --lat 46.550 --lon 7.882 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ch-plateau-M-2m 300:2.5,1500:6,5000:15 --lat 47.200 --lon 7.700 --radius 2500 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60
prof pl-jura-M-2m 300:2.5,1500:6,5000:15 --lat 50.190 --lon 19.735 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60
prof pl-niz-M-2m 300:2.5,1500:6,5000:15 --lat 52.740 --lon 15.355 --radius 2500 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60
prof pl-tatry-M-2m 300:2.5,1500:6,5000:15 --lat 49.235 --lon 20.000 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60
prof pl-tatry-M-5m 300:2.5,1500:6,5000:15 --lat 49.235 --lon 20.000 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ut-sevier-M-2m 300:2.5,1500:6,5000:15 --lat 39.350 --lon -112.550 --radius 2500 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60
prof ut-wasatch-M-2m 300:2.5,1500:6,5000:15 --lat 40.570 --lon -111.680 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 2 --slope-threshold 60
prof ut-wasatch-M-5m 300:2.5,1500:6,5000:15 --lat 40.570 --lon -111.680 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ut-zion-M-5m 300:2.5,1500:6,5000:15 --lat 37.260 --lon -112.950 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ch-alps-area-L-10m 300:2.5,1500:6,5000:15 --area "$MAIN/docs/country-precompute/lauterbrunnen.geojson" --tile-size 30000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 10 --slope-threshold 60
prof ch-alps-area-L-5m 300:2.5,1500:6,5000:15 --area "$MAIN/docs/country-precompute/lauterbrunnen.geojson" --tile-size 30000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ch-plateau-L-5m 300:2.5,1500:6,5000:15 --lat 47.200 --lon 7.700 --radius 2500 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof pl-jura-L-5m 300:2.5,1500:6,5000:15 --lat 50.190 --lon 19.735 --radius 4000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof pl-niz-L-5m 300:2.5,1500:6,5000:15 --lat 52.740 --lon 15.355 --radius 2500 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof pl-tatry-L-5m 300:2.5,1500:6,5000:15 --lat 49.235 --lon 20.000 --radius 4000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ut-canyonlands-L-10m 300:2.5,1500:6,5000:15 --lat 38.470 --lon -109.740 --radius 10000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 10 --slope-threshold 60
prof ut-sevier-L-5m 300:2.5,1500:6,5000:15 --lat 39.350 --lon -112.550 --radius 2500 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ut-wasatch-L-5m 300:2.5,1500:6,5000:15 --lat 40.570 --lon -111.680 --radius 4000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ut-zion-L-5m 300:2.5,1500:6,5000:15 --lat 37.260 --lon -112.950 --radius 4000 --min-length 2000 --max-length 5000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 60
prof ch-alps-S-2m-45 - --lat 46.550 --lon 7.882 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 45
prof ch-plateau-S-1m-nodsm - --lat 47.200 --lon 7.700 --radius 2500 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60 --nmpt off
prof pl-jura-S-1m-nodsm - --lat 50.190 --lon 19.735 --radius 4000 --min-length 30 --max-length 300 --resolution 1 --slope-threshold 60 --nmpt off
prof pl-jura-S-2m-45 - --lat 50.190 --lon 19.735 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 45
prof ut-zion-S-2m-45 - --lat 37.260 --lon -112.950 --radius 4000 --min-length 30 --max-length 300 --resolution 2 --slope-threshold 45
prof ch-alps-M-5m-45 300:2.5,1500:6,5000:15 --lat 46.550 --lon 7.882 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 41.0 --stretch 2.1 --resolution 5 --slope-threshold 45
prof ch-alps-M-5m-axiom 300:2.5,1500:6,5000:15 --lat 46.550 --lon 7.882 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 66.2 --stretch 1.8 --resolution 5 --slope-threshold 60
prof ch-alps-M-5m-tiger 300:2.5,1500:6,5000:15 --lat 46.550 --lon 7.882 --radius 4000 --min-length 300 --max-length 2000 --model sag --webbing-weight 61.7 --stretch 2.8 --resolution 5 --slope-threshold 60
echo "=== done $(date '+%H:%M:%S')"
