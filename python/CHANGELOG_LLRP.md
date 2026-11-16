# Changelog — LLRP kit

## v13.0-llrp.0.5.0-rc1 (2026-11-09) — three search components (algorithm change; the defaults still reproduce v0.4.2 bit for bit)

Reason: the P50 stage (v0.4.2, 180 s, 30 seeds) left alns / lns / grasp / ig (and sa, ta, tabu, aco) 7-13 % above the best-known values while brkga / vns / ils stayed at 0.1-0.4 %.
Diagnosis (sandbox, seed 1, coord50-5-2bBIS): `grasp_construct` opens its K routes at the depot that is cheapest for the next customer, so with a tight fleet all routes end up at one depot of the allowed set; the first-improvement descent over `loffler9` has no depot move and ruin-and-recreate cannot leave that basin. BRKGA does not have the problem because its decoder inserts customers in a random priority order.

1. **`--start-mix q`** (default 0): a start solution is built by random-priority insertion (`priority_construct`, the constructor of the random-key decoders) with probability q, by `grasp_construct` otherwise. `rng.random()` is drawn only when q > 0, so q = 0 is bit-identical to v0.4.2.
   Sandbox check (5 methods x 8 P50 instances, 25 s, seed 1, q = 0 -> 0.5), mean gap %: alns 7.52 -> 0.95, lns 7.31 -> 1.60, grasp 13.53 -> 0.52, ils 0.60 -> 0.26, vns 0.50 -> 0.58; worst instance gap: alns 49.7 -> 3.9, grasp 68.5 -> 1.4. Indicative only (one seed).
2. **`--depot-mode race`** (`heuristics.DepotRace`): the arms are the `--depot-sample` best depot sets of the p-median bound; the budget is allocated by stride scheduling with the weight `1/(rank+1)^gamma` (`--race-gamma`, default 2) corrected by `exp(-5 * excess)` once an arm has >= 2 pulls, and every `--race-explore`-th pull (default 8) goes to the best-ranked arm not pulled yet. Prior: the best-known depot set has p-median rank 1 for 53 of 72 instances, <= 5 for 69, 26 for one (`reference/pmedian_rank_of_published_depot_sets.csv`).
   A first version (successive halving on the best of single pulls) was rejected after a diagnosis on coordP111112: one block is too noisy (7-12 % above BKS) and the rank-1 set was eliminated after two pulls although ILS restricted to it reaches 2.1 % in 90 s.
   Scale test (ILS and ALNS, coordP111112 and coord200-10-1, 90 s, 2 seeds, mix 0.5), mean gap %: pm rotation 4.80, halving race 2.88, rank-prior race 1.31. Note: the rank-prior design was chosen after looking at coordP111112, so that instance is not an independent test.
3. **`--sp-share s`** (`route_pool.py`, default 0): the last share s of `--time-limit` is used to solve a set-partitioning MILP over the routes of all local optima within `--sp-theta` (3 %) of the best and of all new incumbents (at most K routes, at most p depots, HiGHS through scipy.optimize.milp). The incumbent's routes are always columns, so the result is never worse; without scipy the step is skipped and `sp_status = no_scipy` is recorded. New columns in summary.csv: `sp_status, sp_cols, sp_s, sp_improved, sp_obj`.
   Same scale test with the SP polish (s = 0.15): 1.31 -> 0.95; it improved 5 of 8 runs (ILS more often than ALNS), never exceeded the budget (SP time 0.0-8.3 s).
* Tests: `tests/test_search_v05.py` (11 tests: q = 0 identical, mixed starts feasible, race prior/exploration/robustness to one bad block, reproducibility, SP never worse and feasible, missing scipy, end-to-end runner flags + verify_run). Whole suite: 120 tests OK, 1 skipped.
* Not yet evaluated on the cluster; not part of any campaign result of v0.4.2. To reproduce v0.4.2 runs: `--start-mix 0 --depot-mode pmedian --sp-share 0`.

## v13.0-llrp.0.4.2 (2026-11-08) — Python lookup without the `conda` command

* First P20 submission on the cluster: all six arms stopped with "no Python >= 3.10 found" because `~/miniconda3/bin/conda` does not exist there, so `conda activate` could not work on the nodes.
  `hpc/pyenv.sh` now first scans the conda-style folders for a ready interpreter (`$LLRP_PYTHON`, `~/miniconda3/envs/*/bin/python3`, `~/anaconda3`, `~/miniforge3`, `~/mambaforge`, `~/.conda`, `/opt/*conda*`) and uses its full path (`PYTHON`); the `conda activate` route is only the fallback.
* Observed on the cluster (SGE): a finalize job that exits with code 100 goes to the error state `Eqw`, which is what keeps the next stage held (the design assumption of v0.4 is confirmed).
* `tests/smoke_shards.sh`: pyenv scan without a conda command, `LLRP_PYTHON` override.

## v13.0-llrp.0.4.1 (2026-11-08) — the cluster scripts no longer depend on the submitting shell

* Reason: on the project cluster the login shell has no `~/.bashrc`, conda is not on PATH and there is no system `python3`; v0.4 relied on `conda activate` in the shell and on `qsub -V` to carry it to the nodes.
* `hpc/pyenv.sh` (sourced by `run.sh`, `finalize.sh` and the driver): if `python3` >= 3.10 is not on PATH it finds conda (`CONDA_SH`, `~/miniconda3`, `~/anaconda3`, `~/miniforge3`, `/opt/*conda*`) and activates the first environment with Python >= 3.10 (`CONDA_ENV`, `llrp_env`, `clrp_env`, `base`, others). No-op when Python is already fine.
* Stage settings go to `<stage folder>/stage.env`, which the arm and finalize jobs source (`qsub -v STAGE_ENV=<file>`); `qsub -V` is gone (no inherited environment, no exported shell functions in the job environment).
* `hpc/start.sh [STAGE ...]` (renamed from `baslat.sh` in the public release) = `SUBMIT=1 STAGES=... bash hpc/submit_llrp_campaign.sh` (default P20).
* `tests/smoke_shards.sh` extended: arm started from `STAGE_ENV` in an empty environment (`env -i`), pyenv with a fake conda (found / not found), `stage.env` contents, no `-V`, `start.sh`.
* No change to any algorithm or to `llrp_framework/`; VERSION only identifies the scripts.

## v13.0-llrp.0.4 (2026-11-07) — staged, sharded HPC campaign (scripts only; no change to any algorithm)

* **`hpc/run.sh` accepts `SHARD=i/N`.** Every arm builds the same full job list, writes it atomically as the stage manifest `jobs.txt` and runs only its share:
  arm = (position of the (instance, method) pair in the list + seed) mod N (Latin square). Checked on the real stage lists (17 methods, 30 seeds, N = 6):
  every arm gets exactly 340 / 680 / 1020 / 510 runs (P20 / P50 / P100 / P200), and every (instance, method) pair runs exactly 5 times on each arm,
  so no method is tied to one node. (Plain `job index mod N` would have tied every P100 pair to a single arm, because 12 x 17 = 204 is a multiple of 6.)
  A sharded arm does not collect or verify; it writes the marker `shards/arm_<i>of<N>.txt` (state, host, CPU, manifest hash, failed / missing counts) and `methods_used.txt`.
  Without `SHARD` the launcher behaves as before (`tests/smoke_hpc.sh` unchanged).
* **`hpc/finalize.sh`** closes a stage: all arm markers present and done, same manifest hash, shares add up to the manifest, `collect.py`, `verify_run.py` (manifest + re-evaluation of every stored solution),
  `tools/stage_table.py`, `tools/rank_stats.py`; writes `FINALIZE_OK` or `FINALIZE_FAILED` with the reasons.
* **`hpc/submit_llrp_campaign.sh`** (dry run by default; `SUBMIT=1` submits): per stage one SGE array job of ARMS tasks (`-t 1-6 -pe smp 15`), a finalize job held on it,
  and the next stage's arms held on that finalize job (`-hold_jid`), so P20 -> P50 -> P100 -> P200 run in order. Gate: a failed finalize exits with code 100 (error state) and the next arms refuse to start without `FINALIZE_OK`.
  Prints the run counts and the cost estimate. `hpc/campaign_arm.sge`, `hpc/campaign_finalize.sge` are the job scripts.
* New `tools/stage_table.py` (per-method mean gap, best gap, hits, time-to-best, trials, passes, budget overrun).
* `tests/smoke_shards.sh` (about 10 s): partition / balance / rotation of the shares, concurrent manifest writes, finalize gates, resume, arm gate, submit chain with a stub `qsub`.
* The stale CLRP remark "decide the invocation policy" was removed from the method tables: the kit has no such switch (local search is called inside each method).
* Test suite: 109 tests, 1 skipped (unchanged); `tests/smoke_hpc.sh` and `tests/smoke_shards.sh` pass.

## v13.0-llrp.0.3 (2026-11-07) — method set curated for the LLRP paper (the CLRP set is a guide, not a constraint)

* **GRASP+PR excluded** (`EXCLUDED_HEURISTICS`, still runnable with `--allow-excluded`; removed from all `hpc/methods_*.txt`). In a 10 s run it finishes only ~1.3 of the 10 depot subsets,
  so the first random subset decides the result: mean gap 9.67 % on P20 versus <= 1.90 % for every other campaign method. 17 campaign methods remain (19 registered; `rtr` is also excluded).
* **Ruin size of ALNS / LNS / IG** (`heuristics._destroy_size`, `--destroy-mode fixed|range|floor`). The fixed 0.2 n removes only 4 customers at n = 20 and cannot leave local optima that are optimal for every
  ruin set of up to 5 customers (`tools/ruin_neighbourhood_probe.py`). New default for ALNS and LNS: `floor` = max(7, round(0.2 n)), identical to the old rule for n >= 35 (so P50+ results are unchanged by construction);
  IG keeps `fixed`. `--destroy-mode fixed` reproduces the previous behaviour exactly. Evidence (P20, 5 s, 5 seeds, 4 instances, loffler9): mean gap ALNS 2.61 -> 1.11 %, LNS 2.55 -> 0.41 %;
  BKS hits ALNS 7 -> 15 / 20, LNS 9 -> 15 / 20. The `range` rule (Ropke and Pisinger style, q in [max(4, 0.1 n), 0.4 n]) was as good at n = 20 but worse in the time-starved screening at n = 100 (30 s: ALNS 5.6 -> 10.0 %), where its larger removals reduce the number of depot subsets visited; it stays opt-in.
* Test suite: 109 tests, 1 skipped.

## v13.0-llrp.0.2 (2026-11-07) — decisions of the first review

* **Repairs with fleet look-ahead (ALNS / LNS / IG, greedy and regret-2).** `heuristics._repair_core` keeps a best-fit-decreasing (BFD) certificate
  of the unplaced customers: a move is taken only if the others still pack into the residual capacities of the routes and of the unused vehicles;
  if no cheap move keeps the certificate, the largest unplaced customer is placed in its BFD bin (`_bfd_move`), so a certified repair cannot dead-end.
  Repairs without a certificate, or with a vehicle for every unplaced customer, behave as before. The fast (`_InsertionTable`) and the reference
  (`_RefState`) providers share the loop, `tests/test_repair_cache.py` still shows identical results and effort counters.
  Measured on 100-5-1 (K = 24, BFD needs 25): success of 90 repairs on a K-route solution 56/90 -> 90/90; 180/180 on 100-5-1, 131122, 50-5-2, 200-10-1, 20-5-1; cost per repair unchanged (1.8 ms vs 2 ms).
* **Depot-subset policy:** `--depot-mode pmedian` stays the default; new `tools/pmedian_rank_study.py` shows that the depot set of 73 published best solutions is the p-median
  best set in 53 cases and never ranks worse than 26 among C(m,p) > 50 sets (`reference/pmedian_rank_of_published_depot_sets.csv`). For C(m,p) <= `--depot-sample` it equals `enumerate`.
* **Local-search preset:** `first / loffler9` (decision of the project owner); table `hpc/methods_phaseB_loffler9.txt`. Note: it contains no intra-route 2-opt.
* Test suite: 108 tests (new: repairs do not dead-end on 100-5-1), 1 skipped.


## v13.0-llrp.0.1 (2026-11-07) — first LLRP release, ported from the CLRP kit `clean.6.4.0_adaptive`

This is a **new kit**. It is not the earlier Desktop\APP\LLRP kit; results of the two must not be mixed.

### Problem / evaluation
* `core.py`: objective = sum of customer arrival times, no return arc (`_route_latency`, `route_latency`, `arrival_times`);
  aliases `_route_distance` / `route_distance` point to the latency so unchanged callers follow automatically.
* `read_instance(path, profile='llrp', depot_capacity='ignore')`: real Euclidean distances for all families, open cost = 0, vehicle cost = 0,
  depot capacity = total demand unless `enforce`.
* `K` (fleet) and `p` (open depots) are binding "at most" bounds, read from `reference/LLRP_reference.csv` (`--K`, `--p` override).

### Search
* `construction.py`: latency insertion deltas; fleet look-ahead (lazy best-fit-decreasing); packing-first fallback (`pack_construct`).
* `neighborhoods.py`: `_len` is latency (bit-identical to `core._route_latency`); all delta-evaluating scans are objective-agnostic and unchanged.
* `heuristics.py`: `--depot-mode pmedian` (new default) with a numpy-independent ranking; random-key decoder chooses h in {1..p} depots.
* `depot_structural631.py` / `depot_adaptive64.py` / `depot_impact.py`: kinds `swap`, `swap2`, `open` (no `close`, no `merge_swap`), p-median-bound ranking, `pack_rebuild` instead of the CLRP assignment MILP.
* CLRP halving / MILP depot layers: not ported (`depot_layer.py` is a stub, `--depot-layer none` only).

### Infrastructure
* `params.py` loads the 76-instance registry (groups P20, P50, P100, P200, B, T, T100, T150, T200, ALL).
* `data/`: Tuzun-Burke 36, Prodhon 30, Barreto 10 (B pruned to the LLRP files); `SHA256SUMS` regenerated.
* `tools/indep_check.py` (new), `tools/ls_ablation.py`, `tools/polish_report.py`, `collect.py`, `verify_run.py` updated to the registry and tolerance 0.01.
* `hpc/run.sh` default group `ALL`; `hpc/pilot64.sh` uses `hpc/methods_pilot_adaptive.txt`.

### Tests
`python3 -m unittest discover -s tests` — 107 tests, 1 skipped (published-solution reproduction needs `LLRP_PUBLISHED_DIR`).
`tests/testlib.py` replaces the CLRP golden-file loader (CLRP golden results do not apply to LLRP).

### Known limitations (open)
1. (closed in 0.2) repair operators now have the BFD-certified fleet look-ahead.
2. 3-second smoke on `20-5-1` showed GRASP+PR / IG / scatter / SA / TA / tabu clearly weaker than ALNS/GRASP; not investigated yet (smoke only, no statistics).
3. CLRP presets are kept for parity: `loffler9` has no intra-route 2-opt (route direction matters in LLRP); `hgamp`, `light`, `common5` do. An LLRP-specific preset has not been decided.
4. Published RLHEA solution files: three do not reproduce the table (`112222`: customers not served exactly once; `Or_117_14`: the file is empty (0 bytes); `131122`: latency 38761.9 vs BKS 4870.82); `122122` is off by +4.0e-5 relative.
5. No computational campaign has been run yet (by design: awaiting approval of time estimates).
