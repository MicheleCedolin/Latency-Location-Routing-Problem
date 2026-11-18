#!/usr/bin/env python3
"""Pre-registered analysis of the granular-neighbourhood test (B1 + --gran 20 versus the archived B1 campaign; see PLAN_R.md).

  python3 -I analyze_r.py --res results_r_full [--res results_r_n200] --control control/B1_run.csv --manifest manifest.tsv \
          [--literature literature_results.csv] [--arm B1_gran20] --out OUTDIR

--res : result tree(s) written by r_worker.sh (tar/<family>/<instance>_s<seed>_<arm>.tar, one verified run per archive)
--control : merged run.csv of the archived B1 campaign (57 instances x 30 seeds 1..30, 3n s CPU, same engine llrp_fast_v7, same flags without --gran)
Criteria (fixed before any result of this test existed); delta = (mean gap of B1_gran20) - (mean gap of archived B1) per instance, in percentage points above the BKS:
  P1  efficacy, the 18 instances with n = 200: mean delta <= -0.03 AND one-sided Wilcoxon signed-rank (B1_gran20 < B1) p < 0.05
  P2  no harm, all other instances: mean delta <= +0.02 AND harm counter <= 3, where an instance is 'harmed' if delta >= +0.10 AND one-sided Mann-Whitney U (B1_gran20 > B1) p < 0.05
  P3  mechanism, n = 200: median over instances of (median iterations B1_gran20 / median iterations B1) >= 1.5
  S   every run feasible and independently verified; CPU time / limit: mean <= 1.01 and max <= 1.07
  Adoption candidate: P1, P2, P3 and S all hold.  Anything else: not adopted.  Descriptive results (Zou comparison, best-of-30, new BKS) never replace a criterion.
Only instances with all 30 verified runs are used; incomplete ones are listed.
"""
import argparse, csv, io, math, os, re, sys, tarfile, statistics as st
from collections import defaultdict

try:
    from scipy.stats import mannwhitneyu, wilcoxon
except Exception:
    mannwhitneyu = wilcoxon = None

RUN_HEADER = ["Instance", "Algorithm", "Run", "Seed", "Feasible", "Total Latency", "Reference BKS", "Gap to BKS (%)", "CPU Time", "Open Depots", "Number of Routes", "Actual Open Depot Count",
              "Required Ng", "Actual Route Count", "Required Nv", "Max Route Load", "Vehicle Capacity", "Total Demand", "Total Vehicle Capacity", "Nv", "Ng", "Iterations", "Stop Reason",
              "Last Improvement Iteration", "Last Improvement CPU", "Wall Time", "Move Evaluations"]
TOL = 0.005


def read_runs(res_dir, manifest, tc, tmin):
    runs = []
    for root, _, files in os.walk(os.path.join(res_dir, "tar")):
        for f in sorted(files):
            if not f.endswith(".tar"):
                continue
            with tarfile.open(os.path.join(root, f)) as tf:
                names = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
                rc = [n for n in names if n.endswith(".run.csv")]
                if not rc:
                    continue
                stem = rc[0][:-len(".run.csv")]
                raw = [x for x in csv.reader(io.TextIOWrapper(tf.extractfile(names[rc[0]]), encoding="utf-8")) if x]
                if raw and raw[0][0] == "Instance":
                    raw = raw[1:]
                if not raw:
                    continue
                r = dict(zip(RUN_HEADER, raw[0]))
                ver = tf.extractfile(names[stem + ".verify"]).read().decode() if stem + ".verify" in names else ""
                inst = r["Instance"]
                n = int(manifest[inst]["n"]) if inst in manifest else 0
                runs.append(dict(inst=inst, arm=r["Algorithm"], seed=int(r["Seed"]), cost=float(r["Total Latency"]), bks_run=float(r["Reference BKS"]),
                                 feasible=r["Feasible"] == "True", cpu=float(r["CPU Time"]), iters=int(r["Iterations"]), limit=max(tmin, tc * n / 100.0),
                                 verify=ver.lstrip().startswith("OK"), n=n))
    return runs


def read_control(path):
    out = defaultdict(list)
    with open(path) as fh:
        for r in csv.DictReader(fh):
            out[r["Instance"]].append(dict(seed=int(r["Seed"]), cost=float(r["Total Latency"]), bks=float(r["Reference BKS"]), feasible=r["Feasible"] == "True",
                                           cpu=float(r["CPU Time"]), iters=int(r["Iterations"])))
    return out


def mw(a, b, alt):
    if mannwhitneyu is None or not a or not b:
        return float("nan")
    try:
        return float(mannwhitneyu(a, b, alternative=alt).pvalue)
    except ValueError:
        return 1.0


def wx(d, alt):
    if wilcoxon is None or len(d) < 2 or all(abs(x) < 1e-12 for x in d):
        return float("nan")
    try:
        return float(wilcoxon(d, alternative=alt).pvalue)
    except ValueError:
        return float("nan")


def mean(a):
    return sum(a) / len(a) if a else float("nan")


def gap(cost, bks):
    return (cost - bks) / bks * 100.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--res", action="append", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--literature", default=None)
    ap.add_argument("--arm", default="B1_gran20")
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
    ctrl = read_control(a.control)
    zou = {}
    if a.literature:
        with open(a.literature) as fh:
            for r in csv.DictReader(fh):
                if r["algorithm"] == "RLHEA" and r["avg"]:
                    zou[r["instance"]] = (float(r["best"]), float(r["avg"]))
    new = defaultdict(dict)
    nread = 0
    for rd in a.res:
        for r in read_runs(rd, manifest, a.tc, a.tmin):
            if r["arm"] != a.arm:
                continue
            new[r["inst"]][r["seed"]] = r; nread += 1
    bks = {i: ctrl[i][0]["bks"] for i in ctrl}

    # ------------------------------------------------------------------ per run table
    with open(os.path.join(a.out, "r_runs.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["instance", "n", "seed", "cost", "gap_pct", "cpu", "limit", "cpu_over_limit", "iterations", "feasible", "verify", "bks_run_equals_control"])
        for i in sorted(new):
            for s in sorted(new[i]):
                r = new[i][s]
                w.writerow([i, r["n"], s, "%.6f" % r["cost"], "%.5f" % gap(r["cost"], bks.get(i, r["bks_run"])), "%.3f" % r["cpu"], "%.3f" % r["limit"], "%.4f" % (r["cpu"] / r["limit"]),
                            r["iters"], int(r["feasible"]), int(r["verify"]), int(abs(r["bks_run"] - bks.get(i, float("nan"))) < 1e-6)])

    allruns = [r for i in new for r in new[i].values()]
    bad_runs = [r for r in allruns if not (r["feasible"] and r["verify"])]
    ratios = [r["cpu"] / r["limit"] for r in allruns]
    bks_diff = sorted({r["inst"] for r in allruns if abs(r["bks_run"] - bks.get(r["inst"], float("nan"))) > 1e-6})

    # ------------------------------------------------------------------ per instance
    rows, incomplete = [], []
    for i in sorted(new, key=lambda x: (int(manifest[x]["n"]), x)):
        good = [r for r in new[i].values() if r["feasible"] and r["verify"]]
        if len(good) < a.seeds:
            incomplete.append((i, len(good))); continue
        n = int(manifest[i]["n"]); B = bks[i]
        gn = [gap(r["cost"], B) for r in good]; gc = [gap(c["cost"], B) for c in ctrl[i] if c["feasible"]]
        best_n = min(r["cost"] for r in good); best_c = min(c["cost"] for c in ctrl[i] if c["feasible"])
        itn = st.median([r["iters"] for r in good]); itc = st.median([c["iters"] for c in ctrl[i]])
        zg = gap(zou[i][1], B) if i in zou else float("nan")
        rows.append(dict(inst=i, n=n, mean_new=mean(gn), mean_ctl=mean(gc), delta=mean(gn) - mean(gc), p_harm=mw(gn, gc, "greater"), p_help=mw(gn, gc, "less"),
                         best_new=gap(best_n, B), best_ctl=gap(best_c, B), hit_new=int(best_n <= B + TOL), hit_ctl=int(best_c <= B + TOL), newbks=int(best_n < B - TOL),
                         it_ratio=itn / itc, it_new=itn, it_ctl=itc, zou=zg))
    with open(os.path.join(a.out, "r_instances.csv"), "w", newline="") as fh:
        w = csv.writer(fh); keys = list(rows[0].keys()) if rows else ["inst"]; w.writerow(keys)
        for r in rows: w.writerow([("%.5f" % r[k]) if isinstance(r[k], float) else r[k] for k in keys])

    # ------------------------------------------------------------------ criteria
    L = []
    P = L.append
    P("# Granular-neighbourhood test: %s versus archived B1\n" % a.arm)
    P("Runs read: %d (verified+feasible %d); instances complete (%d runs): %d; incomplete: %s\n" % (nread, nread - len(bad_runs), a.seeds, len(rows), ", ".join("%s(%d)" % x for x in incomplete) or "none"))
    n200 = [r for r in rows if r["n"] == 200]; oth = [r for r in rows if r["n"] != 200]
    P("## Criteria (pre-registered)\n")
    if n200:
        d = [r["delta"] for r in n200]; p = wx(d, "less"); m = mean(d)
        ok1 = len(n200) == 18 and m <= -0.03 and p < 0.05
        P("P1 efficacy, n=200 (%d of 18 instances complete): mean delta %+.4f (control mean gap %.4f -> %.4f); one-sided Wilcoxon p = %.4f; better on %d / worse on %d  ->  **%s**" % (
            len(n200), m, mean([r["mean_ctl"] for r in n200]), mean([r["mean_new"] for r in n200]), p, sum(x < -TOL for x in d), sum(x > TOL for x in d), "PASS" if ok1 else "FAIL" if len(n200) == 18 else "NOT EVALUABLE (incomplete)"))
        itr = st.median([r["it_ratio"] for r in n200]); ok3 = itr >= 1.5
        P("P3 mechanism, n=200: median iteration ratio %.2f (range %.2f-%.2f)  ->  **%s**" % (itr, min(r["it_ratio"] for r in n200), max(r["it_ratio"] for r in n200), "PASS" if ok3 else "FAIL"))
    else:
        ok1 = ok3 = False; P("P1/P3: no complete n=200 instance")
    if oth:
        d = [r["delta"] for r in oth]; m = mean(d)
        harmed = [r["inst"] for r in oth if r["delta"] >= 0.10 and r["p_harm"] < 0.05]
        full = len(rows) == 57
        ok2 = m <= 0.02 and len(harmed) <= 3
        P("P2 no harm, other classes (%d instances complete): mean delta %+.4f; harmed instances %d (%s)  ->  **%s**" % (len(oth), m, len(harmed), ", ".join(harmed) or "-", ("PASS" if ok2 else "FAIL") + ("" if full else " (on the complete subset only)")))
    else:
        ok2 = None; P("P2: no complete instance outside n=200 (run MODE=full for P2)")
    ok_s = (not bad_runs) and bool(ratios) and mean(ratios) <= 1.01 and max(ratios) <= 1.07
    P("S safety: %d runs, %d not feasible/verified; CPU/limit mean %.4f max %.4f  ->  **%s**" % (len(allruns), len(bad_runs), mean(ratios) if ratios else float("nan"), max(ratios) if ratios else float("nan"), "PASS" if ok_s else "FAIL"))
    if bks_diff:
        P("note: Reference BKS in the new runs differs from the control for: %s (gaps here use the control BKS)" % ", ".join(bks_diff))
    verdict = ok1 and ok3 and ok_s and ok2 is True and len(rows) == 57
    P("\n**Verdict: %s**\n" % ("ADOPTION CANDIDATE (P1, P2, P3, S all hold on the full 57-instance set)" if verdict else "not adopted / not yet decidable (see the lines above)"))

    # ------------------------------------------------------------------ descriptive
    P("## By instance class (complete instances; gap = % above the BKS; mean over instance means)\n")
    P("| n | instances | B1 (archive) | %s | delta | Zou avg | better/worse/equal (tol 0.005) | best-of-30 hits B1 -> new |" % a.arm)
    P("|---|---|---|---|---|---|---|---|")
    for lab, sel in [(str(k), [r for r in rows if r["n"] == k]) for k in sorted({r["n"] for r in rows})] + [("ALL", rows)]:
        if not sel: continue
        d = [r["delta"] for r in sel]; zz = [r["zou"] for r in sel if not math.isnan(r["zou"])]
        P("| %s | %d | %.4f | %.4f | %+.4f | %s | %d/%d/%d | %d -> %d |" % (lab, len(sel), mean([r["mean_ctl"] for r in sel]), mean([r["mean_new"] for r in sel]), mean(d), "%.4f" % mean(zz) if zz else "-",
                                                                                sum(x < -TOL for x in d), sum(x > TOL for x in d), sum(abs(x) <= TOL for x in d), sum(r["hit_ctl"] for r in sel), sum(r["hit_new"] for r in sel)))
    if rows:
        d = [r["delta"] for r in rows]
        P("\nAll complete instances: two-sided Wilcoxon (new vs B1) p = %.4f" % wx(d, "two-sided"))
        zr = [r for r in rows if not math.isnan(r["zou"])]
        if zr:
            dz = [r["mean_new"] - r["zou"] for r in zr]; dc = [r["mean_ctl"] - r["zou"] for r in zr]
            P("Versus Zou et al. (RLHEA, published averages; hardware not normalised): mean gap difference new-Zou %+.4f (B1-Zou %+.4f); instances with mean gap <= Zou average + 0.005: new %d, B1 %d of %d; two-sided Wilcoxon new vs Zou p = %.4f (B1 vs Zou p = %.4f)" % (
                mean(dz), mean(dc), sum(x <= TOL for x in dz), sum(x <= TOL for x in dc), len(zr), wx(dz, "two-sided"), wx(dc, "two-sided")))
        nb = [r["inst"] for r in rows if r["newbks"]]
        P("New best-known solutions (best run below BKS - 0.005): %s" % (", ".join(nb) or "none"))
        P("\n## Per instance (sorted by delta)\n")
        P("| instance | n | B1 mean gap | new mean gap | delta | MWU p (new<B1) | iteration ratio | Zou avg gap |")
        P("|---|---|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda x: x["delta"]):
            P("| %s | %d | %.4f | %.4f | %+.4f | %.3f | %.2f | %s |" % (r["inst"], r["n"], r["mean_ctl"], r["mean_new"], r["delta"], r["p_help"], r["it_ratio"], "%.4f" % r["zou"] if not math.isnan(r["zou"]) else "-"))
    P("\nCaveat: the control is the archived B1 campaign (same cluster and engine, seeds 1-30), not a concurrent arm; node load can differ slightly between the two campaigns.")
    txt = "\n".join(L)
    open(os.path.join(a.out, "r_summary.md"), "w").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
