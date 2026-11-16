#!/bin/bash
# Launcher check (~25 s): 2 methods x 2 seeds x 1 instance at 1 s each, then resume, stale-run handling, audit + collector.
#   bash tests/smoke_hpc.sh
set -eu
cd "$(dirname "${BASH_SOURCE[0]}")/.."
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export INSTANCES=coord20-5-1 TIME_LIMIT=1 NSEEDS=2 ONLY=grasp:rkrs WORKERS=2 OUT="$TMP/smoke"

bash hpc/run.sh > "$TMP/first.log"
n=$(find "$OUT" -name summary.csv | wc -l)
[ "$n" -eq 4 ] || { echo "FAIL: expected 4 summaries, got $n"; cat "$TMP/first.log"; exit 1; }
[ "$(find "$OUT" -name config.json | wc -l)" -eq 4 ] || { echo "FAIL: config.json missing"; exit 1; }
[ -s "$OUT/report.csv" ] && [ -s "$OUT/checkpoint_long.csv" ] || { echo "FAIL: collector outputs missing"; exit 1; }
[ "$(find "$OUT" -name '*.solution.json' | wc -l)" -eq 4 ] || { echo "FAIL: solution.json missing"; exit 1; }
grep -q "verify_run: expected 4 | ok 4 " "$OUT/verify.log" || { echo "FAIL: audit"; cat "$OUT/verify.log"; exit 1; }
[ "$(wc -l < "$OUT/jobs.txt")" -eq 4 ] && [ -s "$OUT/run_settings.txt" ] || { echo "FAIL: manifest"; exit 1; }

probe="$OUT/coord20-5-1/grasp_first_baseline_route/seed_1/summary.csv"
before=$(stat -c %Y "$probe")
sleep 1.1
bash hpc/run.sh > "$TMP/second.log"
after=$(stat -c %Y "$probe")
[ "$before" = "$after" ] || { echo "FAIL: finished run was recomputed on resume"; exit 1; }
[ ! -e "$OUT/resume_mismatch.log" ] || { echo "FAIL: unchanged configuration was reported as stale"; exit 1; }

# Changed configuration (other checkpoints) must not reuse the old results: they are moved aside and recomputed.
CHECKPOINTS=0.25:1 bash hpc/run.sh > "$TMP/third.log" || true
[ "$(wc -l < "$OUT/resume_mismatch.log")" -eq 4 ] || { echo "FAIL: stale runs not detected"; cat "$TMP/third.log"; exit 1; }
[ "$(find "$OUT.superseded" -name summary.csv | wc -l)" -eq 4 ] || { echo "FAIL: stale runs not preserved"; exit 1; }
[ "$(find "$OUT" -name summary.csv | wc -l)" -eq 4 ] || { echo "FAIL: stale runs not recomputed"; exit 1; }
grep -q "verify_run: expected 4 | ok 4 " "$OUT/verify.log" || { echo "FAIL: audit after recompute"; cat "$OUT/verify.log"; exit 1; }
rm -rf "$OUT.superseded"

# Job order: the default is seed-major, ORDER=instance is instance-major (complete instances first); both audit clean.
for ord in seed instance; do
    ORDER=$ord INSTANCES=coord20-5-1:coord20-5-2 NSEEDS=2 ONLY=grasp OUT="$TMP/order_$ord" bash hpc/run.sh > "$TMP/order_$ord.log"
    grep -q "verify_run: expected 4 | ok 4 " "$TMP/order_$ord/verify.log" || { echo "FAIL: audit ORDER=$ord"; cat "$TMP/order_$ord/verify.log"; exit 1; }
done
[ "$(sed -n 2p "$TMP/order_seed/jobs.txt" | cut -d' ' -f1,5)" = "coord20-5-2 1" ] || { echo "FAIL: seed-major order"; exit 1; }
[ "$(sed -n 2p "$TMP/order_instance/jobs.txt" | cut -d' ' -f1,5)" = "coord20-5-1 2" ] || { echo "FAIL: instance-major order"; exit 1; }
echo "launcher smoke OK (4 runs audited against the manifest, resume skips finished runs, stale runs are moved aside and recomputed, collector ran, both job orders audit clean)"
