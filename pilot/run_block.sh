#!/bin/bash
# One seed block of a pilot on one runner.
#   usage: run_block.sh <family/instance> <cpu_limit_s> <seed0> <nproc> "<arm> [<arm> ...]" <outdir>
# For every arm (in the given order) `nproc` seeds run in parallel (one process per seed), each with a CPU-time limit; the arms of one block run on the SAME runner,
# one after the other, so the paired comparison of two arms is not confounded by the runner hardware.  Every run is verified independently (llrp_tools verify).
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
INSTP=$1; TL=$2; SEED0=$3; NPROC=$4; ARMS=$5; OUT=$6
BIN=$HERE/bin; INSTF=$HERE/../cpp/inst/$INSTP.inst; NAME=$(basename "$INSTP")
[ -f "$INSTF" ] || { echo "no instance file $INSTF"; exit 1; }
mkdir -p "$OUT"
{ echo "date=$(date -Iseconds)"; echo "cpu=$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo)"; echo "nproc=$(nproc)"; echo "load_before=$(cut -d' ' -f1-3 /proc/loadavg)"
  echo "instance=$INSTP cpu_limit_s=$TL seed0=$SEED0 nproc=$NPROC arms=$ARMS"
  echo "binary_sha256=$(sha256sum "$BIN/llrp_fast_v8" | cut -d' ' -f1)"; echo "tools_sha256=$(sha256sum "$BIN/llrp_tools_v7" | cut -d' ' -f1)"
  for a in $ARMS; do echo "flags_$a=$(cat "$HERE/arms/$a.flags")"; done; } > "$OUT/env_seed${SEED0}.txt"
for arm in $ARMS; do
  mkdir -p "$OUT/$arm"
  read -ra FA < "$HERE/arms/$arm.flags"
  for ((i = 0; i < NPROC; i++)); do
    seed=$((SEED0 + i)); pre="$OUT/$arm/${NAME}_s${seed}"
    ( "$BIN/llrp_fast_v8" --instance "$INSTF" --seed "$seed" "${FA[@]}" --time "$TL" --max-iter 100000 --out-level 2 --algo "$arm" --quiet --out "$pre" > "$pre.log" 2>&1
      "$BIN/llrp_tools_v7" verify "$INSTF" "$pre" > "$pre.verify" 2>&1 ) &
  done
  wait
  echo "arm $arm done: $(date +%H:%M:%S)  load $(cut -d' ' -f1-3 /proc/loadavg)"
done
echo "load_after=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT/env_seed${SEED0}.txt"
