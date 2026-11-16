#!/bin/bash
# EXTENDED-BUDGET EVALUATION (sibling of run_final.sh; does NOT touch run_final.sh, writes to its own result directory).
# Same flags (irace/best.flags), same seeds (1..30), same binary; only (a) the instance list and (b) the CPU-time budget differ:
#   INSTLIST=ext10_instances.txt TC=300 TAG=ext10 OUT=results_extended10 ./run_extended.sh   # study setting "ext10": 58 instances, budget 3n s = 10 x max{5, 0.3 n}
#   INSTLIST=list.txt BUDGET_FILE=budgets.tsv ./run_extended.sh     # explicit seconds per instance (file with lines "instance seconds")
#   INSTLIST=list.txt TC=90 ./run_extended.sh                       # K times the base budget: TC = 30*K  (budget = max(TMIN, TC*n/100) s)
#   PLAN_ONLY=1 INSTLIST=... TC=... ./run_extended.sh               # time estimate only; nothing is started
#   qsub run_extended.sge                                           # submit to an SGE queue (environment variables are passed with -V)
# Results: $OUT/<family>/$TAG/{run,routes,ops,trace}.csv , summary.txt , env.txt , runs/   (defaults OUT=results_extended, TAG=ext)
# An interrupted job resumes where it stopped with the same command. The time limit is checked at the end of a GRASP iteration (the limit can be exceeded by at most one iteration).
#
# SCRATCH=1 (default 0): to avoid the small-file latency of a shared file system (NFS), about six files per run are written to the node's LOCAL disk
#   ($TMPDIR, otherwise /tmp; change with SCR_PARENT) instead of NFS; the binaries and instance files are copied to the local disk as well. Merging and summarising are done locally;
#   at the end only the merged CSV files and one runs.tar.gz per family (raw run files) are copied to NFS. Every SYNC_SEC seconds (default 1200) a single-file snapshot of the local
#   'runs' tree ($OUT/scratch_snapshot.tar) is taken; if the job is interrupted, the same command restores the snapshot and skips completed runs
#   (only runs whose .verify says OK are restored; unfinished runs are re-run). The solution path is independent of SCRATCH: only the file location changes.
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=${BIN:-$HERE/bin/llrp_fast}; TOOLS=${TOOLS:-$HERE/bin/llrp_tools}
INSTROOT=${INSTROOT:-$HERE/inst}; MANIFEST=${MANIFEST:-$HERE/manifest.tsv}
FLAGS_FILE=${FLAGS_FILE:-$HERE/irace/best.flags}
SEEDS=${SEEDS:-30}; SEED0=${SEED0:-1}; TC=${TC:-30}; TMIN=${TMIN:-5}; TAG=${TAG:-ext}
OUT=${OUT:-$HERE/results_extended}; OUTLEVEL=${OUTLEVEL:-1}; VERIFY=${VERIFY:-1}; REPLAY=${REPLAY:-10}
PAR=${PAR:-${NSLOTS:-30}}
INSTLIST=${INSTLIST:-}; BUDGET_FILE=${BUDGET_FILE:-}; OVERHEAD=${OVERHEAD:-150}   # OVERHEAD: fixed non-solver wall time per run (s), used for the estimate only
export INSTLIST BUDGET_FILE
export HERE BIN TOOLS INSTROOT MANIFEST SEEDS SEED0 TC TMIN TAG OUT OUTLEVEL VERIFY

# ------------------------------------------------------------------ task mode: one (instance, seed) run
if [ "${1:-}" = "--task" ]; then
  fam=$2; inst=$3; n=$4; seed=$5; mode=${6:-run}
  set -f; read -ra FA <<< "$FA_STR"
  RUNS=${LSCR:-$OUT}/$fam/$TAG/runs; mkdir -p "$RUNS/log"
  pre=$RUNS/${inst}_s${seed}; log=$RUNS/log/${inst}_s${seed}.log
  if [ "$mode" = replay ]; then                     # reproduce a time-limited run from its iteration count
    it=$(awk '$1=="iterations"{print $2}' "$log"); c0=$(awk '$1=="final_cost"{print $2}' "$log")
    c1=$("$BIN" --instance "$INSTROOT/$fam/$inst.inst" --seed "$seed" "${FA[@]}" --max-iter "$it" --quiet | awk '$1=="final_cost"{print $2}')
    if [ -n "$c0" ] && [ "$c0" = "$c1" ]; then echo "OK        $fam/$inst seed $seed iterations $it cost $c0"; else echo "DIFFERENT $fam/$inst seed $seed iterations $it: $c0 <> $c1"; fi
    exit 0
  fi
  [ -s "$pre.run.csv" ] && exit 0                    # run.csv is written LAST: if it exists the run is complete
  if [ -n "$BUDGET_FILE" ]; then
    tl=$(awk -v i="$inst" '$1==i{printf "%.3f", $2; f=1} END{exit f?0:1}' "$BUDGET_FILE") || { echo "NO BUDGET: $inst ($BUDGET_FILE)"; exit 1; }
  else
    tl=$(awk -v tc="$TC" -v n="$n" -v tm="$TMIN" 'BEGIN{t=tc*n/100; if(t<tm)t=tm; printf "%.3f", t}')
  fi
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
if [ -n "$INSTLIST" ]; then
  [ -s "$INSTLIST" ] || { echo "INSTLIST missing/empty: $INSTLIST"; exit 1; }
  set -- $(grep -v '^#' "$INSTLIST" | awk 'NF{print $1}'); FAMILY=custom
fi
[ -z "$BUDGET_FILE" ] || [ -s "$BUDGET_FILE" ] || { echo "BUDGET_FILE missing/empty: $BUDGET_FILE"; exit 1; }
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
echo "$LIST" | awk -v tc="$TC" -v tm="$TMIN" -v S="$SEEDS" -v P="$PAR" -v bf="$BUDGET_FILE" -v oh="$OVERHEAD" '
  BEGIN{if(bf!=""){while((getline l < bf)>0){split(l,a," "); b[a[1]]=a[2]}}}
  {t=(bf!="")?b[$2]:tc*$3/100; if(bf=="" && t<tm)t=tm; cpu[$1]+=t*S; n[$1]++; tot+=t*S; runs+=S}
  END{for(f in cpu) printf "  %-8s %3d instances  %7.2f CPU-hours\n", f, n[f], cpu[f]/3600;
      printf "  TOTAL    %d tasks, %.2f CPU-hours -> about %.1f hours wall time with %d concurrent tasks (solver only, +5-15%% limit overshoot / load)\n", runs, tot/3600, tot/3600/P*1.1, P;
      printf "           with ~%d s of fixed non-solver overhead per run (observed in the final evaluation): about %.1f hours\n", oh, (tot*1.1+runs*oh)/3600/P}'
if [ "${PLAN_ONLY:-0}" = 1 ]; then exit 0; fi

FA_STR=$(cat "$FLAGS_FILE"); export FA_STR
if [ -n "$BUDGET_FILE" ]; then BUDGET_DESC="per-instance seconds from $BUDGET_FILE"; else BUDGET_DESC="max($TMIN, $TC*n/100) s"; fi
FAMS=$(echo "$LIST" | awk '!s[$1]++{print $1}')

# ---- local scratch (SCRATCH=1)
LSCR=""; SYNC_PID=""
if [ "${SCRATCH:-0}" = 1 ]; then
  SP=${SCR_PARENT:-${TMPDIR:-/tmp}}
  LSCR=$(mktemp -d "$SP/llrp_${TAG}_XXXXXX" 2>/dev/null) || { echo "WARNING: cannot create local scratch ($SP); writing directly to $OUT"; LSCR=""; }
  if [ -n "$LSCR" ]; then
    free_kb=$(df -Pk "$LSCR" 2>/dev/null | awk 'NR==2{print $4}')
    if [ "${free_kb:-0}" -lt 2000000 ]; then echo "WARNING: less than 2 GB free in $SP; writing directly to $OUT"; rm -rf "$LSCR"; LSCR=""; fi
  fi
fi
snapshot() {
  [ -n "$LSCR" ] || return 0
  ( cd "$LSCR" && tar cf "$OUT/scratch_snapshot.tar.part" $(for g in $FAMS; do echo "$g/$TAG/runs"; done) 2>/dev/null; [ $? -le 1 ] ) && mv -f "$OUT/scratch_snapshot.tar.part" "$OUT/scratch_snapshot.tar"
}
if [ -n "$LSCR" ]; then
  mkdir -p "$LSCR/bin" "$LSCR/inst" "$OUT"
  cp "$BIN" "$LSCR/bin/llrp_fast" && cp "$TOOLS" "$LSCR/bin/llrp_tools" || { echo "cannot copy binaries"; exit 1; }
  echo "$LIST" | while read -r fam inst n; do mkdir -p "$LSCR/inst/$fam"; cp "$INSTROOT/$fam/$inst.inst" "$LSCR/inst/$fam/" || exit 1; done || { echo "cannot copy instance files"; exit 1; }
  BIN=$LSCR/bin/llrp_fast; TOOLS=$LSCR/bin/llrp_tools; INSTROOT=$LSCR/inst; export BIN TOOLS INSTROOT LSCR
  echo "== SCRATCH=1: local directory $(hostname):$LSCR (free $((free_kb / 1024)) MB), snapshot every ${SYNC_SEC:-1200} s -> $OUT/scratch_snapshot.tar"
fi

for f in $FAMS; do
  D=$OUT/$f/$TAG; mkdir -p "$D"; if [ -n "$LSCR" ]; then mkdir -p "$LSCR/$f/$TAG/runs/log"; else mkdir -p "$D/runs/log"; fi
  ENVF=$D/env.txt; [ -e "$ENVF" ] && ENVF=$D/env_resume_$(date +%H%M%S).txt
  { echo "final_eval tag=$TAG family=$f seeds=$SEED0..$((SEED0+SEEDS-1)) budget=cpu_time $BUDGET_DESC, max-iter 100000, stall off, par=$PAR, pin=no"
    echo "flags=$FA_STR"
    echo "host=$(hostname) date=$(date -Iseconds) user=$(whoami) job=${JOB_ID:-none} NSLOTS=${NSLOTS:-none}"
    echo "cpu=$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo)"
    echo "load_before=$(cut -d' ' -f1-3 /proc/loadavg)"
    echo "scratch=${LSCR:-none}"
    echo "binary_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
    echo "manifest_sha256=$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
    echo "flags_sha256=$(sha256sum "$FLAGS_FILE" | cut -d' ' -f1)"
    echo "instances=$(echo "$LIST" | awk -v f="$f" '$1==f{printf "%s ", $2}')"; } > "$ENVF"
done
TASKS=$(mktemp)
cleanup() { [ -n "$SYNC_PID" ] && { pkill -P "$SYNC_PID" 2>/dev/null; kill "$SYNC_PID" 2>/dev/null; wait "$SYNC_PID" 2>/dev/null; }; rm -f "$TASKS"; }   # also stop the loop's sleep (an orphaned sleep would keep a pipe open)
trap cleanup EXIT
if [ -n "$LSCR" ]; then
  if [ -s "$OUT/scratch_snapshot.tar" ]; then                      # resume after an interruption: restore the snapshot, discard unfinished runs
    tar xf "$OUT/scratch_snapshot.tar" -C "$LSCR" && echo "== previous snapshot restored: $(ls "$LSCR"/*/"$TAG"/runs/*.run.csv 2>/dev/null | wc -l) runs"
    if [ "$VERIFY" = 1 ]; then
      for rf in "$LSCR"/*/"$TAG"/runs/*.run.csv; do
        [ -e "$rf" ] || continue; p=${rf%.run.csv}
        grep -q '^OK' "$p.verify" 2>/dev/null || { rm -f "$p".* "$(dirname "$p")/log/$(basename "$p").log"; echo "  unfinished run deleted (will be re-run): $(basename "$p")"; }
      done
    fi
  fi
  ( while sleep "${SYNC_SEC:-1200}"; do snapshot; done ) & SYNC_PID=$!
  trap 'echo "INTERRUPTED: taking the last snapshot"; snapshot; exit 1' TERM INT USR1 USR2
fi
echo "$LIST" | while read -r fam inst n; do for ((k = 0; k < SEEDS; k++)); do echo "$fam $inst $n $((SEED0 + k))"; done; done > "$TASKS"
echo "== final [$TAG]: $NINST instances x $SEEDS seeds (seed $SEED0..$((SEED0+SEEDS-1))) = $(wc -l < "$TASKS") tasks, $PAR concurrent; flags: $FA_STR"
xargs -P "$PAR" -L 1 "$0" --task < "$TASKS" 2>&1 | tee -a "$OUT/final_progress.log" | grep -E "ERROR|FAILED" ; true
for f in $FAMS; do echo "load_after=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$OUT/$f/$TAG/env.txt"; done

# ---- reproducibility check: re-create REPLAY sample runs from their iteration counts (smallest instances first)
if [ "$REPLAY" -gt 0 ]; then
  stride=$((SEEDS * 2 + 1))
  tac "$TASKS" | awk -v s="$stride" '(NR-1)%s==0' | head -n "$REPLAY" | xargs -P "$PAR" -I{} sh -c '"$0" --task {} replay' "$0" > "$OUT/replay_check_$TAG.txt" 2>&1
  echo "== replay check ($(wc -l < "$OUT/replay_check_$TAG.txt") runs): $(grep -c '^OK' "$OUT/replay_check_$TAG.txt") OK, $(grep -c '^DIFFERENT' "$OUT/replay_check_$TAG.txt") DIFFERENT  -> $OUT/replay_check_$TAG.txt"
fi

# ---- merge + summarise (per family)
rc=0; ROOT=${LSCR:-$OUT}
for f in $FAMS; do
  D=$ROOT/$f/$TAG
  "$TOOLS" merge "$D" > /dev/null || { rc=1; continue; }
  echo "== $f: $D/run.csv ($(($(wc -l < "$D/run.csv") - 1)) runs)"
  TRAINF=$HERE/selection/train.txt; SA=(--manifest "$MANIFEST"); [ -s "$TRAINF" ] && SA+=(--train "$TRAINF")
  "$TOOLS" summarize "$D/run.csv" --csv "$D/summary.csv" "${SA[@]}" | tee "$D/summary.txt" || true
done
if [ "$VERIFY" = 1 ]; then
  nrun=$(ls "$ROOT"/*/"$TAG"/runs/*.verify 2>/dev/null | wc -l); nbad=$(grep -L '^OK' "$ROOT"/*/"$TAG"/runs/*.verify 2>/dev/null | wc -l)
  echo "independent verification (llrp_tools verify): $nrun runs, failed $nbad"; [ "$nbad" -eq 0 ] || rc=1
fi
if [ -n "$LSCR" ]; then                                            # copy to NFS in one go: merged CSVs + raw run files in one archive + last snapshot
  for f in $FAMS; do
    D=$LSCR/$f/$TAG; O=$OUT/$f/$TAG; mkdir -p "$O"
    for k in run routes ops trace; do cp "$D/$k.csv" "$O/" || rc=1; done
    cp "$D/summary.csv" "$D/summary.txt" "$O/" 2>/dev/null || rc=1
    tar czf "$O/runs.tar.gz" -C "$D" runs || rc=1
  done
  snapshot
  if [ "$rc" -eq 0 ]; then rm -rf "$LSCR"; echo "scratch copied to NFS and removed; raw run files: $OUT/<family>/$TAG/runs.tar.gz"
  else echo "WARNING: errors occurred, local directory not removed: $(hostname):$LSCR (snapshot: $OUT/scratch_snapshot.tar)"; fi
fi
exit $rc
