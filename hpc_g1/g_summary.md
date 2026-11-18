# Converged-set tabu: generalisation test (G1/G2), pre-registered analysis

runs read: 840; arms: B1, B1_tabu, B1_tabudraw, B1_tabuskip; instances: 7

## Per instance (mean over the runs of the arm; gap in % above BKS)

| instance | n | arm | runs | verify OK | mean gap | sd | median | best | <= BKS+0.005 | < BKS-0.005 | <= Zou f_avg | mean iters | CPU/limit mean (max) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P111122-20 | 100 | B1 | 30 | 30 | 0.906 | 0.341 | 1.019 | 0.028 | 0 | 0 | 3 | 390 | 0.995 (1.001) |
| P111122-20 | 100 | B1_tabu | 30 | 30 | 0.877 | 0.535 | 1.049 | 0.000 | 1 | 0 | 8 | 384 | 0.995 (1.000) |
| P111122-20 | 100 | B1_tabudraw | 30 | 30 | 0.772 | 0.533 | 1.080 | 0.000 | 1 | 0 | 9 | 383 | 0.995 (1.002) |
| P111122-20 | 100 | B1_tabuskip | 30 | 30 | 0.813 | 0.449 | 1.012 | 0.000 | 2 | 0 | 6 | 396 | 0.994 (1.002) |
| P121112-10 | 200 | B1 | 30 | 30 | 0.549 | 0.328 | 0.479 | 0.000 | 2 | 0 | 2 | 84 | 1.005 (1.015) |
| P121112-10 | 200 | B1_tabu | 30 | 30 | 0.773 | 0.353 | 0.730 | 0.028 | 0 | 0 | 1 | 85 | 1.006 (1.023) |
| P121112-10 | 200 | B1_tabudraw | 30 | 30 | 0.799 | 0.480 | 0.685 | 0.028 | 0 | 0 | 1 | 83 | 1.005 (1.025) |
| P121112-10 | 200 | B1_tabuskip | 30 | 30 | 0.604 | 0.350 | 0.604 | 0.000 | 1 | 0 | 2 | 83 | 1.004 (1.013) |
| P121212-10 | 200 | B1 | 30 | 30 | 0.367 | 0.225 | 0.330 | -0.000 | 1 | 0 | 9 | 92 | 1.006 (1.020) |
| P121212-10 | 200 | B1_tabu | 30 | 30 | 0.446 | 0.214 | 0.447 | 0.076 | 0 | 0 | 4 | 91 | 1.005 (1.015) |
| P121212-10 | 200 | B1_tabudraw | 30 | 30 | 0.407 | 0.166 | 0.441 | 0.034 | 0 | 0 | 4 | 91 | 1.007 (1.017) |
| P121212-10 | 200 | B1_tabuskip | 30 | 30 | 0.393 | 0.205 | 0.421 | -0.000 | 1 | 0 | 6 | 92 | 1.006 (1.019) |
| P122112-10 | 200 | B1 | 30 | 30 | 1.228 | 0.162 | 1.242 | 0.848 | 0 | 0 | 0 | 55 | 1.008 (1.037) |
| P122112-10 | 200 | B1_tabu | 30 | 30 | 1.235 | 0.223 | 1.219 | 0.784 | 0 | 0 | 0 | 54 | 1.007 (1.026) |
| P122112-10 | 200 | B1_tabudraw | 30 | 30 | 1.242 | 0.206 | 1.255 | 0.784 | 0 | 0 | 0 | 55 | 1.008 (1.065) |
| P122112-10 | 200 | B1_tabuskip | 30 | 30 | 1.217 | 0.221 | 1.142 | 0.848 | 0 | 0 | 0 | 54 | 1.006 (1.049) |
| P122122-20 | 200 | B1 | 30 | 30 | 0.220 | 0.091 | 0.204 | 0.075 | 0 | 0 | 3 | 88 | 1.005 (1.018) |
| P122122-20 | 200 | B1_tabu | 30 | 30 | 0.214 | 0.105 | 0.207 | 0.088 | 0 | 0 | 3 | 88 | 1.007 (1.023) |
| P122122-20 | 200 | B1_tabudraw | 30 | 30 | 0.216 | 0.096 | 0.210 | 0.088 | 0 | 0 | 4 | 90 | 1.006 (1.019) |
| P122122-20 | 200 | B1_tabuskip | 30 | 30 | 0.230 | 0.107 | 0.198 | 0.089 | 0 | 0 | 1 | 89 | 1.007 (1.014) |
| P122212-10 | 200 | B1 | 30 | 30 | 0.391 | 0.088 | 0.429 | 0.160 | 0 | 0 | 0 | 84 | 1.007 (1.017) |
| P122212-10 | 200 | B1_tabu | 30 | 30 | 0.323 | 0.144 | 0.409 | 0.000 | 1 | 0 | 1 | 85 | 1.006 (1.014) |
| P122212-10 | 200 | B1_tabudraw | 30 | 30 | 0.287 | 0.158 | 0.289 | 0.000 | 1 | 0 | 1 | 82 | 1.009 (1.022) |
| P122212-10 | 200 | B1_tabuskip | 30 | 30 | 0.368 | 0.123 | 0.424 | 0.059 | 0 | 0 | 0 | 84 | 1.006 (1.023) |
| P123112-10 | 200 | B1 | 30 | 30 | 0.211 | 0.224 | 0.106 | -0.000 | 4 | 0 | 4 | 92 | 1.007 (1.023) |
| P123112-10 | 200 | B1_tabu | 30 | 30 | 0.247 | 0.346 | 0.085 | -0.000 | 6 | 0 | 6 | 92 | 1.006 (1.016) |
| P123112-10 | 200 | B1_tabudraw | 30 | 30 | 0.199 | 0.296 | 0.076 | -0.000 | 5 | 0 | 5 | 94 | 1.006 (1.015) |
| P123112-10 | 200 | B1_tabuskip | 30 | 30 | 0.243 | 0.272 | 0.119 | -0.000 | 3 | 0 | 3 | 93 | 1.005 (1.020) |

## S: safety

- B1: 210 runs, not feasible/verified: 0, CPU/limit mean 1.005, max 1.037 -> PASS
- B1_tabu: 210 runs, not feasible/verified: 0, CPU/limit mean 1.004, max 1.026 -> PASS
- B1_tabudraw: 210 runs, not feasible/verified: 0, CPU/limit mean 1.005, max 1.065 -> PASS
- B1_tabuskip: 210 runs, not feasible/verified: 0, CPU/limit mean 1.004, max 1.049 -> PASS
- iteration parity (mean over instances of mean iterations B1_tabu / B1): 0.998 (range 0.984..1.017); note only, outside 0.85..1.15 the quality numbers are read with caution

## G1: hard instances (B1 vs B1_tabu)

- R (replication on P111122-20, fresh seeds): mean gap 0.906 -> 0.877 (-0.029); one-sided MWU p = 0.8398 -> **FAIL**
- H (other 6): per-instance difference of means (B1_tabu - B1): P122112-10 +0.007, P121112-10 +0.224, P122212-10 -0.068, P121212-10 +0.079, P123112-10 +0.036, P122122-20 -0.006
  mean +0.045 points, B1_tabu better on 2/6 -> **FAIL**

### Decomposition (exploratory; no criterion)

| arm | mean gap over the 7 instances | difference to B1 | difference to B1_tabu | mean cycles | mean skipped intensifications | mean draw skips |
|---|---|---|---|---|---|---|
| B1 | 0.553 | +0.000 | -0.035 | - | - | - |
| B1_tabu | 0.588 | +0.035 | +0.000 | 11.1 | 6.9 | 1.0 |
| B1_tabudraw | 0.560 | +0.007 | -0.028 | 8.5 | 0.0 | 0.6 |
| B1_tabuskip | 0.553 | -0.000 | -0.035 | 11.8 | 8.7 | 0.0 |

Reading rule (stated in advance): if B1_tabuskip is about as good as B1_tabu and B1_tabudraw about as bad as B1, the gain comes from skipping intensification (budget shift), not from the tabu on start sets.


## Verdict

G1 only: R False, H False, S True -> **G1 fails: do not run G2; mechanism not adopted** (R failed: the discovery-instance effect did not replicate)

## Reference: B1 cluster archive (seeds 1..30, different time; drift check of the concurrent control)

| instance | archive B1 mean gap | concurrent B1 mean gap | archive mean iters | concurrent mean iters |
|---|---|---|---|---|
| P111122-20 | 0.849 | 0.906 | 474 | 390 |
| P121112-10 | 0.454 | 0.549 | 93 | 84 |
| P121212-10 | 0.442 | 0.367 | 103 | 92 |
| P122112-10 | 1.255 | 1.228 | 59 | 55 |
| P122122-20 | 0.242 | 0.220 | 99 | 88 |
| P122212-10 | 0.348 | 0.391 | 94 | 84 |
| P123112-10 | 0.219 | 0.211 | 108 | 92 |
