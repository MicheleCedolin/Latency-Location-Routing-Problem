#!/bin/bash
# Self-test (single core, a few seconds to ~2 min).  Run it ONCE after moving to a new machine or compiler.  No Python needed.
#   0) llrp_tools selftest: Wilcoxon / Holm / percentile / natural sorting against known values
#   1) one instance per family (Barreto, Prins, Tuzun) x 6 configurations: the solver with --check (every move evaluation is compared
#      with a full recomputation before it is applied; mismatch -> exit code 3) + the independent verifier (llrp_tools verify: distances,
#      arrival times, latency, load, customer partition and route/depot counts are recomputed from the routes and compared with run.csv)
#   2) the verifier must REJECT a deliberately corrupted route file
#   3) same seed twice -> bit-identical cost (determinism); passing the default constants explicitly gives the same result (flag identity)
#   4) run_config.sh -> merge -> check-csv (small run, 2 seeds)
#   5) irace dry run (target-runner chain; irace itself is not needed)
#   6) --atmost (at most Ng open depots): --check + independent verifier on Prins 50-5-2BIS-5 with the tuned flags; the default (exactly Ng) is unchanged
HERE=$(cd "$(dirname "$0")" && pwd)
BIN=${BIN:-$HERE/bin/llrp_fast}; TOOLS=${TOOLS:-$HERE/bin/llrp_tools}
{ [ -x "$BIN" ] && [ -x "$TOOLS" ]; } || "$HERE/build.sh" || exit 1
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0

echo "0) llrp_tools selftest"
"$TOOLS" selftest > "$T/selftest.log" 2>&1 && echo "   OK ($(grep -c ' ok ' "$T/selftest.log") checks)" || { echo "   FAILED"; grep FAIL "$T/selftest.log"; fail=1; }

echo "1) --check + independent verifier (family x configuration)"
n=0; bad=0
for spec in barreto/Gaskell21-5 barreto/Ch50-5 prins/20-5-1-5 tuzun/P111112-10; do
  inst=$HERE/inst/$spec.inst; b=$(basename "$spec"); c=0
  [ -s "$inst" ] || { echo "   missing instance: $inst"; fail=1; continue; }
  for cfg in "--ops zou" "--ops zou --so --ds" "--ops full --so" "--ops full --so --ds" "--ops full --so --select first --order fixed" "--ops full --so --ils 3"; do
    c=$((c+1)); n=$((n+1)); p=$T/${b}_c$c
    # shellcheck disable=SC2086
    "$BIN" --instance "$inst" --seed $c --max-iter 10 $cfg --check --quiet --out-level 1 --out "$p" > "$p.stdout" 2> "$p.stderr"; rc=$?
    if [ $rc -ne 0 ]; then echo "   ERROR  $b $cfg  (exit code $rc)"; head -3 "$p.stderr"; bad=1; fi
    "$TOOLS" verify "$inst" "$p" > "$p.verify" 2>&1 || { echo "   VERIFICATION FAILED  $b $cfg"; head -3 "$p.verify"; bad=1; }
  done
done
echo "   $n runs: $([ $bad = 0 ] && echo OK || echo FAILED)"; [ $bad = 0 ] || fail=1

echo "2) the verifier rejects a corrupted file"
p=$T/Ch50-5_c3; q=$T/tamper
if [ -s "$p.routes.csv" ]; then
  for k in routes run ops trace; do cp "$p.$k.csv" "$q.$k.csv"; done
  awk -F, 'BEGIN{OFS=","} NR==1{n=split($6,a," -> "); if(n>=2){t=a[1];a[1]=a[2];a[2]=t;s=a[1];for(i=2;i<=n;i++)s=s " -> " a[i];$6=s}} {print}' "$p.routes.csv" > "$q.routes.csv"     # swap the first two customers of the first route
  if "$TOOLS" verify "$HERE/inst/barreto/Ch50-5.inst" "$q" > "$T/tamper.log" 2>&1; then echo "   FAILED: corrupted route was accepted"; fail=1; else echo "   OK (corrupted route rejected)"; fi
else echo "   skipped (no Ch50-5 output)"; fail=1; fi

echo "3) determinism and flag identity"
I=$HERE/inst/barreto/Ch50-5.inst
a=$("$BIN" --instance "$I" --seed 7 --max-iter 10 --ops full --so --ils 3 --quiet 2>/dev/null | grep final_cost)
b=$("$BIN" --instance "$I" --seed 7 --max-iter 10 --ops full --so --ils 3 --quiet 2>/dev/null | grep final_cost)
d=$("$BIN" --instance "$I" --seed 7 --max-iter 10 --ops full --so --ils 3 --rcl 5 --it-div 5 --it-int 3 --so-win-up 4 --so-win-down 4 --so-f1 1.5 --so-f2 2.5 --beta0-scale 1 --quiet 2>/dev/null | grep final_cost)
if [ -n "$a" ] && [ "$a" = "$b" ]; then echo "   determinism: OK ($a)"; else echo "   determinism: FAILED ('$a' / '$b')"; fail=1; fi
if [ -n "$a" ] && [ "$a" = "$d" ]; then echo "   same result when the default constants are given explicitly: OK"; else echo "   flag identity: FAILED ('$a' / '$d')"; fail=1; fi

echo "4) run_config.sh -> merge -> check-csv"
if FAMILY=custom OUT=$T/cfg NPROC=2 PIN=0 MAXITER=5 STALL=0 OUTLEVEL=2 SUMMARY=0 "$HERE/run_config.sh" full3 Gaskell21-5 > "$T/rc.log" 2>&1 \
   && "$TOOLS" merge "$T/cfg/custom/full3" > /dev/null 2>&1 && "$TOOLS" check-csv "$T/cfg/custom/full3" > "$T/cc.log" 2>&1; then
  echo "   OK ($(tail -1 "$T/cc.log"))"
else echo "   FAILED"; tail -5 "$T/rc.log"; cat "$T/cc.log" 2>/dev/null; fail=1; fi

echo "5) irace dry run (irace itself is not required)"
if "$HERE/irace_dryrun.sh" 2 > "$T/dry.log" 2>&1; then echo "   OK"; else echo "   FAILED"; tail -5 "$T/dry.log"; fail=1; fi

echo "6) --atmost (at most Ng open depots) with --check + verifier"
FLT=$(cat "$HERE/irace/best.flags"); I2=$HERE/inst/prins/50-5-2BIS-5.inst
ok6=1
"$BIN" --instance "$I2" --seed 1 $FLT --atmost --max-iter 60 --check --out-level 1 --out "$T/am" --quiet > "$T/am.txt" 2>&1 || ok6=0
"$TOOLS" verify "$I2" "$T/am" > "$T/am.v" 2>&1 || ok6=0
"$BIN" --instance "$I2" --seed 1 $FLT --max-iter 60 --out-level 1 --out "$T/ex" --quiet > "$T/ex.txt" 2>&1 || ok6=0
"$TOOLS" verify "$I2" "$T/ex" > "$T/ex.v" 2>&1 || ok6=0
if [ $ok6 = 1 ]; then echo "   OK (--atmost: $(grep final_cost "$T/am.txt"); default: $(grep final_cost "$T/ex.txt"))"; else echo "   FAILED"; tail -3 "$T/am.txt" "$T/am.v" "$T/ex.v" 2>/dev/null; fail=1; fi

[ $fail = 0 ] && echo "SELFCHECK: ALL OK" || { echo "SELFCHECK: FAILED"; exit 1; }
