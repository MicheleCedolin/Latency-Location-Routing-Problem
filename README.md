# Latency Location-Routing Problem (LLRP) — GRASP + RVND with automatic configuration

Source code, benchmark instances and best-known values accompanying the manuscript on a **GRASP–RVND** heuristic with
constant-time move evaluation and **irace**-tuned configuration for the **Latency Location-Routing Problem**
(manuscript in preparation for *International Transactions in Operational Research*, ITOR).

The LLRP asks for a set of open depots and a set of vehicle routes that serve all customers and **minimise the sum of the customer arrival times**
(cumulative cost; vehicles do not return to the depot; at most `Nv` routes, at most `Ng` open depots; depot capacities are ignored, as in the literature).
The problem definition is given in Section 3 of the manuscript.

## Repository layout

Everything in this repository is used by the manuscript. The one exception is a handful of solver flags of mechanisms that were tried and not adopted (see [`cpp/README.md`](cpp/README.md#engine-stages-and-provenance)); they are off by default and no result of the paper uses them.

| Folder | Content |
|---|---|
| [`cpp/`](cpp) | **Solver and run scripts.** `llrp_fast` (GRASP + RVND, 14 operators, strategic oscillation, depot swap; depot-aware diversification, route pool and memetic phase as flags) and `llrp_tools` (experiment orchestration, independent verification, statistics). C++11 only. Includes the 76 instances in `inst/`, the tuned configuration `irace/best.flags`, the irace scenario and all run scripts. → [`cpp/README.md`](cpp/README.md) |
| [`study_results/`](study_results) | Raw result files of the runs reported in the manuscript (one archive per campaign; the table below says which). → [`study_results/README.md`](study_results/README.md) |
| [`paper/`](paper) | Regenerates the result tables, quoted numbers and figures of the base-method campaigns from `study_results` (`paper/run_all.sh`, ~15 s); the tables are pinned by checksums. → [`paper/README.md`](paper/README.md) |
| [`analysis/`](analysis) | Analyses of the result archives: `ext10_report.py` (tuning budget versus extended budget, comparison with RLHEA), `depot_decomp.py` (where the base method loses: depot set, assignment, route partition, order), `anytime_at_tavg.py` (equal-time comparison with RLHEA). → [`analysis/README.md`](analysis/README.md) |
| [`bks/`](bks) | `LLRP_BKS.csv`: best-known value, bounds and verification status of every instance; `literature_results.csv`: published best / average / time of seven algorithms on the 76 instances; `compare_published.py`; `reference/`: recomputation of the published solutions and the p-median ranks of their depot sets. → [`bks/README.md`](bks/README.md) |
| [`instances_raw/`](instances_raw) | The instance files as published by their authors (`B` Barreto, `P` Prins, `T` Tüzün–Burke), with SHA-256 sums; `cpp/inst/` is their conversion to the solver format. |
| [`.github/workflows/`](.github/workflows) | `ci.yml` (build, self-check, regeneration of the tables), `experiment.yml` (manually triggered runs on GitHub runners), `analysis.yml` (equal-time analysis of an archive). |

## Quick start (C++)

```bash
git clone https://github.com/MicheleCedolin/latency-location-routing-problem.git
cd latency-location-routing-problem/cpp
./build.sh            # g++ >= 4.8, no other dependencies
./selfcheck.sh        # a few seconds; must end with "SELFCHECK: ALL OK"

# one run: instance, seed, full 14-operator pool, strategic oscillation, depot swap
bin/llrp_fast --instance inst/barreto/Ch50-5.inst --seed 1 --ops full --so --ds --max-iter 100 --out /tmp/ch50

# 4 seeds on two instances, iteration-limited; results in results/custom/full3/
FAMILY=custom NPROC=4 PIN=0 MAXITER=100 STALL=0 ./run_config.sh full3 Ch50-5 Gaskell21-5

# the tuned configuration (irace id 267) on a whole family
FLAGS_FILE=irace/best.flags FAMILY=barreto NPROC=30 ./run_config.sh tuned
```

Same seed + same binary ⇒ identical result (compiled with `-O3 -std=c++11 -ffp-contract=off`, no `-march=native`). `env.txt` of every result directory records
the flags, the binary and manifest SHA-256, the host and the CPU. All routes can be re-checked with `bin/llrp_tools verify`.
Full documentation (operators, ablation, irace, final evaluation, time estimates): [`cpp/README.md`](cpp/README.md).

## Benchmark instances

76 instances, in one text format under [`cpp/inst/`](cpp/inst) (raw data in [`instances_raw/`](instances_raw) with SHA-256 sums):

| Family | Instances | Customers `n` | Depots `m` | Source |
|---|---|---|---|---|
| Barreto (`barreto`) | 10 | 21 – 134 | 5 – 14 | Barreto et al. (2007) |
| Prins–Prodhon–Wolfler Calvo (`prins`) | 30 | 20 – 200 | 5 – 10 | Prins et al. (2006) |
| Tüzün–Burke (`tuzun`) | 36 | 100 – 200 | 10 – 20 | Tüzün & Burke (1999) |

The bounds `Nv` (routes) and `Ng` (open depots) follow Moshref-Javadi & Lee (2016) and Zou et al. (2024); Euclidean distances are not rounded.
`cpp/manifest.tsv` lists every instance with its size, bounds, best-known value and tightness. `cpp/selection/` holds the fixed split used for tuning:
17 training instances (`train.txt`) and 59 held-out instances (`test.txt`).

## Best-known values

[`bks/LLRP_BKS.csv`](bks/LLRP_BKS.csv) — best-known latency of every instance (best of the published best-known value and the RLHEA best of Zou et al. 2024)
and the result of re-evaluating the published solutions: 72 instances verified, one reconstructed from an incomplete solution file, three that cannot be verified from published data
(see [`bks/README.md`](bks/README.md)). Averages and running times of competing algorithms are given in the original papers; they are not repeated here because they were measured on different hardware.

## Reproducing the manuscript, stage by stage

The method is built in stages; each stage was evaluated in its own campaign with the same instances, seeds (1 to 30) and extended CPU budget. All stages are flags of one solver (`llrp_fast`); without the flags a stage is switched off.
Every campaign writes `run.csv`, `routes.csv`, `trace.csv` and `env.txt` (flags, binary and manifest SHA-256, host) and is verified run by run with `llrp_tools verify`.

| Stage | Manuscript | Flags (added to the previous stage) | Instances x runs, budget | Command | Archive in `study_results/` |
|---|---|---|---|---|---|
| 0 | Instances, reference values | — | 76 | `cpp/check_inst_data.sh`, `python3 bks/check_literature.py` | `bks/`, `instances_raw/` |
| 1 | Tuning (Table of parameters) | irace scenario of `cpp/irace/` | 17 training instances, 3000 experiments | `cpp/run_irace.sh` | `irace_logs.tar.gz` |
| 2a | Base method, tuning budget | `cpp/irace/best.flags` | 76 x 30, 0.3 n s | `cpp/run_final.sh` | `final_1x_tuned.tar.gz` |
| 2b | Base method, extended budget | same | 58 x 30, 3 n s | `INSTLIST=ext10_instances.txt TC=300 TAG=ext10 OUT=results_extended10 cpp/run_extended.sh` | `ext10_tuned.tar.gz` |
| 2c | Prins `50-5-2BIS-5` | `+ --atmost` (`cpp/irace/atmost.flags`) | 1 x 30, 0.3 n s | `FAMILY=custom FLAGS_FILE=irace/atmost.flags TAG=atmost cpp/run_final.sh 50-5-2BIS-5` | `atmost_50-5-2BIS-5.tar.gz` |
| 3 | + depot-aware diversification | `--dpm-rank 10,0.25 --dpm-prune` | 57 x 30, 3 n s | `FLAGS_FILE=stages/2_depot.flags INSTLIST=stages/instances_n100.txt TC=300 TAG=depot OUT=results_depot cpp/run_extended.sh` | `depot_tuned.tar.gz` (produced with `llrp_fast` v6, `Algorithm` column `V1`; replayed with the current engine) |
| 4 | + route pool (**final method**) | `--pool-sp --pool-tl 3 --pool-sets 3 --pool-first 8 --pool-src 1` | 57 x 30, 3 n s including the set-partitioning time | same with `stages/3_pool.flags`, `TAG=pool` | `b1_tuned.tar.gz` (produced with `llrp_fast` v7; replayed with the current engine) |
| 5 | Exploratory memetic phase (Supporting Information S7) | `--eax-split 0.4 --eax-pop 20 --eax-psi 0.55 --eax-esc 12 --eax-ils 0 --eax-pool-theta 0.01` | 57 x 30, 3 n s | same with `stages/4_memetic.flags`, `TAG=memetic` | `memetic_tuned.tar.gz` (produced with `llrp_fast` v9, the source of this repository; analysis: [`analysis/memetic`](analysis/memetic)) |

The four flag files in [`cpp/stages/`](cpp/stages) are cumulative (each extends the previous one; `2_depot.flags` = `1_base.flags` + depot-aware diversification, and so on), and `stages/instances_n100.txt` lists the 57 instances of stages 3 to 5.
Run the commands from `cpp/` after `./build.sh`; `cpp/run_extended.sh` writes `run.csv`, `routes.csv`, `trace.csv`, `env.txt` and verifies every run.

**Link between archives and source.** A run limited by CPU time is reproduced exactly by running the same seed and flags for the number of GRASP iterations it completed (the column `Iterations` of `run.csv`).
`python3 analysis/replay_archive.py ARCHIVE --flags FLAGS --n-runs N` does this for the cheapest runs of an archive and compares the objective value; CI runs it on the archives of stages 2, 3 and 4. The memetic phase of stage 5 starts when 40 % of the CPU budget is used, so an iteration-limited replay would not enter it; the archive of stage 5 is checked by the independent verification of every run and by regenerating the pre-registered analysis from it ([`analysis/memetic`](analysis/memetic), also run by CI).
With the current engine (`cpp/src/llrp_fast.cpp`, the v9 source that produced the memetic campaigns), the replayed values agree to the last printed digit with the archives of the base method
(built with an earlier version), of the `--atmost` check and of the route-pool campaign (built with v7). For the depot campaign of stage 3 (built with v6) nine runs were replayed (the six cheapest, all on `P122112-10`, and one run each on `100-10-1-10`, `Or117-14` and `P111122-20`): eight agree in every printed digit, the ninth (`Or117-14`, seed 7: 53798.52560740 against 53798.52560744) in the first 12 significant digits.

**Status (26 November 2026).** The archives of all campaigns of the manuscript (stages 0 to 5), the source of all stages and the analysis of the pre-registered criteria of stage 5 are in the repository. Not yet in the repository: the scripts that produce the stage-by-stage comparison of the manuscript (stages 2 to 4, with the pre-registered criteria of stages 3 and 4).

## Running experiments on GitHub Actions

The repository can run the engine on GitHub-hosted runners (4 vCPU each; free for public repositories). Open **Actions → Experiment → Run workflow**:

| Input | Meaning |
|---|---|
| `mode` | `config`: `cpp/run_config.sh` with an iteration / stall budget; `final`: `cpp/run_final.sh` (tuned flags, CPU-time budget `max(5, 30 n/100)` s, independent verification) |
| `config` | `full1`, `full2`, `full3` (operator pools of the ablation stages) or `tuned` (`irace/best.flags`) — mode `config` only |
| `family`, `instances` | `barreto`, `prins`, `tuzun`, `train`, `test`, `all` or `custom` plus a list of instance names |
| `seeds`, `first_seed`, `seeds_per_job` | 30 seeds starting at 1, 4 seeds per runner by default (30 seeds → 8 parallel runners) |
| `max_iter`, `stall`, `time_limit` | budget of mode `config` (defaults 1000 / 300 / off) |

Each runner computes one block of seeds; the final job merges all blocks, writes `run.csv`, `summary.csv` and `summary.txt` (also shown in the run summary) and uploads them as the artifact `aggregate`
(the raw blocks are kept for 30 days as `shard-*`). A run on a GitHub runner is reproducible in cost for iteration-limited budgets; **CPU times are not comparable with a cluster node**
and a single job is limited to 6 hours, so the Tüzün family should be run with a small `max_iter` or on a subset. Plan with the time table in section 6 of [`cpp/README.md`](cpp/README.md).

## Reproducibility notes

* Results of the study were produced with the scripts in `cpp/` (`run_irace.sh`, `run_final.sh`, `run_extended.sh`) on an SGE cluster (30 cores per job, one process per seed); the raw result files are in [`study_results/`](study_results).
* The tuned configuration is stored in [`cpp/irace/best.flags`](cpp/irace/best.flags); the irace set-up (27 parameters, 17 training instances, `time` budget mode) is in `cpp/irace/` and is re-created by `cpp/run_irace.sh`.
* `cpp/selfcheck.sh` and the CI workflow check move evaluation against full recomputation, the independent solution verifier, determinism, the experiment tool chain and the `--atmost` mode.
* The solver option `--atmost` (at most `Ng` open depots instead of exactly `Ng`) is used in the manuscript for one instance only (Prins `50-5-2BIS-5`); all other results use the default.

## References

* Moshref-Javadi, M., Lee, S. (2016). The latency location-routing problem. *European Journal of Operational Research* 255(2):604–619.
* Zou, Y., Hao, J.-K., Wu, Q. (2024). A reinforcement learning guided hybrid evolutionary algorithm for the latency location routing problem. *Computers & Operations Research* 170:106758, doi:10.1016/j.cor.2024.106758 (RLHEA).
* Silva, M. M., Subramanian, A., Vidal, T., Ochi, L. S. (2012). A simple and effective metaheuristic for the Minimum Latency Problem. *European Journal of Operational Research* 221(3):513–520.
* López-Ibáñez, M., Dubois-Lacoste, J., Pérez Cáceres, L., Birattari, M., Stützle, T. (2016). The irace package. *Operations Research Perspectives* 3:43–58.
* Barreto, S. et al. (2007), *EJOR* 179(3):968–977; Prins, C., Prodhon, C., Wolfler Calvo, R. (2006), *4OR* 4(3):221–238; Tüzün, D., Burke, L. I. (1999), *EJOR* 116(1):87–99 (instances).

## License

MIT, see [`LICENSE`](LICENSE). Instance data originate from the cited benchmark sets. A citation (and a DOI, after publication) will be added here.
