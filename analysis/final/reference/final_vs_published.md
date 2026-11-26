# Final method against the published algorithms

Source per instance: n <= 50 base method (standard budget), n = 75 base method (extended budget), n > 75 route-pool method B1 (extended budget). 30 runs each; Prins 50-5-2BIS-5 with the default rule (exactly Ng open depots).

## Quality by instance size (gap in % to the BKS)

| class | instances | source | gap of best | gap of mean | best <= BKS + 0.005 |
|---|---|---|---|---|---|
| n <= 50 | 18 | 1x | 0.021 | 0.022 | 17 / 18 |
| n = 75 | 1 | ext10 | 0.000 | 0.165 | 1 / 1 |
| n = 100 | 25 | B1 | 0.001 | 0.046 | 23 / 25 |
| n = 117/134 | 2 | B1 | 0.000 | 0.001 | 2 / 2 |
| n = 150 | 12 | B1 | 0.018 | 0.054 | 11 / 12 |
| n = 200 | 18 | B1 | 0.055 | 0.254 | 8 / 18 |
| all | 76 |  | 0.021 | 0.091 | 62 / 76 |

## RLHEA (Zou et al. 2024), paired comparison

| instances | our mean vs RLHEA avg: W / T / L | p | our best vs RLHEA best: W / T / L | p | mean gap ours / RLHEA (avg) | mean <= avg strict | mean <= avg (rounded) |
|---|---|---|---|---|---|---|---|
| all 76 instances | 23 / 26 / 27 | 0.579 | 2 / 60 / 14 | 0.0016 | 0.091 / 0.073 | 38 / 76 | 49 / 76 |
| n >= 75 (58) | 22 / 12 / 24 | 0.823 | 0 / 45 / 13 | 0.0015 | 0.113 / 0.096 | 29 / 58 | 34 / 58 |
| held-out n >= 75 (45) | 16 / 10 / 19 | 0.768 | 0 / 35 / 10 | 0.0051 | 0.120 / 0.095 | 22 / 45 | 26 / 45 |
| n >= 150 (30) | 15 / 2 / 13 | 0.891 | 0 / 19 / 11 | 0.0033 | 0.174 / 0.160 | 17 / 30 | 17 / 30 |
| n = 200 (18) | 8 / 1 / 9 | 0.435 | 0 / 8 / 10 | 0.0051 | 0.254 / 0.189 | 9 / 18 | 9 / 18 |

## Other published algorithms (all instances for which the algorithm has values)

| algorithm | instances | mean gap ours / theirs (Avg) | mean vs Avg: W / T / L | p | best vs Best: W / T / L | p |
|---|---|---|---|---|---|---|
| MS-VNS | 76 | 0.091 / 2.486 | 73 / 3 / 0 | 1.1e-13 | 63 / 12 / 1 | 9e-12 |
| M-ILS | 76 | 0.091 / 1.152 | 69 / 6 / 1 | 5.5e-13 | 57 / 18 / 1 | 2.1e-10 |
| SA-VND0 | 76 | 0.091 / 1.996 | 69 / 7 / 0 | 5.2e-13 | 62 / 13 / 1 | 5.4e-12 |
| SA-VND1 | 76 | 0.091 / 2.105 | 69 / 7 / 0 | 5.2e-13 | 62 / 14 / 0 | 7.6e-12 |
| SA-VND2 | 76 | 0.091 / 1.998 | 69 / 7 / 0 | 5.2e-13 | 61 / 14 / 1 | 8e-12 |
| SA-VND (best variant) | 76 | 0.091 / 1.896 | 69 / 7 / 0 | 5.2e-13 | 61 / 14 / 1 | 8e-12 |
| MA | 76 | 0.091 / 14.224 | 76 / 0 / 0 | 3.6e-14 | 75 / 1 / 0 | 5.3e-14 |
| GBILS (our mean vs their best) | 35 | 0.043 / 2.372 | 27 / 8 / 0 | 5.6e-06 | (same comparison) |

GBILS publishes best values only (35 usable instances: Prins 30 and 5 of the 10 Barreto instances). Its Christofides69 rows (50x5, 75x10, 100x10) are values of another variant of the instance and are left out (`GBILS_UNMATCHED`); Min-134-8 and Or-117-14 are not in its table; no Tuzun-Burke instance is.

Rules: ties |ours - theirs| <= 0.005; our best and mean rounded to two decimals; Wilcoxon signed-rank, two-sided, normal approximation without continuity correction on the paired gap differences, ties dropped; published times are not used (different hardware).

