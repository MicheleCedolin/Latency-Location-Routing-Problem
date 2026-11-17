# v8 pilots: results

## p3_tabu  (tuzun/P111122-20, B1 vs B1_tabu)

CPU limit per run: 145 s (cluster-equivalent budget x 1); BKS 3597.64; Zou f_avg 3604.37; Zou depots [2, 3, 16]

Cluster B1 reference (30 runs, 3n s CPU): mean gap 0.849, sd 0.400, best 0.028, mean iterations 473.7

| arm | runs | feasible+verify | mean gap % | sd | median | best | runs <= BKS+0.005 | runs <= Zou f_avg | mean iters | CPU/limit mean (max) | final set = Zou set | allocation = Zou |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | 30 | 30 | 0.766 | 0.442 | 1.019 | 0.000 | 1 | 8 | 647.2 | 0.986 (1.001) | 4 |  |
| B1_tabu | 30 | 30 | 0.520 | 0.495 | 0.276 | 0.000 | 1 | 14 | 633.3 | 0.982 (0.986) | 12 |  |

mean gap B1_tabu - B1 = -0.245 points (bootstrap 95% CI -0.477 .. -0.007); one-sided Mann-Whitney U (B1_tabu < B1): p = 0.09213; paired (same seed) Wilcoxon two-sided p = 0.1385; seeds with B1_tabu better: 19 / 30

**Pre-registered criteria** (PLAN.md): P0 (mean gap drop >= 0.15 points and p < 0.01): **fail** | P1 (more runs at BKS+0.005: 1 vs 1): **fail** | P2 (more runs <= Zou f_avg: 14 vs 8): **PASS** | S (30/30 feasible + verify OK per arm, CPU/limit mean <= 1.01 and max <= 1.07): **PASS**

Verdict: no adoption: P0 not met

Mechanism counters, arm B1_tabu (mean per run): tabu.adds=15.10, tabu.cycles=62.13, tabu.draw_skips=2.87, tabu.on=1.00, tabu.resets=0.00, tabu.size_end=15.10, tabu.skipped_int=48.37


## p7_pr  (tuzun/P122112-10, B1 vs B1_pr)

CPU limit per run: 145 s (cluster-equivalent budget x 1); BKS 6018.59; Zou f_avg 6043.38; Zou depots [5, 6, 7]

Cluster B1 reference (30 runs, 3n s CPU): mean gap 1.255, sd 0.224, best 0.757, mean iterations 59.2

| arm | runs | feasible+verify | mean gap % | sd | median | best | runs <= BKS+0.005 | runs <= Zou f_avg | mean iters | CPU/limit mean (max) | final set = Zou set | allocation = Zou |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | 30 | 30 | 1.282 | 0.245 | 1.282 | 0.757 | 0 | 0 | 51.8 | 0.991 (1.004) | 17 | 1 |
| B1_pr | 30 | 30 | 1.244 | 0.216 | 1.296 | 0.549 | 0 | 0 | 49.0 | 0.991 (1.010) | 16 | 1 |

mean gap B1_pr - B1 = -0.038 points (bootstrap 95% CI -0.154 .. +0.076); one-sided Mann-Whitney U (B1_pr < B1): p = 0.2413; paired (same seed) Wilcoxon two-sided p = 0.3931; seeds with B1_pr better: 18 / 30

**Pre-registered criteria** (PLAN.md): P0 (mean gap drop >= 0.15 points and p < 0.01): **fail** | P1 (more runs at BKS+0.005: 0 vs 0): **fail** | P2 (more runs <= Zou f_avg: 0 vs 0): **fail** | S (30/30 feasible + verify OK per arm, CPU/limit mean <= 1.01 and max <= 1.07): **PASS**

Verdict: no adoption: P0 not met

Mechanism counters, arm B1_pr (mean per run): pr.calls=2.80, pr.elite=10.00, pr.elite_adds=53.13, pr.feasible_points=5.33, pr.improved_best=1.00, pr.nodiff=0.07, pr.on=1.00, pr.points=5.47, pr.skipped_time=0.13


## p7_pr_x4  (tuzun/P122112-10, B1 vs B1_pr, EXPLORATORY)

CPU limit per run: 575 s (cluster-equivalent budget x 4); BKS 6018.59; Zou f_avg 6043.38; Zou depots [5, 6, 7]

Cluster B1 reference (30 runs, 3n s CPU): mean gap 1.255, sd 0.224, best 0.757, mean iterations 59.2

| arm | runs | feasible+verify | mean gap % | sd | median | best | runs <= BKS+0.005 | runs <= Zou f_avg | mean iters | CPU/limit mean (max) | final set = Zou set | allocation = Zou |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | 30 | 30 | 1.001 | 0.190 | 1.020 | 0.392 | 0 | 1 | 222.2 | 1.003 (1.007) | 17 | 3 |
| B1_pr | 30 | 30 | 0.928 | 0.165 | 0.957 | 0.330 | 0 | 1 | 208.8 | 1.003 (1.007) | 19 | 1 |

mean gap B1_pr - B1 = -0.073 points (bootstrap 95% CI -0.161 .. +0.016); one-sided Mann-Whitney U (B1_pr < B1): p = 0.01923; paired (same seed) Wilcoxon two-sided p = 0.08407; seeds with B1_pr better: 22 / 30

**Pre-registered criteria** (PLAN.md): P0 (mean gap drop >= 0.15 points and p < 0.01): **fail** | P1 (more runs at BKS+0.005: 0 vs 0): **fail** | P2 (more runs <= Zou f_avg: 1 vs 1): **fail** | S (30/30 feasible + verify OK per arm, CPU/limit mean <= 1.01 and max <= 1.07): **PASS**

Verdict: no adoption: P0 not met

Mechanism counters, arm B1_pr (mean per run): pr.calls=14.07, pr.elite=10.00, pr.elite_adds=226.93, pr.feasible_points=26.93, pr.improved_best=2.87, pr.nodiff=0.30, pr.on=1.00, pr.points=27.53, pr.skipped_time=0.07

