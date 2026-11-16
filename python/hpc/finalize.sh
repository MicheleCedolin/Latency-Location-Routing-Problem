#!/bin/bash
# Close one sharded stage: check that every arm finished on the SAME manifest, then collect, audit and tabulate. Scheduler independent.
#
#   OUT      stage folder written by the arms of hpc/run.sh (required), e.g. analysis/llrp_campaign/P20_60s_30seeds
#   ARMS     number of arms (default: shards= in <OUT>/run_settings.txt)
#   RANK     1 (default) also runs tools/rank_stats.py -> <OUT>/rank_phaseA/ (non-fatal: it needs a few instances)
#   HIT_PCT  gap threshold of the "hits" column in the stage table (default 0.01)
#   PYTHON   interpreter (default: python3)
#
# Checks (all must hold for exit code 0):
#   1. one marker <OUT>/shards/arm_<i>of<N>.txt per arm, state=done, no failed / missing runs
#   2. all markers carry the same jobs_sha256 and it equals the hash of <OUT>/jobs.txt (the arms agree on the manifest)
#   3. the arm shares add up to the manifest, and the number of summary.csv files equals the manifest
#   4. verify_run.py (manifest completeness, duplicates, stored solutions re-evaluated with the kit's own evaluator)
# Writes FINALIZE_OK or FINALIZE_FAILED (with the reasons) into OUT, collect.log, verify.log, report.csv, stage_table_by_*.csv, arm_hosts.txt.
set -u
ROOT="${KIT_ROOT:-${SGE_O_WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
cd "$ROOT" || exit 2
[ -f "$ROOT/hpc/pyenv.sh" ] && { . "$ROOT/hpc/pyenv.sh" || exit 2; }
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PYTHON="${PYTHON:-python3}"
OUT="${OUT:-}"
[ -n "$OUT" ] || { echo "ERROR: OUT=<stage folder> is required"; exit 2; }
case "$OUT" in /*) ;; *) OUT="$ROOT/$OUT" ;; esac
OUT="${OUT%/}"
[ -f "$OUT/jobs.txt" ] || { echo "ERROR: $OUT/jobs.txt not found (no arm has started in this folder?)"; exit 2; }
ARMS="${ARMS:-$(sed -n 's/^shards=//p' "$OUT/run_settings.txt" 2>/dev/null | head -n 1)}"
case "$ARMS" in ''|*[!0-9]*) echo "ERROR: ARMS is not set and not recorded in $OUT/run_settings.txt"; exit 2 ;; esac
RANK="${RANK:-1}"; HIT_PCT="${HIT_PCT:-0.01}"

rm -f "$OUT/FINALIZE_OK" "$OUT/FINALIZE_FAILED"
PROBLEMS=()
note () { PROBLEMS+=("$1"); echo "PROBLEM: $1"; }
field () { sed -n "s/^$2=//p" "$1" | head -n 1; }

TOTAL=$(wc -l < "$OUT/jobs.txt")
JSHA="$("$PYTHON" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$OUT/jobs.txt")"
echo "== stage $OUT | manifest $TOTAL runs | $ARMS arms"
: > "$OUT/arm_hosts.txt"
sum_arm=0
for ((i=0; i<ARMS; i++)); do
    f="$OUT/shards/arm_${i}of${ARMS}.txt"
    if [ ! -f "$f" ]; then note "arm $i: marker missing (arm never started, or ARMS differs from the submitted value)"; continue; fi
    st="$(field "$f" state)"; sha="$(field "$f" jobs_sha256)"; nj="$(field "$f" jobs_arm)"
    fl="$(field "$f" failed)"; ms="$(field "$f" missing)"
    printf 'arm %s | state=%s | runs=%s | failed=%s | missing=%s | host=%s | cpu=%s | job=%s.%s\n' "$i" "$st" "$nj" "$fl" "$ms" \
        "$(field "$f" host)" "$(field "$f" cpu)" "$(field "$f" job_id)" "$(field "$f" task_id)" | tee -a "$OUT/arm_hosts.txt"
    [ "$st" = "done" ] || note "arm $i: state is '$st' (not done)"
    { [ "${fl:-0}" = "0" ] && [ "${ms:-0}" = "0" ]; } || note "arm $i: failed=$fl missing=$ms"
    [ "$sha" = "$JSHA" ] || note "arm $i: manifest hash differs from jobs.txt (the arms were started with different settings)"
    case "$nj" in ''|*[!0-9]*) ;; *) sum_arm=$((sum_arm + nj)) ;; esac
done
[ "$sum_arm" -eq "$TOTAL" ] || note "arm shares add up to $sum_arm runs, manifest has $TOTAL"
SUMMARIES=$(find "$OUT" -name summary.csv | wc -l)
[ "$SUMMARIES" -eq "$TOTAL" ] || note "$SUMMARIES summary.csv files, manifest has $TOTAL"
FAILED=$(find "$OUT" -name exit_code.txt -exec sh -c 'test "$(cat "$1")" != 0' _ {} \; -print | wc -l)
[ "$FAILED" -eq 0 ] || note "$FAILED runs with exit code != 0"

echo "== collect"
"$PYTHON" collect.py "$OUT" > "$OUT/collect.log" 2>&1 || note "collect.py failed, see $OUT/collect.log"
tail -n 3 "$OUT/collect.log"
echo "== verify (manifest + re-evaluation of every stored solution)"
"$PYTHON" verify_run.py "$OUT" > "$OUT/verify.log" 2>&1 || note "verify_run.py reported problems, see $OUT/verify.log"
tail -n 3 "$OUT/verify.log"
echo "== stage table"
"$PYTHON" tools/stage_table.py "$OUT" --hit-pct "$HIT_PCT" | tee "$OUT/stage_table.txt" || note "stage_table.py failed"
if [ "$RANK" = "1" ] && [ -f "$OUT/report.csv" ]; then
    echo "== ranking statistics"
    "$PYTHON" tools/rank_stats.py --report "$OUT/report.csv" --out "$OUT/rank_phaseA" > "$OUT/rank.log" 2>&1 \
        && echo "rank_stats ok -> $OUT/rank_phaseA" || echo "NOTE: rank_stats.py did not finish (see $OUT/rank.log); not a stage failure"
fi

if [ "${#PROBLEMS[@]}" -eq 0 ]; then
    { echo "finalized_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "runs=$TOTAL"; echo "arms=$ARMS"; echo "jobs_sha256=$JSHA"
      echo "code_version=$(cat "$ROOT/VERSION" 2>/dev/null)"; } > "$OUT/FINALIZE_OK"
    echo "== FINALIZE OK: $TOTAL runs, $ARMS arms, manifest hash $JSHA"
    exit 0
fi
printf '%s\n' "${PROBLEMS[@]}" > "$OUT/FINALIZE_FAILED"
echo "== FINALIZE FAILED (${#PROBLEMS[@]} problem(s)); see $OUT/FINALIZE_FAILED. Missing or failed runs: resubmit the affected arms (resume skips finished runs), then run finalize again."
exit 1
