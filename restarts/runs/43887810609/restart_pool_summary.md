# Equal CPU: one long run (ext10) vs 10 pooled short runs (tuned); 10 draws; 58 instances

| class | inst | long run mean gap % | short best-of-k gap % | short SP+DP gap % | SP < long | long best-of-30 gap % |
|---|---|---|---|---|---|---|
| <=75 | 1 | 0.164 | 0.282 | 0.279 | 0/1 | -0.000 |
| 100 | 25 | 0.182 | 0.142 | 0.088 | 21/25 | 0.021 |
| 117-134 | 2 | 0.575 | 0.610 | 0.320 | 1/2 | -0.000 |
| 150 | 12 | 0.505 | 0.394 | 0.316 | 10/12 | 0.082 |
| 200 | 18 | 1.232 | 1.289 | 1.138 | 15/18 | 0.320 |
| ALL | 58 | 0.588 | 0.569 | 0.472 | 47/58 | 0.125 |

Wilcoxon (long mean vs SP+DP of 10 short runs, paired by instance): p = 1.89e-05; median difference in latency 1.643

Instances whose mean is at most the published average of RLHEA: long run 6, SP of short runs 12 (of 58).
