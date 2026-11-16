# Latency Location-Routing Problem (LLRP) — GRASP + RVND with automatic configuration

Source code, benchmark instances and best-known values accompanying the manuscript on a **GRASP–RVND** heuristic with
constant-time move evaluation and **irace**-tuned configuration for the **Latency Location-Routing Problem**
(manuscript in preparation for *International Transactions in Operational Research*, ITOR).

The LLRP asks for a set of open depots and a set of vehicle routes that serve all customers and **minimise the sum of the customer arrival times**
(cumulative cost; vehicles do not return to the depot; at most `Nv` routes, at most `Ng` open depots; depot capacities are ignored, as in the literature).
Problem definition: [`python/FORMULATION_LLRP.md`](python/FORMULATION_LLRP.md).

## Repository layout

| Folder | Content |
|---|---|
| [`cpp/`](cpp) | **Main code.** `llrp_fast` (GRASP + RVND, 14 operators, strategic oscillation, depot swap) and `llrp_tools` (experiment orchestration, ablation, irace set-up, verification, statistics). C++11 only. Includes the 76 instances in `inst/`, the tuned configuration `irace/best.flags` and all run scripts. → [`cpp/README.md`](cpp/README.md) |
| [`bks/`](bks) | `LLRP_BKS.csv`: best-known value, bounds and verification status of every instance. → [`bks/README.md`](bks/README.md) |
| [`python/`](python) | Python heuristic laboratory (17 campaign metaheuristics, delta-evaluating local search, adaptive depot layer, SGE launcher, 120 unit tests) with the raw instance files and the registry of the 76 instances. → [`python/README.md`](python/README.md) |
| [`.github/workflows/`](.github/workflows) | `ci.yml` (build + self-check + unit tests) and `experiment.yml` (manually triggered experiments on GitHub runners). |

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

76 instances, in one text format under [`cpp/inst/`](cpp/inst) (raw data in [`python/data/`](python/data) with SHA-256 sums):

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

* Results of the study were produced with the scripts in `cpp/` (`run_config.sh`, `run_ablation.sh`, `run_irace.sh`, `run_final.sh`) on an SGE cluster (30 cores per job, one process per seed).
* The tuned configuration is stored in [`cpp/irace/best.flags`](cpp/irace/best.flags); the irace set-up (27 parameters, 17 training instances, `time` budget mode) is in `cpp/irace/` and is re-created by `cpp/run_irace.sh`.
* `cpp/selfcheck.sh` and the CI workflow check move evaluation against full recomputation, the independent solution verifier, determinism and the experiment tool chain.

## References

* Moshref-Javadi, M., Lee, S. (2016). The latency location-routing problem. *European Journal of Operational Research* 255(2):604–619.
* Zou, Y., Hao, J.-K., Wu, Q. (2024). *Computers & Operations Research* 170:106758 (RLHEA for the LLRP).
* Silva, M. M., Subramanian, A., Vidal, T., Ochi, L. S. (2012). A simple and effective metaheuristic for the Minimum Latency Problem. *European Journal of Operational Research* 221(3):513–520.
* López-Ibáñez, M., Dubois-Lacoste, J., Pérez Cáceres, L., Birattari, M., Stützle, T. (2016). The irace package. *Operations Research Perspectives* 3:43–58.
* Barreto, S. et al. (2007), *EJOR* 179(3):968–977; Prins, C., Prodhon, C., Wolfler Calvo, R. (2006), *4OR* 4(3):221–238; Tüzün, D., Burke, L. I. (1999), *EJOR* 116(1):87–99 (instances).

## License

MIT, see [`LICENSE`](LICENSE). Instance data originate from the cited benchmark sets. A citation (and a DOI, after publication) will be added here.
