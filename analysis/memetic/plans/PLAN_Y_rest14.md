# B1-E: running the skipped 14 instances (pre-registered plan)

> English translation of the Turkish original, which was first committed in `43fa2e5` and remains in the git history. Content, numbers, criteria and identifiers are unchanged.

This document was written **before the results of these 14 instances were seen**. Previous stages: pilot (PLAN_E.md) and extension (PLAN_X.md) -- P1, P2, S passed (43 instances; at n=200 mean gap 0.254 -> 0.197, on the 25 evaluated n<200 instances 0.072 -> 0.045). The arm, engine and parameters were NOT changed (`B1_eax40`, `llrp_fast_v9`, binary sha256 0356d2b4...).

## Correction
PLAN_X.md and README_X.txt say "15 instances"; the correct number is **14** (43 evaluated + 14 skipped = 57). The list (14 names) was correct: `instances_rest14.txt`.

## Scope
- 14 instances: n<200 instances for which the archived B1 reached the BKS in 30/30 runs and that were skipped in the extension: 100-10-2b-10, 100-5-2b-5, Mi134-8, P111112-10, P112112-10, P112122-20, P112212-10, P112222-20, P113112-10, P113122-20, P113212-10, P113222-20, P132212-10, P133222-20. The mean gaps of the archived B1 are smaller than |0.0003| (rounding level).
- Same arm, same seeds (1..30), CPU limit 3n s (SP included; n=100: 300 s, 134: 402 s, 150: 450 s). 420 tasks, ~38.4 CPU-hours; ideal ~1.3 h with 32 slots (excluding queue waiting).
- Purpose: to be able to report B1-E on the SAME 57 instances as B1, V1 and Zou, and to test the "no harm" claim on these 14 (the archived B1 is already at the ceiling here; no improvement is expected, only harm is sought).

## Pre-specified criterion (P3) and full-set decision
delta = B1_eax40 mean gap - archived B1 mean gap (percentage points above the BKS).
- **P3 (no harm, 14 instances):** mean delta <= +0.02 AND the number of instances with delta >= +0.10 is <= 1. (As opposed to P2, no p-value is required: the control has ~zero variance on these instances, and rare tail events (for example 3 bad runs out of 30) would not show in a p-value.)
- Note: the mean rule alone catches a SINGLE tail event with delta larger than ~0.28 (for example +0.478 as for P123212-10; 0.28/14 > 0.02); the count rule allows a single medium-sized event in the 0.10-0.28 range.
- **S:** every run feasible and independently verified; CPU/limit mean <= 1.01, maximum <= 1.07.
- **Full-set adoption candidate:** if P1, P2 (unchanged, passed), P3 and S hold when all 57 instances are completed. If P3 fails, B1-E is reported only for the 43 evaluated instances and the harm risk in the skipped class is stated explicitly; the manuscript decision lies with the user.
- Rationale for the thresholds: the P3 thresholds were set after the extension results (43 instances) had been seen, but before the results of these 14; tail events were observed on three of the 43 instances (P123212-10 +0.478, 200-10-2b-10 +0.097, P131212-10 +0.059), so the harm count was kept tight (<= 1).
- Descriptive (not criteria): tail table (number of runs with gap > 0.5 / > 1.0, mean worst-30), comparison with Zou (hardware not normalised), best-of-30 BKS hits, new BKS, mechanism counters.

## Caveats
1. The control is not concurrent (archive from 16 Nov).
2. On these 14 instances there is no room for improvement; the result answers only the question "is there harm".
3. The parameters (F=0.4, population 20) were not tuned; a sensitivity trial of F for the tail risk is outside this plan.
