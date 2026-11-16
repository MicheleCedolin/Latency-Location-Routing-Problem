#!/bin/bash
# Post-hoc local-search (VND) ablation on a FINISHED campaign, see ABLATION.md. Scheduler independent. Nothing inside the run folders is modified;
# everything goes to $OUT (default $RUN/ablation) and the stages share that folder (profile.csv, configs.json, configs/*.csv).
#
#   RUN          run folder that holds (or will hold) report.csv, e.g. analysis/phaseA_P50_120s_30seeds           (required)
#   STAGE        stages to run, separated by colons (qsub -v splits on commas):  0:1  (default)  |  2  |  3  |  4  |  0:1:3 ...
#                2 needs KEEP; 3 and 4 need SET (or KEEP).  Stage 3 runs `profile` first if profile.csv is missing.
#   KEEP         classes retained after stage 1, letters only, e.g. ABCDE      (stage 2; default SET = classes:KEEP for stages 3/4)
#   SET          operator set for stages 3/4: classes:ABCDE | ops:a+b+c | a configuration name such as S2_ref_ABCDE
#   SEEDS        seed filter, a range such as 1-10 (default 1-10; use `1-30` for the confirmation run)
#   INSTANCES    optional instance filter, colon separated
#   METHODS      optional method filter, colon separated (e.g. lns:tabu:grasp+first)
#   CONFIG_FILE  optional extra configurations ("name | driver | ops | reference" per line)
#   MAX_SECONDS  safety cap per solution            (default 120)
#   WORKERS      parallel processes                 (default $NSLOTS, $SLURM_CPUS_PER_TASK, else nproc)
#   OUT          output folder                      (default $RUN/ablation)
#   MARGIN       equivalence margin in gap points   (default 0.05)
#   BOOT         bootstrap resamples                (default 4000)
#   PYTHON       interpreter                        (default python3)
#
# Exit code 1 if any step reported a problem (e.g. a stored solution that does not reproduce its objective).
set -u

ROOT="${KIT_ROOT:-${SGE_O_WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
cd "$ROOT" || exit 2
[ -f "$ROOT/hpc/pyenv.sh" ] && { . "$ROOT/hpc/pyenv.sh" || exit 2; }
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

PYTHON="${PYTHON:-python3}"
RUN="${RUN:-}"
STAGE="${STAGE:-0:1}"
KEEP="${KEEP:-}"
SET="${SET:-}"
SEEDS="${SEEDS:-1-10}"
INSTANCES="${INSTANCES:-}"
METHODS="${METHODS:-}"
CONFIG_FILE="${CONFIG_FILE:-}"
MAX_SECONDS="${MAX_SECONDS:-120}"
WORKERS="${WORKERS:-${NSLOTS:-${SLURM_CPUS_PER_TASK:-$(nproc)}}}"
MARGIN="${MARGIN:-0.05}"
BOOT="${BOOT:-4000}"

[ -n "$RUN" ] || { echo "ERROR: RUN=<run folder> is required, e.g. RUN=analysis/phaseA_P50_120s_30seeds"; exit 2; }
case "$RUN" in /*) ;; *) RUN="$ROOT/$RUN" ;; esac
RUN="${RUN%/}"
[ -d "$RUN" ] || { echo "ERROR: run folder not found: $RUN"; exit 2; }
OUT="${OUT:-$RUN/ablation}"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "ERROR: Python >= 3.10 required, got $("$PYTHON" -V 2>&1) -- no conda environment with Python >= 3.10 was found (set CONDA_SH / CONDA_ENV)"; exit 2; }
[ -f tools/ls_ablation.py ] || { echo "ERROR: tools/ls_ablation.py missing (unzip the ablation package into the kit folder)"; exit 2; }

if [ ! -f "$RUN/report.csv" ]; then
    echo "== report.csv not found, running collect.py"
    "$PYTHON" collect.py "$RUN" || { echo "ERROR: collect.py failed (exit $?)"; exit 3; }
fi
[ -f "$RUN/report.csv" ] || { echo "ERROR: $RUN/report.csv still missing"; exit 3; }

ST="$(echo "$STAGE" | tr ':;' ',,')"
FILT=(--seeds "$SEEDS")
[ -n "$INSTANCES" ] && FILT+=(--instances "$(echo "$INSTANCES" | tr ':;' ',,')")
[ -n "$METHODS" ] && FILT+=(--methods "$(echo "$METHODS" | tr ':;' ',,')")
EXTRA=()
[ -n "$KEEP" ] && EXTRA+=(--keep "$KEEP")
[ -n "$SET" ] && EXTRA+=(--set "$SET")
[ -n "$CONFIG_FILE" ] && EXTRA+=(--config-file "$CONFIG_FILE")

rc=0
echo "== run folder : $RUN"
echo "== output     : $OUT"
echo "== stages     : $ST, seeds: $SEEDS, workers: $WORKERS, cap per solution: ${MAX_SECONDS}s"
case ",$ST," in
    *,3,*)
        if [ ! -f "$OUT/profile.csv" ]; then
            echo "== profile (needed by the stage-3 orders)"
            "$PYTHON" tools/ls_ablation.py profile --report "$RUN/report.csv" --out "$OUT" --workers "$WORKERS" ${FILT[@]+"${FILT[@]}"} || rc=1
        fi ;;
esac
echo "== run"
"$PYTHON" tools/ls_ablation.py run --report "$RUN/report.csv" --out "$OUT" --stage "$ST" --workers "$WORKERS" --max-seconds "$MAX_SECONDS" ${FILT[@]+"${FILT[@]}"} ${EXTRA[@]+"${EXTRA[@]}"} || rc=1
echo
echo "== summarize"
"$PYTHON" tools/ls_ablation.py summarize --out "$OUT" --margin "$MARGIN" --boot "$BOOT" || rc=1
echo
[ "$rc" -eq 0 ] && echo "== ablation finished without problems" || echo "== ablation finished WITH PROBLEMS (see messages above)"
exit $rc
