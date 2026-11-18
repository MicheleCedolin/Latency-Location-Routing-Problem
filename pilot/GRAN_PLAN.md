# Granular-neighbourhood test: B1 + `--gran 20` versus the archived B1 campaign (pre-registered)

Written and committed **before any result of this test exists**. Package: `llrp_gran` (HPC, SGE task pool; scripts are not part of the repository, the analysis script `analyze_r.py` and this plan are archived with the results).

## Question
Does adding granular neighbourhoods (Toth & Vigo 2003; `--gran D` of `llrp_fast_v7`, D = 0 switches it off) to B1 raise the number of GRASP iterations within the same CPU budget and lower the mean gap at n = 200? D = 20 is the value selected by irace in Zou et al. (2024, RLHEA; candidate set {10, 15, 20, 25, 30}).

## Design
Engine `llrp_fast_v7`, unchanged source. Arm `B1_gran20` = B1 flags + `--gran 20`. No concurrent control arm: the control is the archived B1 campaign (same cluster, engine and flags, seeds 1..30, CPU limit 3n s including set partitioning; 57 instances with n > 75). New runs: the same 57 instances, seeds 1..30, 3n s CPU, ~204 CPU-hours, queue ordered by decreasing limit (n = 200 first). Every run independently verified (`llrp_tools verify`). No instance, seed or D was selected after looking at results.

## Criteria (delta = mean gap of B1_gran20 minus mean gap of archived B1, per instance, percentage points above the BKS)
- P1 (efficacy, the 18 instances with n = 200): mean delta <= -0.03 and one-sided Wilcoxon signed-rank (B1_gran20 < B1) p < 0.05.
- P2 (no harm, the other 39 instances): mean delta <= +0.02 and at most 3 harmed instances (delta >= +0.10 and one-sided Mann-Whitney U (B1_gran20 > B1) p < 0.05).
- P3 (mechanism, n = 200): median over instances of (median iterations B1_gran20 / median iterations B1) >= 1.5.
- S (safety): every run feasible and verified; CPU time / limit: mean <= 1.01, max <= 1.07.
- Adoption candidate: P1, P2, P3 and S all hold on the full 57 instances. Otherwise not adopted. Stage `n200` alone can only evaluate P1, P3, S. Zou comparison, best-of-30 hits and new BKS are descriptive.

## Known caveats (stated in advance)
The control is not concurrent (node load may differ slightly). The engine's `--gran` is a filter inside the move loops, not a neighbour-list traversal, so its speed-up is smaller than that of a list-based implementation (measured in a sandbox, 40 s CPU, one seed, B1 flags: iteration ratio 2.04 / 2.16 / 2.07 / 1.53 on four n = 200 instances, 1.99 on an n = 150 instance, 1.15 on an n = 100 instance at 20 s). The definition of the restricted moves may differ in detail from the one in RLHEA. Other parameters were not re-tuned for `--gran 20`.
