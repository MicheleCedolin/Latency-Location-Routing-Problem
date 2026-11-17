# Converged-set tabu (`--dpm-tabu`): pre-registered generalisation test on the HPC cluster

Written on 2026-11-17 **before any result of this test existed**; committed to the repository (branch `pilot/v8`, file `pilot/GENERALIZATION_PLAN.md`) before the jobs are submitted.
Engine: `llrp_fast_v8` (= v7 + two experimental mechanisms, default off; with the new flags off it reproduces v7 bit for bit, checked by `g_selfcheck.sh` and by the GitHub workflow `pilot.yml`).

## Question
The GitHub pilot (17 Nov 2026, instance P111122-20, 30 paired seeds, iteration-matched budget) gave a mean gap drop of 0.245 points (95 % bootstrap CI -0.477..-0.007), one-sided
Mann-Whitney p = 0.092 and 8 -> 14 runs at or below the RLHEA average.  The pre-registered pilot criterion P0 (p < 0.01) was **not** met, so the mechanism was not adopted.
This test asks (i) whether the effect replicates on fresh seeds, (ii) whether it appears on the other instances where B1 lags RLHEA most, (iii) whether it harms the instances where B1 is already good, and
(iv) (exploratory) which of the two rules of the mechanism produces the effect.

## Mechanism (unchanged from the pilot)
A GRASP cycle = 9 diversification iterations (start depot sets drawn by `--dpm-rank 10,0.25`) followed by 5 intensification iterations from the best diversification set.
`--dpm-tabu`: the depot sets on which a cycle converged (best diversification set; open set of the best intensification solution) are tabu for the rest of the run.
*Draw rule*: later start-set draws never return a tabu set.  *Skip rule*: if the diversification phase of a later cycle ends on a tabu set, its intensification phase is skipped
(in the pilot 78 % of the cycles were skipped, so part of the gain may be a budget shift from intensification to diversification, not the tabu on start sets).
`--dpm-tabu-parts draw|skip|both` (new in this package; default both = the pilot arm) switches the two rules separately.

## Arms (flags = `flags/*.flags`)
| arm | flags | stage |
|---|---|---|
| B1 | campaign flags of B1 (V1 depot layer + route pool/SP), identical to `study_results/b1_tuned` | G1, G2 (control, run concurrently) |
| B1_tabu | B1 + `--dpm-tabu` | G1, G2 (primary) |
| B1_tabudraw | B1 + `--dpm-tabu --dpm-tabu-parts draw` | G1 (exploratory) |
| B1_tabuskip | B1 + `--dpm-tabu --dpm-tabu-parts skip` | G1 (exploratory) |

## Design
* **Instances.**  The 57 instances with n > 75 of the B1 campaign.  G1 = the 7 instances where B1 lags the RLHEA average most (they contain 87 % of the total positive difference; selected from the archived B1 campaign,
  not from this test): P111122-20 (the discovery instance of the mechanism), P122112-10, P121112-10, P122212-10, P121212-10, P123112-10, P122122-20.  G2 = the other 50 instances.
* **Seeds and budget.**  Seeds 101..130 (fresh; the B1 archive used 1..30, the GitHub pilot 1..30); CPU limit 3n s per run including the set-partitioning time (as in the B1 campaign); one process per run.
* **Concurrency.**  The queue order is limit (descending), instance, seed, arm: the arms of the same (instance, seed) are adjacent in the queue and run at the same time, mostly on the same node,
  so that load and hardware drift hit every arm alike.  The B1 archive (seeds 1..30, run earlier) is used only as a drift check and is not the control.
* **Verification.**  Every run is independently verified with `llrp_tools verify` before it is accepted (otherwise it is re-queued as failed).
* **Stages.**  G1 = 7 instances x 4 arms x 30 seeds = 840 runs, 130 CPU-h.  G2 = 50 instances x 2 arms x 30 seeds = 3000 runs, 343 CPU-h; **G2 is submitted only if G1 passes (R, H and S)**.

## Cost (CPU limits; ideal wall time = CPU-h / slots x 1.04, all jobs starting together)
| stage | runs | CPU-h | 24 slots | 48 slots | 96 slots |
|---|---|---|---|---|---|
| G1 (4 arms) | 840 | 130 | 5.6 h | 2.8 h | 1.4 h |
| G1 without the two exploratory arms (`ARMS="B1 B1_tabu"`) | 420 | 65 | 2.8 h | 1.4 h | 0.7 h |
| G2 (2 arms) | 3000 | 343 | 14.8 h | 7.4 h | 3.7 h |

## Pre-registered criteria (implemented in `analyze_g.py`; gap = % above the BKS of `bks/LLRP_BKS.csv`)
* **R** (replication, discovery instance P111122-20): one-sided Mann-Whitney U (B1_tabu < B1) over the 30 runs, p < 0.05.
* **H** (the other 6 G1 instances): mean over the 6 instances of (instance mean gap of B1_tabu - instance mean gap of B1) <= -0.10 points **and** B1_tabu better on >= 5 of the 6.
* **Z** (harm, G2): the number of instances where B1_tabu is worse by >= 0.10 points (difference of instance means) **and** one-sided Mann-Whitney U (B1_tabu > B1) p < 0.05 is **<= 3 of 50**.
* **S** (safety, every stage): all runs feasible and verified in every arm; CPU time / limit: mean <= 1.01 and max <= 1.07 per arm.  Reported, not a criterion: mean ratio of iterations B1_tabu / B1 (outside 0.85..1.15 the quality numbers are read with caution).
* **G0** (secondary, not required): one-sided Wilcoxon signed-rank over the 50 instance-mean differences p < 0.01 and mean difference <= -0.03 points.
* **Adoption candidate** = R, H, Z and S all hold.  If G1 fails (H or S), G2 is not run and the mechanism is not adopted.  If R fails but H and S hold, G2 may be run (author's decision); the replication failure is then reported.
* Exploratory (no criterion): decomposition table of the four arms on G1, number of new BKS (< BKS - 0.005), runs at BKS + 0.005, runs at or below the RLHEA average, mechanism counters, drift check against the B1 archive.
  Stated in advance: if B1_tabuskip is about as good as B1_tabu and B1_tabudraw about as bad as B1, the gain comes from skipping intensification, not from the tabu on start sets.

## Limitations (stated in advance)
* The discovery instance is part of G1 (as replication, with fresh seeds); it is excluded from H and from G2.  The other six G1 instances are the weakest ones of the same B1 campaign (selection on B1's gap, not on the effect of the mechanism).
* A positive result is "adoption candidate" for the final B1 configuration; a manuscript claim needs the author's decision and a new label for the configuration.  The mechanism is not tuned (tabu rule and list handling fixed before the pilot).
* The HPC nodes are shared and older-generation; the concurrent control removes common drift but not node-to-node differences.  Time-limited runs are not bit-reproducible; a run is reproduced with `--max-iter <iterations>` (same seed, flags, binary).
* Gap statistics at the 0.1-point level on single hard instances are noisy (sd of single runs 0.2-0.5 points); H and R are therefore deliberately modest and Z is a count, not an average.
