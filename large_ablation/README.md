# Large-instance extension of the component analysis (Base+SO vs. Base+SO+DS)

Purpose: run Base+SO and Base+SO+DS on Prins and Tuzun instances with n >= 100
(about 12 stratified instances, or all 66 Prins and Tuzun instances) to check
whether the component effects seen on the smaller instances carry over.

This folder contains a resumable, parallel runner that executes exactly these two
configurations with the **unmodified** algorithm modules used in the
component (ablation) analysis of the Python GRASP-VND implementation.

| Config  | Label        | Module (`code/`)   | Description                                   |
|---------|--------------|--------------------|-----------------------------------------------|
| `SO`    | Base+SO      | `VND0SO.py`        | 5-neighbourhood VND + strategic oscillation   |
| `SO_DS` | Base+SO+DS   | `VND0SOdepot.py`   | `SO` + depot-swap (DS) perturbation           |

The only difference between the two modules is the function
`depot_swap_perturbation` and its call at the start of every VND pass
(`diff code/VND0SO.py code/VND0SOdepot.py`).

## Protocol (identical to the main experiments)

* 30 independent runs per (instance, configuration); seeds `0..29`,
  `run_id = seed + 1`, `random.seed(seed)` and `numpy.random.seed(seed)`.
* `I_max = 50` GRASP iterations, RCL size 5, diversification/intensification
  cycle 5 + 3 (as implemented in the modules).
* Single-threaded runs (BLAS/OpenMP threads forced to 1), one run = one job.
* The same seed is used for both configurations (paired design).
* Recorded time: wall-clock (`perf_counter`) **and** process CPU time.

## Instance selection (stratified, reproducible)

Candidate pool: all 54 instances with n >= 100 (Prins 18, Tuzun 36).
One instance is drawn per stratum with `numpy.random.RandomState(2026)`:

* Prins: strata (n, |depots|, Q) = {100-5, 100-10, 200-10} x {Q=70, Q=150} -> 6
* Tuzun: strata (n, |depots|) = {100, 150, 200} x {10, 20 depots} -> 6

`python run_large_ablation.py select` regenerates `selected_instances.csv`
(and `candidates_n100plus.csv`). Any other set can be used with
`--instances A,B,...`.

## Requirements

Python >= 3.6, `numpy`, `pandas`, `openpyxl`, `numba`, and `scipy` (only for
`analyze`). Place the instance workbooks in `data/` and the two modules in
`code/` (already included).

## HPC functional test (time-limited, run this first)

```bash
nohup bash hpc_test.sh > hpc_test.log 2>&1 &      # WORKERS=24 LIMIT_MIN=40 by default
tail -f hpc_test.log
```

Stages: (1) environment check and smoke test, (2) `calibrate`: all 12 instances
x 2 configurations, seed 0, 5 iterations (24 jobs, about 15-25 min), which
prints the extrapolated core-hours for the real experiment, (3) optional
(`FULL_PIPELINE=1`) short `run -> aggregate -> analyze` test. No new job is
started after `LIMIT_MIN` minutes; running jobs may continue for `GRACE_MIN`
minutes and are then terminated. The same options exist on the command line
(`--time-limit-min`, `--grace-min`) for `run` and `calibrate`. Results of an
interrupted `run` are kept and resumed by repeating the command. An output
directory is bound to its settings: existing results with other
`--iters`/`--rcl` values are refused, never overwritten.

## Full experiment: all Prins and Tuzun instances, staged

`bash run_full.sh` runs Base+SO and Base+SO+DS on **all 66 Prins and Tuzun
instances** (the Barreto instances are covered by the earlier ablation), 30
seeds x 50 iterations, in five stages (`selected_all.csv`, column `Stage`):

| Stage | Instances                      | Count |
|-------|--------------------------------|-------|
| 0     | Prins n=20, 50                 | 12    |
| 1     | Prins and Tuzun n=100          | 24    |
| 2     | Tuzun n=150                    | 12    |
| 3     | Prins n=200                    | 6     |
| 4     | Tuzun n=200                    | 12    |

A stage is finished before the next one starts; inside a stage every instance
is completed (30 paired runs per configuration) before the next one, so each
finished instance is immediately usable. The runner keeps a continuous job
queue (no idle workers between instances).

```bash
setsid nohup bash run_full.sh > run_full.log 2>&1 &     # start (WORKERS=30 by default)
bash status.sh                                          # progress, per-stage ETA, errors
python3 run_large_ablation.py aggregate --out results_full   # interim tables, any time
python3 run_large_ablation.py analyze   --out results_full   # interim statistics
```

* Crash/restart safety: `run_full.sh` restarts the runner up to 10 times while
  jobs are pending; after a reboot start the same command again.
* Interim tables are refreshed hourly (`results_full/aggregated/`).
* `plan`/`status.sh` print per-stage remaining core-hours; the estimate uses
  measured runs first, then `calibration.csv`, then a power-law fit.
* `analyze` reports, besides the paired tests, in how many runs DS changed
  nothing (identical latency to SO for the same seed) and only includes
  instances with 30 feasible pairs in Holm / the instance-level test.

## Quick start

```bash
python tests/test_smoke.py                                   # ~1 min, checks the environment
python run_large_ablation.py select
python run_large_ablation.py calibrate --workers 8 --iters 10   # firms up the time estimate
python run_large_ablation.py run --workers 30                   # prints the plan only (dry)
nohup python run_large_ablation.py run --workers 30 --yes > run.log 2>&1 &
python run_large_ablation.py plan --workers 30                  # progress at any time
python run_large_ablation.py aggregate                          # tables (CSV; --xlsx for workbooks)
python run_large_ablation.py analyze                            # paired SO vs SO+DS statistics
```

`run` without `--yes` never starts a computation. Jobs are ordered
longest-first inside three seed waves, so an interrupted experiment still
contains complete paired blocks of seeds. Re-running the same command resumes:
finished runs (`results_large/raw/<config>/<instance>/seed_XX.json`) are
skipped, results are written atomically.

## Outputs (`results_large/`)

* `raw/<config>/<instance>/seed_XX.json` - run summary, 50 iteration logs,
  best routes (one file per run).
* `aggregated/run_level.csv`, `iteration_level.csv`, `best_routes.csv`,
  `summary_by_instance_config.csv`, `analysis_SO_vs_SO_DS.csv`.
* `environment_<timestamp>.json` - host, CPU, Python/numpy/pandas/numba
  versions, SHA-256 of the modules and workbooks, command-line arguments.
* `progress.log`, `calibration.csv`.

Run-level columns follow the earlier runners (`Instance`, `Algorithm`, `Run`,
`Seed`, `Feasible`, `Total Latency`, `CPU Time`, `Open Depots`,
`Number of Routes`) plus `Config`, `Wall Time (s)`, `BKS/Reference`,
`Gap (%)`, `Feasible (independent)`, `Latency (independent)`.

## Built-in verification

After every run the solution is re-checked **independently of the algorithm
code** (coverage of every customer exactly once, capacity, at most Nv routes,
exactly Ng open depots, and recomputation of the total latency from the
coordinates). `aggregate` reports any run that fails this check or whose
latency disagrees with the module's value. The module label
`GRASP-VND0-SO-LLRP` is hard-coded in both modules; the runner overwrites it
with `GRASP-VND0-SO` / `GRASP-VND0-SO-DS` in the logs so the two
configurations cannot be confused.

## Statistics (`analyze`)

Per instance: paired Wilcoxon signed-rank over the 30 seeds (both
configurations feasible), Holm correction across instances. Across instances:
paired Wilcoxon on instance means, rank-biserial effect size, and a bootstrap
(10,000 resamples, seed 2026) 95 % CI for the mean improvement of DS over SO.
The run-level CSV keeps the column schema of the earlier runners, so other analysis
scripts can read it as well.

## Runtime estimate (to be confirmed with `calibrate`)

Extrapolated from the published Barreto runs (mean CPU time per run, 30 runs):

| n   | Base (VND0) | Base+SO | Base+SO+DS |
|-----|-------------|---------|------------|
| 50  | 71.8 s      | 81.1 s  | 79.8 s     |
| 75  | 219.8 s     | 299.0 s | 295.8 s    |
| 100 | 574.1 s     | 763.0 s | 752.6 s    |
| 134 | 1574.2 s    | 1917.3 s| 1937.9 s   |

A log-log fit gives CPU time ~ n^3.3 for all three variants, SO costs about
1.2x Base, and DS adds no measurable overhead on these instances
(DS/SO = 0.99). With 6 instances at n=100, 2 at n=150 and 4 at n=200 this
yields roughly **400-700 core-hours (central estimate about 600)**, i.e.
about 13-22 h wall-clock on 32 single-threaded workers. The extrapolation ignores differences
in the number of routes (Prins n=200, Q=70 needs about 49 routes), which may
increase the cost of inter-route neighbourhoods; hence `calibrate` should be
run on the target machine before the full experiment.
