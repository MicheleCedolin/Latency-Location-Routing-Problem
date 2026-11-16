#!/bin/bash
# Sharded-launcher check (~1 min): 3 arms x 2 workers on 2 instances x 3 methods x 3 seeds at 1 s, then finalize, gate and the staged submit driver.
#   bash tests/smoke_shards.sh
set -eu
cd "$(dirname "${BASH_SOURCE[0]}")/.."
KIT="$(pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export INSTANCES=coord20-5-1:coord20-5-2 TIME_LIMIT=1 NSEEDS=3 ONLY=grasp:ils:vns WORKERS=2 OUT="$TMP/stage"
fail () { echo "FAIL: $*"; exit 1; }

# invalid SHARD values are refused before anything is written
for bad in 3/3 a/b 1/2/3 -1/3 1/ /3 0/0; do
    if SHARD=$bad bash hpc/run.sh > "$TMP/bad.log" 2>&1; then fail "SHARD=$bad accepted"; fi
done
[ ! -e "$OUT/jobs.txt" ] || fail "an invalid SHARD wrote a manifest"

# all three arms start together (the manifest is written concurrently by all of them)
for i in 0 1 2; do ( SHARD=$i/3 bash hpc/run.sh > "$TMP/arm$i.log" 2>&1 ) & done
wait
for i in 0 1 2; do grep -q "ARM $i/3 done" "$TMP/arm$i.log" || { cat "$TMP/arm$i.log"; fail "arm $i did not finish cleanly"; }; done
[ "$(wc -l < "$OUT/jobs.txt")" -eq 18 ] || fail "manifest size"
cat "$OUT"/shards/jobs_arm_*of3.txt | sort > "$TMP/union.txt"; sort "$OUT/jobs.txt" > "$TMP/manifest.txt"
cmp -s "$TMP/union.txt" "$TMP/manifest.txt" || fail "the arm shares are not a partition of the manifest"
for i in 0 1 2; do [ "$(wc -l < "$OUT/shards/jobs_arm_${i}of3.txt")" -eq 6 ] || fail "arm $i is not balanced"; done
# every (instance, method) pair visits every arm once over the 3 seeds (no method tied to one arm)
bad=$(cat "$OUT"/shards/jobs_arm_0of3.txt | awk '{print $1" "$2}' | sort | uniq -c | awk '$1!=1' | wc -l)
[ "$bad" -eq 0 ] || fail "an (instance, method) pair runs twice on the same arm"
[ "$(find "$OUT" -name summary.csv | wc -l)" -eq 18 ] || fail "summaries"
[ -s "$OUT/methods_used.txt" ] && grep -q "^shards=3" "$OUT/run_settings.txt" || fail "settings files"
[ ! -e "$OUT/collect.log" ] || fail "a sharded arm must not collect"

# finalize: refuses a stage in which an arm marker is missing, accepts the complete one
mv "$OUT/shards/arm_2of3.txt" "$TMP/arm2.marker"
if ARMS=3 bash hpc/finalize.sh > "$TMP/fin_bad.log" 2>&1; then fail "finalize accepted a stage without arm 2"; fi
[ -f "$OUT/FINALIZE_FAILED" ] && [ ! -f "$OUT/FINALIZE_OK" ] || fail "FINALIZE_FAILED marker"
grep -q "arm 2: marker missing" "$OUT/FINALIZE_FAILED" || fail "reason not reported"
mv "$TMP/arm2.marker" "$OUT/shards/arm_2of3.txt"
ARMS=3 bash hpc/finalize.sh > "$TMP/fin.log" 2>&1 || { cat "$TMP/fin.log"; fail "finalize rejected a complete stage"; }
[ -f "$OUT/FINALIZE_OK" ] && [ ! -f "$OUT/FINALIZE_FAILED" ] || fail "FINALIZE_OK marker"
grep -q "verify_run: expected 18 | ok 18 " "$OUT/verify.log" || { cat "$OUT/verify.log"; fail "audit"; }
[ -s "$OUT/stage_table_by_method.csv" ] && [ "$(wc -l < "$OUT/stage_table_by_method.csv")" -eq 4 ] || fail "stage table"
# an arm started with other settings changes the manifest hash and is caught
sed -i 's/^jobs_sha256=.*/jobs_sha256=deadbeef/' "$OUT/shards/arm_1of3.txt"
if ARMS=3 bash hpc/finalize.sh > "$TMP/fin_hash.log" 2>&1; then fail "finalize accepted a different manifest hash"; fi
grep -q "arm 1: manifest hash differs" "$OUT/FINALIZE_FAILED" || fail "hash mismatch not reported"

# resume: a finished arm does not recompute anything
probe="$(ls "$OUT"/coord20-5-1/*/seed_1/summary.csv | head -1)"; before=$(stat -c %Y "$probe"); sleep 1.1
SHARD=0/3 bash hpc/run.sh > "$TMP/resume.log" 2>&1 || fail "resume of arm 0"
[ "$before" = "$(stat -c %Y "$probe")" ] || fail "a finished run was recomputed"

# arm script: gate refuses to start without the previous stage's FINALIZE_OK; ARM/ARMS (no SGE) select the arm
if REQUIRE_OK="$TMP/nothing" ARM=0 ARMS=3 OUT="$TMP/gated" bash hpc/campaign_arm.sge > "$TMP/gate.log" 2>&1; then fail "gate did not stop the arm"; fi
[ ! -e "$TMP/gated" ] || fail "a gated arm created output"
touch "$TMP/open_gate"
REQUIRE_OK="$TMP/open_gate" ARM=1 ARMS=3 bash hpc/campaign_arm.sge > "$TMP/arm_sge.log" 2>&1 || { cat "$TMP/arm_sge.log"; fail "campaign_arm.sge with an open gate"; }
grep -q "ARM 1/3 done" "$TMP/arm_sge.log" || fail "campaign_arm.sge did not run arm 1"

# arm script from a stage file (the way the scheduler starts it): STAGE_ENV carries the settings, no other environment is needed
cat > "$TMP/stage_tiny.env" <<ENVF
export INSTANCES=coord20-5-1 TIME_LIMIT=1 NSEEDS=2 METHODS_FILE=hpc/methods_phaseB_loffler9.txt CHECKPOINTS=0.5:1 OUT=$TMP/from_stage_env ARMS=2 ORDER=seed ONLY=grasp EXTRA_ARGS='' REQUIRE_OK=''
ENVF
env -i HOME="$HOME" PATH="$PATH" STAGE_ENV="$TMP/stage_tiny.env" ARM=1 WORKERS=1 bash hpc/campaign_arm.sge > "$TMP/arm_stage_env.log" 2>&1 || { cat "$TMP/arm_stage_env.log"; fail "arm from STAGE_ENV"; }
grep -q "ARM 1/2 done" "$TMP/arm_stage_env.log" || fail "STAGE_ENV arm did not run arm 1 of 2"
[ "$(wc -l < "$TMP/from_stage_env/shards/jobs_arm_1of2.txt")" -eq 1 ] || fail "STAGE_ENV arm share"

# hpc/pyenv.sh: no-op when python is fine; finds conda and activates an environment when the interpreter is missing
bash -c 'cd "$1"; . hpc/pyenv.sh; echo ok' _ "$KIT" | grep -q '^ok$' || fail "pyenv with a working python3"
mkdir -p "$TMP/fakeconda/etc/profile.d" "$TMP/fakeconda/envs/clrp_env/bin"
ln -s "$(command -v python3)" "$TMP/fakeconda/envs/clrp_env/bin/pyfake"
cat > "$TMP/fakeconda/etc/profile.d/conda.sh" <<'CSH'
conda () {
    case "$1" in
        env) printf '# conda environments:\nbase  /x\nclrp_env  /y\n' ;;
        activate) [ "$2" = clrp_env ] || return 1; PATH="$(dirname "${BASH_SOURCE[0]}")/../../envs/clrp_env/bin:$PATH" ;;
    esac
}
CSH
sed -i "s|PATH=\"\$(dirname \"\${BASH_SOURCE\[0\]}\")/../../envs/clrp_env/bin:\$PATH\"|PATH=\"$TMP/fakeconda/envs/clrp_env/bin:\$PATH\"|" "$TMP/fakeconda/etc/profile.d/conda.sh"
out=$(PYTHON=pyfake CONDA_SH="$TMP/fakeconda/etc/profile.d/conda.sh" bash -c 'cd "$1"; set -u; . hpc/pyenv.sh && echo found' _ "$KIT" 2>&1) || true
echo "$out" | grep -q "^found$" && echo "$out" | grep -q "conda environment 'clrp_env'" || { echo "$out"; fail "pyenv did not find the conda environment"; }
# a conda install without the `conda` command (as on the project cluster): the interpreter is found by scanning the environment folders
mkdir -p "$TMP/fakehome/miniconda3/envs/clrp_env/bin" "$TMP/fakehome/miniconda3/etc/profile.d"
ln -s "$(command -v python3)" "$TMP/fakehome/miniconda3/envs/clrp_env/bin/pyfake"
echo 'conda () { echo "conda: command not available" >&2; return 127; }' > "$TMP/fakehome/miniconda3/etc/profile.d/conda.sh"
out=$(PYTHON=pyfake HOME="$TMP/fakehome" bash -c 'cd "$1"; set -u; . hpc/pyenv.sh && echo "found $PYTHON"' _ "$KIT" 2>&1) || true
echo "$out" | grep -q "pyenv: using $TMP/fakehome/miniconda3/envs/clrp_env/bin/pyfake" && echo "$out" | grep -q "^found $TMP/fakehome/miniconda3/envs/clrp_env/bin/pyfake$" || { echo "$out"; fail "pyenv scan without a conda command"; }
out=$(PYTHON=pyfake LLRP_PYTHON="$TMP/fakehome/miniconda3/envs/clrp_env/bin/pyfake" HOME="$TMP/nohome" bash -c 'cd "$1"; . hpc/pyenv.sh && echo "ok $PYTHON"' _ "$KIT" 2>&1) || true
echo "$out" | grep -q "^ok $TMP/fakehome/miniconda3/envs/clrp_env/bin/pyfake$" || { echo "$out"; fail "pyenv LLRP_PYTHON override"; }
if PYTHON=pyfake HOME="$TMP/nohome" CONDA_SH= bash -c 'cd "$1"; . hpc/pyenv.sh' _ "$KIT" > "$TMP/pyenv_none.log" 2>&1; then fail "pyenv accepted a missing interpreter"; fi
grep -q "no Python >= 3.10 found" "$TMP/pyenv_none.log" || fail "pyenv error message"

# submit driver with a stub qsub: dry run has no side effects, SUBMIT=1 chains arms -> finalize -> next arms through -hold_jid
cat > "$TMP/qsub" <<'STUB'
#!/bin/bash
n=$(( $(cat "$STUB_DIR/n" 2>/dev/null || echo 100) + 1 )); echo "$n" > "$STUB_DIR/n"
echo "$n $*" >> "$STUB_DIR/calls"
echo "$n"
STUB
chmod +x "$TMP/qsub"; mkdir "$TMP/stub"
CAMP="$TMP/camp"
env -u INSTANCES -u TIME_LIMIT -u NSEEDS -u ONLY -u WORKERS -u OUT STAGES="P20 P50" CAMPAIGN_DIR="$CAMP" QSUB="$TMP/qsub" STUB_DIR="$TMP/stub" bash hpc/submit_llrp_campaign.sh > "$TMP/dry.log"
[ ! -e "$CAMP" ] && [ ! -e "$TMP/stub/calls" ] || fail "dry run had side effects"
grep -q "Dry run" "$TMP/dry.log" || fail "dry run message"
env -u INSTANCES -u TIME_LIMIT -u NSEEDS -u ONLY -u WORKERS -u OUT SUBMIT=1 STAGES="P20 P50" EXTRA_ARGS="--depot-impact adaptive" CAMPAIGN_DIR="$CAMP" QSUB="$TMP/qsub" STUB_DIR="$TMP/stub" QSUB_OPTS="-q long.q" bash hpc/submit_llrp_campaign.sh > "$TMP/sub.log"
[ "$(wc -l < "$TMP/stub/calls")" -eq 4 ] || { cat "$TMP/stub/calls"; fail "expected 4 qsub calls"; }
sed -n 1p "$TMP/stub/calls" | grep -q -- "-v STAGE_ENV=$CAMP/P20_60s_30seeds/stage.env -t 1-6 -N LLRP_P20 -pe smp 15 -q long.q hpc/campaign_arm.sge" || fail "arms of P20"
sed -n 1p "$TMP/stub/calls" | grep -q -- " -V" && fail "qsub -V must not be used"
sed -n 2p "$TMP/stub/calls" | grep -q -- "-N LLRP_P20_fin -hold_jid 101 -q long.q hpc/campaign_finalize.sge" || fail "finalize of P20 must wait for the arms"
sed -n 3p "$TMP/stub/calls" | grep -q -- "-hold_jid 102 .*hpc/campaign_arm.sge" || fail "P50 arms must wait for the P20 finalize"
( . "$CAMP/P50_180s_30seeds/stage.env"
  [ "$REQUIRE_OK" = "$CAMP/P20_60s_30seeds/FINALIZE_OK" ] || exit 1
  [ "$TIME_LIMIT" = 180 ] && [ "$INSTANCES" = P50 ] && [ "$EXTRA_ARGS" = "--depot-impact adaptive" ] && [ "$ARMS" = 6 ] ) || fail "stage.env of P50"
[ -s "$CAMP/submitted_jobs.txt" ] || fail "job ids not recorded"
# start.sh: one command, submits the given stages (default P20)
( cd "$KIT" && env -u INSTANCES -u TIME_LIMIT -u NSEEDS -u ONLY -u WORKERS -u OUT CAMPAIGN_DIR="$TMP/camp2" QSUB="$TMP/qsub" STUB_DIR="$TMP/stub" bash hpc/start.sh > "$TMP/start.log" )
grep -q "arms job 105 | finalize job 106" "$TMP/start.log" || { cat "$TMP/start.log"; fail "start.sh default stage"; }
if ARMS=7 SLOTS=15 CORES=96 bash hpc/submit_llrp_campaign.sh > /dev/null 2>&1; then fail "more cores than the cluster has were accepted"; fi
echo "shard smoke OK (partition + balance + rotation, concurrent manifest writes, finalize gates, resume, arm gate, stage file, pyenv, staged submit chain)"
