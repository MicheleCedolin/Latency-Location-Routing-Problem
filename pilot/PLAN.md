# Pilots of two experimental mechanisms (llrp_fast v8) - pre-registered plan

Written **before any result of these pilots existed** (2026-11-17).  Nothing in this folder is part of the published engine (`cpp/`, v5); it extends the engine of the
B1 campaign (llrp_fast v7: V1 depot layer + run-internal route pool, exact DP, set partitioning).  Both mechanisms are behind flags and **off by default**; with the flags off,
`llrp_fast_v8` reproduces `llrp_fast_v7` exactly (checked by `identity_check.sh` in every workflow run: final cost, iterations, routes and iteration log of 4 instances).

## Mechanisms

**M1 `--dpm-tabu` (converged-set tabu).**  A GRASP cycle = `--it-div 9` diversification iterations (start depot sets drawn by `--dpm-rank 10,0.25`) followed by `--it-int 5`
intensification iterations that start from the best diversification set.  The set a cycle converges on (best diversification set, and the open set of the best
intensification solution) is put on a tabu list for the rest of the run.  Later start-set draws never return a tabu set (top-K and uniform draws); if the diversification phase of a later
cycle ends on a tabu set, its intensification phase is skipped.  Motivation: on P111122-20 the cycles keep re-converging on the same few depot sets (Zou's set {2,3,16} is
rarely reached).  Unlike `--dpm-memory` (D3, every start set at most once) only *converged* sets are excluded.

**M2 `--pr-elite E` (assignment path relinking; E = 10, not tuned).**  An elite list keeps up to E feasible GRASP-iteration solutions with pairwise different customer-to-depot assignments (cheapest
kept).  At the end of every cycle the incumbent and a random elite **with the same open depot set but a different assignment** are relinked in a random direction: the customers whose depot differs
are moved, in random order, from the initiating solution towards the guiding solution's depots (cheapest insertion into a route of the target depot; capacity violations allowed, the strategic-oscillation
local search repairs them); the half-way and the final point are improved with the usual local search + ILS.  Results enter the elite list, the route pool and, if better, the incumbent.
Motivation: the gap to Zou et al. is 66 % assignment inside the right depot set (about 4 % of the customers at another depot), concentrated on tightly capacitated instances (P122112-10).

## Pilots (`plan.json`)

| pilot | instance | arms (paired by seed, 1..30) | CPU budget | status |
|---|---|---|---|---|
| `p3_tabu` | tuzun/P111122-20 (n=100, m=20, Ng=3) | B1 vs B1 + `--dpm-tabu` | cluster-equivalent | primary |
| `p7_pr` | tuzun/P122112-10 (n=200, m=10, Ng=3) | B1 vs B1 + `--pr-elite 10` | cluster-equivalent | primary |
| `p7_pr_x4` | tuzun/P122112-10 | B1 vs B1 + `--pr-elite 10` | 4 x cluster-equivalent | exploratory (no criterion; reported separately) |

*B1 flags* = `pilot/arms/B1.flags` (identical to the campaign).  *Budget*: GitHub runners are not the cluster (about 3-8 x faster per CPU second).  The cluster budget of the study is 3n CPU s; the control arm
completed on average **473.7 iterations (P111122-20) and 59.2 iterations (P122112-10)** in it (`study_results/b1_tuned.tar.gz`).  A calibration job runs B1 with `--max-iter` set to these iteration counts
(4 seeds in parallel, same runner type) and the mean CPU time it needs is the CPU limit of the pilot ("cluster-equivalent budget"); the set-partitioning time is inside the limit, as in the campaign.
The two arms of a seed block run one after the other on the same runner (order alternates between blocks), 4 seeds in parallel; every run is verified with `llrp_tools verify`.
Estimated cost: calibrated limits are expected to be 30-120 s per run, i.e. about 1-3 CPU hours per pilot arm pair (the x4 pilot about 4 times that).

## Criteria (X = new arm, C = control B1; gap = % above the BKS of `bks/LLRP_BKS.csv`)

* **P0 (primary)**: mean gap(X) <= mean gap(C) - 0.15 points **and** one-sided Mann-Whitney U (X < C) p < 0.01.
* **P1**: more runs reach BKS + 0.005 with X than with C.
* **P2**: more runs end at or below the RLHEA average of Zou et al. (P111122-20: 3604.37, P122112-10: 6043.38) with X than with C.
* **S (safety)**: 30/30 runs feasible with independent verification OK in both arms; CPU time / limit: mean <= 1.01 and max <= 1.07 (B1 on the cluster: max 1.065).
* Descriptive (no criterion): bootstrap CI of the mean difference, seed-paired Wilcoxon, mechanism counters (`tabu.*`, `pr.*`), final open set equal to Zou's set, allocation (routes per depot) equal to Zou's (8, 8, 5) on P122112-10.

**Reading.**  S failed -> the quality numbers are not read.  P0 and S met -> the mechanism is a *candidate*: a **new pre-registered generalisation test** (several hard instances, n >= 100, including some where B1 is already
at the BKS, with a harm criterion like Z of the B1 campaign) is required before any claim; a single-instance pilot chosen because B1 is weakest there carries selection bias (lesson of the V1 pilot).  P0 not met -> not adopted, reported as a negative result.
Exploratory runs never replace a primary result.

## Limitations (stated in advance)

* One instance per mechanism; the instances are those where B1 is furthest behind Zou et al. (selection bias).  E = 10, the relink points (half way and end), once per cycle, and the tabu rules were fixed
  before the pilot and are not tuned.
* Runner hardware differs from the cluster; the iteration-matched budget removes the speed difference only approximately (calibration noise).  Absolute gaps are compared with the cluster B1 only as a plausibility check.
* Time-limited runs are not bit-reproducible; a run can be reproduced with `--max-iter` (iterations column of `run.csv`).
