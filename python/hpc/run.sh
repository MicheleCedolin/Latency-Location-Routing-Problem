#!/bin/bash
# LLRP Phase-A fixed-budget launcher. Scheduler independent and resumable.
#
#   INSTANCES     group (P20 | P50 | P100 | P200 | B | T | T100 | T150 | T200 | ALL) or instance ids, separated by space, comma or colon;
#                 groups and ids can be mixed, e.g. P20:B or coord50-5-1:coordChrist50      (default: P50)
#   TIME_LIMIT    wall-clock seconds per run                                  (default: 120)
#   NSEEDS        seeds 1..NSEEDS                                             (default: 30)
#   CHECKPOINTS   colon separated seconds                                     (default: quarters of TIME_LIMIT)
#   METHODS_FILE  table "heuristic local_search neighborhoods" per line       (default: hpc/methods_phaseA.txt)
#   ONLY          optional heuristic filter, e.g. ONLY=grasp:sa
#   WORKERS       parallel single-core processes   (default: $NSLOTS, $SLURM_CPUS_PER_TASK, else nproc)
#   OUT           output directory                 (default: analysis/phaseA_<INSTANCES>_<T>s_<N>seeds)
#   ORDER         job order: seed (default) or instance
#                 seed     = seed-major: one seed of every instance and method, then the next seed (all methods of a seed
#                            run under similar machine load; a cut-off campaign has every instance with the same seeds)
#                 instance = instance-major: all seeds and methods of one instance, then the next instance (a cut-off
#                            campaign has complete instances; use it for long runs that may be stopped)
#   PYTHON        interpreter                                                 (default: python3)
#   SHARD         optional "i/N" (0 <= i < N): this process is arm i of N and runs only its share of the stage (see hpc/campaign_arm.sge).
#                 Every arm builds the SAME full job list, writes it as the manifest <OUT>/jobs.txt, and keeps the jobs with
#                     (position of the (instance, method) pair in the list + seed) mod N == i
#                 (a Latin-square rule: every arm gets the same number of runs, +-1 per seed, and every (instance, method) pair visits
#                 every arm in turn, so no method is tied to one node). Arms of one stage share OUT. A sharded run does not collect
#                 or verify (the other arms are still running); run hpc/finalize.sh when all arms are done.
#   EXTRA_ARGS    optional extra run_llrp.py options for every run, e.g. "--depot-impact adaptive --depot-impact-max-share 0.30" (adaptive depot layer;
#                 see hpc/pilot64.sh). They enter the run fingerprint, so a resume with other EXTRA_ARGS recomputes.
#                 Use a separate OUT per layer setting.
#
# Re-running with the same OUT resumes: a run is skipped only if it finished (exit_code.txt = 0) AND the fingerprint stored in
# its config.json equals the fingerprint the current code, parameters, instance and reference would produce. A finished run
# with a different fingerprint (code, parameters, budget, checkpoints, instance or interpreter family changed) is moved to
# <OUT>.superseded/ and recomputed; nothing is silently reused or deleted. jobs.txt is the manifest of expected runs that
# verify_run.py reconciles against the result folders.
# Algorithm hyper-parameters are NOT set here: they are the defaults of run_llrp.py
# (frozen values of this kit version) and are written to
# <run dir>/config.json for every run.
set -u

ROOT="${KIT_ROOT:-${SGE_O_WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
cd "$ROOT" || exit 2
[ -f "$ROOT/hpc/pyenv.sh" ] && { . "$ROOT/hpc/pyenv.sh" || exit 2; }   # python3 >= 3.10 (conda is found automatically)

export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1 MKL_DYNAMIC=FALSE OMP_DYNAMIC=FALSE

PYTHON="${PYTHON:-python3}"
TIME_LIMIT="${TIME_LIMIT:-120}"
NSEEDS="${NSEEDS:-30}"
WORKERS="${WORKERS:-${NSLOTS:-${SLURM_CPUS_PER_TASK:-$(nproc)}}}"
METHODS_FILE="${METHODS_FILE:-hpc/methods_phaseA.txt}"
INSTANCES="${INSTANCES:-P50}"
ORDER="${ORDER:-seed}"
case "$ORDER" in seed|instance) ;; *) echo "ERROR: ORDER must be seed or instance, got '$ORDER'"; exit 2 ;; esac
SHARD="${SHARD:-}"; SHARD_I=""; SHARD_N=""
if [ -n "$SHARD" ]; then
    SHARD_I="${SHARD%%/*}"; SHARD_N="${SHARD#*/}"
    case "$SHARD_I" in ''|*[!0-9]*) echo "ERROR: SHARD must look like i/N (e.g. 0/6), got '$SHARD'"; exit 2 ;; esac
    case "$SHARD_N" in ''|*[!0-9]*) echo "ERROR: SHARD must look like i/N (e.g. 0/6), got '$SHARD'"; exit 2 ;; esac
    { [ "$SHARD_N" -ge 1 ] && [ "$SHARD_I" -lt "$SHARD_N" ]; } || { echo "ERROR: SHARD=$SHARD needs 0 <= i < N"; exit 2; }
fi
expand_groups () {
    for tok in $(echo "$INSTANCES" | tr ',:;' '   '); do
        case "$tok" in
            P20|P50|P100|P200|B|T|T100|T150|T200|ALL) "$PYTHON" -c "from llrp_framework.params import GROUPS; print(' '.join(GROUPS['$tok']))" ;;
            *) echo "$tok" ;;
        esac
    done
}
INST_LIST="$(expand_groups | tr '\n' ' ')"
CHECKPOINTS="${CHECKPOINTS:-$(awk -v t="$TIME_LIMIT" 'BEGIN{printf "%g:%g:%g:%g", t/4, t/2, 3*t/4, t}')}"
OUT="${OUT:-$ROOT/analysis/phaseA_$(echo "$INSTANCES" | tr ',:; ' '____')_${TIME_LIMIT}s_${NSEEDS}seeds}"
SUPERSEDED="${OUT%/}.superseded"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "ERROR: Python >= 3.10 required, got $("$PYTHON" -V 2>&1) -- no conda environment with Python >= 3.10 was found (set CONDA_SH / CONDA_ENV)"; exit 2; }
[ -n "${INST_LIST// /}" ] || { echo "ERROR: no instances resolved from INSTANCES=$INSTANCES"; exit 2; }
mkdir -p "$OUT"

run_one () {
    inst="$1"; heur="$2"; ls="$3"; neigh="$4"; seed="$5"
    odir="$OUT/$inst/${heur}_${ls}_${neigh}/seed_${seed}"
    mkdir -p "$odir"
    args=(run_llrp.py --kit-root "$ROOT" --instances "$inst" --seeds "$seed" --heuristic "$heur"
          --local-search "$ls" --neighborhoods "$neigh" --budget-mode fixed_time
          --time-limit "$TIME_LIMIT" --checkpoints "$CHECKPOINTS")
    if [ -n "${EXTRA_ARGS:-}" ]; then read -r -a extra <<< "$EXTRA_ARGS"; args+=("${extra[@]}"); fi

    if [ -s "$odir/summary.csv" ] && [ -s "$odir/trajectory.csv" ] && \
       [ "$(cat "$odir/exit_code.txt" 2>/dev/null)" = "0" ]; then
        expected_fp="$("$PYTHON" "${args[@]}" --print-fingerprint 2>/dev/null)"
        stored_fp="$(sed -n 's/.*"fingerprint": "\([0-9a-f]*\)".*/\1/p' "$odir/config.json" 2>/dev/null | head -n 1)"
        if [ -n "$expected_fp" ] && [ "$stored_fp" = "$expected_fp" ]; then
            return 0
        fi
        dest="$SUPERSEDED/$inst/${heur}_${ls}_${neigh}/seed_${seed}.$(date +%Y%m%dT%H%M%S)"
        mkdir -p "$(dirname "$dest")" && rm -rf "$dest" && mv "$odir" "$dest" && mkdir -p "$odir"
        echo "STALE $inst $heur $ls $neigh seed $seed: stored fingerprint '${stored_fp:-none}' != current '${expected_fp:-?}'; moved to $dest" >> "$OUT/resume_mismatch.log"
    fi
    rm -f "$odir/summary.csv" "$odir/aggregate.csv" "$odir/trajectory.csv" "$odir/exit_code.txt"

    "$PYTHON" "${args[@]}" --out-dir "$odir" > "$odir/stdout.txt" 2> "$odir/stderr.txt"
    rc=$?
    if [ "$rc" -eq 0 ] && { [ ! -s "$odir/summary.csv" ] || [ ! -s "$odir/trajectory.csv" ]; }; then
        rc=98
        echo "Runner exited 0 but summary.csv or trajectory.csv is missing/empty" >> "$odir/stderr.txt"
    fi
    echo "$rc" > "$odir/exit_code.txt"
    return "$rc"
}
export -f run_one
export ROOT OUT SUPERSEDED PYTHON TIME_LIMIT CHECKPOINTS EXTRA_ARGS

# Job order: ORDER=seed (default) is seed-major, ORDER=instance is instance-major. Every run writes its own folder as soon as it
# finishes, so a stopped campaign keeps all finished runs; the order only decides which ones exist when it stops.
file_sha () { "$PYTHON" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
put_atomic () { mv -f "$1.tmp.$$" "$1"; }   # $1 = final path; the content was written to "$1.tmp.$$" (same directory => atomic rename)
JOBFILE="$OUT/jobs.txt"
BUILD="$JOBFILE"; [ -n "$SHARD" ] && BUILD="$OUT/.jobs.txt.build.$$"
: > "$BUILD"
ONLY_PAD=" $(echo "${ONLY:-}" | tr ',:;' '   ') "
emit_jobs () {   # $1 instance, $2 seed
    while read -r heur ls neigh; do
        case "$heur" in ''|'#'*) continue ;; esac
        if [ -n "${ONLY:-}" ] && [[ "$ONLY_PAD" != *" $heur "* ]]; then continue; fi
        echo "$1 $heur $ls $neigh $2" >> "$BUILD"
    done < "$METHODS_FILE"
}
if [ "$ORDER" = "instance" ]; then
    for inst in $INST_LIST; do for seed in $(seq 1 "$NSEEDS"); do emit_jobs "$inst" "$seed"; done; done
else
    for seed in $(seq 1 "$NSEEDS"); do for inst in $INST_LIST; do emit_jobs "$inst" "$seed"; done; done
fi
EXPECTED=$(wc -l < "$BUILD")
RUNLIST="$JOBFILE"; ARMJOBS="$EXPECTED"; JOBS_SHA=""
settings_body () {
    echo "instances=$INSTANCES"; echo "time_limit=$TIME_LIMIT"; echo "nseeds=$NSEEDS"; echo "checkpoints=$CHECKPOINTS"
    echo "only=${ONLY:-}"; echo "methods_file=$METHODS_FILE"; echo "order=$ORDER"; echo "extra_args=${EXTRA_ARGS:-}"
    echo "code_version=$(cat "$ROOT/VERSION" 2>/dev/null)"
    echo "python=$("$PYTHON" -c 'import sys; print(sys.version.split()[0])')"
    echo "expected_runs=$EXPECTED"
}
if [ -z "$SHARD" ]; then
    { echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; settings_body; } > "$OUT/run_settings.txt"
    cp -f "$METHODS_FILE" "$OUT/methods_used.txt"
else
    # Sharded: every arm builds the full list (deterministic) and keeps its own share. The share is cut from the arm's OWN build,
    # whose hash goes into the arm marker; hpc/finalize.sh refuses a stage whose arms disagree on the manifest.
    mkdir -p "$OUT/shards"
    RUNLIST="$OUT/shards/jobs_arm_${SHARD_I}of${SHARD_N}.txt"
    awk -v n="$SHARD_N" -v i="$SHARD_I" '{ k=$1" "$2" "$3" "$4; if (!(k in pos)) pos[k]=np++; if ((pos[k]+$5) % n == i) print }' "$BUILD" > "$RUNLIST"
    ARMJOBS=$(wc -l < "$RUNLIST")
    JOBS_SHA="$(file_sha "$BUILD")"
    mv -f "$BUILD" "$OUT/jobs.txt.tmp.$$" && put_atomic "$OUT/jobs.txt"
    settings_body > "$OUT/run_settings.txt.tmp.$$" && { echo "shards=$SHARD_N"; echo "jobs_sha256=$JOBS_SHA"; } >> "$OUT/run_settings.txt.tmp.$$" && put_atomic "$OUT/run_settings.txt"
    cp -f "$METHODS_FILE" "$OUT/methods_used.txt.tmp.$$" && put_atomic "$OUT/methods_used.txt"
    ARMFILE="$OUT/shards/arm_${SHARD_I}of${SHARD_N}.txt"
    START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    arm_marker () {   # $1 state, $2 failed, $3 missing, $4 xargs rc
        {
            echo "state=$1"; echo "arm=$SHARD_I"; echo "arms=$SHARD_N"
            echo "jobs_total=$EXPECTED"; echo "jobs_arm=$ARMJOBS"; echo "jobs_sha256=$JOBS_SHA"
            echo "failed=${2:-}"; echo "missing=${3:-}"; echo "xargs_rc=${4:-}"
            echo "host=$(hostname)"; echo "cpu=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | sed 's/^ //')"
            echo "workers=$WORKERS"; echo "job_id=${JOB_ID:-none}"; echo "task_id=${SGE_TASK_ID:-none}"
            echo "started_utc=$START_UTC"; echo "updated_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        } > "$ARMFILE.tmp.$$" && mv -f "$ARMFILE.tmp.$$" "$ARMFILE"
    }
    arm_marker running
fi

echo "LLRP launcher | instances=$INSTANCES time_limit=$TIME_LIMIT nseeds=$NSEEDS checkpoints=$CHECKPOINTS workers=$WORKERS order=$ORDER${SHARD:+ shard=$SHARD}"
if [ -n "$SHARD" ]; then
    echo "Stage runs: $EXPECTED   this arm ($SHARD): $ARMJOBS   Output: $OUT"
else
    echo "Expected runs: $EXPECTED   Output: $OUT"
fi
echo "Python: $("$PYTHON" -c 'import sys; print(sys.version.split()[0], sys.executable)')"
xargs -n 5 -P "$WORKERS" bash -c 'run_one "$@"' _ < "$RUNLIST"
xrc=$?

if [ -n "$SHARD" ]; then
    # Count only this arm's own runs: the other arms may still be running.
    failed=0; missing=0
    while read -r inst heur ls neigh seed; do
        d="$OUT/$inst/${heur}_${ls}_${neigh}/seed_${seed}"
        ec="$(cat "$d/exit_code.txt" 2>/dev/null)"
        if [ -z "$ec" ] || [ ! -s "$d/summary.csv" ] || [ ! -s "$d/trajectory.csv" ]; then missing=$((missing+1))
        elif [ "$ec" != "0" ]; then failed=$((failed+1)); fi
    done < "$RUNLIST"
    state=done; { [ "$failed" -eq 0 ] && [ "$missing" -eq 0 ] && [ "$xrc" -eq 0 ]; } || state=failed
    arm_marker "$state" "$failed" "$missing" "$xrc"
    echo "======================================"
    echo "ARM $SHARD $state | arm runs: $ARMJOBS | failed: $failed | missing: $missing | xargs rc: $xrc"
    echo "Output: $OUT   (collect + verify once all arms are done: OUT=$OUT ARMS=$SHARD_N bash hpc/finalize.sh)"
    echo "======================================"
    [ "$state" = "done" ]
    exit $?
fi

summaries=$(find "$OUT" -name summary.csv | wc -l)
trajectories=$(find "$OUT" -name trajectory.csv | wc -l)
completed=$(find "$OUT" -name exit_code.txt | wc -l)
failed=$(find "$OUT" -name exit_code.txt -exec sh -c 'test "$(cat "$1")" != 0' _ {} \; -print | wc -l)
nonempty_stderr=$(find "$OUT" -name stderr.txt -size +0c | wc -l)

echo "======================================"
echo "FINISHED"
echo "Expected:          $EXPECTED"
echo "Summaries:         $summaries"
echo "Trajectories:      $trajectories"
echo "Completed markers: $completed"
echo "Failed:            $failed"
echo "Nonempty stderr:   $nonempty_stderr"
echo "xargs rc:          $xrc"
echo "Output:            $OUT"
echo "======================================"

"$PYTHON" collect.py "$OUT" > "$OUT/collect.log" 2>&1 && tail -n 6 "$OUT/collect.log"
"$PYTHON" verify_run.py "$OUT" > "$OUT/verify.log" 2>&1; vrc=$?
tail -n 3 "$OUT/verify.log"
[ "$failed" -eq 0 ] && [ "$summaries" -eq "$EXPECTED" ] && [ "$vrc" -eq 0 ]
