# Stage-by-stage comparison and the pre-registered criteria of stages 3 and 4

Regenerates, from the archived raw runs, the comparison of the three cumulative stages of the method on the 57 instances with n >= 100 (30 seeds each, CPU limit 3n s) and the
**pre-registered criteria** of stage 3 (depot-aware diversification, arm `V1`, against the base method `ext10`) and of stage 4 (route pool with set partitioning, arm `B1`, against `V1`).
The analysis of stage 5 (memetic phase) is in [`../memetic`](../memetic); the analysis of stages 1 and 2 (tuning budget against extended budget, comparison with RLHEA) is in [`../../paper`](../../paper) and [`../ext10_report.py`](../ext10_report.py).

```bash
D=/tmp/stages; mkdir -p $D
for a in ext10_tuned depot_tuned b1_tuned; do tar xzf study_results/$a.tar.gz -C $D; done
python3 analysis/stages/analyze_stages.py --base $D/results_extended10 --depot $D/results_depot --pool $D/results_b1 --manifest cpp/manifest.tsv \
    --literature bks/literature_results.csv --instances cpp/stages/instances_n100.txt --pmedian bks/reference/pmedian_rank_of_published_depot_sets.csv --out $D/out
```

About 2 seconds; needs `scipy`. Output: `stages_summary.md` (all tables below) and `stages_instances.csv` (one row per instance: gap and best-of-30 gap of each arm, hit flags, Zou values).
[`reference/`](reference) holds the two files as produced from the archives of this repository; the CI job `stages` regenerates them and fails on any difference.
Self-test of the script on synthetic archives: `python3 -I analysis/stages/test_analyze_stages.py`.

| File | Content |
|---|---|
| [`analyze_stages.py`](analyze_stages.py) | The analysis. The criteria and their thresholds are written in its docstring and as constants (`STAGE3`, `STAGE4`) |
| [`plans/PLAN_stage3_depot.md`](plans/PLAN_stage3_depot.md) | The plan of stage 3, written on 15 Nov 2026 before any result of the 57 instances existed: English translation of the Turkish original |
| [`plans/PLAN_stage4_pool.md`](plans/PLAN_stage4_pool.md) | The pre-registered criteria of stage 4 as recorded on 15 Nov 2026 (a restatement, not a translation: the original plan file was not kept; see the provenance note in the file) |
| [`reference/stages_summary.md`](reference/stages_summary.md), [`reference/stages_instances.csv`](reference/stages_instances.csv) | Output regenerated from the archives, checked by CI |

## What the script reports

* **Integrity** of each archive: runs, feasible runs, independently verified runs (`verify.txt`, present in the depot and pool archives), CPU time over limit, stop reasons, agreement of the BKS in the runs with `cpp/manifest.tsv`.
* **Criteria**, each with the value, the threshold and the verdict, in the words of the plans: stage 3 G0, G1, G2, Z (and the reading rule of the plan); stage 4 G1, G0, Z. The Wilcoxon tests are
  one-sided signed-rank tests on the 57 instance gaps (normal approximation; zero differences are dropped); the instance gap is the mean of the 30 run gaps. The pilot instance P121122-20, on which the depot
  mechanism was chosen, stays in every criterion (as pre-registered); the analysis is repeated without it as a robustness check.
* **Descriptive** (never replaces a criterion): table by size class and by family, hits (best of 30 <= BKS + 0.005), comparison with the published RLHEA values (hardware not normalised), instance-level and
  same-seed counts of better / worse / equal, instance-bootstrap 95 % intervals (10000 resamples, fixed seed), anytime values at multiples of b = max(5, 0.3 n) s and at the RLHEA run time, the log of the
  set-partitioning step of `B1` (`pool.csv`), and, for an instance that stage 3 harms, the rank of its published depot set in the p-median ranking (`bks/reference/`).

## Verdicts (from `reference/stages_summary.md`)

| Stage | Criterion | Value | Verdict |
|---|---|---|---|
| 3 (V1 against ext10) | G0 | mean gap 0.595 -> 0.290 %, Wilcoxon p = 1.3e-8, better / worse / equal on 47 / 5 / 5 instances | met |
| | G1 (n >= 150) | 0.448 % (ext10 0.941 %) | met |
| | G2 (Zou f_avg) | 9 of 57 (threshold 10; ext10 6) | **not met** |
| | Z | 1 of 57 (P111122-20, +0.287; its optimal depot set is number 26 of 1140 in the p-median order, outside the focus window of 10) | within the limit |
| | Reading rule | G0 and G1 met | "V1 generalises to n > 75" |
| 4 (B1 against V1) | G1 (n >= 150) | 0.448 -> 0.174 % (drop 0.274; threshold 0.10) | met |
| | G0 | 0.290 -> 0.112 %, p = 1.9e-10, better / worse / equal on 51 / 1 / 5 instances | met |
| | Z | 0 of 57 (worst single difference +0.002, Or117-14) | within the limit |

Whole chain: 0.595 -> 0.290 -> 0.112 % mean gap; hits 28 -> 30 -> 44 of 57; mean latency <= RLHEA average on 6 -> 9 -> 29 of 57 instances.

## Notes on reproducing earlier quotations

* The instance-level counts and the p value of the step V1 -> B1 differ from those first quoted in the project notes (54 better / 3 worse / 0 equal, p = 5.4e-11). The first analysis took the V1 gaps from a rounded
  per-instance table; the archives give the same value for V1 and B1 in all 30 runs on five instances (among them P113212-10 and P113222-20, which the first analysis counted as +0.0003 worse), so those are equal here.
  The verdict does not change. The steps ext10 -> V1 (47 / 5 / 5, p = 1.3e-8) and ext10 -> B1 (51 / 2 / 4, p = 3.9e-10) agree with the first analysis.
* The bootstrap endpoints depend on the resampling; with the fixed seed of the script the interval of the step ext10 -> V1 is -0.477 ... -0.160 (first analysis: -0.472 ... -0.162).
* The anytime point 10b is the final value of the run for every arm (the CPU limit is checked at the end of an iteration, so the last iteration, and for `B1` the last set-partitioning call, end a little after 10b).
  For `ext10` and `V1` this gives 0.595 and 0.290 %, the class-table values; evaluating the traces strictly at 10b gives 0.598 and 0.291 %.

## Not regenerated here

The anytime points at fixed seconds (60, 150, 300 s) of the stage-3 plan (the multiples of b above are used instead), the distribution of the final depot set by lower-bound order and the counters of the depot mechanism (`dpm.csv`
is in the depot archive), and the post-hoc multi-start aggregation of the 30 final solutions of an instance (route pool plus set partitioning over seeds), which is a different quantity from the single-run result of `B1`.
The decomposition of the difference to the published RLHEA solutions (classes A to E) is [`../depot_decomp.py`](../depot_decomp.py); it needs the third-party solution files and is not part of CI.
