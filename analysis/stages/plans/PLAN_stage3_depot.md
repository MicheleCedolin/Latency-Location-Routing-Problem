# Stage 3: depot-aware diversification (V1) on all 57 instances with n > 75 (pre-registered plan)

> English translation of the Turkish plan `README_V1_ALL.txt` that accompanied the campaign kit (`llrp_v1_all`, engine `llrp_fast` v6). The plan was written on 15 November 2026,
> **before any result of the 57 instances existed**. Content, numbers, criteria, thresholds and identifiers are unchanged; nothing was added or removed.
> The Turkish original was part of the cluster kit and is not stored in this repository (the kit scripts it names, `v1_submit.sh` and so on, are not stored either; the
> archive `study_results/depot_tuned.tar.gz` holds the runs, their flags, the checksum of the binary and the verification of every run).
> Names: the plan calls the campaign "Stage 1" (the first of the extension campaigns of the study); the manuscript and this repository call the depot layer **stage 3**
> (flags `cpp/stages/2_depot.flags`, arm name `V1`), and the reference arm `ext10` is the base method at the budget 3n s (stage 2). The analysis of the criteria is `analysis/stages/analyze_stages.py`.

## STAGE 1 -- V1 (depot layer: D1+D2) on ALL instances with n > 75 (llrp_fast v6, 57 instances x 30 seeds)

**AIM.** In the pilot on P121122-20, V1 (`--dpm-rank 10,0.25 --dpm-prune`) reduced the mean gap from 3.56 % to 0.80 %. This package tests V1 on **all** 57 instances with n > 75
(25 x n=100, 12 x n=150, 18 x n=200, Or117-14, Mi134-8) with the SAME protocol as ext10 and measures whether the effect generalises.
Decision: the user (15 Nov 2026) -- the earlier rule "extend only if it beats Zou" was replaced by this decision; the extension is already approved and the result will be reported.
WARNING: the pilot instance had been chosen where the effect is largest; this run tests the "selection bias" of the pilot.

**PROTOCOL (same as ext10).** Seeds 1..30; CPU limit max(5, 3n) s (TC=300; n=200 -> 600 s; n=100 -> 300 s); max-iter 100000; no stall limit; the CPU limit is checked at the END of a GRASP iteration.
Flags: `flags/V1.flags` (= the V1.flags of the pilot: kit best.flags [config 267] + `--dpm-rank 10,0.25 --dpm-prune`).
Binary: `~/llrp_depot_v6/bin/llrp_fast_v6` (the one used in the pilot, bit-identical to the flagless v5). Data: kit `inst/` (md5 check in the preflight).
Differences (honesty): (a) OUTLEVEL=2 (iteration log; it does not change the solution path); (b) the runs are written to the node's LOCAL disk and one archive per task is copied to NFS
(in the 1x run, NFS latency added about 125-185 s of wall time to every run); (c) node load / hardware may differ from ext10 (recorded in the env files).

**COST.** 1710 tasks, 203.8 CPU-hours (solver). If 96 slots (12 jobs x 8) run at the same time, the ideal wall time is about 2.2 hours; it is longer if the slot gaps open late (8 slots per job have to be found).

**RUN STRUCTURE** (the work is split into pieces and stuck in as 8-slot gaps appear)
- `queue/tasks.tsv`: 1710 tasks (instance, seed), large limit first (LPT). A task = a single run (the smallest unit).
- `v1_submit.sh` submits NJOBS (= 12) jobs with `-pe smp 8` (12 x 8 = 96 = your limit; guarded by MAXSLOTS). Each job starts to pull tasks from the queue when it has found an 8-slot gap and has started
  (atomic claim with `mkdir`; two jobs never take the same task) and ends when the queue is empty. The jobs that start first process more tasks; the jobs that start late take the remaining tasks;
  a job that never gets to start is harmless (if the queue is empty when it starts, it exits at once).
- If a job dies or is interrupted (qdel, node failure): the claimed-but-unfinished tasks are given back with requeue (`v1_requeue.sh`), then new jobs are submitted with `v1_submit.sh`.
- To stop without touching the running jobs: `touch queue/STOP` (the jobs finish their current task and exit); to restart: `rm queue/STOP`.

**SETUP** (cluster; the kit `~/llrp_fast_kit_v4` and `~/llrp_depot_v6` must be left over from the pilot)
```
cd ~ && tar xzf llrp_v1_all.tar.gz && cd llrp_v1_all
./v1_preflight.sh                 # binary sha256, flags, md5 of the 57 instances, check of the Tuzun coordinates, 5 s smoke run  ->  "READY"
PLAN_ONLY=1 ./v1_submit.sh        # plan
./v1_submit.sh                    # submits the 12 jobs (it also runs the preflight itself)
./v1_status.sh                    # progress (finished / waiting tasks, CPU-hours, by n class)
```
NOTE: if the sha256 of the binary differs from the one of the pilot (a different build), the preflight WARNS and does not stop; the checksum is recorded in the env files.

**RESULT (send it to me)**
```
./v1_collect.sh                   # v1_all_results_<date>.tgz  (task archives + env + progress + qacct; a few tens of MB)
```
It can also be run before the campaign has finished, for an interim check (it takes the completed tasks). I will do the merging and the analysis (`v1_merge.sh` also works in the sandbox).

**PRE-REGISTERED CRITERIA** (fixed before the results were seen; not changed without your approval)
Reference = ext10 (V0; the same 57 instances, seeds 1..30, 3n s). There is no matching of paths (the seed paths separate in the first iteration); the comparison is at instance level.
ext10 reference values (57 instances): mean gap (mean of the 30 runs) 0.595 % (median 0.223); n >= 150: 0.941; n = 200: 1.232; best-of-30 reaching BKS + 0.005: 28/57;
mean <= Zou f_avg: 6/57; instances with mean gap > 1 %: 12, > 2 %: 5.

| criterion | definition |
|---|---|
| **G0** overall improvement | the mean gaps of the 57 instances satisfy V1 < ext10 with one-sided Wilcoxon signed-rank p < 0.01 **and** the mean over the 57 instances drops by >= 0.15 points (<= 0.445) |
| **G1** hard class | mean gap of the instances with n >= 150 (30 instances) <= 0.60 % (ext10: 0.941) |
| **G2** Zou average | the number of instances with mean <= Zou f_avg is >= 10 of 57 (ext10: 6) |
| **Z** harm | the number of instances whose mean gap is more than 0.2 points WORSE than ext10 is reported (threshold: <= 5/57); for each of them, the LB order of the Zou / published depot set is examined, and whether it lies outside K = 10 |

Reported without a threshold: number of best-of-30 BKS values, mean / median / best gap, table by n class, anytime curves (at 60 s, 150 s, 300 s, and at Zou T_avg),
A/B/C decomposition (against the Zou solution), distribution of the final depot set by LB order, dpm counters, bootstrap 95 % confidence interval; route pool + DP + SP (the pools of V1).

**Reading rule:** if G0 and G1 are met, "V1 generalises to n > 75"; if only G0 is met, "partially"; if neither is met, the result of the pilot is read as selection bias.

**TROUBLESHOOTING**
- "binary missing": `./build_v6.sh` in `~/llrp_depot_v6` (g++ >= 4.8).
- If a job with 8 slots never starts: adjust NJOBS and SLOTS (example: `NJOBS=6 ./v1_submit.sh`); the total NJOBS*SLOTS must be <= 96.
- If a task fails: `results_v1_all/fail/<task>.log`; to retry all failed tasks, first run `./v1_requeue.sh` when the jobs have finished (it only gives back the claimed-but-unfinished tasks;
  to delete a failure record, delete the corresponding claim directory: `rmdir queue/claim/<task>`), then `./v1_submit.sh`.
- If the local disk (`$TMPDIR`) has less than 500 MB, the job falls back to NFS (it warns).

## Outcome (added when the English version was written; the plan above is unchanged)

Regenerated by `analysis/stages/analyze_stages.py` from `ext10_tuned.tar.gz` and `depot_tuned.tar.gz` (`analysis/stages/reference/stages_summary.md`): G0 met (0.595 -> 0.290, p = 1.3e-8),
G1 met (0.448), G2 not met (9/57; threshold 10), Z within the limit (1/57: P111122-20, +0.287). By the reading rule: V1 generalises to n > 75.
