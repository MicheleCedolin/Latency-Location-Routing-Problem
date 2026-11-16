# LLRP — problem definition used by this kit (v13.0-llrp.0.4.2)

This is the exact problem that `llrp_framework/core.py` evaluates and `feasible()` enforces.
Any result that is reported from the kit refers to this definition.

## 1. Problem

* Customers `C = {1..n}`, demand `q_c`; depots `D = {1..m}`; homogeneous vehicles of capacity `Q`.
* Distances `d(i,j)`: **real Euclidean** (no rounding, no `ceil`) for all three benchmark families
  (Tuzun-Burke, Prodhon, Barreto). Checked against the published solutions, see `reference/published_check.csv`.
* A *route* is an ordered list `(depot o; c_1, ..., c_L)`. Direction matters; there is **no return arc** to the depot.
* Arrival time of the k-th customer: `t_k = d(o,c_1) + sum_{j=2..k} d(c_{j-1},c_j)`.
* Route latency `lat(r) = sum_{k=1..L} t_k = sum_{j=1..L} (L-j+1) * d(c_{j-1}, c_j)`, with `c_0 = o`.
* **Objective:** minimise `sum_r lat(r)` (total customer waiting time / cumulative cost).

### Constraints (`core.feasible`)

1. every customer is visited exactly once;
2. route load `sum q_c <= Q`;
3. number of routes `<= K` (fleet bound `N_v`);
4. number of **used** depots `<= p` (bound `N_d`);
5. depot capacity — *optional*: `--depot-capacity enforce`; default `ignore` (see section 3).

Opening cost = 0 and vehicle fixed cost = 0 (the objective contains no fixed costs).

`K` and `p` are *upper bounds*. Published best-known solutions use exactly `K` routes and `p` depots, and
the kit reproduces that: opening more depots or splitting a route never increases the latency
(split a route after position `j`; for the tail, `d(o,c_{j+1}) <= t_j + d(c_j,c_{j+1})` by the triangle inequality, and the head is unchanged),
so bounds are *binding* in good solutions, but the kit does not force equality.

## 2. Registered parameters and references

`reference/LLRP_reference.csv` (76 rows) holds, per instance: `n, m, Q, total_demand, min_vehicles` (= ceil(sum q / Q)),
`min_depots_by_capacity`, `K`, `p`, `bks`. Provenance (`reference/ref_raw.py`): `K` and `p` transcribed from the benchmark tables
of "MJ&L 2016" (Tables 2-4), `bks` from the Osorio-Mora 2025 supplement; `n, m, Q`, demands from the `.dat` files.
All three were cross-checked by recomputing the 76 published solutions of Zou et al. (2024) from scratch with `tools/indep_check.py`
(73 reproduce the BKS within 4.1e-5 relative, see section 3). `--K` / `--p` override the registry.

`K * Q` exceeds the total demand by only 3-20 %: for many instances the best-fit-decreasing packing of the
demands needs `K` or `K+1` bins (e.g. `100-5-1`: BFD needs 25 bins, `K = 24`). Consequently a naive greedy
insertion runs into dead ends; section 4 describes how the kit handles this.

## 3. Depot capacity is not enforced in the literature

Of the 76 published best solutions, 25 exceed the depot capacities of the instance files (P family and `Min-134-8`),
and all 73 parseable files reproduce the published BKS value within 4.1e-5 relative (`reference/published_check.csv`)
**ignoring** depot capacity. Therefore the default is `depot_capacity='ignore'` (every depot gets the capacity
"total demand"); `--depot-capacity enforce` reads the depot capacities from the file and enforces them.
The fact that the benchmarks are solved without depot capacities must be stated explicitly in any paper that
uses these results.

## 4. Latency arithmetic used by the search

For a route with prefix arrival times `T[0]=0, T[i]` and a customer `c` inserted at position `pos` (0-based gap, `L` customers):

```
a_c    = T[pos-1] + d(prev, c)               (T[-1] = 0 and prev = depot when pos = 0)
Delta  = d(prev,c) + d(c,next) - d(prev,next)   (next absent: Delta = 0)
delta_latency = a_c + (L - pos) * Delta
```

i.e. the new customer's own arrival time plus the delay that each of the `L - pos` customers behind it suffers.
A new singleton route costs `d(depot, c)`. All move deltas in `neighborhoods.Scan` are evaluated by the same
difference-of-prefix arithmetic as `core._route_latency`; the reported objective is **always** recomputed by
`core.objective`, never accumulated from deltas (deltas agree with recomputation to about 1e-13 relative).

### Fleet look-ahead (constructors)

Construction with a tight fleet can reach a state where the remaining customers cannot be packed into the remaining
route slots. `grasp_construct` / `priority_construct` therefore validate lazily with a best-fit-decreasing check
(`_pack_ok`) whenever a customer would open a new route, and fall back to `pack_construct` (packing-first:
randomised BFD with a Gupta-Ho minimum-slack subset-sum improvement, then latency-greedy ordering/assignment).
Dead ends: none on the 76 instances in the test-suite (`tests/test_llrp_core.py`).
**Repairs (ALNS / LNS / IG).** The greedy / regret-2 repairs use the same idea inside `heuristics._repair_core`: a move is accepted only if the remaining unplaced
customers still pack (BFD) into the residual capacities of the routes and the unused vehicles; otherwise the largest unplaced customer goes to its BFD bin, which keeps the certificate.
Without it 34 of 90 repairs failed on a K-route solution of 100-5-1; with it none (see CHANGELOG 0.2). The certificate ignores depot capacities (a relaxation).

## 5. Depot-set decision

`p` depots may be chosen among `m`. The solvers iterate over `p`-subsets:

* `--depot-mode enumerate`  all `C(m,p)` subsets in random order (CLRP behaviour; large for `m = 20`);
* `--depot-mode sample`     random subset sample;
* `--depot-mode pmedian`    (**default**) the `--depot-sample` best subsets ranked by the p-median bound
  `LB(S) = sum_c min_{d in S} d(d,c)`.
  `LB(S)` is a valid lower bound on the latency of every solution that uses only depots of `S`
  (each customer's arrival time is at least the distance to the nearest open depot). Values are rounded to 1e-6 before ranking so the order does not depend on numpy.

Why `pmedian` is the default. (i) Literature: RLHEA (Zou et al. 2024, Sections 2.2-2.5) does not enumerate depot sets; it opens a random set of `N_d` depots at initialisation,
repairs offspring that open too many depots by keeping the `N_d` depots that occur most often in high-quality local optima (or random ones), and mutates by swapping an open depot with a closed one.
Enumerating all `C(m,p)` sets is a design choice of the CLRP kit, not of the LLRP literature, and is impractical for `m = 20` (C(20,5) = 15504). (ii) Evidence from the benchmark
(`tools/pmedian_rank_study.py`): for the 73 usable published best solutions the depot set is the p-median-best set in 53 cases, and the worst rank among the 45 instances with `C(m,p) > 50`
is 26 (instance 111122, m = 20), so the default `--depot-sample 50` contains the published depot set of every instance. For `C(m,p) <= 50` (all `m = 5` instances) `pmedian` and `enumerate` coincide.
Limits: the check concerns the best-known depot sets, found by other methods; it does not prove that no better set outside the top 50 exists, which is what the adaptive layer (swap / swap2 / open) is for.

Adaptive depot layer (`--depot-impact adaptive`; port of the CLRP 6.4.0 layer): exchange kinds `swap`, `swap2`, `open`
(no `close`: opening is free), ranking by p-median-bound delta, set-restricted ruin-and-recreate for exploitation,
packing-first rebuild for tight `K`. The CLRP "halving"/MILP depot layers were not ported.

## 6. Reproducibility notes

* The independent checker `tools/indep_check.py` (stand-alone, no kit imports) recomputes latency, loads and feasibility from a solution file.
* `verify_run.py` reconciles result folders with `jobs.txt` and re-evaluates every stored solution with the kit's own evaluator.
* Run fingerprints (code, parameters, instance, reference, interpreter family) are stored in `config.json`; `hpc/run.sh` resumes only matching runs.
* Reference: Zou, Y., et al. (2024). *Computers & Operations Research* 170:106758 (RLHEA); open code and solution files: <https://github.com/YujiZou/llrp>.
