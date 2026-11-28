# Final method against the published algorithms

Regenerates, from the archived raw runs, the per-instance results of the **final method** (as reported in the manuscript) next to the published values of RLHEA, MS-VNS, M-ILS, SA-VND (three variants and the best variant),
MA and GBILS, and the paired comparisons (win / tie / loss, Wilcoxon signed-rank test).

```bash
python3 analysis/final/final_vs_published.py --out /tmp/final          # about 2 seconds; needs scipy
```

The script reads `study_results/*.tar.gz` directly. The final method is the base method at the standard budget for n <= 50 (`final_1x_tuned`), at the extended budget for n = 75 (`ext10_tuned`)
and the route-pool method B1 for n > 75 (`b1_tuned`); 30 seeds each. All rules (ties, rounding, test, subsets) are in the docstring and are repeated at the end of `final_vs_published.md`.

| File | Content |
|---|---|
| [`final_vs_published.py`](final_vs_published.py) | The generator |
| [`reference/final_vs_published.md`](reference/final_vs_published.md) | Quality by size class, RLHEA comparison on five instance subsets, comparison with the other algorithms |
| [`reference/final_per_instance.csv`](reference/final_per_instance.csv) | One row per instance: source, BKS, best and mean of the final method, gaps, and best / average of every published algorithm |
| [`reference/final_per_instance.tex`](reference/final_per_instance.tex) | Readable LaTeX `longtable` of the same data (own layout, **not** the layout of the manuscript table) |

The three reference files are what the script writes from the archives of this repository; the CI job `final` regenerates them and fails on any difference.

## How this relates to the manuscript

* **Reproduced.** With the rules above (our best and mean rounded to two decimals, ties at 0.005, two-sided Wilcoxon, normal approximation) the script gives the RLHEA p values quoted in the manuscript:
  mean objective 0.82 (58 instances with n >= 75), 0.77 (45 held-out), 0.74 (all 76; quoted as 7e-1); best value 0.0015 (n >= 75), 0.0051 (held-out), 0.0033 (n >= 150);
  the counts 18 / 26 / 11 / 8 / 45 / 63 instances with the best run at the BKS (n <= 50, 75-134, 150, 200, n >= 75, all), the mean gaps of the size classes (n <= 50: 0.00 / 0.00; all 76: 0.02 / 0.09),
  "mean not above the RLHEA average" on 34 of the instances with n >= 75 (rounded rule; 29 with the strict rule), and the mean gaps on the GBILS instances (0.03 against 2.37 %).
* **Rows of the other algorithms.** All rows of the comparison table are produced with the same single rule as the RLHEA rows (ties at 0.005 after rounding, two-sided Wilcoxon, ties dropped): SA-VND (best variant) 69 / 7 / 0 (p = 5.2e-13), M-ILS 70 / 6 / 0 (p = 3.6e-13), GBILS (our mean against their best value, since GBILS reports best values only) 27 / 7 / 1 (p = 4.2e-6), RLHEA on all 76 instances 23 / 27 / 26 (p = 0.74). Earlier drafts of the manuscript used other tie rules for these rows (a tolerance of 0.1 for SA-VND and M-ILS, zero differences split between the signs); they are not used any more.
  One p value of the RLHEA block (0.85) was not matched to a subset.
* **GBILS.** Its Christofides69 rows (50x5, 75x10, 100x10) are values of another variant of the instance and are excluded (`GBILS_UNMATCHED`); 35 usable instances remain.
* Prins 50-5-2BIS-5 is reported with the `--atmost` runs (945.45), as in the manuscript; `--no-atmost` switches to the runs of the default setting (exactly Ng open depots) of `final_1x_tuned.tar.gz`.
