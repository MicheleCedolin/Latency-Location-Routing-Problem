# Best-known values (BKS) of the 76 LLRP benchmark instances

[`LLRP_BKS.csv`](LLRP_BKS.csv) — one row per instance (Barreto 10, Prins 30, Tüzün–Burke 36):

| Column | Meaning |
|---|---|
| `family`, `instance` | Family (`barreto`, `prins`, `tuzun`) and instance name as used in `cpp/inst/<family>/<instance>.inst` |
| `n`, `m_depots`, `Q` | Customers, candidate depots, vehicle capacity |
| `Nv_max_routes`, `Ng_max_open_depots` | Upper bounds on the number of routes and of open depots (Moshref-Javadi & Lee 2016, Tables 2–4; Zou et al. 2024, Appendix A) |
| `bks` | Best-known total latency (sum of customer arrival times) |
| `bks_source` | Origin of the value: minimum of the best-known value and the RLHEA best value listed by Zou et al. (2024), C&OR 170:106758 |
| `bks_status` | `verified`, `verified (reconstructed)` or `not verifiable` (see below) |
| `note` | Details for the four instances that are not plain `verified` |

## How the values were checked

The 76 published solution files of Zou et al. (GitHub `YujiZou/LLRP`, `solutions/*.txt`) were re-evaluated on the instance data of this repository
(latency = sum of arrival times, float arithmetic; depot = first node − n − 1; customer = id − 1) and compared with `bks` (tolerance ± 0.01, the published values have two decimals).

* **72 / 76 reproduce the value** (`verified`). `P111222-20` differs by 0.005 (rounding) and counts as verified.
* **`P112222-20` — verified (reconstructed).** The solution file covers 90 of 100 customers and misses one route. The 10 missing customers (total demand 142 ≤ Q = 150) fit one route from open depot D13 (index 12, part of the depot set {3, 12}); with minimum-latency order the total is 1614.8323 = published 1614.83.
* **`P122122-20` — not verifiable.** The file evaluates to 3705.7386 (+0.004 % above the published 3705.59, apparently an older best-known solution); no solution for 3705.59 is available.
* **`P131122-20` — not verifiable.** The file is unrelated to this instance (evaluates to 38761.86; it does not fit any Tüzün instance with n ≥ 150); no solution for 4870.82 is available.
* **`Or117-14` — not verifiable.** The published solution file is empty (0 bytes). The value 53798.5256 is reproduced independently by the heuristics of this repository (reached in 46.7 % of 30 runs of one study configuration).

No BKS turned out to be numerically wrong; two of them cannot be verified from published solutions and two files are defective. Gap computations in the experiment scripts use the published `bks` unchanged.

## Notes

* `python/reference/LLRP_reference.csv` carries the same values (plus `K`, `p`, minimum vehicles/depots by capacity) under the Python kit's instance names (`coordP111112`, ...). Two entries differ in the last digit because of rounding:
  `20-5-1b-5` (608.05 here, 608.06 there; the unrounded value is 608.055) and `Or117-14` (53798.53 here, 53798.5 there).
* `python/reference/published_check.csv` lists, for every published solution file, its recomputed latency and relative deviation from the registry value.
* Literature results other than the best-known values are in [`literature_results.csv`](literature_results.csv) (next section).

## Published results of other algorithms (`literature_results.csv`)

Best value, average value and running time of seven published algorithms on the 76 instances, for context and for the gap/win-tie-loss comparison with this repository.

| Column | Meaning |
|---|---|
| `instance`, `family`, `n`, `m`, `Nv` | As in `LLRP_BKS.csv` (`m` = candidate depots, `Nv` = route bound) |
| `algorithm` | `MA` (memetic algorithm, Moshref-Javadi & Lee 2016), `GBILS`, `SA-VND0`, `SA-VND1`, `SA-VND2` (simulated annealing + VND, Osorio-Mora et al. 2023, ITOR 30(6):3801–3832, DOI 10.1111/itor.13294), `M-ILS` (Osorio-Mora et al. 2023, C&OR 158:106293), `RLHEA` (Zou et al. 2024, C&OR 170:106758), `MS-VNS` (Osorio-Mora, Saldanha-da-Gama & Toth 2025, EJOR 321(3):837–850) |
| `best`, `avg` | Best and average total latency over the runs of the original study (two decimals; `avg` is empty for `GBILS`, which is reported with its best value only) |
| `time_s` | Running time in seconds as reported (mean over the runs; for RLHEA the stopping time) |

570 rows = 76 instances × 7 algorithms + `GBILS` on 38 instances (Barreto and Prins; no values for two Barreto instances, none for Tüzün–Burke).

* **Source and transcription.** The values were transcribed from the supplementary tables SM-5, SM-6 and SM-7 (deterministic LLRP) of Osorio-Mora et al. (2025). Checks: n / m / Nv agree with `LLRP_BKS.csv`, and the best-known value of the supplement equals the smallest `best` of every instance (re-run by `check_literature.py`); at transcription the column means were also compared with the printed "Global avg." rows.
  One inconsistency lies inside the source: the Prins-set `MA` average column (the 30 rows average 1658.85, the printed global average is 1610.33; the other columns reconcile). Instance names follow `LLRP_BKS.csv`; the supplement's `Gaskell-32-5b` is `Gaskell32-5`, `Christ-*` is `Ch*`, `Min-*` is `Mi*`.
* **Not comparable with our CPU budgets.** The times come from other machines, run counts and stopping rules (the numbers of runs behind each `avg` are those of the original papers). Use them for orders of magnitude, not as a speed comparison.
* **Differences to the registry.** `bks` equals the smallest published `best` for 74 of 76 instances; the two exceptions are the rounding cases above (`20-5-1b-5`: 608.05 vs 608.06, `Or117-14`: 53798.53 vs 53798.50).
* Please cite the original papers when using these values; `python3 bks/check_literature.py` re-checks the file against `LLRP_BKS.csv` (CI runs it).

### Comparing your own results

```bash
# any summary.csv written by run_final.sh / run_config.sh (columns instance, best, mean, cpu_mean, ...)
tar xzf study_results/final_1x_tuned.tar.gz -C /tmp
python3 bks/compare_published.py /tmp/results_final/*/tuned/summary.csv
python3 bks/compare_published.py my_summary.csv --only-n-ge 75 --per-instance per_instance.csv
```

The script prints, per family and overall, the mean gap to the BKS of our best run and mean, the same for every published algorithm, the number of instances at the BKS and the win / tie / loss counts of our best (mean) against the published `best` (`avg`) of each algorithm (a tie is a difference of at most 0.005). Standard library only.
