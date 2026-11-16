#!/bin/bash
# Pipeline check WITHOUT irace: draws random configurations from the parameter space and runs target-runner the way irace calls it.
#   ./irace_dryrun.sh [NUMBER_OF_CONFIGURATIONS=3]      (every run uses ITERS=5 iterations; the first 2 instances of the training list)
HERE=$(cd "$(dirname "$0")" && pwd)
N=${1:-3}
[ -x "$HERE/irace/target-runner" ] || "$HERE/bin/llrp_tools" irace-gen --train "$HERE/selection/train.txt" --out "$HERE/irace" > /dev/null
i=0; bad=0
while read -r cfg; do
  i=$((i+1))
  for inst in $(head -2 "$HERE/irace/instances_train.txt"); do
    set -f
    c=$(cd "$HERE/irace" && IRACE_MODE=iter ITERS=5 ./target-runner "$i" 1 $((1000+i)) "../inst/$inst" $cfg)
    set +f
    echo "config $i  $inst  cost=$c"
    case "${c#-}" in ''|*[!0-9.]*) bad=1;; esac       # a negative gap (below the BKS) is valid
  done
done < <("$HERE/bin/llrp_tools" irace-sample "$N" --seed "${SEED:-1}")
[ $bad = 0 ] && echo "DRYRUN: OK" || { echo "DRYRUN: FAILED"; exit 1; }
