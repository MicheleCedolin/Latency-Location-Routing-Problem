# Stage 4: run-internal route pool with set partitioning (B1) on all 57 instances with n > 75 (pre-registered plan)

> English translation of the Turkish plan `README_B.txt` that accompanied the campaign kit (`llrp_pool_b`, engine `llrp_fast` v7). The plan was written on 15 November 2026,
> **before any result of the pilot or of the 57 instances existed**. Content, numbers, criteria, thresholds and identifiers are unchanged; nothing was added or removed
> (Turkish decimal commas are written as decimal points; the sentence the original writes as "G0-G2" is translated literally and flagged in place).
> The Turkish original was part of the cluster kit and is not stored in this repository (the kit scripts it names, `b_submit.sh` and so on, are not stored either; the
> archive `study_results/b1_tuned.tar.gz` holds the runs, their flags, the checksum of the binary and the verification of every run).
> Provenance of the translated text: `README_B.txt` of the kit archive `llrp_pool_b.tar.gz` (58 lines, 6202 bytes, md5 `036ecba428dc198accaf6d5f5a4591c0`; archive md5 `af1a779383d374109ce5becf82445814`).
> Names: the plan calls the campaign "Stage 2 (B)" (the second of the extension campaigns of the study; its "Stage 1" is the depot campaign `V1`, `V1ALL` in the criteria);
> the manuscript and this repository call the route pool **stage 4** (flags `cpp/stages/3_pool.flags`, arm name `B1`) and the depot layer **stage 3** (flags `cpp/stages/2_depot.flags`, arm name `V1`).
> The analysis of the criteria is `analysis/stages/analyze_stages.py`.

## STAGE 2 (B): RUN-INTERNAL ROUTE POOL + EXACT DP SEQUENCE POLISH + SET PARTITIONING (llrp_fast_v7)

**AIM.** Inside GRASP+RVND+ILS (the V1 flags), pool the routes found during the run and combine them periodically by set partitioning (SP). It also measures whether the finding of the
cross-run, post-hoc "SP of 30" is useful as a SINGLE-RUN component. The pool + SP budget is INSIDE the CPU limit (for the last SP call `--pool-tl` s is reserved; the intermediate calls are also deducted
from the same CPU counter), hence the comparison with V1 is fair at equal CPU.

**ALGORITHM** (everything is switched on by flags; v7 without flags = v6, bit for bit identical, verified by `b_selfcheck.sh`):

- Pool: the routes of the final solution of every GRASP iteration (key: depot + customer set); when a route is added, its sequence is brought to minimum latency by an exact DP (Held-Karp, k <= 16).
- With `--pool-src 2`, the ILS local optima that lie within (1+theta) of the best are also put into the pool (theta = 0.02).
- SP: at iteration 8, 16, 32, ... and at the end of the run (`--pool-first 8`). Each call works on the best `--pool-sets` (3) open-depot sets seen up to that moment:
  a coarse Lagrangian stage (at most 4000 subgradient steps) + reduced-cost elimination against the UB + an exact DFS (node limit 300000, time limit `--pool-tl` = 3 s CPU).
  A solution is adopted only if it passes `check_validity` and its cost is strictly smaller than the current best; when adopted, it is written to the anytime trace and the depot-pruning
  threshold of GRASP (`--dpm-prune`) is updated.
- SP uses no randomness; consequence: up to the first improvement by SP the run follows the same path as V1.
- Validation (sandbox): the C++ SP gave the same value as the exact optimum of HiGHS on 134 cross-run pools (1x and ext10, 76+58 instances) (134/134); the slowest call took 4.7 s (n=200, m=10;
  even where it hits the node limit it finds the optimum). v7 without flags = v6: 6 instances x 1-2 seeds, run/iter/trace/ops/routes/dpm identical.

**ARMS**

| arm | definition |
|---|---|
| V1 | (reference, NOT RE-RUN) Stage pilot (job 153847), P121122-20, 30 seeds, 600 s CPU: mean gap 0.792 %, best 0.110 %, runs reaching the BKS 0/30, <= Zou f_avg 2/30. |
| B1 | V1 flags + `--pool-sp --pool-tl 3 --pool-sets 3 --pool-first 8 --pool-src 1` (**PRIMARY ARM**) |
| B2 | V1 flags + `--pool-sp --pool-tl 3 --pool-sets 3 --pool-first 8 --pool-src 2 --pool-theta 0.02` (exploratory) |

**MODES** (`b.conf`)

- `MODE=pilot` (default): P121122-20, B1+B2, seeds 1..30, 600 s -> 60 tasks, ~10 CPU-hours (ideal wall time ~11 min for 12 x 8 slots, if all start at the same time).
- `MODE=full`: the 57 instances with n > 75, B1, seeds 1..30, 3n s -> 1710 tasks, ~203 CPU-hours (ideal ~2.2 h @ 96 slots); B2 can be added with `ARMS="B1 B2"`.
- The pilot was run on P121122-20, a HARD instance, and that instance was chosen: the result is not a GENERALISATION but a check of the mechanism/feasibility; generalisation can only be tested with `MODE=full`.
  (The lesson of the pilot-then-generalisation of Stage 1: a pilot result may carry a selection bias.)

**INSTALLATION** (on the cluster; `~/llrp_fast_kit_v4` and `~/llrp_depot_v6` exist)

```
1) tar xzf llrp_pool_b.tar.gz && cd llrp_pool_b
2) ./build_v7.sh            # bin/llrp_fast_v7, bin/llrp_tools_v7, bin/sp_test
3) ./b_selfcheck.sh         # ~3 min, on the login node; "HEPSI TAMAM" (all done) is expected
4) PLAN_ONLY=1 ./b_submit.sh      # plan + duration estimate
5) ./b_submit.sh                  # 12 x 8 = 96 slots; -hold_jid V1ALL: waits until the Stage 1 jobs have FINISHED (you run the qsub yourself)
   HOLD_AFTER= ./b_submit.sh      # without waiting (take care not to exceed the 96-slot limit together with Stage 1)
   MODE=full ./b_submit.sh        # 57 instances (decide after looking at the pilot result)
```

- Monitoring: `./b_status.sh`. Stopping: `touch queue_$MODE/STOP` (no new task is taken, the running ones finish). Dead jobs: `./b_requeue.sh` (only when no BPOOL job is running at all).
- Result: `./b_collect.sh` -> `b_<mode>_results_*.tgz` (send it to me). Merge/analysis: `./b_merge.sh` ; `python3 analyze_b.py ...` (below).

## PRE-REGISTERED CRITERIA (before the results were seen; will not be changed)

**PILOT** (`MODE=pilot`, P121122-20, B1 primary; reference V1: the 30 runs above):

| criterion | definition |
|---|---|
| **P0** | one-sided Mann-Whitney U against V1 (B1 < V1) p < 0.01 AND a drop of the mean gap >= 0.15 points. |
| **P1** | at least 1 run reaches BKS + 0.005 (V1: 0/30). |
| **P2** | at least 5/30 runs <= Zou f_avg = 5592.63 (V1: 2/30). |
| **S** | (safety) 30/30 feasible and independent verification OK; CPU overrun at the same limit as the V1 pilot (mean <= 1 %, maximum <= 2 %); the SP share of the CPU is reported (expected: <= ~10 s/run). |

Reading: P0 passes -> B is a candidate for a "single-run component"; the decision on the FULL run is yours (for generalisation there are in addition G0-G2 below [sic: the criteria listed below are G0, G1 and Z]).
P0 fails -> pool + SP is reported only as a post-hoc column "SP of 30" (in the paper: a multi-start aggregation, with a label SEPARATE from the single-run result); B2 only as an exploratory comparison.

**FULL** (`MODE=full`; reference: the result of Stage 1 (V1 @ 3n s, 57 instances) -- same seeds, same CPU limit):

| criterion | definition |
|---|---|
| **G0** | instance-level difference of the mean gap (B1 - V1ALL), one-sided Wilcoxon p < 0.01 and a mean drop >= 0.10 points. |
| **G1** | on the subset n >= 150, mean gap(B1) <= mean gap(V1ALL) - 0.10 points. |
| **Z** | harm counter: the number of instances on which B1 is more than 0.2 points WORSE than V1ALL is <= 5/57; each of them is examined (SP time / node limit / pool size). |

Note: for the FULL analysis the V1ALL results (Stage 1) must have been merged; the analysis script is written separately (`analyze_b.py` is for the pilot and does not support the instance-level comparison).

## OUTPUT FILES, ANALYSIS, LITERATURE, LIMIT

- OUTPUT FILES (per run; inside the tar): `<inst>_s<seed>_<arm>.{run,trace,routes,ops,iter,dpm,pool}.csv`, `.verify`, `log`. `pool.csv`: the SP call log
  (call no., iteration, CPU, SP CPU, previous/next best, root lower bound, pool size, nodes, tried set, improved, completed).
- ANALYSIS (pilot):
  ```
  ./b_merge.sh ; python3 analyze_b.py --ref <V1 run.csv (pilot job 153847)> --b1 merged_b_pilot/tuzun/B1/run.csv --b2 merged_b_pilot/tuzun/B2/run.csv \
                      --pool1 merged_b_pilot/tuzun/B1/pool_all.csv --pool2 merged_b_pilot/tuzun/B2/pool_all.csv --zou-avg 5592.63 --budget 600
  ```
- LITERATURE: Rosing & ReVelle 1997 (EJOR 97(1):75-86, heuristic concentration); Subramanian, Uchoa & Ochi 2013 (COR 40(10):2519-2531, ILS-SP).
- LIMIT: a pilot on a single instance; SP uses no randomness, but it does not adopt an improvement unless it is permitted (valid + strictly smaller); the pool of ILS local optima (B2) increases memory and SP time.

## Outcome (added when the English version was written; the plan and the criteria above are unchanged)

Regenerated by `analysis/stages/analyze_stages.py` from `depot_tuned.tar.gz` and `b1_tuned.tar.gz` (`analysis/stages/reference/stages_summary.md`): G1 met (0.448 -> 0.174), G0 met (0.290 -> 0.112, p = 1.9e-10),
Z within the limit (0/57). All three criteria are met. The pilot (60 runs) is not archived in this repository and its outcome is not restated here; the criteria of the full campaign do not depend on it.
