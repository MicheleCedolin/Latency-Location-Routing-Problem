#!/bin/bash
# Runs ONE configuration on ONE INSTANCE FAMILY (Barreto / Tuzun / Prins): a SEPARATE process per seed, each pinned to its own core (optional).
# No Python needed: summary and merge are done with bin/llrp_tools.
#
#   FAMILY=barreto ./run_config.sh full1     # FULL pool, stage 1: 13 operators (without ds), classic (improving moves only)
#   FAMILY=barreto ./run_config.sh full2     # stage 2: the same 13 operators + SO (strategic oscillation)
#   FAMILY=barreto ./run_config.sh full3     # stage 3: + depot swap (ds) -> 14 operators, SO
#   FAMILY=tuzun   ./run_config.sh full3     # same configuration, Tuzun-Burke family (separate result directory)
#   FAMILY=prins   ./run_config.sh full3     # Prins family
#   FAMILY=train   ./run_config.sh full3     # irace training instances (selection/train.txt)   |  FAMILY=test : the remaining instances
#   FAMILY=all     ./run_config.sh full3     # the three families ONE AFTER ANOTHER (each in its own directory); to use three nodes run them separately
#   FAMILY=custom ./run_config.sh full3 Ch50-5 P113212-10     # only the given instances (names are looked up in manifest.tsv)
#   FLAGS_FILE=irace/best.flags FAMILY=all ./run_config.sh tuned     # parameters found by irace (output of llrp_tools irace-flags)
#   OPS=relocate,2opt,swapstar SO=1 FAMILY=barreto ./run_config.sh my_experiment            # free-form operator pool
#
# Results:  $OUT/<family>/<NAME>/{run,routes,iter,ops,trace}.csv , summary.txt , env.txt , runs/ (per-run files; an interrupted job resumes where it stopped)
#
# Environment variables (all optional):
#   FAMILY   barreto|tuzun|prins|train|test|all|custom   (REQUIRED; family names come from manifest.tsv)
#   OPS      operator pool: zou | legacy5 | full | comma-separated list (operators: ./bin/llrp_fast --list-ops)
#   SO=0|1   strategic oscillation        DS=0|1  add the ds operator to the pool     ILS=K  double-bridge ILS (K consecutive failed perturbations; 0 = off)
#   SELECT=best|first   ORDER=random|fixed        (default: best, random = RVND)
#   MAXITER  upper limit of GRASP iterations (default 1000)   STALL  stop after K consecutive non-improving iterations (default 300; 0 = off)
#   TLIMIT   CPU-second limit per run (0 = off).  Whichever limit is reached first ends the run; run.csv "Stop Reason" = max_iter | stall | time
#   EXTRA    additional flags for llrp_fast, for example EXTRA="--it-div 6 --so-f1 1.3"
#   FLAGS_FILE  all flags are read from this file (presets are ignored); budget flags (MAXITER/STALL/TLIMIT) are still appended
#   NPROC=30 (number of processes = number of seeds)   SEED0=0 (seeds SEED0..SEED0+NPROC-1)   RCL=5
#   CPUS="0-29"  PIN=0   INSTROOT   MANIFEST   BIN   TOOLS   OUT=results   TAG (output sub-directory; default NAME)
#   ALGO  algorithm name in run.csv / Excel (default: TAG or the configuration name)
#   SUMMARY=0 (do not write the summary table at the end)     XLSX=1 (also write an Excel file at the end; can be large with OUTLEVEL=2)
#   OUTLEVEL=0|1|2   0: run summary + operator statistics; 1: + routes + anytime trace; 2: + GRASP iteration log (default 2)
HERE=$(cd "$(dirname "$0")" && pwd)
NAME=${1:?usage: FAMILY=barreto|tuzun|prins|train|test|all ./run_config.sh NAME [INSTANCE ...]}; shift
BIN=${BIN:-$HERE/bin/llrp_fast}; TOOLS=${TOOLS:-$HERE/bin/llrp_tools}
INSTROOT=${INSTROOT:-$HERE/inst}; MANIFEST=${MANIFEST:-$HERE/manifest.tsv}
NPROC=${NPROC:-30}; SEED0=${SEED0:-0}; RCL=${RCL:-5}; PIN=${PIN:-1}; OUT=${OUT:-$HERE/results}
[ -x "$BIN" ] && [ -x "$TOOLS" ] || { echo "binaries missing (bin/llrp_fast, bin/llrp_tools): run ./build.sh first"; exit 1; }
[ -s "$MANIFEST" ] || { echo "manifest missing: $MANIFEST   (to create it: $TOOLS manifest $INSTROOT --out $MANIFEST)"; exit 1; }
[ -x "$HERE/check_inst_data.sh" ] && { INSTROOT="$INSTROOT" "$HERE/check_inst_data.sh" || exit 1; }   # are the Tuzun coordinates truncated? (skip with SKIP_DATA_CHECK=1)
FAMILY=${FAMILY:-}
[ -n "$FAMILY" ] || { echo "FAMILY is required: barreto | tuzun | prins | train | test | all | custom   (example: FAMILY=barreto ./run_config.sh $NAME)"; exit 1; }

# ---- FAMILY=all : run the families one after another in separate directories
if [ "$FAMILY" = all ]; then
  rc=0
  for f in $(awk -F'\t' 'NR>1 && !s[$1]++{print $1}' "$MANIFEST"); do
    echo "################ family: $f"; FAMILY=$f "$0" "$NAME" "$@" || rc=1
  done
  exit $rc
fi

FULL13=relocate,oropt2,oropt3,swap11,swap21,swap22,swap31,swap32,2opt,2opt*,swapstar,dexch,rdepot     # the 'full' pool without ds
if [ -z "${FLAGS_FILE:-}" ]; then
  case $NAME in
    full1)        : "${OPS:=$FULL13}"; : "${SO:=0}"; : "${DS:=0}";;
    full2)        : "${OPS:=$FULL13}"; : "${SO:=1}"; : "${DS:=0}";;
    full3)        : "${OPS:=$FULL13}"; : "${SO:=1}"; : "${DS:=1}";;          # --ds adds the ds operator to the 13 -> 14
    stage1)       : "${OPS:=zou}";    : "${SO:=0}"; : "${DS:=0}";;           # the 8-operator Zou pool
    stage2)       : "${OPS:=zou}";    : "${SO:=1}"; : "${DS:=0}";;
    stage3)       : "${OPS:=zou}";    : "${SO:=1}"; : "${DS:=1}";;
    full)         : "${OPS:=full}";   : "${SO:=1}"; : "${DS:=0}";;
    full_classic) : "${OPS:=full}";   : "${SO:=0}"; : "${DS:=0}";;
    full_ils)     : "${OPS:=full}";   : "${SO:=1}"; : "${DS:=0}"; : "${ILS:=20}";;
    legacy5)      : "${OPS:=legacy5}"; : "${SO:=0}"; : "${DS:=0}";;
    legacy5_so)   : "${OPS:=legacy5}"; : "${SO:=1}"; : "${DS:=0}";;
    *)            : "${OPS:?for this name give OPS=... (or FLAGS_FILE=...); preset names: full1 full2 full3 stage1 stage2 stage3 full full_classic full_ils legacy5 legacy5_so}"; : "${SO:=1}"; : "${DS:=0}";;
  esac
fi
: "${ILS:=0}"; : "${SELECT:=best}"; : "${ORDER:=random}"; : "${MAXITER:=1000}"; : "${STALL:=300}"; : "${TLIMIT:=0}"; : "${OUTLEVEL:=2}"; : "${EXTRA:=}"
set -f                                              # names such as '2opt*' must not be expanded by the shell
FA=()
if [ -n "${FLAGS_FILE:-}" ]; then
  [ -s "$FLAGS_FILE" ] || { echo "FLAGS_FILE empty/missing: $FLAGS_FILE"; exit 1; }
  FA=($(cat "$FLAGS_FILE"))
else
  FA=(--ops "$OPS" --select "$SELECT" --order "$ORDER" --rcl "$RCL")
  [ "$SO" = 1 ] && FA+=(--so); [ "$DS" = 1 ] && FA+=(--ds); [ "$ILS" != 0 ] && FA+=(--ils "$ILS")
fi
FA+=(--max-iter "$MAXITER" --out-level "$OUTLEVEL" --algo "${ALGO:-${TAG:-$NAME}}")
[ "$STALL" != 0 ] && FA+=(--stall "$STALL"); [ "$TLIMIT" != 0 ] && FA+=(--time "$TLIMIT")
[ -n "$EXTRA" ] && FA+=($EXTRA)
F="${FA[*]}"

# ---- instance list:  "family/name n"  (large instances first)
list_family() { awk -F'\t' -v f="$1" 'NR>1 && $1==f{print $1"/"$2, $3}' "$MANIFEST"; }
lookup() { awk -F'\t' -v nm="$1" 'NR>1 && $2==nm{print $1"/"$2, $3; f=1} END{exit f?0:1}' "$MANIFEST"; }
LIST=""
case $FAMILY in
  train|test) [ -s "$HERE/selection/$FAMILY.txt" ] || { echo "missing: $HERE/selection/$FAMILY.txt  (create it with: bin/llrp_tools select manifest.tsv)"; exit 1; }
              for l in $(grep -v '^#' "$HERE/selection/$FAMILY.txt"); do LIST+="$(lookup "${l#*/}")"$'\n'; done; LABEL=$FAMILY;;
  custom)     [ $# -gt 0 ] || { echo "FAMILY=custom needs instance names"; exit 1; }
              for i in "$@"; do r=$(lookup "$i") || { echo "not in manifest: $i"; exit 1; }; LIST+="$r"$'\n'; done; LABEL=custom;;
  *)          LIST=$(list_family "$FAMILY"); LABEL=$FAMILY
              [ -n "$LIST" ] || { echo "no such family in the manifest: $FAMILY  (available: $(awk -F'\t' 'NR>1 && !s[$1]++{printf "%s ",$1}' "$MANIFEST"))"; exit 1; }
              if [ $# -gt 0 ]; then SEL=" $* "; LIST=$(echo "$LIST" | awk -v s="$SEL" '{n=$1; sub(/^.*\//,"",n); if (index(s," "n" ")) print}'); LABEL=$FAMILY; fi;;
esac
INST=($(echo "$LIST" | grep -v '^$' | sort -k2,2nr -s | awk '{print $1}'))
[ "${#INST[@]}" -gt 0 ] || { echo "instance list is empty"; exit 1; }
if [ "${LIST_ONLY:-0}" = 1 ]; then printf '%s\n' "${INST[@]}"; exit 0; fi          # only print the instance list (used by run_ablation.sh for the time estimate)
DIR=$OUT/$LABEL/${TAG:-$NAME}; RUNS=$DIR/runs; mkdir -p "$RUNS/log"

cpus=(); l=${CPUS:-$(awk '/Cpus_allowed_list/{print $2}' /proc/self/status 2>/dev/null)}
IFS=',' read -ra parts <<< "$l"
for p in "${parts[@]}"; do if [[ $p == *-* ]]; then cpus+=($(seq "${p%-*}" "${p#*-}")); elif [ -n "$p" ]; then cpus+=("$p"); fi; done
PINCMD=""
if [ "$PIN" = 1 ] && command -v taskset >/dev/null 2>&1 && [ "${#cpus[@]}" -ge "$NPROC" ]; then PINCMD=taskset
else
  if [ "$PIN" != 1 ]; then why="PIN=$PIN"; elif ! command -v taskset >/dev/null 2>&1; then why="taskset not found"; else why="allowed cores ${#cpus[@]} < NPROC=$NPROC"; fi
  echo "WARNING: core pinning is off ($why)"
fi

ENVF=$DIR/env.txt; [ -e "$ENVF" ] && ENVF=$DIR/env_resume_$(date +%H%M%S).txt
{ echo "config=$NAME family=$LABEL flags=$F nproc=$NPROC seed0=$SEED0 pin=${PINCMD:-no}"
  echo "host=$(hostname) date=$(date -Iseconds) user=$(whoami)"
  echo "cpu=$(awk -F: '/model name/{print $2; exit}' /proc/cpuinfo)"
  echo "logical_cpus=$(nproc) allowed_cpus=${cpus[*]:0:$NPROC}"
  echo "load_before=$(cut -d' ' -f1-3 /proc/loadavg)"
  echo "compiler=$(g++ --version 2>/dev/null | head -1)"
  echo "binary_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
  echo "manifest_sha256=$(sha256sum "$MANIFEST" | cut -d' ' -f1)"
  echo "instances(${#INST[@]})=${INST[*]}"; } > "$ENVF"

worker() {                                         # one seed, all instances, one core
  local seed=$1 cpu=$2 fi inst fam t0
  for fi in "${INST[@]}"; do
    fam=${fi%/*}; inst=${fi#*/}
    [ -s "$RUNS/${inst}_s${seed}.run.csv" ] && continue         # run.csv is written LAST: if it exists the run is complete
    t0=$(date +%s)
    ${PINCMD:+taskset -c $cpu} "$BIN" --instance "$INSTROOT/$fam/$inst.inst" --seed "$seed" "${FA[@]}" --quiet --out "$RUNS/${inst}_s${seed}" \
        > "$RUNS/log/${inst}_s${seed}.log" 2>&1 || echo "ERROR: $inst seed $seed (see $RUNS/log/${inst}_s${seed}.log)"
    echo "[$(date +%H:%M:%S)] seed $seed  $inst  $(( $(date +%s) - t0 )) s"
  done
}
echo "== $NAME [$LABEL]: ${#INST[@]} instances x $NPROC processes (seed $SEED0..$((SEED0+NPROC-1))), flags: $F"
for ((k = 0; k < NPROC; k++)); do worker $((SEED0 + k)) "${cpus[$k]:-}" & done
wait
echo "load_after=$(cut -d' ' -f1-3 /proc/loadavg)" >> "$ENVF"
set +f

"$TOOLS" merge "$DIR" > /dev/null || exit 1
echo "== done: $DIR/run.csv  ($(($(wc -l < "$DIR/run.csv") - 1)) runs)"
if [ "${SUMMARY:-1}" = 1 ]; then
  TRAINF=${TRAIN_LIST:-$HERE/selection/train.txt}; SA=(--manifest "$MANIFEST"); [ -s "$TRAINF" ] && SA+=(--train "$TRAINF")
  "$TOOLS" summarize "$DIR/run.csv" --csv "$DIR/summary.csv" "${SA[@]}" | tee "$DIR/summary.txt" || true
fi
if [ "${XLSX:-0}" = 1 ]; then "$TOOLS" workbook "$DIR" --manifest "$MANIFEST" || true
elif [ "${SUMMARY:-1}" = 1 ]; then echo "excel:  $TOOLS workbook $DIR --manifest $MANIFEST     (use --no-iter to skip the large iteration log)"; fi
