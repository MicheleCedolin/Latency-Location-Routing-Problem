#!/usr/bin/env python3
"""Pre-registered analysis of the B1-E extension INCLUDING the 14 'easy' instances that the first extension skipped; see plans/PLAN_Y_rest14.md.

  python3 -I analyze_y.py --res RESULTS_MEMETIC --control B1_ARCHIVE_DIR --manifest cpp/manifest.tsv \
        --ext-list instances_ext.txt --rest-list instances_rest14.txt [--literature bks/literature_results.csv] --out OUTDIR
  (RESULTS_MEMETIC = extracted study_results/memetic_tuned.tar.gz, B1_ARCHIVE_DIR = extracted study_results/b1_tuned.tar.gz; see README.md of this directory)

delta = (mean gap of B1_eax40) - (mean gap of archived B1) per instance, percentage points above the BKS.
  P1  efficacy, the 18 instances with n = 200:      mean delta <= -0.03 AND one-sided Wilcoxon signed-rank (B1_eax40 < B1) p < 0.05      (unchanged, already PASSED)
  P2  no harm, the 25 evaluated n < 200 instances:  mean delta <= +0.02 AND harm counter <= 3 ('harmed' = delta >= +0.10 AND one-sided MWU p < 0.05)   (unchanged, already PASSED)
  P3  no harm, the 14 instances the archived B1 solved in 30/30 runs: mean delta <= +0.02 AND at most ONE instance with delta >= +0.10
      (effect size only: the control has ~zero variance there, so a p-value would hide rare tail events)
  S   every run feasible and independently verified; CPU time / limit: mean <= 1.01 and max <= 1.07
  Full-set adoption candidate: P1, P2, P3 and S all hold on the complete 57 instances.  Otherwise B1-E is reported for the evaluated instances only.
Descriptive (never replaces a criterion): tails (runs with gap > 0.5 / > 1.0, worst-of-30), Zou comparison, best-of-30 hits, new BKS, mechanism counters.
"""
import argparse, csv, math, os, sys, statistics as st
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_x as X  # noqa: E402  (read_runs, read_control, mw, wx, mean, gap)

TOL = X.TOL


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--res", action="append", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--literature", default=None)
    ap.add_argument("--arm", default="B1_eax40")
    ap.add_argument("--ext-list", default="instances_ext.txt")
    ap.add_argument("--rest-list", default="instances_rest14.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tc", type=float, default=300.0)
    ap.add_argument("--tmin", type=float, default=5.0)
    ap.add_argument("--seeds", type=int, default=30)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    manifest = {}
    with open(a.manifest) as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            manifest[r["name"]] = r
    ctrl = X.read_control(a.control)
    zou = {}
    if a.literature:
        with open(a.literature) as fh:
            for r in csv.DictReader(fh):
                if r["algorithm"] == "RLHEA" and r["avg"]:
                    zou[r["instance"]] = (float(r["best"]), float(r["avg"]))
    new = defaultdict(dict); nread = 0
    for rd in a.res:
        for r in X.read_runs(rd, manifest, a.tc, a.tmin):
            if r["arm"] != a.arm:
                continue
            new[r["inst"]][r["seed"]] = r; nread += 1
    bks = {i: ctrl[i][0]["bks"] for i in ctrl}
    ext = [l.strip() for l in open(a.ext_list) if l.strip() and not l.startswith("#")]
    rest = [l.strip() for l in open(a.rest_list) if l.strip() and not l.startswith("#")]
    ext_oth = [i for i in ext if i in manifest and int(manifest[i]["n"]) != 200]

    with open(os.path.join(a.out, "y_runs.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["instance", "n", "seed", "cost", "gap_pct", "cpu", "limit", "cpu_over_limit", "iterations", "feasible", "verify"])
        for i in sorted(new):
            for s in sorted(new[i]):
                r = new[i][s]
                w.writerow([i, r["n"], s, "%.6f" % r["cost"], "%.5f" % X.gap(r["cost"], bks.get(i, r["bks_run"])), "%.3f" % r["cpu"], "%.3f" % r["limit"], "%.4f" % (r["cpu"] / r["limit"]), r["iters"], int(r["feasible"]), int(r["verify"])])
    allruns = [r for i in new for r in new[i].values()]
    bad_runs = [r for r in allruns if not (r["feasible"] and r["verify"])]
    ratios = [r["cpu"] / r["limit"] for r in allruns]

    rows, incomplete = [], []
    gaps_new, gaps_ctl = {}, {}
    for i in sorted(new, key=lambda x: (int(manifest[x]["n"]), x)):
        good = [r for r in new[i].values() if r["feasible"] and r["verify"]]
        if len(good) < a.seeds:
            incomplete.append((i, len(good))); continue
        n = int(manifest[i]["n"]); B = bks[i]
        gn = [X.gap(r["cost"], B) for r in good]; gc = [X.gap(c["cost"], B) for c in ctrl[i] if c["feasible"]]
        gaps_new[i], gaps_ctl[i] = gn, gc
        best_n = min(r["cost"] for r in good); best_c = min(c["cost"] for c in ctrl[i] if c["feasible"])
        zg = X.gap(zou[i][1], B) if i in zou else float("nan")
        rows.append(dict(inst=i, n=n, grp="rest14" if i in rest else ("n200" if n == 200 else "ext"), mean_new=X.mean(gn), mean_ctl=X.mean(gc), delta=X.mean(gn) - X.mean(gc),
                         p_harm=X.mw(gn, gc, "greater"), p_help=X.mw(gn, gc, "less"), worst_new=max(gn), worst_ctl=max(gc), best_new=X.gap(best_n, B), best_ctl=X.gap(best_c, B),
                         hit_new=int(best_n <= B + TOL), hit_ctl=int(best_c <= B + TOL), newbks=int(best_n < B - TOL), zou=zg))
    with open(os.path.join(a.out, "y_instances.csv"), "w", newline="") as fh:
        w = csv.writer(fh); keys = list(rows[0].keys()) if rows else ["inst"]; w.writerow(keys)
        for r in rows: w.writerow([("%.5f" % r[k]) if isinstance(r[k], float) else r[k] for k in keys])

    L = []; P = L.append
    P("# B1-E: full-set analysis (18 n=200 + 25 evaluated n<200 + 14 previously skipped) versus archived B1\n")
    P("Runs read: %d (verified+feasible %d); instances complete (%d runs): %d of 57; incomplete: %s\n" % (nread, nread - len(bad_runs), a.seeds, len(rows), ", ".join("%s(%d)" % x for x in incomplete) or "none"))
    n200 = [r for r in rows if r["n"] == 200 and r["grp"] != "rest14"]
    oth = [r for r in rows if r["inst"] in ext_oth]
    rst = [r for r in rows if r["inst"] in rest]
    P("## Criteria (pre-registered)\n")
    ok1 = None
    if n200:
        d = [r["delta"] for r in n200]; p = X.wx(d, "less"); m = X.mean(d)
        ok1 = len(n200) == 18 and m <= -0.03 and p < 0.05
        P("P1 efficacy, n=200 (%d of 18 complete): mean delta %+.4f; one-sided Wilcoxon p = %.4f; better %d / worse %d  ->  **%s**" % (len(n200), m, p, sum(x < -TOL for x in d), sum(x > TOL for x in d), "PASS" if ok1 else "FAIL" if len(n200) == 18 else "NOT EVALUABLE (incomplete)"))
    ok2 = None
    if oth:
        d = [r["delta"] for r in oth]; m = X.mean(d)
        harmed = [r["inst"] for r in oth if r["delta"] >= 0.10 and r["p_harm"] < 0.05]
        ok2 = m <= 0.02 and len(harmed) <= 3
        P("P2 no harm, n<200 evaluated (%d of %d complete): mean delta %+.4f; harmed %d (%s)  ->  **%s**" % (len(oth), len(ext_oth), m, len(harmed), ", ".join(harmed) or "-", ("PASS" if ok2 else "FAIL") + ("" if len(oth) == len(ext_oth) else " (subset only)")))
    ok3 = None
    if rst:
        d = [r["delta"] for r in rst]; m = X.mean(d)
        big = [r["inst"] for r in rst if r["delta"] >= 0.10]
        ok3 = m <= 0.02 and len(big) <= 1
        P("P3 no harm, previously skipped 14 (%d of %d complete): mean delta %+.4f (B1 mean gap %.5f -> %.5f); instances with delta >= +0.10: %d (%s)  ->  **%s**" % (
            len(rst), len(rest), m, X.mean([r["mean_ctl"] for r in rst]), X.mean([r["mean_new"] for r in rst]), len(big), ", ".join(big) or "-", ("PASS" if ok3 else "FAIL") + ("" if len(rst) == len(rest) else " (subset only)")))
    else:
        P("P3: no complete skipped-14 instance yet")
    ok_s = (not bad_runs) and bool(ratios) and X.mean(ratios) <= 1.01 and max(ratios) <= 1.07
    P("S safety: %d runs, %d not feasible/verified; CPU/limit mean %.4f max %.4f  ->  **%s**" % (len(allruns), len(bad_runs), X.mean(ratios) if ratios else float("nan"), max(ratios) if ratios else float("nan"), "PASS" if ok_s else "FAIL"))
    full = len(n200) == 18 and len(oth) == len(ext_oth) and len(rst) == len(rest) and len(rows) == 57
    verdict = full and ok1 and ok2 and ok3 and ok_s
    P("\n**Verdict: %s**\n" % ("FULL-SET ADOPTION CANDIDATE (P1, P2, P3, S hold on all 57 instances)" if verdict else ("not adopted on the full set (see the lines above)" if full else "not yet decidable (incomplete)")))
    ex = [r["eax"] for r in allruns if r["eax"]]
    if ex:
        def col(k): return [e[k] for e in ex if k in e]
        P("Mechanism (descriptive; %d runs): median generations %.0f; improved best %.1f per run; runs whose best improved after the switch: %d of %d; structural failures %.2f per run\n" % (
            len(ex), st.median(col("gens")), X.mean(col("improved_best")), sum(1 for e in ex if e.get("improved_best", 0) > 0), len(ex), X.mean(col("fail_struct"))))

    P("## By group and class (gap = % above the BKS; mean over instance means)\n")
    P("| group | instances | B1 (archive) | %s | delta | Zou avg | better/worse/equal (tol 0.005) | best-of-30 hits B1 -> new |" % a.arm)
    P("|---|---|---|---|---|---|---|---|")
    groups = [("n=200", [r for r in rows if r["grp"] == "n200"]), ("n<200 evaluated (ext)", [r for r in rows if r["grp"] == "ext"]), ("skipped 14 (rest14)", rst), ("ALL", rows)]
    for lab, sel in groups:
        if not sel: continue
        d = [r["delta"] for r in sel]; zz = [r["zou"] for r in sel if not math.isnan(r["zou"])]
        P("| %s | %d | %.4f | %.4f | %+.4f | %s | %d/%d/%d | %d -> %d |" % (lab, len(sel), X.mean([r["mean_ctl"] for r in sel]), X.mean([r["mean_new"] for r in sel]), X.mean(d), "%.4f" % X.mean(zz) if zz else "-",
                                                                                sum(x < -TOL for x in d), sum(x > TOL for x in d), sum(abs(x) <= TOL for x in d), sum(r["hit_ctl"] for r in sel), sum(r["hit_new"] for r in sel)))
    if rows:
        d = [r["delta"] for r in rows]
        P("\nAll complete instances: two-sided Wilcoxon (new vs B1) p = %.4f" % X.wx(d, "two-sided"))
        zr = [r for r in rows if not math.isnan(r["zou"])]
        if zr:
            dz = [r["mean_new"] - r["zou"] for r in zr]; dc = [r["mean_ctl"] - r["zou"] for r in zr]
            P("Versus Zou et al. (RLHEA published averages; hardware not normalised): mean gap difference new-Zou %+.4f (B1-Zou %+.4f); instances with mean gap <= Zou avg + 0.005: new %d, B1 %d of %d; two-sided Wilcoxon new vs Zou p = %.4f (B1 vs Zou p = %.4f)" % (
                X.mean(dz), X.mean(dc), sum(x <= TOL for x in dz), sum(x <= TOL for x in dc), len(zr), X.wx(dz, "two-sided"), X.wx(dc, "two-sided")))
        nb = [r["inst"] for r in rows if r["newbks"]]
        P("New best-known solutions (best run below BKS - 0.005): %s" % (", ".join(nb) or "none"))
        P("\n## Tails (descriptive)\n")
        P("| group | runs gap>0.5 B1 -> new | runs gap>1.0 B1 -> new | mean worst-of-30 B1 -> new | instances with delta >= +0.05 |")
        P("|---|---|---|---|---|")
        for lab, sel in groups:
            if not sel: continue
            n05c = sum(1 for r in sel for g in gaps_ctl[r["inst"]] if g > 0.5); n05n = sum(1 for r in sel for g in gaps_new[r["inst"]] if g > 0.5)
            n10c = sum(1 for r in sel for g in gaps_ctl[r["inst"]] if g > 1.0); n10n = sum(1 for r in sel for g in gaps_new[r["inst"]] if g > 1.0)
            P("| %s | %d -> %d | %d -> %d | %.3f -> %.3f | %d |" % (lab, n05c, n05n, n10c, n10n, X.mean([r["worst_ctl"] for r in sel]), X.mean([r["worst_new"] for r in sel]), sum(r["delta"] >= 0.05 for r in sel)))
        P("\n## Skipped-14 instances (per instance)\n")
        P("| instance | n | B1 mean gap | new mean gap | delta | worst-of-30 new | best-of-30 hit B1 -> new |")
        P("|---|---|---|---|---|---|---|")
        for r in sorted(rst, key=lambda x: -x["delta"]):
            P("| %s | %d | %.5f | %.5f | %+.5f | %.4f | %d -> %d |" % (r["inst"], r["n"], r["mean_ctl"], r["mean_new"], r["delta"], r["worst_new"], r["hit_ctl"], r["hit_new"]))
        P("\n## Five worst deltas over all complete instances\n")
        for r in sorted(rows, key=lambda x: -x["delta"])[:5]:
            P("- %s (n=%d, %s): delta %+.4f (B1 %.4f -> new %.4f; worst-of-30 new %.3f)" % (r["inst"], r["n"], r["grp"], r["delta"], r["mean_ctl"], r["mean_new"], r["worst_new"]))
    P("\nNote: the control is the archived B1 campaign (seeds 1-30), not a concurrent arm.")
    txt = "\n".join(L)
    open(os.path.join(a.out, "y_summary.md"), "w").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
