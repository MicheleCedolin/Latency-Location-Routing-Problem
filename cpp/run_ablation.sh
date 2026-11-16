#!/bin/bash
# Operator-contribution ablation: FULL, LEAVE-ONE-OUT (remove each operator), ADD-ONE-IN (add a single operator to the base pool).
# Every FAMILY is run separately and written to its own directory:  results/ablation/<family>/<TAG>/...   (plan.tsv is in the family directory too)
#
#   FAMILY=barreto ./run_ablation.sh          # asks for confirmation, then runs all configurations one after another (each on 30 cores)
#   FAMILY=train   ./run_ablation.sh          # on the irace training instances (for the train/test split: run FAMILY=test afterwards)
#   FAMILY=all     ./run_ablation.sh          # the families one after another (each in its own directory)
#   MODE=loo FAMILY=prins ./run_ablation.sh   # only FULL + leave-one-out        (MODE=add: only BASE + add-one-in)
#   YES=1 ...                                 # do not ask for confirmation
#   PLAN_ONLY=1 FAMILY=tuzun ./run_ablation.sh   # only print the plan and the time estimate
#   FAMILY=custom ./run_ablation.sh Mi134-8 Or117-14   # only the selected instances (names are looked up in manifest.tsv)
#
# Analysis (C++):  bin/llrp_tools ablation results/ablation/<family> [--train selection/train.txt]
#                  to merge several families:  bin/llrp_tools ablation results/ablation/barreto results/ablation/prins results/ablation/tuzun --out results/ablation/all
#
# Defaults: MAXITER=300 fixed, STALL=0 (all configurations run the SAME iteration horizon, so 'equal iterations' and
# 'equal CPU' comparisons can be made from the anytime trace). OUTLEVEL=1 (routes + trace; no GRASP iteration log -> small files).
# Environment: BASE (base pool), FULL_OPS, SO=1, NPROC=30, SEED0=0, MAXITER, STALL, ABL (ablation root directory); the rest as in run_config.sh.
HERE=$(cd "$(dirname "$0")" && pwd)
FAMILY=${FAMILY:-}
[ -n "$FAMILY" ] || { echo "FAMILY is required: barreto | tuzun | prins | train | test | all | custom"; exit 1; }
MANIFEST=${MANIFEST:-$HERE/manifest.tsv}
if [ "$FAMILY" = all ]; then
  rc=0
  for f in $(awk -F'\t' 'NR>1 && !s[$1]++{print $1}' "$MANIFEST"); do echo "################ family: $f"; FAMILY=$f "$0" "$@" || rc=1; done
  exit $rc
fi
MODE=${MODE:-all}; BASE=${BASE:-relocate,swap11,2opt}
FULL_OPS=${FULL_OPS:-relocate,oropt2,oropt3,swap11,swap21,swap22,swap31,swap32,2opt,2opt*,swapstar,dexch,rdepot,ds}
export MAXITER=${MAXITER:-300} STALL=${STALL:-0} OUTLEVEL=${OUTLEVEL:-1} SO=${SO:-1} DS=0 SUMMARY=0
ABL=${ABL:-$HERE/results/ablation}; LABEL=$FAMILY; mkdir -p "$ABL/$LABEL"
safe() { echo "$1" | sed 's/\*/star/g'; }
set -f
IFS=',' read -ra ALL <<< "$FULL_OPS"; IFS=',' read -ra BAS <<< "$BASE"
inbase() { local x; for x in "${BAS[@]}"; do [ "$x" = "$1" ] && return 0; done; return 1; }
minus() { local o out=(); for o in "${ALL[@]}"; do [ "$o" != "$1" ] && out+=("$o"); done; (IFS=,; echo "${out[*]}"); }

TAGS=(); KIND=(); OPN=(); OPL=()
add() { TAGS+=("$1"); KIND+=("$2"); OPN+=("$3"); OPL+=("$4"); }
if [ "$MODE" = all ] || [ "$MODE" = loo ]; then
  add FULL full - "$FULL_OPS"
  for o in "${ALL[@]}"; do add "LOO_$(safe "$o")" loo "$o" "$(minus "$o")"; done
fi
if [ "$MODE" = all ] || [ "$MODE" = add ]; then
  add BASE base - "$BASE"
  for o in "${ALL[@]}"; do inbase "$o" || add "ADD_$(safe "$o")" add "$o" "$BASE,$o"; done
fi
PLAN=$ABL/$LABEL/plan.tsv
{ printf "tag\tkind\top\tops\n"; for i in "${!TAGS[@]}"; do printf "%s\t%s\t%s\t%s\n" "${TAGS[$i]}" "${KIND[$i]}" "${OPN[$i]}" "${OPL[$i]}"; done; } > "$PLAN"

NPROC=${NPROC:-30}
echo "== ABLATION PLAN [$LABEL]: ${#TAGS[@]} configurations x $NPROC seeds | MAXITER=$MAXITER STALL=$STALL SO=$SO"
column -t -s$'\t' "$PLAN" 2>/dev/null || cat "$PLAN"
echo
# time estimate: data/timing_probe_20it.tsv = CPU time of 20 iterations for every instance (full pool + SO, 2.1 GHz Xeon, single process, seed 0)
LISTING=$(LIST_ONLY=1 OPS=x FAMILY=$FAMILY "$HERE/run_config.sh" abl "$@") || { echo "$LISTING"; exit 1; }
SWEEP=$(echo "$LISTING" | awk -v tf="$HERE/data/timing_probe_20it.tsv" 'BEGIN{while ((getline l < tf) > 0) {split(l, a, "\t"); t[a[2]] = a[3]}} {n=$1; sub(/^.*\//, "", n); if (n in t) s += t[n] / 20; else miss++} END{printf "%.2f", s}')
nbig=0; nsmall=0; for k in "${KIND[@]}"; do case $k in full|loo) nbig=$((nbig+1));; *) nsmall=$((nsmall+1));; esac; done
est=$(awk -v nb=$nbig -v ns=$nsmall -v sw=$SWEEP -v it=$MAXITER 'BEGIN{printf "%d", (nb*1.0 + ns*0.45) * sw * it}')
echo "Time estimate: one configuration ~ (CPU seconds per iteration summed over all instances: ${SWEEP} s) x MAXITER s per seed; seeds run in parallel on separate cores."
echo "  estimate: $nbig large (14/13 operators) + $nsmall small (3-4 operators) configurations -> ~$(( est / 60 )) min wall time (assuming >= $NPROC idle cores; +/- 30%; scales with cluster speed)"
[ "${PLAN_ONLY:-0}" = 1 ] && exit 0
if [ "${YES:-0}" != 1 ]; then
  if [ -t 0 ]; then read -r -p "Start? [y/N] " a; [ "$a" = y ] || [ "$a" = Y ] || { echo "cancelled"; exit 0; }
  else echo "not interactive: set YES=1"; exit 1; fi
fi
for i in "${!TAGS[@]}"; do
  echo; echo "### [$((i+1))/${#TAGS[@]}] $LABEL / ${TAGS[$i]}  ops=${OPL[$i]}"
  FAMILY=$FAMILY OPS="${OPL[$i]}" OUT="$ABL" TAG="${TAGS[$i]}" "$HERE/run_config.sh" abl "$@"
  # run_config.sh writes to: $ABL/<family>/<TAG>
done
echo; echo "== done. Analysis:  $HERE/bin/llrp_tools ablation $ABL/$LABEL$( [ -s "$HERE/selection/train.txt" ] && [ "$FAMILY" != train ] && [ "$FAMILY" != test ] && echo " --train $HERE/selection/train.txt")"
