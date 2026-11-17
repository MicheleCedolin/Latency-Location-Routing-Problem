#!/bin/bash
# With the new flags OFF, llrp_fast_v8 must give exactly the results of llrp_fast_v7 (fixed iteration count, B1 flags): final cost, iterations, routes, iteration log.
#   usage: identity_check.sh <bin_dir> <inst_root> <arms_dir>
BIN=$1; INST=$2; ARMS=$3; bad=0
read -ra F < "$ARMS/B1.flags"
T=$(mktemp -d)
for spec in "tuzun/P111122-20 40" "prins/100-10-1-10 40" "barreto/Ch75-10 30" "tuzun/P122112-10 12"; do
  set -- $spec; nm=$(basename "$1")
  for v in 7 8; do "$BIN/llrp_fast_v$v" --instance "$INST/$1.inst" --seed 1 "${F[@]}" --max-iter "$2" --out-level 2 --algo X --quiet --out "$T/v${v}_$nm" > "$T/v${v}_$nm.txt" 2>&1 & done
  wait
  a=$(grep -E '^(final_cost|iterations|last_improvement_iter|dpm|pool )' "$T/v7_$nm.txt" | sed 's/sp_cpu_s=[0-9.]*//;s/build_cpu_s=[0-9.]*//' | md5sum)
  b=$(grep -E '^(final_cost|iterations|last_improvement_iter|dpm|pool )' "$T/v8_$nm.txt" | sed 's/sp_cpu_s=[0-9.]*//;s/build_cpu_s=[0-9.]*//' | md5sum)
  r1=$(md5sum < "$T/v7_$nm.routes.csv"); r2=$(md5sum < "$T/v8_$nm.routes.csv")
  i1=$(cut -d, -f5-12 "$T/v7_$nm.iter.csv" | md5sum); i2=$(cut -d, -f5-12 "$T/v8_$nm.iter.csv" | md5sum)
  if [ "$a" = "$b" ] && [ "$r1" = "$r2" ] && [ "$i1" = "$i2" ]; then echo "OK    v8 (flags off) = v7: $nm ($(grep final_cost "$T/v8_$nm.txt"))"; else echo "DIFF  v8 (flags off) != v7: $nm"; bad=1; fi
done
exit $bad
