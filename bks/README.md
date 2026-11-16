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
* Literature results other than the best-known values (average values and running times of RLHEA and other algorithms) are published in the original papers and are **not** reproduced in this table; running times in the literature were measured on different hardware and are not comparable with the CPU-time budgets used here.
