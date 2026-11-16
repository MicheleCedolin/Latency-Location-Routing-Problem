# LLRP heuristic laboratory (v13.0-llrp.0.5.0-rc1)

Modular heuristic infrastructure for the **Latency Location-Routing Problem** (LLRP), ported from the CLRP kit
`clean.6.4.0_adaptive`: 17 campaign metaheuristics (19 registered; `rtr` and `grasppr` are excluded, see `EXCLUDED_HEURISTICS`), the delta-evaluating local-search library, the adaptive depot-set layer,
the resumable HPC launcher, and the verification/analysis tooling.
Problem definition: **[FORMULATION_LLRP.md](FORMULATION_LLRP.md)** · changes and open items: **[CHANGELOG_LLRP.md](CHANGELOG_LLRP.md)**.

* Objective: sum of customer arrival times (cumulative cost), no return to the depot, route direction matters.
* Bounds: at most `K` routes (fleet), at most `p` used depots; no fixed or opening costs.
* Depot capacity is ignored by default (as in the published best-known solutions); `--depot-capacity enforce` switches it on.
* 76 benchmark instances: Tuzun-Burke 36 (`T`), Prodhon 30 (`P`), Barreto 10 (`B`). Real Euclidean distances. State-of-the-art reference: RLHEA (Zou et al. 2024, C&OR 170:106758).

## Requirements

Python >= 3.10, standard library only for the search itself. `numpy` is optional (p-median ranking, same result without it); `scipy` (>= 1.9, `scipy.optimize.milp`) is needed only for the set-partitioning route-pool option `--sp-share` (the runner refuses to start without it; two tests are skipped / fail without scipy). `pip install numpy scipy` covers both.
On the cluster the scripts find conda and a suitable Python themselves (`hpc/pyenv.sh`). No package installation is required.

## Quick start

```bash
bash tests/smoke_hpc.sh && bash tests/smoke_shards.sh   # launcher checks (~20 s)
python3 -m unittest discover -s tests            # 128 tests, 1 skipped (~95 s); LLRP_PUBLISHED_DIR=<clone of github.com/YujiZou/llrp>/solutions enables the published-solution reproduction test

# one short run: instance id, seed, method, 10 s budget
python3 run_llrp.py --instances coord50-5-1 --seeds 1 --heuristic alns --local-search none \
       --budget-mode fixed_time --time-limit 10 --out-dir /tmp/llrp_try

# the same with the adaptive depot layer
python3 run_llrp.py --instances coord100-10-1b --seeds 1 --heuristic grasp --local-search first --neighborhoods baseline_route \
       --budget-mode fixed_time --time-limit 40 --depot-impact adaptive --out-dir /tmp/llrp_try2

python3 run_llrp.py --list-heuristics            # methods, presets
```

`K` and `p` come from `reference/LLRP_reference.csv` (override: `--K`, `--p`). The output directory receives `<run>.solution.json`, `<run>.sol.txt`, `config.json` (with the run fingerprint),
`summary.csv` (result row: `n, m, K, p, latency, gap_pct, ...`), `trajectory.csv` and `aggregate.csv`.

## Instances

IDs are the file stems in `data/` (`coord50-5-1`, `coordChrist100`, `coordP111112`, ...). Groups (for `hpc/run.sh`):

| group | instances | | group | instances |
|---|---|---|---|---|
| `P20` | 4 | | `B` | 10 |
| `P50` | 8 | | `T` | 36 (`T100`, `T150`, `T200`: 12 each) |
| `P100` | 12 | | `ALL` | 76 |
| `P200` | 6 | | | |

`data/*/SHA256SUMS` fix the instance files; `tests/test_integrity.py` verifies them.

## Campaign launcher (do not start without a time estimate)

Single node (resumable, fingerprint-checked; see the header of `hpc/run.sh`):

```bash
INSTANCES=P50 TIME_LIMIT=120 NSEEDS=30 METHODS_FILE=hpc/methods_phaseA.txt WORKERS=8 bash hpc/run.sh
```

Wall-clock cost is `runs x TIME_LIMIT / WORKERS` with `runs = |instances| x |methods| x seeds`. Agree on scope before launching.

### Staged campaign on the SGE cluster (P20 -> P50 -> P100 -> P200, 6 arms x 15 cores)

```bash
cd <kit folder>
bash hpc/start.sh P20                         # submits P20 (6 jobs x 15 cores) to the queue and returns at once
bash hpc/start.sh P20 P50 P100 P200           # the whole chain, each stage starts when the previous one is verified
bash hpc/submit_llrp_campaign.sh               # DRY RUN: plan, cost table and qsub commands, nothing is submitted
```

No `conda activate` is needed: `hpc/pyenv.sh` finds conda and a Python >= 3.10 by itself (it scans `~/miniconda3/envs/*/bin/python3` and similar folders first; override: `LLRP_PYTHON=<full path of python3>`, or `CONDA_SH=<path>/etc/profile.d/conda.sh CONDA_ENV=<name>`), and the jobs read their settings from `<stage folder>/stage.env`
instead of inheriting the environment of the submitting shell (no `qsub -V`).

Per stage: one array job (`-t 1-6 -pe smp 15`) whose tasks are the arms, then a finalize job held on it; the next stage's arms are held on that finalize job.
Each arm runs 15 single-core workers on its share of the stage (`SHARD=i/6`, Latin-square rule, see CHANGELOG 0.4). Defaults (all overridable, see the header of the script): 30 seeds,
time limits 60 / 180 / 300 / 900 s for P20 / P50 / P100 / P200 (provisional), method table `hpc/methods_phaseB_loffler9.txt`, output `analysis/llrp_campaign/<stage>_<TL>s_30seeds/`.
Results of a stage: `report.csv`, `stage_table.txt`, `stage_table_by_*.csv`, `rank_phaseA/`, `verify.log`, `arm_hosts.txt` (host and CPU of every arm), `FINALIZE_OK` or `FINALIZE_FAILED`.

If an arm dies, resubmit that arm (`qsub -t <i+1> -v STAGE_ENV=<stage folder>/stage.env -pe smp 15 hpc/campaign_arm.sge`, or the whole stage again with `bash hpc/start.sh <stage>`): finished runs are skipped, so only the missing runs are computed.
`OUT=<stage folder> bash hpc/finalize.sh` re-checks a stage by hand. A failed finalize job stays in the error state (Eqw) and keeps the next stage held; when the repaired arms have finished, `qmod -cj <finalize job id>`
runs it again and, if it passes, releases the next stage. Independently of the scheduler, the arms of a stage refuse to start unless the previous stage's `FINALIZE_OK` exists.

After a campaign:

```bash
python3 verify_run.py <campaign dir>           # reconcile with jobs.txt, re-evaluate every stored solution (--no-manifest for ad-hoc folders)
python3 collect.py --out <dir> <campaign dir>  # anytime / checkpoint tables, time-to-target, gap vs registry BKS (tolerance 1 %)
python3 tools/rank_stats.py --report <csv> --out <dir>   # ranks and significance tests
```

## Search components of v0.5 (opt-in; defaults reproduce v0.4.2)

| flag | default | effect |
|---|---|---|
| `--start-mix q` | 0 | probability that a start solution is built by random-priority insertion instead of `grasp_construct` (removes the single-depot basin of the tight-fleet instances) |
| `--depot-mode race` | `pmedian` | budget over the p-median-ranked depot sets by a rank prior `1/(rank+1)^gamma`, corrected by the evidence (`--race-gamma`, `--race-explore`) |
| `--sp-share s` | 0 | last share of the time limit: set-partitioning over the routes of all local optima (needs scipy; skipped and reported otherwise) |

Campaign use: `EXTRA_ARGS="--start-mix 0.5 --depot-mode race --sp-share 0.15"` (the flags enter the run fingerprint). Details and evidence: CHANGELOG_LLRP.md, v0.5.0-rc1.

## Layout

| path | content |
|---|---|
| `run_llrp.py` | CLI of a single run (instance, seed, method) |
| `llrp_framework/core.py` | instance reader, latency objective, feasibility |
| `llrp_framework/construction.py` | GRASP / priority constructors, fleet look-ahead, packing fallback |
| `llrp_framework/neighborhoods.py`, `local_search.py`, `walker.py` | delta-evaluating neighbourhoods, descent / VND / RVND |
| `llrp_framework/heuristics.py` | 17 campaign metaheuristics (+2 excluded), depot-subset policy (`enumerate` / `sample` / `pmedian`) |
| `llrp_framework/depot_*.py` | adaptive depot-set layer (explore swap / swap2 / open; exploit by set-restricted ruin-and-recreate) |
| `llrp_framework/params.py` | instance registry (K, p, BKS) and groups |
| `reference/` | `LLRP_reference.csv`, `published_check.csv`, scripts that generate them |
| `llrp_framework/exact.py` | exact reference solvers for tiny instances: dynamic program (n <= 11, standard objective) and brute force (n <= 6, any constraint of the kit), `random_instance` generator |
| `tools/indep_check.py` | stand-alone latency / feasibility checker (no kit imports) |
| `tools/exact_vs_engine.py` | validates the C++ solver `llrp_fast` against exact optima on tiny random instances (no run may be cheaper than the optimum; with `--atmost` the best seed reaches it) |
| `hpc/` | launcher (`run.sh`, `SHARD=i/N`), staged campaign (`submit_llrp_campaign.sh`, `campaign_arm.sge`, `finalize.sh`), method tables, SGE scripts |
| `tests/` | unit, equivalence and integrity tests |

## Open code and data

* RLHEA code and published solutions: <https://github.com/YujiZou/llrp> (three of the 76 published solution files do not reproduce the table, see CHANGELOG).
* Pre-LLRP lineage: the CLRP kit; its CLRP-specific files (golden results, MILP depot layer) were moved out and are not part of this package.

## Reproducibility checklist for a paper

1. Cite `VERSION` and the `config.json` fingerprints of the runs.
2. State "depot capacities are not enforced, as in the literature" (FORMULATION section 3), and the `K`/`p` source.
3. Use identical time budgets and seeds across methods; report gap to the registry BKS with the tolerance used.
4. Re-evaluate all reported solutions with `tools/indep_check.py`.
