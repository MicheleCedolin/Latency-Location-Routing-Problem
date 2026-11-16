# Equal-time comparison with RLHEA and time to target

Time reference = published mean run time of RLHEA (other machine, other stopping rule; see bks/README.md). Gap = 100 (x - BKS) / BKS. `mean` = mean over instances of the per-instance 30-run mean; `best` = of the best of the runs; `pub` = the same quantity of RLHEA on the same instances. Only instances where >= 90 % of the runs reach f * T.

## Group `B1`

| f | instances | mean gap (ours) | mean gap (pub) | best gap (ours) | best gap (pub) | # mean <= pub avg | # best <= pub best |
|---|---|---|---|---|---|---|---|
| 0.5 | 57 | 0.484 | 0.098 | 0.094 | 0.000 | 3 | 34 |
| 1 | 57 | 0.279 | 0.098 | 0.050 | 0.000 | 12 | 40 |
| 1.2 | 57 | 0.233 | 0.098 | 0.041 | 0.000 | 17 | 40 |
| 1.5 | 56 | 0.170 | 0.092 | 0.018 | 0.000 | 20 | 41 |
| 2 | 49 | 0.108 | 0.077 | 0.012 | 0.000 | 24 | 39 |

f = 1 by size class:

| n class | # | mean gap (ours) | mean gap (pub) | best gap (ours) | # mean <= pub avg |
|---|---|---|---|---|---|
| 100 | 25 | 0.130 | 0.023 | 0.004 | 8 |
| 117-134 | 2 | 0.462 | 0.101 | -0.000 | 0 |
| 150 | 12 | 0.208 | 0.116 | 0.020 | 3 |
| 200 | 18 | 0.514 | 0.189 | 0.138 | 1 |

Time to the published average (+0.005): >= 1 run reaches it on 55 of 57 instances, >= half of the runs on 44; median hit time / T_pub: 0.67 over all reaching runs, 0.84 over the instance medians.

## Group `ext10`

| f | instances | mean gap (ours) | mean gap (pub) | best gap (ours) | best gap (pub) | # mean <= pub avg | # best <= pub best |
|---|---|---|---|---|---|---|---|
| 0.5 | 58 | 1.476 | 0.096 | 0.267 | 0.000 | 0 | 21 |
| 1 | 58 | 0.985 | 0.096 | 0.166 | 0.000 | 1 | 25 |
| 1.2 | 58 | 0.895 | 0.096 | 0.154 | 0.000 | 2 | 27 |
| 1.5 | 57 | 0.783 | 0.091 | 0.137 | 0.000 | 2 | 27 |
| 2 | 50 | 0.495 | 0.075 | 0.063 | 0.000 | 3 | 27 |

f = 1 by size class:

| n class | # | mean gap (ours) | mean gap (pub) | best gap (ours) | # mean <= pub avg |
|---|---|---|---|---|---|
| <=75 | 1 | 0.818 | 0.000 | -0.000 | 0 |
| 100 | 25 | 0.423 | 0.023 | 0.024 | 0 |
| 117-134 | 2 | 1.074 | 0.101 | -0.000 | 1 |
| 150 | 12 | 0.841 | 0.116 | 0.139 | 0 |
| 200 | 18 | 1.859 | 0.189 | 0.408 | 0 |

Time to the published average (+0.005): >= 1 run reaches it on 37 of 58 instances, >= half of the runs on 10; median hit time / T_pub: 0.98 over all reaching runs, 1.29 over the instance medians.

