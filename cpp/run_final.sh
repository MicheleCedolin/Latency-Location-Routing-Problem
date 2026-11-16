#!/bin/bash
# FINAL EVALUATION: all instances x 30 seeds with the parameters found by irace (reproducible).  No Python needed.
#   ./run_final.sh                              # FLAGS_FILE=irace/best.flags, FAMILY=all (76 instances), 30 seeds (1..30), same CPU-time budget as irace
#   PLAN_ONLY=1 ./run_final.sh                  # only the time estimate; nothing is started
#   FAMILY=barreto ./run_final.sh               # one family (barreto | tuzun | prins);   FAMILY=custom ./run_final.sh Ch50-5 P113212-10
#   FLAGS_FILE=other.flags TAG=second ./run_final.sh        # another configuration / separate result directory
# Budget (the SAME as the irace training budget; keep TC/TMIN equal to what you used in irace):  CPU-time limit per run = max(TMIN, TC*n/100) s,
#   no iteration cap (100000), no stall rule.  The time limit is checked at the END of a GRASP iteration (the limit can be exceeded by at most one iteration).
# Parallelism: one process = one (instance, seed) task, PAR tasks at a time (default: NSLOTS granted by SGE, otherwise 30); NO core pinning (same conditions as irace).
# Reproducibility: seeds SEED0..SEED0+SEEDS-1 (default 1..30); flags, budget, binary and manifest SHA-256 are stored in env.txt.  A time-limited run is reproduced
#   exactly by passing the 'iterations' value of its run log as --max-iter; REPLAY=n checks n sample runs this way automatically (replay_check.txt).
# Verification: the routes of every run are recomputed independently with llrp_tools verify (VERIFY=1, default).
# Results:  $OUT/<family>/$TAG/{run,routes,ops,trace}.csv , summary.txt , env.txt , runs/ ;  an interrupted job resumes with the same command.
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=${BIN:-$HERE/bin/llrp_fast}; TOOLS=${TOOLS:-$HERE/bin/llrp_tools}
INSTROOT=${INSTROOT:-$HERE/inst}; MANIFEST=${MANIFEST:-$HERE/manifest.tsv}
FLAGS_FILE=${FLAGS_FILE:-$HERE/irace/best.flags}
SEEDS=${SEEDS:-30}; SEED0=${SEED0:-1}; TC=${TC:-30}; TMIN=${TMIN:-5}; TAG=${TAG:-tuned}
OUT=${OUT:-$HERE/results_final}; OUTLEVEL=${OUTLEVEL:-1}; VERIFY=${VERIFY:-1}; REPLAY=${REPLAY:-10}
PAR=${PAR:-${NSLOTS:-30}}
export HERE BIN TOOLS INSTROOT MANIFEST SEEDS SEED0 TC TMIN TAG OUT OUTLEVEL VERIFY

# ------------------------------------------------------------------ task mode: one (instance, seed) run
if [ "${1:-}" = "--task" ]; then
  fam=$2; inst=$3; n=$4; seed=$5; mode=${6:-run}
  set -f; read -ra FA <<< "$FA_STR"
  RUNS=$OUT/$fam/$TAG/runs; mkdir -p "$RUNS/log"
  pre=$RUNS/${inst}_s${seed}; log=$RUNS/log/${inst}_s${seed}.log
  if [ "$mode" = replay ]; then                     # reproduce a time-limited run from its iteration count
    it=$(awk '$1=="iterations"{print $2}' "$log"); c0=$(awk '$1=="final_cost"{print $2}' "$log")
    c1=$("$BIN" --instance "$INSTROOT/$fam/$inst.inst" --seed "$seed" "${FA[@]}" --max-iter "$it" --quiet | awk '$1=="final_cost"{print $2}')
    if [ -n "$c0" ] && [ "$c0" = "$c1" ]; then echo "OK        $fam/$inst seed $seed iterations $it cost $c0"; else echo "DIFFERENT $fam/$inst seed $seed iterations $it: $c0 <> $c1"; fi
    exit 0
  fi
  [ -s "$pre.run.csv" ] && exit 0                    # run.csv is written LAST: if it exists the run is complete
  tl=$(awk -v tc="$TC" -v n="$n" -v tm="$TMIN" 'BEGIN{t=tc*n/100; if(t<tm)t=tm; printf "%.3f", t}')
  t0=$(date +%s)
  "$BIN" --instance "$INSTROOT/$fam/$inst.inst" --seed "$seed" "${FA[@]}" --time "$tl" --max-iter 100000 --out-level "$OUTLEVEL" --algo "$TAG" --quiet --out "$pre" \
      > "$log" 2>&1 || echo "ERROR: $fam/$inst seed $seed (see $log)"
  if [ "$VERIFY" = 1 ] && [ -s "$pre.run.csv" ]; then "$TOOLS" verify "$INSTROOT/$fam/$inst.inst" "$pre" > "$pre.verify" 2>&1 || echo "VERIFICATION FAILED: $fam/$inst seed $seed (see $pre.verify)"; fi
  echo "[$(date +%H:%M:%S)] $fam/$inst seed $seed  limit ${tl}s  $(( $(date +%s) - t0 )) s wall"
  exit 0
fi

# ------------------------------------------------------------------ main mode
[ -x "$BIN" ] && [ -x "$TOOLS" ] || { echo "binaries missing (bin/llrp_fast, bin/llrp_tools): run ./build.sh first"; exit 1; }
[ -s "$MANIFEST" ] || { echo "manifest missing: $MANIFEST"; exit 1; }
[ -x "$HERE/check_inst_data.sh" ] && { "$HERE/check_inst_data.sh" || exit 1; }
[ "${PLAN_ONLY:-0}" = 1 ] || [ -s "$FLAGS_FILE" ] || { echo "FLAGS_FILE empty/missing: $FLAGS_FILE  (after irace: bin/llrp_tools irace-flags --from-log irace/irace_stdout.txt --out irace/best.flags)"; exit 1; }
FAMILY=${FAMILY:-all}
case $FAMILY in
  custom) [ $# -gt 0 ] || { echo "FAMILY=custom needs instance names"; exit 1; }
          LIST=""; for i in "$@"; do r=$(awk -F'\t' -v nm="$i" 'NR>1 && $2==nm{print $1, $2, $3; f=1} END{exit f?0:1}' "$MANIFEST") || { echo "not in manifest: $i"; exit 1; }; LIST+="$r"$'\n'; done;;
  all)    LIST=$(awk -F'\t' 'NR>1{print $1, $2, $3}' "$MANIFEST");;
  *)      LIST=$(awk -F'\t' -v f="$FAMILY" 'NR>1 && $1==f{print $1, $2, $3}' "$MANIFEST")
          [ -n "$LIST" ] || { echo "no such family in the manifest: $FAMILY"; exit 1; };;
esac
LIST=$(echo "$LIST" | grep -v '^$' | sort -k3,3nr -s)               # large instances first (LPT)
NINST=$(echo "$LIST" | wc -l)

# ---- time estimate
echo "$LIST" | awk -v tc="$TC" -v tm="$TMIN" -v S="$SEEDS" -v P="$PAR" '{t=tc*$3/100; if(t<tm)t=tm; cpu[$1]+=t*S; n[$1]++; tot+=t*S}
  END{for(f in cpu) printf "  %-8s %3d instances  %7.2f CPU-hours\n", f, n[f], cpu[f]/3600;
      printf "  TOTAL    %d tasks, %.2f CPU-hours -> about %.1f hours wall time with %d concurrent tasks (+5-15%%: limit overshoot and node load)\n", NR*S, tot/3600, tot/3600/P*1.1, P}'
if [ "${PLAN_ONLY:-0}" = 1 ]; then exit 0; fi

FA_STR=$(cat "$FLAGS_FILE"); export FA_STR
FAMS=$(echo "$LIST" | awk '!s[$1]++{print $1}')
for f in $FAMS; do
  D=$OUT/$f/$TAG; mkdir -p "$D/runs/log"
  ENVF=$D/env.txt; [ -e "$ENVF" ] && ENVF=$D/env_resume_$(date +%H%M%S).txt
  { echo "final_eval tag=$TAG family=$f seeds=$SEED0..$((SEED0+SEEDS-1)) budget=cpu_time max($TMIN, $TC*n/100) s, max-iter 100000, stall off, par=$PAR, pin=no"
    echo "flags=$FA_STR"
    echo "host=$(hostname) date=$(date -Iseconds) user=$(whoami) job=${JOB_ID:-none} NSLOTS=${NSLOTS:-none}"
    echo "cpu=$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo)"
    echo "load_before=$(cut -d' ' -f1-3 /proc/loadavg)"
    echo "binary_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
    echo "manifest_sha256=$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
    echo "flags_sha256=$(sha256sum "$FLAGS_FILE" | cut -d' ' -f1)"
    echo "instances=$(echo "$LIST" | awk -v f="$f" '$1==f{printf "%s ", $2}')"; } > "$ENVF"
done
TASKS=$(mktemp); trap 'rm -f "$TASKS"' EXIT
echo "$LIST" | while read -r fam inst n; do for ((k = 0; k < SEEDS; k++)); do echo "$fam $inst $n $((SEED0 + k))"; done; done > "$TASKS"
echo "== final [$TAG]: $NINST instances x $SEEDS seeds (seed $SEED0..$((SEED0+SEEDS-1))) = $(wc -l < "$TASKS") tasks, $PAR concurrent; flags: $FA_STR"
mkdir -p "$OUT"
xargs -P "$PAR" -L 1 "$0" --task < "$TASKS" 2>&1 | tee -a "$OUT/final_progress.log" | grep -E "ERROR|FAILED" ; true
for f in $FAMS; do echo "load_after=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT/$f/$TAG/env.txt"; done

# ---- reproducibility check: re-create REPLAY sample runs from their iteration counts (smallest instances first)
if [ "$REPLAY" -gt 0 ]; then
  stride=$((SEEDS * 2 + 1))
  tac "$TASKS" | awk -v s="$stride" '(NR-1)%s==0' | head -n "$REPLAY" | xargs -P "$PAR" -I{} sh -c '"$0" --task {} replay' "$0" > "$OUT/replay_check_$TAG.txt" 2>&1
  echo "== replay check ($(wc -l < "$OUT/replay_check_$TAG.txt") runs): $(grep -c '^OK' "$OUT/replay_check_$TAG.txt") OK, $(grep -c '^DIFFERENT' "$OUT/replay_check_$TAG.txt") DIFFERENT  -> $OUT/replay_check_$TAG.txt"
fi

# ---- merge + summarise (per family)
rc=0
for f in $FAMS; do
  D=$OUT/$f/$TAG
  "$TOOLS" merge "$D" > /dev/null || { rc=1; continue; }
  echo "== $f: $D/run.csv ($(($(wc -l < "$D/run.csv") - 1)) runs)"
  TRAINF=$HERE/selection/train.txt; SA=(--manifest "$MANIFEST"); [ -s "$TRAINF" ] && SA+=(--train "$TRAINF")
  "$TOOLS" summarize "$D/run.csv" --csv "$D/summary.csv" "${SA[@]}" | tee "$D/summary.txt" || true
done
if [ "$VERIFY" = 1 ]; then
  nrun=$(ls "$OUT"/*/"$TAG"/runs/*.verify 2>/dev/null | wc -l); nbad=$(grep -L '^OK' "$OUT"/*/"$TAG"/runs/*.verify 2>/dev/null | wc -l)
  echo "independent verification (llrp_tools verify): $nrun runs, failed $nbad"; [ "$nbad" -eq 0 ] || rc=1
fi
exit $rc
