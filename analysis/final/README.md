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

The manuscript as submitted is the reference; this directory reproduces its numbers and says where a printed value differs from a recomputation.

* **Reproduced with the single rule** (our best and mean rounded to two decimals, ties at 0.005, two-sided Wilcoxon, normal approximation): the RLHEA p values quoted in the manuscript:
  mean objective 0.82 (58 instances with n >= 75), 0.77 (45 held-out), 0.74 (all 76; quoted as 7e-1); best value 0.0015 (n >= 75), 0.0051 (held-out), 0.0033 (n >= 150);
  the counts 18 / 26 / 11 / 8 / 45 / 63 instances with the best run at the BKS (n <= 50, 75-134, 150, 200, n >= 75, all), the mean gaps of the size classes (n <= 50: 0.00 / 0.00; all 76: 0.02 / 0.09),
  "mean not above the RLHEA average" on 34 of the instances with n >= 75 (rounded rule; 29 with the strict rule), and the mean gaps on the GBILS instances (0.03 against 2.37 %).
  One p value of the RLHEA block (0.85) was not matched to a subset.
* **Comparison table of the manuscript (Panel B).** Its rows were produced with one tie rule per algorithm, which is not the single rule above. `final_vs_published.py` reproduces the printed rows (section "Comparison table of the manuscript" of `reference/final_vs_published.md`):

  | row | rule | W / T / L | p printed | p regenerated |
  |---|---|---|---|---|
  | RLHEA, all 76, mean vs Avg | tie: the two gaps differ by <= 0.005 points | 19 / 36 / 21 | 7e-1 | 0.74 (the p value is that of the single rule) |
  | SA-VND (best variant), mean vs Avg | tie: \|difference\| <= 0.1, zero differences split between the signs | 65 / 11 / 0 | 1.3e-13 | 1.3e-13 |
  | M-ILS, mean vs Avg | tie: \|difference\| <= 0.1, zero differences dropped | 69 / 7 / 0 | 5.2e-13 | 5.2e-13 |
  | GBILS (35), our mean vs their best | tie: \|difference\| <= 0.1, zero differences dropped | 25 / 10 / 0 | 6.3e-6 | not matched: 6.1e-6 one-sided, 1.2e-5 two-sided |

  The section "Other published algorithms, single rule" applies the single rule of the docstring to every algorithm instead (SA-VND best variant 69 / 7 / 0, M-ILS 70 / 6 / 0, GBILS 27 / 7 / 1, RLHEA 23 / 27 / 26); it is a sensitivity check, not the printed table.
  The conclusion of every row (the final method is better than SA-VND, M-ILS and GBILS and not significantly different from RLHEA on the mean) is the same under both sets of rules.
* **Appendix G.** Recomputed from the archives, 758 of the 760 cells agree with the printed table to the printed precision. Where the printed value differs: 20-5-2b, best and mean of the final method, printed 486.55, the 30 runs all give 486.5449
  (486.54 with two decimals; the BKS is 486.55 and the gap is 0.00 either way). The other two cells that earlier looked different were resolved in the data files: the published RLHEA best of 20-5-1b is 608.05 as printed in the manuscript (the supplementary table of the study printed 608.06;
  not checked against the original table of Zou et al.), and the GBILS value of Min-27-5 is 5387.54 as in the GBILS paper.
* **GBILS.** Its Christofides69 rows (50x5, 75x10, 100x10) are values of another variant of the instance and are excluded (`GBILS_UNMATCHED`); 35 usable instances remain.
* Prins 50-5-2BIS-5 is reported with the `--atmost` runs (945.45), as in the manuscript; `--no-atmost` switches to the runs of the default setting (exactly Ng open depots) of `final_1x_tuned.tar.gz`.
