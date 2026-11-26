# Final method against the published algorithms

Regenerates, from the archived raw runs, the per-instance results of the **final method** (as reported in the manuscript) next to the published values of RLHEA, MS-VNS, M-ILS, SA-VND (three variants and the best variant),
MA and GBILS, and the paired comparisons (win / tie / loss, Wilcoxon signed-rank test).

```bash
python3 analysis/final/final_vs_published.py --out /tmp/final          # about 2 seconds; needs scipy; add --atmost to report 50-5-2BIS-5 with the at-most-Ng runs (945.45)
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
  mean objective 0.82 (58 instances with n >= 75), 0.77 (45 held-out), 0.58 (all 76); best value 0.0015 (n >= 75), 0.0051 (held-out), 0.0033 (n >= 150);
  the counts 17 / 26 / 11 / 8 / 45 / 62 instances with the best run at the BKS (n <= 50, 75-134, 150, 200, n >= 75, all), and "mean not above the RLHEA average" on 34 of the instances with n >= 75 (rounded rule; 29 with the strict rule).
* **Not reproduced.** The comparison rows of the other algorithms in the manuscript (e.g. SA-VND 65 / 11 / 0 with p = 1.3e-13, GBILS 25 / 10 / 0) cannot be recovered from the archives with a rule I could identify;
  the script reports 69 / 7 / 0 for the best SA-VND variant (mean against Avg, p = 5.2e-13) and 27 / 8 / 0 for GBILS (our mean against their best value, since GBILS reports best values only; p = 5.6e-6), with the stated rules. The mean gaps on the GBILS instances (0.043 against 2.372 %) agree with the manuscript.
  One p value of the RLHEA block (0.85) was not matched to a subset either. Treat the script as the reference for these numbers and align the manuscript text with it, or tell me the rule the manuscript used.
* **GBILS.** Its Christofides69 rows (50x5, 75x10, 100x10) are values of another variant of the instance and are excluded (`GBILS_UNMATCHED`); 35 usable instances remain.
* Prins 50-5-2BIS-5 is reported with the default rule (949.10) as in the manuscript; `--atmost` switches to the 945.45 runs.
