#!/bin/bash
# Staged LLRP campaign on an SGE cluster: P20 -> P50 -> P100 -> P200, each stage split over ARMS concurrent 15-core array tasks.
#
#   bash hpc/submit_llrp_campaign.sh                  # DRY RUN: prints the plan, the cost estimate and the qsub commands; submits nothing
#   SUBMIT=1 bash hpc/submit_llrp_campaign.sh         # submits (works from any shell: the jobs find Python themselves, see below)
#
# Chain (all through -hold_jid):  arms(P20) -> finalize(P20) -> arms(P50) -> finalize(P50) -> ...
# A stage is finalized only if every arm finished on the same manifest, all runs exist and verify_run.py passes (hpc/finalize.sh).
# A failed finalize ends with exit code 100 (job error state) and the next stage's arms additionally refuse to start without
# <previous stage>/FINALIZE_OK, so a broken stage never feeds the next one.
#
# Python: hpc/pyenv.sh finds conda and a Python >= 3.10 by itself (override with CONDA_SH=<conda.sh> CONDA_ENV=<name>).
#
# Settings (environment variables):
#   STAGES         stages in order                                   (default: "P20 P50 P100 P200"; one stage, e.g. STAGES=P20, is allowed)
#   ARMS           concurrent array tasks per stage                  (default: 6)
#   SLOTS          PE slots = worker processes per arm               (default: 15); ARMS x SLOTS must not exceed CORES
#   CORES          cluster capacity you may use                      (default: 96)
#   NSEEDS         seeds 1..NSEEDS per (instance, method)            (default: 30)
#   TL_P20 TL_P50 TL_P100 TL_P200   wall-clock seconds per run       (defaults 60 180 300 900 -- provisional, see the cost table)
#   METHODS_FILE   method table for all stages                       (default: hpc/methods_phaseB_loffler9.txt); METHODS_FILE_<stage> overrides one stage
#                  (read when the stage starts: curate the table between stages if you want to, methods_used.txt in each stage records what ran)
#   CAMPAIGN_DIR   output root                                       (default: analysis/llrp_campaign); a stage goes to <CAMPAIGN_DIR>/<stage>_<TL>s_<NSEEDS>seeds
#   ORDER, ONLY, EXTRA_ARGS   passed through to hpc/run.sh
#   QSUB_OPTS      extra qsub options for every job, e.g. "-q long.q -l h_rt=48:00:00"
#   AFTER_JOB      job id the first stage should wait for           (optional)
#   OVERHEAD_S     assumed start-up cost per run in the estimate    (default: 2)
#   CKPT_STEPS     number of equally spaced anytime checkpoints per run (default: 10)
set -u
ROOT="${KIT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT" || exit 2
[ -f "$ROOT/hpc/pyenv.sh" ] && { . "$ROOT/hpc/pyenv.sh" || exit 2; }   # python3 >= 3.10 (conda is found automatically)
PYTHON="${PYTHON:-python3}"
STAGES="${STAGES:-P20 P50 P100 P200}"
ARMS="${ARMS:-6}"; SLOTS="${SLOTS:-15}"; CORES="${CORES:-96}"
NSEEDS="${NSEEDS:-30}"
TL_P20="${TL_P20:-60}"; TL_P50="${TL_P50:-180}"; TL_P100="${TL_P100:-300}"; TL_P200="${TL_P200:-900}"
METHODS_FILE="${METHODS_FILE:-hpc/methods_phaseB_loffler9.txt}"
CAMPAIGN_DIR="${CAMPAIGN_DIR:-analysis/llrp_campaign}"
SUBMIT="${SUBMIT:-0}"; QSUB="${QSUB:-qsub}"; QSUB_OPTS="${QSUB_OPTS:-}"; AFTER_JOB="${AFTER_JOB:-}"
OVERHEAD_S="${OVERHEAD_S:-2}"; CKPT_STEPS="${CKPT_STEPS:-10}"
ORDER="${ORDER:-seed}"; ONLY="${ONLY:-}"; EXTRA_ARGS="${EXTRA_ARGS:-}"
case "$CAMPAIGN_DIR" in /*) ;; *) CAMPAIGN_DIR="$ROOT/$CAMPAIGN_DIR" ;; esac

[ $((ARMS * SLOTS)) -le "$CORES" ] || { echo "ERROR: ARMS x SLOTS = $((ARMS * SLOTS)) exceeds CORES=$CORES"; exit 2; }
[ -d hpc ] && [ -f hpc/run.sh ] || { echo "ERROR: run from the kit folder"; exit 2; }

group_size () { "$PYTHON" -c "from llrp_framework.params import GROUPS; print(len(GROUPS['$1']))" 2>/dev/null; }
methods_count () {   # $1 methods file
    local n=0 heur ls neigh only_pad=" $(echo "$ONLY" | tr ',:;' '   ') "
    while read -r heur ls neigh; do
        case "$heur" in ''|'#'*) continue ;; esac
        if [ -n "$ONLY" ] && [[ "$only_pad" != *" $heur "* ]]; then continue; fi
        n=$((n + 1))
    done < "$1"
    echo "$n"
}

declare -A S_TL S_OUT S_MF S_RUNS S_CK
total_core_s=0; total_wall_s=0
echo "LLRP campaign plan | kit $(cat VERSION 2>/dev/null) | ${ARMS} arms x ${SLOTS} cores = $((ARMS * SLOTS)) of ${CORES} cores | ${NSEEDS} seeds | order ${ORDER}"
printf '%-6s %5s %7s %6s %8s %6s %9s %9s  %s\n' stage inst methods seeds runs "TL(s)" core-h wall-h "output"
for st in $STAGES; do
    tl_var="TL_$st"; tl="${!tl_var:-}"
    [ -n "$tl" ] || { echo "ERROR: no time limit for stage $st (set TL_$st)"; exit 2; }
    mf_var="METHODS_FILE_$st"; mf="${!mf_var:-$METHODS_FILE}"
    [ -f "$mf" ] || { echo "ERROR: methods file for $st not found: $mf"; exit 2; }
    ni="$(group_size "$st")"; [ -n "$ni" ] || { echo "ERROR: unknown group $st"; exit 2; }
    nm="$(methods_count "$mf")"; [ "$nm" -gt 0 ] || { echo "ERROR: no methods selected for $st"; exit 2; }
    runs=$((ni * nm * NSEEDS))
    core_s=$("$PYTHON" -c "print($runs * ($tl + $OVERHEAD_S))")
    wall_s=$("$PYTHON" -c "import math; print(math.ceil($runs / ($ARMS * $SLOTS)) * ($tl + $OVERHEAD_S))")
    total_core_s=$("$PYTHON" -c "print($total_core_s + $core_s)"); total_wall_s=$("$PYTHON" -c "print($total_wall_s + $wall_s)")
    S_TL[$st]="$tl"; S_MF[$st]="$mf"; S_RUNS[$st]="$runs"
    S_OUT[$st]="$CAMPAIGN_DIR/${st}_${tl}s_${NSEEDS}seeds"
    S_CK[$st]="$(awk -v t="$tl" -v k="$CKPT_STEPS" 'BEGIN{for(i=1;i<=k;i++) printf "%s%g", (i>1?":":""), t*i/k}')"
    printf '%-6s %5s %7s %6s %8s %6s %9.1f %9.2f  %s\n' "$st" "$ni" "$nm" "$NSEEDS" "$runs" "$tl" \
        "$("$PYTHON" -c "print($core_s/3600)")" "$("$PYTHON" -c "print($wall_s/3600)")" "${S_OUT[$st]}"
done
printf '%-6s %5s %7s %6s %8s %6s %9.1f %9.2f\n' total "" "" "" "" "" "$("$PYTHON" -c "print($total_core_s/3600)")" "$("$PYTHON" -c "print($total_wall_s/3600)")"
echo "Estimate = runs x (TL + ${OVERHEAD_S}s start-up) on ${ARMS}x${SLOTS} cores, all arms starting together, no queue time. Older nodes do not change the wall-clock"
echo "of a run (the budget is time), only the search effort it buys; a delayed arm only delays its own stage."

[ "$SUBMIT" = "1" ] && mkdir -p logs "$CAMPAIGN_DIR"
# The stage settings are written to <stage folder>/stage.env, which the job scripts source (qsub -v STAGE_ENV=<file>); nothing depends on the
# environment of the shell that submits (no qsub -V). The file also documents exactly how the stage was configured.
# submit LABEL qsub-args... : prints the job id (dry run: the command goes to the terminal and a placeholder id JOBID_<label> is returned).
submit () {
    local label="$1"; shift
    if [ "$SUBMIT" = "1" ]; then
        "$QSUB" -terse -v "STAGE_ENV=$stage_file" "$@"
    else
        printf '   %s -terse -v STAGE_ENV=%s' "$QSUB" "$stage_file" >&2; printf ' %q' "$@" >&2; echo >&2
        echo "JOBID_${label// /_}"
    fi
}
prev_hold="$AFTER_JOB"; prev_ok=""
for st in $STAGES; do
    echo
    echo "== stage $st -> ${S_OUT[$st]}"
    stage_env=(INSTANCES="$st" TIME_LIMIT="${S_TL[$st]}" NSEEDS="$NSEEDS" METHODS_FILE="${S_MF[$st]}" CHECKPOINTS="${S_CK[$st]}"
               OUT="${S_OUT[$st]}" ARMS="$ARMS" ORDER="$ORDER" ONLY="$ONLY" EXTRA_ARGS="$EXTRA_ARGS" REQUIRE_OK="$prev_ok")
    stage_file="${S_OUT[$st]}/stage.env"
    echo "   settings (${stage_file}): ${stage_env[*]}"
    if [ "$SUBMIT" = "1" ]; then
        mkdir -p "${S_OUT[$st]}"
        { echo "# stage settings written by hpc/submit_llrp_campaign.sh"; for kv in "${stage_env[@]}"; do printf 'export %s=%q\n' "${kv%%=*}" "${kv#*=}"; done; } > "$stage_file"
    fi
    hold=(); [ -n "$prev_hold" ] && hold=(-hold_jid "$prev_hold")
    raw_arms="$(submit "arms $st" -t "1-$ARMS" -N "LLRP_${st}" -pe smp "$SLOTS" ${hold[@]+"${hold[@]}"} $QSUB_OPTS hpc/campaign_arm.sge)" || { echo "ERROR: qsub failed for the arms of $st"; exit 3; }
    arm_job="${raw_arms%%.*}"
    [ -n "$arm_job" ] || { echo "ERROR: no job id from qsub for the arms of $st"; exit 3; }
    raw_fin="$(submit "finalize $st" -N "LLRP_${st}_fin" -hold_jid "$arm_job" $QSUB_OPTS hpc/campaign_finalize.sge)" || { echo "ERROR: qsub failed for the finalize of $st"; exit 3; }
    fin_job="${raw_fin%%.*}"
    [ -n "$fin_job" ] || { echo "ERROR: no job id from qsub for the finalize of $st"; exit 3; }
    echo "   arms job $arm_job | finalize job $fin_job"
    [ "$SUBMIT" = "1" ] && echo "$st arms=$arm_job finalize=$fin_job out=${S_OUT[$st]}" >> "$CAMPAIGN_DIR/submitted_jobs.txt"
    prev_hold="$fin_job"; prev_ok="${S_OUT[$st]}/FINALIZE_OK"
done
echo
if [ "$SUBMIT" = "1" ]; then
    { echo "submitted_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "kit=$(cat VERSION 2>/dev/null)"; echo "stages=$STAGES"; echo "arms=$ARMS slots=$SLOTS nseeds=$NSEEDS order=$ORDER"
      echo "methods_file=$METHODS_FILE"; echo "extra_args=$EXTRA_ARGS"; echo "only=$ONLY"; } >> "$CAMPAIGN_DIR/campaign_plan.txt"
    echo "Submitted. Progress: ls ${CAMPAIGN_DIR}/<stage>/shards/ (arm markers), qstat. Job ids: ${CAMPAIGN_DIR}/submitted_jobs.txt"
else
    echo "Dry run: nothing was submitted. Repeat with SUBMIT=1 after you have agreed on the time limits and the method table."
fi
