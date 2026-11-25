# `llrp_fast` — GRASP + RVND engine for the LLRP (C++)

Fast C++ implementation of GRASP with RVND for the **Latency Location-Routing Problem** (LLRP), together with the tooling for experiments: family-wise experiment runner, leave-one-out / add-one-in ablation, automatic parameter tuning with
[irace](https://mlopez-ibanez.github.io/irace/), independent solution verification and statistical summaries.

* **Everything is C++11** (`g++ >= 4.8`). No Python and no R are needed to build, test and run experiments; R + irace are needed only to re-run the tuning.
* 76 benchmark instances in three families (Barreto 10, Tüzün–Burke 36, Prins 30), see [`../README.md`](../README.md#benchmark-instances).
* Every solution can be re-evaluated by an independent verifier (`llrp_tools verify`) and every move evaluation can be cross-checked against a full recomputation (`--check`).

## 1. Quick start

```bash
./build.sh          # bin/llrp_fast (solver) + bin/llrp_tools (analysis / orchestration);  -O3 -ffp-contract=off, no -march=native
./selfcheck.sh      # a few seconds on one core: --check, independent verifier, corrupted-file rejection, determinism, run_config/merge, irace dry run, --atmost
                    # it must end with "SELFCHECK: ALL OK" before you start a long run

# one short run on one instance
bin/llrp_fast --instance inst/barreto/Ch50-5.inst --seed 1 --ops full --so --ds --max-iter 100 --out /tmp/ch50
# a small experiment: 4 seeds on two instances, results in results/custom/full3/
FAMILY=custom NPROC=4 PIN=0 MAXITER=100 STALL=0 ./run_config.sh full3 Ch50-5 Gaskell21-5
```

Compilers: tested with g++ 13 (Ubuntu 24.04, run by the GitHub Actions workflow of this repository) and with g++ 4.8.5 (CentOS 7, the HPC cluster the study was run on).
The code compiles cleanly with `-std=c++11 -pedantic-errors` and with clang; it uses no C++14 features and no `<regex>`.

## 2. Contents

| Path | Content |
|---|---|
| `src/llrp_fast.cpp` | Solver (v5): GRASP + RVND, 14 operators, strategic oscillation (SO), depot swap `ds`, stopping rules, per-operator CPU / benefit counters; optional `--atmost` (at most `Ng` open depots) and `--gran D` (granular neighbourhoods, experimental) |
| `src/llrp_tools.cpp` (+ `cmd_*.hpp`, `tools_*.hpp`) | Tools: `manifest select merge check-csv summarize compare ablation calibrate verify workbook irace-gen irace-flags irace-sample selftest wilcoxon` (`bin/llrp_tools` prints the usage) |
| `inst/{barreto,tuzun,prins}/*.inst` | The 76 instances in one text format (see below) |
| `manifest.tsv` | Per instance: n, m, Q, Nv, Ng, BKS, total demand, tightness, size class, flag |
| `selection/` | `train.txt` (17 irace training instances), `test.txt` (the remaining 59), `selection.tsv` |
| `run_config.sh` | Runs one configuration on one family (or `train` / `test` / `all` / `custom`), one process per seed |
| `run_ablation.sh` | FULL + leave-one-out + add-one-in, one result directory per family |
| `run_irace.sh`, `irace/` | irace scenario, parameter file (27 parameters), `target-runner`, initial configurations, `best.flags` (tuned configuration) |
| `run_final.sh` | Final evaluation: tuned configuration on all instances x 30 seeds with the irace CPU-time budget, verified and replay-checked |
| `run_extended.sh`, `run_extended.sge`, `ext10_instances.txt` | Extended-budget evaluation (same flags, seeds and binary as `run_final.sh`, other instance list and CPU budget): the study's "ext10" setting = 10 x the 1x budget on the 58 instances with n >= 75; optional node-local scratch directory (`SCRATCH=1`) |
| `irace/atmost.flags` | `irace/best.flags` + `--atmost` (used for Prins `50-5-2BIS-5` only) |
| [`../study_results/`](../study_results) | Raw result files of the study (1x and ext10 final evaluation, `--atmost` check, irace log) |
| `irace_dryrun.sh` | Exercises the target-runner chain without irace |
| `*.sge`, `setup_irace_env.sh` | Job scripts for an SGE cluster and a root-less R + irace installation (micromamba) |
| `data/` | `timing_probe_20it.tsv` (CPU time of 20 iterations on every instance), `inst_validation_published_solutions.txt` |

### Instance format (`*.inst`)

```
LLRP_INSTANCE 1
name Ch50-5
n 50                # customers
m 5                 # candidate depots
Q 160.0             # vehicle capacity
Nv 6                # at most Nv routes
Ng 2                # at most Ng open depots
bks 1661.64         # best-known latency (see ../bks)
depots              # m lines:  x y
...
customers           # n lines:  x y demand
...
```

Distances are Euclidean (computed identically in the solver and in the verifier), the objective is the sum of customer arrival times, vehicles do not return to the depot,
depot capacities are not enforced (as in the literature). The Tüzün–Burke files carry the full-precision decimal coordinates of the published instances;
`check_inst_data.sh` (called by `run_config.sh`, `run_final.sh`, `run_irace.sh`) verifies this before any run starts (skip with `SKIP_DATA_CHECK=1`).

## 3. Running a configuration (family-wise)

```bash
FAMILY=barreto ./run_config.sh full1     # 13 operators (without ds), classic (improving moves only)
FAMILY=barreto ./run_config.sh full2     # the same 13 operators + SO
FAMILY=barreto ./run_config.sh full3     # 13 + ds = 14 operators, SO
FAMILY=prins   ./run_config.sh full3
FAMILY=tuzun   ./run_config.sh full3
FAMILY=custom  ./run_config.sh trial Ch50-5 P113212-10                 # selected instances only
FLAGS_FILE=irace/best.flags FAMILY=all ./run_config.sh tuned           # tuned parameters on all instances
```

Each seed is a separate process (`NPROC` = number of seeds, seeds `SEED0 .. SEED0+NPROC-1`, optionally pinned to its own core: `PIN=1`, `CPUS="0-29"`).
Results go to `results/<family>/<name>/`: `run.csv, routes.csv, ops.csv, trace.csv, iter.csv, summary.txt, env.txt`; per-run files are in `runs/`, an interrupted job resumes where it stopped
(`run.csv` of a run is written last and marks it as complete).

**Termination.** Stop after `STALL=300` consecutive non-improving GRASP iterations, hard cap `MAXITER=1000`, optional CPU limit `TLIMIT` (seconds).
`run.csv` column "Stop Reason" is `stall | max_iter | time`. The stall rule is used only by the iteration-limited `run_config.sh` experiments; the runs of the study are CPU-time limited (`run_final.sh`, `run_extended.sh`).

```bash
bin/llrp_tools summarize results/barreto/full3 --manifest manifest.tsv --train selection/train.txt
bin/llrp_tools compare results/barreto/full2 results/barreto/full3          # paired (instance, seed); Wilcoxon, bootstrap CI
bin/llrp_tools workbook results/barreto/full3 -o barreto_full3.xlsx          # optional Excel workbook
bin/llrp_tools verify inst/barreto/Ch50-5.inst results/barreto/full3/runs/Ch50-5_s0     # independent verification
```

`routes.csv` lists the open depots and the chosen routes (depot, customer sequence, arrival times, load, route latency); `run.csv` lists the open depot set of every run.

## 4. Operator ablation

*The ablation tooling is provided for completeness; the manuscript reports no ablation result (it lists an ablation of the base method among its limitations and future work).*

```bash
PLAN_ONLY=1 FAMILY=prins ./run_ablation.sh       # plan + time estimate
FAMILY=barreto ./run_ablation.sh                 # asks for confirmation (YES=1 skips it); MODE=loo|add|all
bin/llrp_tools ablation results/ablation/barreto --train selection/train.txt
bin/llrp_tools ablation results/ablation/barreto results/ablation/prins results/ablation/tuzun --out results/ablation/all
```

Configurations: `FULL` (14 operators), `LOO_<op>` (FULL − op; 14), `BASE` (`relocate,swap11,2opt`), `ADD_<op>` (BASE + op; 11); all with SO, **fixed horizon `MAXITER=300`, `STALL=0`**
(the same iteration horizon, so "equal iterations" and "equal CPU" comparisons can be made from the anytime trace), 30 seeds.
The report has six parts: (1) configuration summary; (2) LOO: Δ = gap(FULL − op) − gap(FULL) (**> 0 ⇒ the operator is useful**), 95 % bootstrap CI, win/tie/loss per instance,
Wilcoxon signed-rank test on (instance, seed) pairs with Holm correction, ΔCPU; (3) ADD; (4) operator counters in the FULL runs (calls, evaluations, applied moves, gain, CPU);
(5) equal-iteration and equal-CPU quality; (6) cost–benefit table with a decision label (`NEEDED / REMOVE / CANDIDATE: REMOVE / OPTIONAL`; the thresholds — CPU share ≥ 5 % and no proven benefit — are a modelling choice and are printed in the output);
(6b) with `--train`, the decisions are computed separately on training and test instances. CSV files are written next to the report.

**Wilcoxon rule** (zero differences are dropped; the same decision rule as scipy 1.18 `method='auto'`, differences ≤ 2·10⁻¹⁶ in 600 random cases): no ties and n ≤ 50 → exact distribution;
ties and n ≤ 13 → exact sign-flip permutation; otherwise normal approximation with tie correction and no continuity correction.

**Interpretation limits.** RNG streams of different configurations diverge after the first iteration, so (instance, seed) pairing builds blocks, not common random numbers. LOO hides interactions
(a substituting operator takes the share) — read it together with ADD. Pair-level p-values treat the seeds of one instance as independent (optimistic); the instance level is conservative.
A non-significant result is not evidence of no benefit (power).

## 5. Parameter tuning with irace and final evaluation

```bash
bin/llrp_tools irace-gen --train selection/train.txt --out irace --budget 3000 --parallel 30 --mode time --tc 30 --tmin 5   # writes the irace files and a time estimate
./irace_dryrun.sh 3                                  # target-runner chain without irace
./setup_irace_env.sh                                 # once: R + irace without root (micromamba / conda-forge)
./run_irace.sh                                       # finds the environment itself;  SGE: qsub run_irace.sge  (30 slots, one node)
bin/llrp_tools irace-flags --from-log irace/irace_stdout.txt --out irace/best.flags      # [--row k for the k-th elite]
PLAN_ONLY=1 ./run_final.sh                           # time estimate for the final evaluation (76 instances x 30 seeds)
./run_final.sh                                       # SGE: qsub run_final.sge
```

* **Parameter space (27):** 14 binary operator switches; `so`; `rcl` ∈ [2,12]; `it_div` ∈ [2,12], `it_int` ∈ [1,8] (GRASP depot cycle: diversification / intensification iterations; defaults 5/3);
  `sel` ∈ {best, first}; `ord` ∈ {random, fixed}; `ils_on` and (conditional) `ils_k` ∈ [5,60]; conditional on `so=1`: `so_win_up`, `so_win_down` ∈ [2,10] (defaults 4/4), `so_f1` ∈ [1.10, 2.00] (1.5),
  `so_f2` ∈ [2.00, 4.00] (2.5), `beta0` ∈ [0.1, 10] on a log scale (1.0). An empty pool is penalised (cost 1000). Initial configurations: 14 operators + SO; the 8-operator Zou pool + ds + SO; 13 operators classic.
* **Target:** `100·(cost − BKS)/BKS` (gap %), 1000 if the solution is infeasible. **Budget mode `time`** (default): CPU limit per run `max(TMIN, TC·n/100)` s (TC = 30, TMIN = 5) — equal CPU, so the CPU cost of an operator set counts;
  `iter` mode uses `--iters 150` iterations. `maxExperiments = 3000`, `firstTest = 5`. Tuning uses the 17 training instances only; the final evaluation is reported on all instances and separately on the 59 test instances.
* `irace/best.flags` is the configuration (irace id 267) selected by the irace run of the study (irace 4.5.1, R 4.5.3, time mode, 3000 experiments, 17 training instances, seed 1).
  The irace log (`irace_stdout.txt`, `irace.Rdata`, `trlog.txt`) is not part of the repository; `run_irace.sh` recreates it.
* The three Prins instances `50-5-2b-5`, `50-5-2BIS-5`, `50-5-2bBIS-5` were excluded from the training selection as a precaution (suspected Nv/Ng mismatch between table and code); a later check against Moshref-Javadi & Lee (2016) and Zou et al. (2024) found no mismatch.
  They belong to the test set. `selection/train.txt` is fixed; do not re-run `llrp_tools select` unless you intend to change it.
* **Final evaluation budget:** CPU limit `max(5, 30·n/100)` s per run, no iteration cap, no stall rule; the limit is checked at the end of a GRASP iteration, so a run may exceed it by at most one iteration. Seeds 1..30. Flags, budget, binary and manifest SHA-256 are stored in `env.txt`.
  A time-limited run is reproduced exactly by giving the `iterations` value of its log as `--max-iter` (`REPLAY=n` checks n sample runs automatically).
* **Extended budget ("ext10").** `run_extended.sh` repeats the final evaluation with a larger CPU limit and its own instance list, with the same flags, seeds `1..30` and binary:
  `PLAN_ONLY=1 INSTLIST=ext10_instances.txt TC=300 ./run_extended.sh` prints the time estimate; `SCRATCH=1 INSTLIST=ext10_instances.txt TC=300 TAG=ext10 OUT=results_extended10 ./run_extended.sh` runs it
  (budget `max(5, TC·n/100)` s, i.e. `3n` s for TC = 300 = 10 x the 1x budget; `BUDGET_FILE=<file with lines "instance seconds">` gives explicit budgets; `qsub run_extended.sge` submits it to an SGE queue).
  The ext10 list contains the 58 instances with n >= 75 (57 with n >= 100 plus Ch75-10).
* **`--atmost`.** The problem definition allows *at most* `Ng` open depots, while the default of `llrp_fast` opens exactly `Ng` (every earlier result was produced this way). With `--atmost` the solution is valid with 1..`Ng` open depots,
  the "force exactly `Ng`" steps are skipped and the GRASP diversification draws the number of candidate depots uniformly from 1..`Ng`; `llrp_tools verify` accepts both. Without the flag the behaviour is bit-identical to v4.
  The manuscript uses it for one instance, Prins `50-5-2BIS-5` (30/30 runs reach the BKS 945.45187; default: 949.10): `FAMILY=custom FLAGS_FILE=irace/atmost.flags TAG=atmost ./run_final.sh 50-5-2BIS-5`.

## 6. Time estimates (30 seeds = 30 cores, 2.1 GHz Xeon, from `data/timing_probe_20it.tsv`; ± 30 %)

CPU time per iteration summed over all instances of a family (full pool + SO): Barreto 0.32 s, Prins 2.54 s, Tüzün 7.89 s (training set 2.50 s).

| Job | Barreto | Prins | Tüzün | Training set (17) |
|---|---|---|---|---|
| `run_config`, one configuration, 400 iterations (stall) | ≈ 2 min | ≈ 17 min | ≈ 53 min | ≈ 17 min |
| same, 1000 iterations (cap) | ≈ 5 min | ≈ 42 min | ≈ 2.2 h | ≈ 42 min |
| ablation (27 configurations, MAXITER = 300) | ≈ 32 min | ≈ 4.3 h | ≈ 13.4 h | ≈ 4.3 h |
| irace, 3000 experiments, `time` mode | 28.9 CPU-h ≈ 58 min on 30 cores (≈ 68 min at 85 % efficiency) | | | |

Reducing the number of seeds (e.g. `NPROC=10`) does not shorten the wall time, only the number of cores and CPU-hours; to shorten it, use the training set or run the families on different nodes.

## 7. Validation and reproducibility

* `--check`: every move evaluation is compared with a full recomputation before the move is applied (mismatch → exit code 3). `llrp_tools verify` recomputes distances, arrival times, latency, load, customer partition and the number of routes/depots from the routes;
  deliberately corrupted route files (swapped order, dropped customer, wrong depot) are rejected.
* The default values of all tunable constants (`--it-div 5 --it-int 3 --so-win-up 4 --so-win-down 4 --so-f1 1.5 --so-f2 2.5 --beta0-scale 1`) reproduce the behaviour before they became flags bit for bit (`selfcheck.sh`, step 3).
* `selfcheck.sh` step 6 runs `--atmost --check` and the verifier on Prins `50-5-2BIS-5` (the default exactly-`Ng` mode is checked there as well).
* The C++ tools (`summarize`, `compare`, `calibrate`, `ablation`, `workbook`) were cross-checked against an earlier Python implementation (numerically identical, Excel cell by cell); Python is not part of this package.
* Same seed + same binary ⇒ same result. Bit-identity across compilers or CPUs is not guaranteed; `env.txt` records the binary SHA-256, node and CPU model — compare results only for the same binary.

## 8. Engine summary

* O(1) move evaluation by sub-sequence concatenation (Silva, Subramanian, Vidal, Ochi 2012); per-route forward/reversed tables are rebuilt in O(L²); every move is a "recipe" of at most six route pieces shared by evaluation and application.
* 14 operators: `relocate, oropt2, oropt3, swap11, swap21, swap22, swap31, swap32, 2opt, 2opt*, swapstar, dexch, rdepot, ds` (only `ds` changes the set of open depots). Presets: `zou` (8), `legacy5` (5), `full` (14).
* ECWA construction with O(1) merge evaluation. SO objective: latency + β·max(0, load − Q) with adaptive β; GRASP depot-set cycle of 5 diversification + 3 intensification iterations, RCL size 5.
* Granular neighbourhoods (`--gran D`, after Toth & Vigo 2003; default 0 = off): between-route moves are evaluated only if they create an edge between neighbouring customers (the `D` nearest, symmetric) or an edge at a depot;
  `swapstar` pairs are restricted likewise. This is an implemented but **untested** extension (no results are reported with it); Zou et al. (2024) use δ = 20 in their tuned setting.

## 9. Limitations

* The stall threshold (K = 300) comes from a Barreto-only pilot (not part of this repository). The ablation uses a fixed horizon (300 iterations), so on large instances non-converged results may be compared; section 5 of the ablation report (equal iterations / equal CPU) makes this visible.
* Operator "gain" counters are latency reductions of applied moves; because of the SO penalty they are not identical to the LOO delta.
* The Tüzün-family ablation is long (≈ 13 h on 30 cores); running it on the training set (17 instances, ≈ 4.3 h) and testing the decisions on the test instances is cheaper.

## 10. References, open data and code

* Silva, M. M., Subramanian, A., Vidal, T., Ochi, L. S. (2012). A simple and effective metaheuristic for the Minimum Latency Problem. *EJOR* 221(3):513–520 — GILS-RVND, O(1) sub-sequence evaluation. Further research proposed there: profit-collecting and multi-vehicle variants of the MLP.
* Zou, Y., Hao, J.-K., Wu, Q. (2024). *Computers & Operations Research* 170:106758 — RLHEA for the LLRP (ablation design RLHEA1–6, 54 large instances, 30 runs, Wilcoxon α = 0.05). Data: "on request"; GitHub `YujiZou/LLRP` contains only a compiled binary and the published solutions.
* Moshref-Javadi, M., Lee, S. (2016). The latency location-routing problem. *EJOR* 255(2):604–619 — problem definition and benchmark sets (definition of Nv / open depots).
* Barreto, S., Ferreira, C., Paixão, J., Santos, B. S. (2007). Using clustering analysis in a capacitated location-routing problem. *EJOR* 179(3):968–977. Prins, C., Prodhon, C., Wolfler Calvo, R. (2006). Solving the capacitated location-routing problem by a GRASP complemented by a learning process and a path relinking. *4OR* 4(3):221–238. Tüzün, D., Burke, L. I. (1999). A two-phase tabu search approach to the location routing problem. *EJOR* 116(1):87–99.
* López-Ibáñez, M., Dubois-Lacoste, J., Pérez Cáceres, L., Birattari, M., Stützle, T. (2016). The irace package: Iterated racing for automatic algorithm configuration. *Operations Research Perspectives* 3:43–58. Fawcett, C., Hoos, H. H. (2016). Analysing differences between algorithm configurations through ablation. *J. Heuristics* 22:431–458 (irace `ablation()` is a path ablation, different from the LOO/ADD design used here).
* Experimental methodology: Barr et al. (1995, *J. Heuristics* 1:9–32); Johnson (2002, DIMACS); Hoos & Stützle (2005, *Stochastic Local Search*).
* Open data / code: Salehipour et al. (2011) TRP-S10…S1000; GitHub `fredericoguerra/MinimumLatencyProblem` (GILS-RVND; licence not verified); arXiv 1908.10705 (Santana, Plastino, Rosseti).
* Possible next steps: Fawcett–Hoos path ablation (BASE → tuned configuration); ILS threshold experiment; route-pair caching; re-calibration of the stall threshold for Prins/Tüzün.
