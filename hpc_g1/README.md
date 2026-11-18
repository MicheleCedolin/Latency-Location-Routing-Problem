# Converged-set tabu, stage G1 (HPC cluster, 17-18 Nov 2026)

Pre-registered plan: branch `pilot/v8`, `pilot/GENERALIZATION_PLAN.md` (commit d1f3b35).  Analysis: `pilot/analyze_g.py` -> `g_summary.md`, `g_instances.csv` (per instance and arm), `g_runs.csv` (840 runs).
Raw archive of the 840 runs (per-run tars with run.csv, routes, logs, verify): `g_g1_results_20261118_0147.tgz`.

**Verdict (pre-registered criteria): G1 fails.**  R (replication on P111122-20, fresh seeds): mean gap 0.906 -> 0.877, one-sided Mann-Whitney p = 0.84 (pilot on GitHub runners: 0.766 -> 0.520).
H (other six instances): mean difference +0.045 points, B1_tabu better on 2 of 6.  S (safety) passes: 840/840 runs feasible and independently verified, CPU/limit mean 1.004-1.005, max 1.065.
G2 was therefore not run and the mechanism is not adopted.

Decomposition (exploratory): mean gap over the 7 instances B1 0.553, B1_tabu 0.588, B1_tabudraw 0.560, B1_tabuskip 0.553; no arm differs from the control.
Post hoc, descriptive: final open depot set equal to the RLHEA set {2,3,16} on P111122-20: B1 2/30, B1_tabu 7/30, B1_tabudraw 4/30, B1_tabuskip 4/30 (the gap did not follow).
Per-instance two-sided Mann-Whitney (B1_tabu vs B1, uncorrected, 7 instances): P121112-10 +0.224 (p = 0.01, worse), P122212-10 -0.068 (p = 0.02, better), all others p >= 0.19.
No run beat the BKS (< BKS - 0.005); runs at BKS + 0.005: B1 7, B1_tabu 8, B1_tabudraw 7, B1_tabuskip 7.
Cluster context: 24 worker jobs x 4 slots on 2 x Xeon E5-2698 v3 nodes (CentOS 7.4, kernel 3.10.0-693.5.2.el7), node load 55-64 on 64 hardware threads; the concurrent B1 control reached 0.82-0.92 of the iterations of the archived B1 runs.
