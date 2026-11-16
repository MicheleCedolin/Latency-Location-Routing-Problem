#!/usr/bin/env bash
# Regenerates every table, number and figure of the paper from the archived study results.
#   usage: paper/run_all.sh [WORKDIR]      (default /tmp/llrp_paper; output in WORKDIR/out/{data,tables,figs})
# Needs python3 with numpy, pandas, scipy, matplotlib (paper/requirements.txt). Takes ~15 s.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; REPO="$(dirname "$HERE")"
W="${1:-/tmp/llrp_paper}"
rm -rf "$W/in"; mkdir -p "$W/in/1x" "$W/in/ext10" "$W/in/atmost" "$W/in/irace" "$W/out"
tar xzf "$REPO/study_results/final_1x_tuned.tar.gz"       -C "$W/in/1x"
tar xzf "$REPO/study_results/ext10_tuned.tar.gz"          -C "$W/in/ext10"
tar xzf "$REPO/study_results/atmost_50-5-2BIS-5.tar.gz"   -C "$W/in/atmost"
tar xzf "$REPO/study_results/irace_logs.tar.gz"           -C "$W/in/irace"
BASE="$W/in/1x/results_final"; EXT="$W/in/ext10/results_extended10"; AM="$W/in/atmost/results_atmost"; OUT="$W/out"
python3 "$HERE/prep.py"            --base "$BASE" --ext "$EXT" --atmost "$AM" --out "$OUT"
python3 "$HERE/tables.py"          --out "$OUT"
python3 "$HERE/tables_ext.py"      --out "$OUT"
python3 "$HERE/anytime_numbers.py" --base "$BASE" --atmost "$AM" --out "$OUT" | tee "$OUT/tables/numbers_anytime.txt"
python3 "$HERE/figs.py"            --out "$OUT" --irace "$W/in/irace"
python3 "$HERE/figs_ext.py"        --out "$OUT"
echo "done: $OUT/tables ($(ls "$OUT/tables" | wc -l) files), $OUT/figs ($(ls "$OUT/figs" | wc -l) files)"
