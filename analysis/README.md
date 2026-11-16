# Analysis of the archived study results

Scripts that turn the raw result archives of [`../study_results`](../study_results) into the numbers of the study. Standard library only
(`scipy` is used by the self-test if it is installed).

| File | Content |
|---|---|
| [`ext10_report.py`](ext10_report.py) | 1x budget versus the extended "ext10" budget, anytime behaviour in iteration space, paired comparison with the published RLHEA values (Wilcoxon signed-rank) |
| [`pool_sp.py`](pool_sp.py) | **Route pool + exact DP + set partitioning** over the final solutions of many runs (each customer once, at most `Nv` routes, at most `Ng` open depots): best run, SP raw, SP+DP (every route re-ordered optimally, [`dp_latency.cpp`](dp_latency.cpp)), and SP+DP with the routes of the published solution of Zou et al. (2024) added; coverage of the published routes by the pool (exact / same customer set / other depot / none). Needs numpy, scipy and g++. |
| [`anytime_at_tavg.py`](anytime_at_tavg.py) | **Equal-time comparison:** best latency of every run at `f` x the published mean running time of RLHEA, for several `f`, and the time at which a run first reaches the published RLHEA average. The times come from different machines: `f` shows the sensitivity, it is not a hardware normalisation. |
| [`llrp_pool.py`](llrp_pool.py) | Helpers of the two scripts above (instance / result / published-solution readers, route cost, DP wrapper). |
| [`test_report.py`](test_report.py) | Self-test of the rank test and of the iteration bookkeeping (`python3 analysis/test_report.py`) |
| [`depot_decomp.py`](depot_decomp.py) | Hierarchical decomposition of the difference between our final solutions and a reference solution: depot set (A), customer-to-depot assignment (B), route partition (C), visiting order (D), identical (E) |
| [`test_depot_decomp.py`](test_depot_decomp.py) | Self-test of the decomposition (`python3 analysis/test_depot_decomp.py`) |

## Reproduce

```bash
tar xzf study_results/final_1x_tuned.tar.gz -C /tmp          # -> /tmp/results_final
tar xzf study_results/ext10_tuned.tar.gz    -C /tmp          # -> /tmp/results_extended10
python3 analysis/ext10_report.py --base /tmp/results_final --ext /tmp/results_extended10
python3 analysis/ext10_report.py --base /tmp/results_final --ext /tmp/results_extended10 --heldout --min-n 75   # held-out instances with n >= 75
python3 analysis/ext10_report.py ... --out-dir report/        # also writes ext10_instances.csv and ext10_anytime_iter.csv
```

For the per-instance comparison with all published algorithms (not only RLHEA) see [`../bks/compare_published.py`](../bks/compare_published.py).

## What the report contains and what it gives on the archived runs

1. **Budget.** The extended runs have a CPU-time limit of 10x the 1x limit, but they ran on a node with a higher CPU time per iteration, so the
   effective budget in iterations is smaller: median **7.38x** the iterations of the 1x run of the same seed (5-95 %: 5.28-9.84; min 4.17, max 12.09; 58 instances x 30 seeds).
2. **Continuation check.** Same seed, same binary and flags: the extended run repeats the 1x run up to the iteration where that one stopped.
   The best-so-far of the extended trace after the 1x iteration count equals the 1x result in **1740 / 1740** (instance, seed) pairs.
3. **Base versus extended**, 58 instances with n >= 75 (gap in % to the best-known values of [`../bks/LLRP_BKS.csv`](../bks/LLRP_BKS.csv)):

   | | best run at the BKS | mean gap of best run | mean gap of the mean | runs at the BKS |
   |---|---|---|---|---|
   | 1x | 21 / 58 | 0.359 | 1.707 | 8.0 % |
   | ext10 | 29 / 58 | 0.125 | 0.588 | 21.4 % |

   No instance has an extended best below the registry BKS by more than 0.01 (no new best-known values).
4. **Anytime behaviour in iteration space** (machine independent): mean gap after f x the iterations of the 1x run, f = 0.25 ... 10; a column uses
   only instances for which all 30 runs reached that many iterations (4.68 % at f = 0.25, 1.71 % at f = 1, 0.81 % at f = 4 over all 58 instances).
   CPU-time slices of the extended traces are not used: the extended node is slower per iteration, so they are not comparable with the 1x runs.
5. **Paired comparison with RLHEA** (published values of [`../bks/literature_results.csv`](../bks/literature_results.csv), other hardware and run counts;
   differences of at most 0.005 are ties). On the 45 held-out instances with n >= 75 (`--heldout --min-n 75`) the mean of our 30 runs against the published RLHEA average:
   win / tie / loss 0 / 4 / 41, Wilcoxon signed-rank on the 41 non-tied instances W+ = 861, W- = 0, normal approximation p = 2.4e-8 (the exact p-value is 9.1e-13);
   best run against the published best: 0 / 21 / 24.
   Our extended-budget results are therefore behind the published RLHEA values on the large instances; this is a statement about these runs and values, not about equal-time performance
   (RLHEA's published times are on other hardware).

All sections are deterministic functions of the archived `run.csv` / `trace.csv` files; the CI job `bks` runs the report and checks the continuation count.

## Pooled recombination and equal-time comparison (`pool_sp.py`, `anytime_at_tavg.py`)

```bash
mkdir -p /tmp/trees && tar xzf study_results/ext10_tuned.tar.gz -C /tmp/trees
git clone --depth 1 https://github.com/YujiZou/LLRP /tmp/zou            # published solutions of Zou et al. (2024)
python3 analysis/pool_sp.py /tmp/trees --published /tmp/zou/solutions --out out --jobs 4
python3 analysis/anytime_at_tavg.py /tmp/trees --out out
```

A pooled value is a **multi-start recombination of many runs, not the result of one run** (cf. heuristic concentration, Rosing and ReVelle 1997;
ILS-SP, Subramanian, Uchoa and Ochi 2013); report it in a column of its own. Integrity checks are part of the output: every run's latency is
recomputed from its routes and every SP solution is audited (feasibility, recomputed latency = objective).

**On GitHub:** *Actions -> Analysis -> Run workflow* ([`../.github/workflows/analysis.yml`](../.github/workflows/analysis.yml)). Inputs: result archives
(paths in the repository or https URLs, space separated; default: the 1x and ext10 archives), whether to add the published solutions, an optional instance subset.
The tables go to the job summary and to the branch `analysis-results` (`latest/`, `runs/<run id>/`). A full pass over 1x + ext10 takes roughly half an hour.

## Depot-set decomposition (`depot_decomp.py`)

When the engine ends above the reference value, is it because it opens other depots than the reference solution (class A), serves customers from other depots (B), partitions the
customers into other routes (C) or only orders a route differently (D)? The script compares every final solution of a result directory (`run.csv` + `routes.csv`) with a reference
solution and reports the class per run (`--out`, one row per instance and seed) and a summary.

```bash
git clone --depth 1 https://github.com/YujiZou/LLRP /tmp/zou                      # published solutions of Zou et al. (2024), the same source as pool_sp.py
python3 analysis/depot_decomp.py /tmp/results_final/{barreto,prins,tuzun}/tuned --ref-solutions /tmp/zou/solutions --out decomp_1x.csv
python3 analysis/depot_decomp.py /tmp/results_extended10/{barreto,prins,tuzun}/ext10 --ref-solutions /tmp/zou/solutions --out decomp_ext10.csv
```

The reference solutions are the files published with RLHEA (Zou et al. 2024), one `<name>.txt` per instance; they are third-party files and are not part of this repository.
A file is used only if it covers every customer once and its latency, recomputed from the instance file, is within 0.1 % of the best published value; the instances that fail
(Tuzun P112222-20: 90 of 100 customers; P131122-20: latency 8 times the published value; Barreto Or117-14: empty file) are listed and left out.
On the 1x archive the classes of all 2190 runs on the remaining 73 instances equal those of the analysis of the study (A 25.7 %, B 34.2 %, C 13.6 %, D 5.8 %, E 20.8 % of the runs;
the mean gap to the BKS falls from 3.7 % in class A to 0.8 / 0.4 / 0.01 / 0.00 % in B / C / D / E; 562 / 748 / 298 / 127 / 455 runs). On the ext10 archive the same 73-instance rule leaves out one instance more
than the study did, Tuzun P112222-20, which the study included with a repaired solution file.

## Edge structure of the published solutions

| script | question |
|---|---|
| `edge_granularity.py` | neighbour rank (k-NN) of every route edge of the published solutions of Zou et al. and of ours; which published edges our runs never use |
| `edge_candidates.py` | coverage of the published edges by candidate edge sets (k-NN, union of the edges of m runs) versus their size |
| `backbone_sp.py` + `enum_paths.cpp` | routes that can be built from the edges shared by many runs (frequency threshold) versus the pool of the runs' own routes; optional set partitioning. Workflow `Backbone` |
| `restart_pool.py` | equal CPU: one long run versus k pooled short runs (route pool + DP + set partitioning). Workflow `Restarts` |
| `edge_summary.py` | markdown summary of the edge analyses (delta* and shares paired with the published solutions, Zou-edge discovery, coverage versus candidate-set size). Workflow `Edges` |
