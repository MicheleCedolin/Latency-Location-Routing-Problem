# Route pool + DP + set partitioning (post-hoc multi-start recombination)

Runs read: 6900; runs whose recomputed latency differs from `Total Latency` by > 1e-6 (relative): 0; SP solutions that failed the independent audit: 0. A hit is a value <= BKS + 0.005.

## Group `B1`  (57 instances)

| n class | # | hit best | hit SP raw | hit SP+DP | hit SP+DP+pub | gap best | gap SP+DP | gap SP+DP+pub |
|---|---|---|---|---|---|---|---|---|
| 100 | 25 | 23 | 23 | 23 | 24 | 0.001 | 0.001 | 0.000 |
| 117-134 | 2 | 2 | 2 | 2 | 1 | -0.000 | -0.000 | -0.000 |
| 150 | 12 | 11 | 11 | 11 | 11 | 0.018 | 0.018 | 0.018 |
| 200 | 18 | 8 | 12 | 12 | 17 | 0.055 | 0.044 | -0.000 |
| all | 57 | 44 | 48 | 48 | 53 | 0.022 | 0.018 | 0.004 |

Published solution improved by SP+DP+pub (file valid and its cost matches the BKS): 1 instance(s)
- P123112-10: 4842.0473 -> 4842.0455 (BKS 4842.05)

Coverage of the published routes by the pool of `B1` (instances with SP+DP gap > 0.3 %):

| instance | gap best | gap SP+DP | gap SP+DP+pub | pub routes | exact | same set | other depot | none | customers on exact routes |
|---|---|---|---|---|---|---|---|---|---|
| P122112-10 | 0.757 | 0.742 | 0.000 | 21 | 11 | 0 | 0 | 10 | 50 % |

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

## Group `UNION`  (58 instances)

| n class | # | hit best | hit SP raw | hit SP+DP | hit SP+DP+pub | gap best | gap SP+DP | gap SP+DP+pub |
|---|---|---|---|---|---|---|---|---|
| <=75 | 1 | 1 | 1 | 1 | 1 | -0.000 | -0.000 | -0.000 |
| 100 | 25 | 24 | 24 | 24 | 24 | 0.000 | 0.000 | 0.000 |
| 117-134 | 2 | 2 | 2 | 2 | 1 | -0.000 | -0.000 | -0.000 |
| 150 | 12 | 11 | 11 | 11 | 11 | 0.018 | 0.018 | 0.018 |
| 200 | 18 | 8 | 12 | 12 | 17 | 0.050 | 0.034 | -0.000 |
| all | 58 | 46 | 50 | 50 | 54 | 0.019 | 0.014 | 0.004 |

Published solution improved by SP+DP+pub (file valid and its cost matches the BKS): 1 instance(s)
- P123112-10: 4842.0473 -> 4842.0455 (BKS 4842.05)

Coverage of the published routes by the pool of `UNION` (instances with SP+DP gap > 0.3 %):

| instance | gap best | gap SP+DP | gap SP+DP+pub | pub routes | exact | same set | other depot | none | customers on exact routes |
|---|---|---|---|---|---|---|---|---|---|
| P122112-10 | 0.675 | 0.571 | 0.000 | 21 | 12 | 0 | 0 | 9 | 56 % |

Published files that are missing, infeasible or whose cost differs from the BKS (their routes are still used as columns when each route is feasible): Or117-14, P112222-20, P122122-20, P131122-20

