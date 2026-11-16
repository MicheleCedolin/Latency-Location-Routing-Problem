# Route pool + DP + set partitioning (post-hoc multi-start recombination)

Runs read: 8040; runs whose recomputed latency differs from `Total Latency` by > 1e-6 (relative): 0; SP solutions that failed the independent audit: 0. A hit is a value <= BKS + 0.005.

## Group `ext10`  (58 instances)

| n class | # | hit best | hit SP raw | hit SP+DP | hit SP+DP+pub | gap best | gap SP+DP | gap SP+DP+pub |
|---|---|---|---|---|---|---|---|---|
| <=75 | 1 | 1 | 1 | 1 | 1 | -0.000 | -0.000 | -0.000 |
| 100 | 25 | 20 | 22 | 22 | 24 | 0.021 | 0.007 | 0.000 |
| 117-134 | 2 | 2 | 2 | 2 | 1 | -0.000 | -0.000 | -0.000 |
| 150 | 12 | 6 | 8 | 8 | 11 | 0.082 | 0.050 | 0.021 |
| 200 | 18 | 0 | 5 | 5 | 16 | 0.320 | 0.161 | 0.000 |
| all | 58 | 29 | 38 | 38 | 53 | 0.125 | 0.063 | 0.005 |

Published solution improved by SP+DP+pub (file valid and its cost matches the BKS): 1 instance(s)
- P123112-10: 4842.0473 -> 4842.0455 (BKS 4842.05)

Coverage of the published routes by the pool of `ext10` (instances with SP+DP gap > 0.3 %):

| instance | gap best | gap SP+DP | gap SP+DP+pub | pub routes | exact | same set | other depot | none | customers on exact routes |
|---|---|---|---|---|---|---|---|---|---|
| P121222-20 | 0.797 | 0.797 | 0.000 | 21 | 14 | 0 | 0 | 7 | 66 % |
| P121112-10 | 0.797 | 0.679 | 0.000 | 21 | 17 | 0 | 0 | 4 | 82 % |
| P122112-10 | 0.675 | 0.586 | 0.000 | 21 | 8 | 0 | 0 | 13 | 36 % |
| P121212-10 | 0.405 | 0.405 | -0.000 | 21 | 16 | 0 | 0 | 5 | 76 % |

## Group `tuned`  (76 instances)

| n class | # | hit best | hit SP raw | hit SP+DP | hit SP+DP+pub | gap best | gap SP+DP | gap SP+DP+pub |
|---|---|---|---|---|---|---|---|---|
| <=75 | 19 | 18 | 18 | 18 | 19 | 0.020 | 0.020 | -0.000 |
| 100 | 25 | 14 | 18 | 18 | 24 | 0.064 | 0.030 | 0.000 |
| 117-134 | 2 | 2 | 2 | 2 | 1 | -0.000 | -0.000 | -0.000 |
| 150 | 12 | 4 | 7 | 7 | 11 | 0.246 | 0.164 | 0.029 |
| 200 | 18 | 0 | 2 | 2 | 16 | 0.906 | 0.746 | 0.000 |
| all | 76 | 38 | 47 | 47 | 71 | 0.279 | 0.217 | 0.005 |

Published solution improved by SP+DP+pub (file valid and its cost matches the BKS): 1 instance(s)
- P123112-10: 4842.0473 -> 4842.0455 (BKS 4842.05)

Coverage of the published routes by the pool of `tuned` (instances with SP+DP gap > 0.3 %):

| instance | gap best | gap SP+DP | gap SP+DP+pub | pub routes | exact | same set | other depot | none | customers on exact routes |
|---|---|---|---|---|---|---|---|---|---|
| P121222-20 | 4.776 | 4.776 | 0.000 | 21 | 9 | 0 | 0 | 12 | 43 % |
| 200-10-1b-10 | 3.131 | 3.131 | -0.000 | 22 | 6 | 2 | 0 | 14 | 28 % |
| P131222-20 | 1.457 | 1.436 | -0.000 | 16 | 6 | 1 | 0 | 9 | 37 % |
| P122112-10 | 1.670 | 1.332 | 0.000 | 21 | 5 | 0 | 0 | 16 | 22 % |
| P121212-10 | 1.258 | 1.257 | -0.000 | 21 | 9 | 1 | 0 | 11 | 43 % |
| P121112-10 | 1.112 | 1.112 | 0.000 | 21 | 12 | 0 | 0 | 9 | 58 % |
| P121122-20 | 0.888 | 0.658 | -0.000 | 22 | 17 | 1 | 0 | 4 | 78 % |
| P111212-10 | 0.525 | 0.430 | 0.000 | 10 | 4 | 0 | 0 | 6 | 39 % |
| 50-5-2BIS-5 | 0.386 | 0.386 | 0.000 | 12 | 8 | 0 | 0 | 4 | 66 % |
| P131122-20 | 0.349 | 0.349 | 0.349 | 16 | 0 | 0 | 0 | 16 | 0 % |
| P123112-10 | 0.680 | 0.325 | -0.000 | 22 | 13 | 0 | 0 | 9 | 57 % |

## Group `UNION`  (76 instances)

| n class | # | hit best | hit SP raw | hit SP+DP | hit SP+DP+pub | gap best | gap SP+DP | gap SP+DP+pub |
|---|---|---|---|---|---|---|---|---|
| <=75 | 19 | 18 | 18 | 18 | 19 | 0.020 | 0.020 | -0.000 |
| 100 | 25 | 20 | 23 | 23 | 24 | 0.021 | 0.005 | 0.000 |
| 117-134 | 2 | 2 | 2 | 2 | 1 | -0.000 | -0.000 | -0.000 |
| 150 | 12 | 6 | 8 | 8 | 11 | 0.082 | 0.050 | 0.021 |
| 200 | 18 | 0 | 6 | 6 | 16 | 0.320 | 0.148 | 0.000 |
| all | 76 | 46 | 57 | 57 | 71 | 0.101 | 0.050 | 0.003 |

Published solution improved by SP+DP+pub (file valid and its cost matches the BKS): 1 instance(s)
- P123112-10: 4842.0473 -> 4842.0455 (BKS 4842.05)

Coverage of the published routes by the pool of `UNION` (instances with SP+DP gap > 0.3 %):

| instance | gap best | gap SP+DP | gap SP+DP+pub | pub routes | exact | same set | other depot | none | customers on exact routes |
|---|---|---|---|---|---|---|---|---|---|
| P121222-20 | 0.797 | 0.797 | 0.000 | 21 | 14 | 0 | 0 | 7 | 66 % |
| P121112-10 | 0.797 | 0.679 | 0.000 | 21 | 17 | 0 | 0 | 4 | 82 % |
| P122112-10 | 0.675 | 0.586 | 0.000 | 21 | 9 | 0 | 0 | 12 | 41 % |
| 50-5-2BIS-5 | 0.386 | 0.386 | 0.000 | 12 | 8 | 0 | 0 | 4 | 66 % |

Published files that are missing, infeasible or whose cost differs from the BKS (their routes are still used as columns when each route is feasible): Or117-14, P112222-20, P122122-20, P131122-20

