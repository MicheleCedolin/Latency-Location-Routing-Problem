# B1-E: full-set analysis (18 n=200 + 25 evaluated n<200 + 14 previously skipped) versus archived B1

Runs read: 1710 (verified+feasible 1710); instances complete (30 runs): 57 of 57; incomplete: none

## Criteria (pre-registered)

P1 efficacy, n=200 (18 of 18 complete): mean delta -0.0574; one-sided Wilcoxon p = 0.0123; better 14 / worse 2  ->  **PASS**
P2 no harm, n<200 evaluated (25 of 25 complete): mean delta -0.0273; harmed 0 (-)  ->  **PASS**
P3 no harm, previously skipped 14 (14 of 14 complete): mean delta -0.0000 (B1 mean gap -0.00000 -> -0.00000); instances with delta >= +0.10: 0 (-)  ->  **PASS**
S safety: 1710 runs, 0 not feasible/verified; CPU/limit mean 0.9974 max 1.0029  ->  **PASS**

**Verdict: FULL-SET ADOPTION CANDIDATE (P1, P2, P3, S hold on all 57 instances)**

Mechanism (descriptive; 1710 runs): median generations 5614; improved best 2.7 per run; runs whose best improved after the switch: 891 of 1710; structural failures 0.00 per run

## By group and class (gap = % above the BKS; mean over instance means)

| group | instances | B1 (archive) | B1_eax40 | delta | Zou avg | better/worse/equal (tol 0.005) | best-of-30 hits B1 -> new |
|---|---|---|---|---|---|---|---|
| n=200 | 18 | 0.2539 | 0.1965 | -0.0574 | 0.1886 | 14/2/2 | 8 -> 13 |
| n<200 evaluated (ext) | 25 | 0.0721 | 0.0448 | -0.0273 | 0.0868 | 12/2/11 | 22 -> 23 |
| skipped 14 (rest14) | 14 | -0.0000 | -0.0000 | -0.0000 | 0.0010 | 0/0/14 | 14 -> 14 |
| ALL | 57 | 0.1118 | 0.0817 | -0.0301 | 0.0979 | 26/4/27 | 44 -> 50 |

All complete instances: two-sided Wilcoxon (new vs B1) p = 0.0001
Versus Zou et al. (RLHEA published averages; hardware not normalised): mean gap difference new-Zou -0.0162 (B1-Zou +0.0139); instances with mean gap <= Zou avg + 0.005: new 44, B1 38 of 57; two-sided Wilcoxon new vs Zou p = 0.0840 (B1 vs Zou p = 0.9272)
New best-known solutions (best run below BKS - 0.005): none

## Tails (descriptive)

| group | runs gap>0.5 B1 -> new | runs gap>1.0 B1 -> new | mean worst-of-30 B1 -> new | instances with delta >= +0.05 |
|---|---|---|---|---|
| n=200 | 75 -> 44 | 27 -> 23 | 0.520 -> 0.814 | 2 |
| n<200 evaluated (ext) | 24 -> 17 | 23 -> 10 | 0.187 -> 0.175 | 1 |
| skipped 14 (rest14) | 0 -> 0 | 0 -> 0 | 0.000 -> -0.000 | 0 |
| ALL | 99 -> 61 | 50 -> 33 | 0.246 -> 0.334 | 3 |

## Skipped-14 instances (per instance)

| instance | n | B1 mean gap | new mean gap | delta | worst-of-30 new | best-of-30 hit B1 -> new |
|---|---|---|---|---|---|---|
| 100-10-2b-10 | 100 | 0.00024 | 0.00024 | +0.00000 | 0.0002 | 1 -> 1 |
| 100-5-2b-5 | 100 | 0.00002 | 0.00002 | +0.00000 | 0.0000 | 1 -> 1 |
| P111112-10 | 100 | -0.00003 | -0.00003 | +0.00000 | -0.0000 | 1 -> 1 |
| P112112-10 | 100 | 0.00009 | 0.00009 | +0.00000 | 0.0001 | 1 -> 1 |
| P112122-20 | 100 | -0.00001 | -0.00001 | +0.00000 | -0.0000 | 1 -> 1 |
| P112212-10 | 100 | -0.00008 | -0.00008 | +0.00000 | -0.0001 | 1 -> 1 |
| P112222-20 | 100 | 0.00014 | 0.00014 | +0.00000 | 0.0001 | 1 -> 1 |
| P113112-10 | 100 | 0.00004 | 0.00004 | +0.00000 | 0.0000 | 1 -> 1 |
| P113122-20 | 100 | -0.00006 | -0.00006 | +0.00000 | -0.0001 | 1 -> 1 |
| P113212-10 | 100 | -0.00022 | -0.00022 | +0.00000 | -0.0002 | 1 -> 1 |
| P113222-20 | 100 | -0.00005 | -0.00005 | +0.00000 | -0.0001 | 1 -> 1 |
| Mi134-8 | 134 | -0.00002 | -0.00002 | +0.00000 | -0.0000 | 1 -> 1 |
| P132212-10 | 150 | -0.00004 | -0.00004 | +0.00000 | -0.0000 | 1 -> 1 |
| P133222-20 | 150 | -0.00002 | -0.00005 | -0.00003 | -0.0000 | 1 -> 1 |

## Five worst deltas over all complete instances

- P123212-10 (n=200, n200): delta +0.4780 (B1 0.0006 -> new 0.4786; worst-of-30 new 4.779)
- 200-10-2b-10 (n=200, n200): delta +0.0972 (B1 0.0246 -> new 0.1218; worst-of-30 new 1.371)
- P131212-10 (n=150, ext): delta +0.0589 (B1 0.0745 -> new 0.1334; worst-of-30 new 0.765)
- 100-10-3b-10 (n=100, ext): delta +0.0258 (B1 0.0208 -> new 0.0466; worst-of-30 new 0.318)
- 100-5-3b-5 (n=100, ext): delta +0.0037 (B1 0.0084 -> new 0.0121; worst-of-30 new 0.056)

Note: the control is the archived B1 campaign (seeds 1-30), not a concurrent arm.
