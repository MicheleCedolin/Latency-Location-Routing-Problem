# B1-E extension (pre-registered plan; the pilot passed)

> English translation of the Turkish original, which is no longer part of the repository. Content, numbers, criteria and identifiers are unchanged.

This document was written **before the extension result was seen** (`pilot/EAX_PLAN_X.md`). Pilot (PLAN_E.md): 4 instances, n=200 x 30 seeds -- P1, P2, S passed (P122112-10 -0.223, P122212-10 -0.094, 200-10-1-10 -0.069, P121122-20 -0.008 points; 120/120 valid). The arm, engine and parameters were NOT changed after the pilot (`B1_eax40`, `llrp_fast_v9`, binary sha256 0356d2b4...).

## Scope
- Evaluated set (39 new instances): the remaining 14 of n=200 + 25 instances with n<200 for which the archived B1 (control/B1_run.csv) NEVER reached the BKS (<= BKS+0.005) in 30 runs (n=100: 14, n=117: 1, n=150: 10). The selection rule looks only at the archived B1, not at B1-E results.
- 15 instances not run [the list contains 14 instances; see the correction in PLAN_Y_rest14.md]: n<200 instances for which the archived B1 reached the BKS in 30/30 runs (Mi134-8; the 100-customer instances P111112-10, P112112-10, P112122-20, P112212-10, P112222-20, P113112-10, P113122-20, P113212-10, P113222-20, 100-5-2b-5, 100-10-2b-10; P132212-10, P133222-20 [n=150]) -- there is no room for improvement. Results are reported only for the evaluated set; NO "no harm" claim is made for these (they can be run with `MODE=extall` if desired).
- 30 seeds (1..30), CPU limit 3n s (SP included; n=100: 300 s, 117: 351 s, 150: 450 s, 200: 600 s), total ~145 CPU-hours, ~4.5 hours (32 slots). Queue with the large limits first: first n=200 (14 task groups, ~2.3 h), then 150, 117, 100. Partial results can be analysed.

## Pre-specified criteria (delta = B1_eax40 mean gap - archived B1 mean gap, per instance, in percentage points above the BKS)
- **P1 (effectiveness, n=200, 18 instances = 4 pilot + 14 new):** mean delta <= -0.03 AND one-sided Wilcoxon signed-rank (B1_eax40 < B1) p < 0.05.
- **P2 (no harm, evaluated n<200 instances, 25):** mean delta <= +0.02 AND harm count <= 3 (harm: delta >= +0.10 AND one-sided Mann-Whitney U (B1_eax40 > B1) p < 0.05).
- **S (safety):** every run feasible and independently verified; CPU/limit mean <= 1.01, maximum <= 1.07.
- **Adoption candidate:** if P1, P2 and S all hold on the full set. Otherwise it is not adopted. The n=200 results alone are not sufficient; if P2 fails, only "effective at n=200" is stated (the manuscript decision lies with the user).
- Descriptive (not criteria): mechanism counters, comparison with Zou's published means (hardware not normalised), best-of-30 BKS hits, new BKS, table by class (n).

## Known caveats
1. The control is not concurrent (archive from 16 Nov).
2. The same 4 pilot instances are analysed together with the extension (pilot and extension are the same arm; the P1/P2 result of the pilot is already known, but the 18-instance P1 is evaluated together with the 14 new instances).
3. For P1 the 4 pilot instances were pre-selected as "hard" (selection bias): a separate summary of the 14 new instances is also reported.
4. The parameters (F=0.4, population 20) were not tuned on these data; there is no sensitivity analysis for F.
5. The implementation rebuilds Zou's MPEAX from the paper ("inspired by Zou").
