# B1-E pilot: B1 + memetic MPEAX phase (pre-registered plan)

> English translation of the Turkish original, which was first committed in `43fa2e5` and remains in the git history. Content, numbers, criteria and identifiers are unchanged.

This document was written **before the pilot result was seen** (`pilot/EAX_PLAN.md`, branch `pilot/v8`). During development only P122112-10 (1 seed, 90 s) and P121212-10 (6 seeds, 150 s; NOT used in the pilot) were run; the pilot instances, seeds and parameters were not changed after these runs.

## Question
Does adding to B1 a phase resembling the structure of Zou et al. (2024, RLHEA) -- population + 3-parent edge assembly crossover (MPEAX) + distance/quality population management -- lower the mean gap of B1, especially on the tight-capacity n=200 instances where the B1-Zou gap is large? (Diagnosis: 66% of the gaps are different customer assignments within the same depot set; the route-pool SP of B1 only recombines whole routes, whereas MPEAX recombines at the level of edges inside routes.)

## Method (llrp_fast_v9, `--eax-split F`; with the flag off it is bit-identical to v7/v8 -- verified by `r_selfcheck.sh`)
- The first F=0.40 of the budget (excluding the final 3 s reserved for SP) is identical to B1 (GRASP + RVND-SO + ILS + V1 depot layer); every feasible GRASP-iteration solution enters the population (<=20 members): fitness = 0.55 * quality + 0.45 * edge distance to the nearest member (IDist); duplicates are rejected, the best member is never removed.
- Remaining 60%: in each generation 3 random parents; MPEAX = E-set from AB-cycles (one random cycle + all cycles that share a node with it), depots merged into one node, applied to parent 1; subtours are inserted into the cheapest arc; the result is combined with the third parent in the same way. If the number of routes > Nv, the lightest route is appended to the end of the closest route; if the number of open depots > Ng, the Ng most frequent depots among the parents (or Ng random ones) are kept and orphan routes go to the nearest depot; if < Ng, a random depot is opened. Capacity is not enforced by the crossover; the engine's RVND-SO local search (no ILS) repairs it (if no feasible solution results at the end of SO, beta is multiplied by 2.068, at most 12 times). The child enters the population; if it is within 1.01 of the best it is also added to the route pool. Mutation, population renewal and Q-learning are NOT included (not part of this test).
- Parameters (fixed, not tuned for this test): F=0.4, population 20, psi=0.55 (the value in Zou), esc=12, ILS=0, pool theta=0.01.

## Design
- Arm **B1_eax40** = B1 flags + `--eax-split 0.4 --eax-pop 20 --eax-psi 0.55 --eax-esc 12 --eax-ils 0 --eax-pool-theta 0.01` (no other difference; `r_preflight.sh` verifies).
- Control: not run; the **B1 archive** (`control/B1_run.csv`), run on the same cluster with the same engine source, flags and seeds (1..30), 3n s CPU.
- Scope (pilot): P122112-10, P122212-10 (tight capacity, large B1-Zou gap: H), P121122-20, 200-10-1-10 (reference: R); all n=200, 30 seeds, 600 s CPU (SP included), 120 tasks, 20 CPU-hours. Every run is verified by the independent `llrp_tools verify`.

## Pre-specified criteria (delta = B1_eax40 mean gap - archived B1 mean gap, per instance, in percentage points above the BKS)
- **P1 (effectiveness, H):** on both instances one-sided Mann-Whitney U (B1_eax40 < B1) p < 0.05 AND the mean of the two deltas <= -0.10.
- **P2 (no harm, R):** no instance with (delta >= +0.10 AND one-sided MWU (B1_eax40 > B1) p < 0.05) AND the mean of the two deltas <= +0.02.
- **S (safety):** every run feasible and independently verified; CPU/limit mean <= 1.01, maximum <= 1.07.
- The pilot passes if P1, P2 and S all hold -> a separate plan is written for all of n=200 (18 instances, MODE=n200, ~90 CPU-hours). Otherwise the idea is closed and does not go into the manuscript.
- Descriptive (not criteria): mechanism counters (number of generations, children entering / rejected by the population, improvement of the best after the switch), comparison with Zou's published means (hardware not normalised), best-of-30 BKS hits, new BKS.

## Known caveats
1. The control is not concurrent (archive from the 16 Nov run); a difference in node load may cause a small bias. The analysis reports CPU/limit.
2. The implementation rebuilds Zou's MPEAX from the paper text (the source code was not published): details of AB-cycle generation, depot merging and repair may differ; it cannot be called "the same as Zou", only "inspired by Zou". It is not the whole of Zou's RLHEA with its 5000 generations, mutation, Q-learning and population renewal.
3. The pilot looks at only 4 instances; lesson from G1: the effect seen in one pilot may not repeat over the whole class. Passing is therefore not adoption by itself, but a condition for the n=200 extension.
4. The development instance P121212-10 is not in the pilot; F=0.4 is a heuristic choice, no sensitivity analysis (F) has been done.
