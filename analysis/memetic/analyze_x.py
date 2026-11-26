#!/usr/bin/env python3
"""Pre-registered analysis of the B1-E extension (B1 + memetic MPEAX phase, llrp_fast_v9 --eax-split 0.4) versus the archived B1 campaign; see plans/PLAN_X_extension.md.

  python3 -I analyze_x.py --res RESULTS_MEMETIC --control B1_ARCHIVE_DIR --manifest cpp/manifest.tsv --ext-list instances_ext.txt [--literature bks/literature_results.csv] --out OUTDIR
  (RESULTS_MEMETIC = extracted study_results/memetic_tuned.tar.gz, B1_ARCHIVE_DIR = extracted study_results/b1_tuned.tar.gz; stage X looks at the pilot + extension instances, so on the full archive use analyze_y.py)

delta = (mean gap of B1_eax40) - (mean gap of archived B1) per instance, percentage points above the BKS (fixed before any extension result existed):
  P1  efficacy, the 18 instances with n = 200 (4 from the pilot + 14 new): mean delta <= -0.03 AND one-sided Wilcoxon signed-rank (B1_eax40 < B1) p < 0.05
  P2  no harm, the evaluated instances with n < 200: mean delta <= +0.02 AND harm counter <= 3, where an instance is 'harmed' if delta >= +0.10 AND one-sided Mann-Whitney U (B1_eax40 > B1) p < 0.05
  S   every run feasible and independently verified; CPU time / limit: mean <= 1.01 and max <= 1.07
  Adoption candidate: P1, P2 and S all hold on the complete evaluated set (18 + the n < 200 instances of instances_ext.txt).  Otherwise not adopted.
  The 15 instances that the archived B1 solved in all 30 runs (n < 200) are NOT evaluated; results are reported for the evaluated set only.
Descriptive (never replaces a criterion): mechanism counters, Zou comparison, best-of-30 hits, new BKS.  Only instances with all 30 verified runs are used; incomplete ones are listed.
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


def read_runs_merged(res_dir, manifest, tc, tmin):
    """Same records as the per-run-tar reader, from the merged layout of study_results/memetic_tuned.tar.gz: <res_dir>/<family>/<arm>/{run.csv,verify.txt,eax_summary.csv}."""
    runs = []
    for fam in sorted(os.listdir(res_dir)):
        for arm in sorted(os.listdir(os.path.join(res_dir, fam))) if os.path.isdir(os.path.join(res_dir, fam)) else []:
            d = os.path.join(res_dir, fam, arm)
            if not os.path.isfile(os.path.join(d, "run.csv")):
                continue
            ver = {}
            for line in open(os.path.join(d, "verify.txt"), encoding="utf-8"):
                p = line.split()
                if len(p) >= 2:
                    ver[p[1]] = p[0]
            eaxs = {}
            for r in csv.DictReader(open(os.path.join(d, "eax_summary.csv"), encoding="utf-8")):
                e = {}
                for k, v in r.items():
                    if k not in ("Instance", "Seed"):
                        try: e[k] = float(v)
                        except (ValueError, TypeError): pass
                eaxs[(r["Instance"], int(r["Seed"]))] = e
            for r in csv.DictReader(open(os.path.join(d, "run.csv"), encoding="utf-8")):
                inst, seed = r["Instance"], int(r["Seed"])
                n = int(manifest[inst]["n"]) if inst in manifest else 0
                runs.append(dict(inst=inst, arm=r["Algorithm"], seed=seed, cost=float(r["Total Latency"]), bks_run=float(r["Reference BKS"]),
                                 feasible=r["Feasible"] == "True", cpu=float(r["CPU Time"]), iters=int(r["Iterations"]), limit=max(tmin, tc * n / 100.0),
                                 verify=ver.get("%s_s%d_%s" % (inst, seed, r["Algorithm"]), "") == "OK", n=n, eax=eaxs.get((inst, seed), {})))
    return runs


def read_runs(res_dir, manifest, tc, tmin):
    if not os.path.isdir(os.path.join(res_dir, "tar")):    # merged layout of the archive in study_results/
        return read_runs_merged(res_dir, manifest, tc, tmin)
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
                eax = {}
                lg = [n for n in names if n.endswith(".log")]
                if lg:
                    for line in tf.extractfile(names[lg[0]]).read().decode(errors="replace").splitlines():
                        if line.startswith("eax on=1"):
                            for kv in line.split()[2:]:
                                if "=" in kv:
                                    k, v = kv.split("=", 1)
                                    try: eax[k] = float(v)
                                    except ValueError: pass
                inst = r["Instance"]
                n = int(manifest[inst]["n"]) if inst in manifest else 0
                runs.append(dict(inst=inst, arm=r["Algorithm"], seed=int(r["Seed"]), cost=float(r["Total Latency"]), bks_run=float(r["Reference BKS"]),
                                 feasible=r["Feasible"] == "True", cpu=float(r["CPU Time"]), iters=int(r["Iterations"]), limit=max(tmin, tc * n / 100.0),
                                 verify=ver.lstrip().startswith("OK"), n=n, eax=eax))
    return runs


def read_control(path):
    """path: one run.csv, or the directory of an archive in the merged layout (<dir>/<family>/<arm>/run.csv), e.g. the extracted study_results/b1_tuned.tar.gz."""
    out = defaultdict(list)
    files = [path]
    if os.path.isdir(path):
        files = sorted(os.path.join(path, fam, arm, "run.csv") for fam in os.listdir(path) if os.path.isdir(os.path.join(path, fam))
                       for arm in os.listdir(os.path.join(path, fam)) if os.path.isfile(os.path.join(path, fam, arm, "run.csv")))
    for fn in files:
      with open(fn) as fh:
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
    ap.add_argument("--arm", default="B1_eax40")
    ap.add_argument("--ext-list", default="instances_ext.txt")
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
    with open(os.path.join(a.out, "x_runs.csv"), "w", newline="") as fh:
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
    with open(os.path.join(a.out, "x_instances.csv"), "w", newline="") as fh:
        w = csv.writer(fh); keys = list(rows[0].keys()) if rows else ["inst"]; w.writerow(keys)
        for r in rows: w.writerow([("%.5f" % r[k]) if isinstance(r[k], float) else r[k] for k in keys])

    # ------------------------------------------------------------------ criteria
    L = []
    P = L.append
    P("# B1-E extension: %s versus archived B1\n" % a.arm)
    ext = [l.strip() for l in open(a.ext_list) if l.strip()]
    exp_oth = [i for i in ext if i in manifest and int(manifest[i]["n"]) != 200]
    P("Runs read: %d (verified+feasible %d); instances complete (%d runs): %d; incomplete: %s\n" % (nread, nread - len(bad_runs), a.seeds, len(rows), ", ".join("%s(%d)" % x for x in incomplete) or "none"))
    n200 = [r for r in rows if r["n"] == 200]; oth = [r for r in rows if r["n"] != 200 and r["inst"] in exp_oth]
    P("## Criteria (pre-registered)\n")
    if n200:
        d = [r["delta"] for r in n200]; p = wx(d, "less"); m = mean(d)
        ok1 = len(n200) == 18 and m <= -0.03 and p < 0.05
        P("P1 efficacy, n=200 (%d of 18 instances complete): mean delta %+.4f (B1 mean gap %.4f -> %.4f); one-sided Wilcoxon p = %.4f; better on %d / worse on %d  ->  **%s**" % (
            len(n200), m, mean([r["mean_ctl"] for r in n200]), mean([r["mean_new"] for r in n200]), p, sum(x < -TOL for x in d), sum(x > TOL for x in d), "PASS" if ok1 else "FAIL" if len(n200) == 18 else "NOT EVALUABLE (incomplete)"))
    else:
        ok1 = False; P("P1: no complete n=200 instance")
    ok2 = None
    if oth:
        d = [r["delta"] for r in oth]; m = mean(d)
        harmed = [r["inst"] for r in oth if r["delta"] >= 0.10 and r["p_harm"] < 0.05]
        full = len(oth) == len(exp_oth)
        ok2 = m <= 0.02 and len(harmed) <= 3
        P("P2 no harm, n<200 evaluated (%d of %d instances complete): mean delta %+.4f (B1 mean gap %.4f -> %.4f); harmed instances %d (%s)  ->  **%s**" % (
            len(oth), len(exp_oth), m, mean([r["mean_ctl"] for r in oth]), mean([r["mean_new"] for r in oth]), len(harmed), ", ".join(harmed) or "-", ("PASS" if ok2 else "FAIL") + ("" if full else " (on the complete subset only)")))
    else:
        full = False; P("P2: no complete evaluated instance with n<200 yet")
    ok_s = (not bad_runs) and bool(ratios) and mean(ratios) <= 1.01 and max(ratios) <= 1.07
    P("S safety: %d runs, %d not feasible/verified; CPU/limit mean %.4f max %.4f  ->  **%s**" % (len(allruns), len(bad_runs), mean(ratios) if ratios else float("nan"), max(ratios) if ratios else float("nan"), "PASS" if ok_s else "FAIL"))
    if bks_diff:
        P("note: Reference BKS in the new runs differs from the control for: %s (gaps here use the control BKS)" % ", ".join(bks_diff))
    verdict = ok1 and ok2 is True and ok_s and full and len(n200) == 18
    P("\n**Verdict: %s**\n" % ("ADOPTION CANDIDATE (P1, P2, S hold on the complete evaluated set)" if verdict else "not adopted / not yet decidable (see the lines above)"))
    ex = [r["eax"] for r in allruns if r["eax"]]
    if ex:
        def col(k): return [e[k] for e in ex if k in e]
        P("## Mechanism (descriptive; %d runs with an eax line)\n" % len(ex))
        P("median generations %.0f; inserted into population %.0f; improved best %.1f per run (mean); runs whose best improved after the switch: %d of %d; structural failures %.2f per run" % (
            st.median(col("gens")), st.median(col("inserted")), mean(col("improved_best")), sum(1 for e in ex if e.get("improved_best", 0) > 0), len(ex), mean(col("fail_struct"))))
    P("")

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
    open(os.path.join(a.out, "x_summary.md"), "w").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
