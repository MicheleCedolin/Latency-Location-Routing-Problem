# Memetic phase (stage 5, Appendix F): pre-registered analysis

The exploratory memetic phase (a population of the feasible GRASP solutions, three-parent edge assembly crossover, `--eax-split 0.4`) was evaluated in three steps.
For every step the plan (question, method, parameters, criteria and known caveats) was written before the results of that step were seen and is kept here unchanged in content.
The plans were first committed to this repository after the runs (commit `03cf6b1` on branch `pilot/v8`, in the original wording); the English versions in [`plans/`](plans) are translations of those files.

| Step | Plan | Instances x seeds | Criteria |
|---|---|---|---|
| Pilot (18 Nov 2026) | [`plans/PLAN_E_pilot.md`](plans/PLAN_E_pilot.md) | 4 instances with n = 200 ([`instances_pilot.txt`](instances_pilot.txt)) x 30 | P1 efficacy, P2 no harm, S safety |
| Extension (18 Nov 2026) | [`plans/PLAN_X_extension.md`](plans/PLAN_X_extension.md) | the 14 other instances with n = 200 and 25 instances with n < 200 ([`instances_ext.txt`](instances_ext.txt), 39 in total) x 30 | P1 on the 18 instances with n = 200, P2 on the 25 with n < 200, S |
| Remaining instances (19 Nov 2026) | [`plans/PLAN_Y_rest14.md`](plans/PLAN_Y_rest14.md) | 14 instances (n < 200) on which the final method without the phase reached the BKS in all 30 runs ([`instances_rest14.txt`](instances_rest14.txt)) x 30 | P3 no harm, full-set decision |

delta = (mean gap of the memetic arm) - (mean gap of the final method without the memetic phase), per instance, in percentage points above the BKS. The final method without the phase is
the route-pool campaign of [`../../study_results/b1_tuned.tar.gz`](../../study_results/b1_tuned.tar.gz) (the same flags without the memetic ones, the same seeds 1 to 30 and the same CPU limit; produced earlier with `llrp_fast` v7, not concurrently).

Names in the output: `B1` is the final method without the phase (route-pool campaign), `B1_eax40` the arm with the memetic phase. "Adoption candidate" is the label of the pre-registered decision rule;
the manuscript reports the phase as an exploratory extension and does not make it part of the final method.

## Reproduce

```bash
mkdir -p /tmp/memetic && tar xzf study_results/memetic_tuned.tar.gz -C /tmp/memetic          # -> /tmp/memetic/results_memetic/{barreto,prins,tuzun}/B1_eax40/
tar xzf study_results/b1_tuned.tar.gz -C /tmp/memetic                                         # -> /tmp/memetic/results_b1/{barreto,prins,tuzun}/B1/
python3 -I analysis/memetic/analyze_y.py --res /tmp/memetic/results_memetic --control /tmp/memetic/results_b1 \
    --manifest cpp/manifest.tsv --literature bks/literature_results.csv \
    --ext-list analysis/memetic/instances_ext.txt --rest-list analysis/memetic/instances_rest14.txt --out /tmp/memetic/analysis      # needs scipy
diff /tmp/memetic/analysis/y_summary.md analysis/memetic/reference/y_summary.md                  # identical
diff /tmp/memetic/analysis/y_instances.csv analysis/memetic/reference/y_instances.csv            # identical
```

`y_summary.md` holds the criteria P1, P2, P3 and S with their verdicts, the table by group and size class, the tails and the mechanism counters of the memetic phase;
`y_instances.csv` has one row per instance (mean gap of both arms, delta, p-values, best-of-30 hits); `y_runs.csv` (written, not kept here) one row per run.
CI runs this reproduction and compares the two files with the reference copies in [`reference/`](reference).

| File | Content |
|---|---|
| [`analyze_y.py`](analyze_y.py) | Full-set analysis (P1, P2, P3, S, tails, comparison with the published RLHEA averages) |
| [`analyze_x.py`](analyze_x.py) | Readers and statistics used by `analyze_y.py`; run alone it evaluates the pilot and extension steps |
| [`pack_runs.py`](pack_runs.py) | How the cluster output (one tar per run) was merged into `study_results/memetic_tuned.tar.gz`; the raw per-run files are not in the repository |
| [`instances_pilot.txt`](instances_pilot.txt), [`instances_ext.txt`](instances_ext.txt), [`instances_rest14.txt`](instances_rest14.txt) | The instance lists of the three steps |

## Limits of the evidence

* The control is an earlier campaign, not a concurrent arm. The analysis reports CPU time per limit (mean 0.9974, max 1.0029 for the memetic arm).
* The memetic phase is re-built from the description of the published algorithm (the source code of Zou et al. was not available); the parameters (population 20, psi = 0.55, the split 0.4) were not tuned on these instances.
* Because the phase starts at 40 % of the CPU budget, a run cannot be replayed from its iteration count (`analysis/replay_archive.py`); the archive is checked by the independent verification of every run (`verify.txt`) and by the reproduction above.
