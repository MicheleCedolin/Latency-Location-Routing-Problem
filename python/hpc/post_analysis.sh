#!/bin/bash
# Post-analysis of a FINISHED campaign: ONE common local search is applied to the stored final solution of EVERY method (no re-run),
# followed by ranking statistics. Scheduler independent. Nothing inside the run folders is modified; results go to new sub-folders of RUN.
#
#   RUN          run folder that holds (or will hold) report.csv, e.g. analysis/phaseA_P50_120s_30seeds     (required)
#                if report.csv is missing, `collect.py RUN` is run first
#   PRESETS      colon separated list of neighbourhood presets; each is applied to ALL methods   (default: common5)
#                common5 = frozen Phase-B VND (5 moves); hgamp = 15 moves; baseline_route / light also exist
#   LS           vnd | rvnd | best | first                                         (default: vnd)
#   SEEDS        optional seed filter, e.g. 1-10 (default: all seeds)
#   MAX_SECONDS  safety cap per polished solution                                   (default: 120)
#   WORKERS      parallel processes   (default: $NSLOTS, $SLURM_CPUS_PER_TASK, else nproc)
#   PYTHON       interpreter                                                        (default: python3)
#
# Outputs (RUN/...):
#   rank_phaseA/                      ranking + tests of the campaign as it is (stage "before")
#   polish_<LS>_<PRESET>[_s<SEEDS>]/  polished_report.csv, polish_by_heuristic.csv, polish_by_instance_heuristic.csv, polish_settings.txt,
#                                     rank/ (before vs after: rank_before_after.csv, rank_summary_*.csv, friedman_*.txt, pairwise_wins_*.csv, rank_report.md)
# Exit code 1 if any step reported a problem (e.g. a stored solution that does not reproduce its objective).
set -u

ROOT="${KIT_ROOT:-${SGE_O_WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
cd "$ROOT" || exit 2
[ -f "$ROOT/hpc/pyenv.sh" ] && { . "$ROOT/hpc/pyenv.sh" || exit 2; }
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

PYTHON="${PYTHON:-python3}"
RUN="${RUN:-}"
PRESETS="${PRESETS:-common5}"
LS="${LS:-vnd}"
SEEDS="${SEEDS:-}"
MAX_SECONDS="${MAX_SECONDS:-120}"
WORKERS="${WORKERS:-${NSLOTS:-${SLURM_CPUS_PER_TASK:-$(nproc)}}}"

[ -n "$RUN" ] || { echo "ERROR: RUN=<run folder> is required, e.g. RUN=analysis/phaseA_P50_120s_30seeds"; exit 2; }
case "$RUN" in /*) ;; *) RUN="$ROOT/$RUN" ;; esac
RUN="${RUN%/}"
[ -d "$RUN" ] || { echo "ERROR: run folder not found: $RUN"; exit 2; }
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "ERROR: Python >= 3.10 required, got $("$PYTHON" -V 2>&1) -- no conda environment with Python >= 3.10 was found (set CONDA_SH / CONDA_ENV)"; exit 2; }
for f in tools/polish_report.py tools/rank_stats.py; do [ -f "$f" ] || { echo "ERROR: $f missing (unzip the post-analysis package into the kit folder)"; exit 2; }; done

if [ ! -f "$RUN/report.csv" ]; then
    echo "== report.csv not found, running collect.py"
    "$PYTHON" collect.py "$RUN" || { echo "ERROR: collect.py failed (exit $?)"; exit 3; }
fi
[ -f "$RUN/report.csv" ] || { echo "ERROR: $RUN/report.csv still missing"; exit 3; }

rc=0
echo "== run folder : $RUN"
echo "== local search: $LS, presets: $PRESETS, seeds: ${SEEDS:-all}, workers: $WORKERS, cap per solution: ${MAX_SECONDS}s"
echo "== stage 0: ranking of the campaign as it is"
"$PYTHON" tools/rank_stats.py --report "$RUN/report.csv" --out "$RUN/rank_phaseA" || rc=1

for P in $(echo "$PRESETS" | tr ',:;' '   '); do
    SUF="${LS}_${P}"; [ -n "$SEEDS" ] && SUF="${SUF}_s${SEEDS}"
    OUTD="$RUN/polish_${SUF}"
    echo
    echo "== polish with $LS/$P on every method -> $OUTD"
    "$PYTHON" tools/polish_report.py --report "$RUN/report.csv" --ls "$LS" --preset "$P" --workers "$WORKERS" \
              --max-seconds "$MAX_SECONDS" ${SEEDS:+--seeds "$SEEDS"} --out "$OUTD" || rc=1
    if [ -f "$OUTD/polished_report.csv" ]; then
        "$PYTHON" tools/rank_stats.py --report "$OUTD/polished_report.csv" --out "$OUTD/rank" || rc=1
        echo "-- before / after (mean gap %, mean rank over instances):"
        "$PYTHON" - "$OUTD/rank/rank_before_after.csv" <<'PY'
import csv, sys
try:
    rows = list(csv.DictReader(open(sys.argv[1])))
except OSError:
    sys.exit(0)
print(f"{'method':14} {'gap before':>10} {'gap after':>10} {'pos before':>10} {'pos after':>10}")
for r in rows:
    print(f"{r['method']:14} {float(r['gap_before_pct']):10.2f} {float(r['gap_after_pct']):10.2f} {r['position_before']:>10} {r['position_after']:>10}")
PY
    fi
done
echo
[ "$rc" -eq 0 ] && echo "== post-analysis finished without problems" || echo "== post-analysis finished WITH PROBLEMS (see messages above)"
exit $rc
