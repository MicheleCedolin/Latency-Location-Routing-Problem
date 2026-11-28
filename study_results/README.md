# Study results (ITOR manuscript)

Raw result files of the runs reported in the manuscript. Everything here was produced with the scripts in [`../cpp`](../cpp) on an SGE cluster
(one node, one process per seed, 30 seeds `1..30`, Intel Xeon E5-2698 v3 @ 2.30 GHz, see `env.txt` of each archive); nothing was edited by hand. Host names and account paths were replaced by `user` / `login-node`.
Directory trees are the standard output of `run_final.sh` / `run_extended.sh`: `<family>/<tag>/{run,routes,ops,trace,summary}.csv`, `summary.txt`, `env.txt` (flags, budget, binary / manifest SHA-256, node).

| Archive | Content | Runs |
|---|---|---|
| [`final_1x_tuned.tar.gz`](final_1x_tuned.tar.gz) | **Final evaluation, 1x budget.** Tuned flags (`cpp/irace/best.flags`, irace configuration 267), CPU limit `max(5, 0.3 n)` s per run, 76 instances x 30 seeds. Tag `tuned`. Also `final_progress.log` and `replay_check_tuned.txt`. | 2280 |
| [`ext10_tuned.tar.gz`](ext10_tuned.tar.gz) | **Extended budget "ext10".** Same flags, seeds and binary; CPU limit `3 n` s = 10x the 1x budget; the 58 instances with `n >= 75` (list: [`cpp/ext10_instances.txt`](../cpp/ext10_instances.txt)). Tag `ext10`. Written by `cpp/run_extended.sh`. | 1740 |
| [`depot_tuned.tar.gz`](depot_tuned.tar.gz) | **Depot-aware diversification** (stage 3): the base method plus `--dpm-rank 10,0.25 --dpm-prune` (`cpp/stages/2_depot.flags`, also `flags_V1.txt` inside), ext10 budget `3 n` s, the 57 instances with `n > 75` x 30 seeds (the instances of `b1_tuned.tar.gz`; control: `ext10_tuned.tar.gz`). Built with `llrp_fast` v6 (see `env.txt` inside); the current engine of this repository reproduces its runs (replay, see the main README). `Algorithm` column: `V1`. Per family: `run`, `routes`, `trace`, `ops`, `dpm` (log of the depot-set draws) and `verify.txt` (independent verification of every run); the per-iteration log (about 70 MB) is not included. | 1710 |
| [`b1_tuned.tar.gz`](b1_tuned.tar.gz) | **B1** (V1 depot layer + run-internal route pool, exact DP and set partitioning), ext10 budget `3 n` s **including** the set-partitioning time, 57 instances with `n > 75` x 30 seeds. Built with `llrp_fast` v7 (see `env.txt` inside; flags in `flags_B1.txt`); the current engine of this repository reproduces its runs (replay, see the main README). `Algorithm` column: `B1`. | 1710 |
| [`memetic_tuned.tar.gz`](memetic_tuned.tar.gz) | **Exploratory memetic phase** (Appendix F): the final method plus the three-parent edge assembly crossover phase (`cpp/stages/4_memetic.flags`, `--eax-split 0.4`), ext10 budget `3 n` s **including** the set-partitioning time, the same 57 instances x 30 seeds as `b1_tuned.tar.gz`; three campaigns (pilot, extension, remaining 14 instances; see [`../analysis/memetic`](../analysis/memetic)). Built with `llrp_fast` v9 = `cpp/src/llrp_fast.cpp`. `Algorithm` column: `B1_eax40`. Per family: `run`, `routes`, `trace`, `ops`, `pool`, `dpm`, `eax_summary` (counters of the memetic phase) and `verify.txt` (independent verification of every run); the per-generation log is not included. | 1710 |
| [`atmost_50-5-2BIS-5.tar.gz`](atmost_50-5-2BIS-5.tar.gz) | **`--atmost` check** on Prins `50-5-2BIS-5` (tuned flags + `--atmost`, 1x budget, 30 seeds, [`cpp/irace/atmost.flags`](../cpp/irace/atmost.flags)): 30/30 runs reach 945.45187 = BKS. | 30 |
| [`irace_logs.tar.gz`](irace_logs.tar.gz) | irace 4.5.1 log of the tuning run (3000 experiments, 17 training instances, seed 1): `irace/irace_stdout.txt`, `irace/trlog.txt`, `irace/best.flags`, scheduler log. | - |

## Headline numbers (mean over instances, gap in % to the BKS of [`../bks/LLRP_BKS.csv`](../bks/LLRP_BKS.csv))

| Budget | Family | Instances | gap of best run | gap of mean | mean CPU per run [s] |
|---|---|---|---|---|---|
| 1x | Barreto | 10 | 0.001 | 0.531 | 18.9 |
| 1x | Prins | 30 | 0.184 | 0.808 | 29.4 |
| 1x | Tüzün–Burke | 36 | 0.426 | 1.930 | 46.7 |
| ext10 | Barreto (n >= 75) | 4 | -0.000 | 0.365 | 320.2 |
| ext10 | Prins (n >= 75) | 18 | 0.065 | 0.445 | 401.1 |
| ext10 | Tüzün–Burke | 36 | 0.169 | 0.684 | 452.3 |

These are the `ALL` rows of the `summary.txt` files (the Prins 1x row is recomputed with the `--atmost` runs of `50-5-2BIS-5`, as in the manuscript, see `bks/compare_published.py`); the ext10 rows cover only the instances in the extended list and are therefore not comparable with the 1x rows of the same family.
A negative gap means that the BKS was improved.

## How to inspect or re-check

```bash
mkdir -p /tmp/study && tar xzf final_1x_tuned.tar.gz -C /tmp/study             # -> /tmp/study/results_final/{barreto,prins,tuzun}/tuned/
cd ../cpp && ./build.sh
bin/llrp_tools summarize /tmp/study/results_final/prins/tuned/run.csv --manifest manifest.tsv --train selection/train.txt     # same table as summary.txt
bin/llrp_tools check-csv /tmp/study/results_final/prins/tuned                  # headers / columns
```

* Cost and route data (`run.csv`, `routes.csv`) are what the manuscript tables are computed from; `trace.csv` is the anytime trace (best cost after each iteration), `ops.csv` the operator counters.
* The runs were time-limited. A time-limited run is reproduced exactly with `--max-iter <iterations>` (the `iterations` column of `run.csv`, same seed, same flags): `replay_check_*.txt` lists the sample runs that were re-created this way (`OK` = identical cost; 10 of 10 for the 1x set, 10 of 10 for ext10, 1 of 1 for the `--atmost` set).
  The scripts also verify every run independently with `llrp_tools verify` while the job is running (`VERIFY=1`); those per-run files are not part of the archives, but `bin/llrp_tools verify INSTANCE.inst PREFIX` can be run on any run you re-create.
* **Binary.** The result files of the base method were produced by the v4 build (`binary_sha256` in `env.txt`); `atmost_50-5-2BIS-5` by v5 (the flag `--atmost`), the depot campaign by v6, the route-pool campaign by v7 and the memetic campaigns by v9.
  The engine of this repository is v9: without stage flags it is the base method, and replaying a sample of runs of each archive with it reproduces their objective values (see the main README, section "Link between archives and source"; CI replays the archives of stages 2 to 4).
  Compare results only for the same compiler and flags; bit-identity across CPUs or compilers is not guaranteed.
* `--atmost` allows fewer than `Ng` open depots (the problem definition says *at most* `Ng`); it was needed only for `50-5-2BIS-5`, where `--atmost` gives the BKS 945.45.
