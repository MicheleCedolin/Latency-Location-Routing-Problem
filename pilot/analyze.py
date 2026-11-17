#!/usr/bin/env python3
"""Pre-registered analysis of the v8 pilots (see PLAN.md).  usage: analyze.py <plan.json> <agg_dir> <out_dir> [<b1_archive.tar.gz>] [--limits limits.json]

agg_dir/<pilot>/<arm>/<instance>_s<seed>.{run.csv,routes.csv,verify,log,...}"""
import csv, glob, json, math, os, random, statistics as st, sys, tarfile
import numpy as np
from scipy import stats

def readrun(pre):
    try:
        row = next(csv.reader(open(pre + ".run.csv")))
    except Exception:
        return None
    d = {"seed": int(row[3]), "feasible": row[4] == "True", "cost": float(row[5]), "bks": float(row[6]), "gap": float(row[7]), "cpu": float(row[8]),
         "open": sorted(int(x) for x in row[9].strip('"[]').replace(" ", "").split(",") if x), "iters": int(row[21]), "stop": row[22], "wall": float(row[25])}
    try:
        v = open(pre + ".verify").read().strip().splitlines()
        d["verify_ok"] = bool(v) and v[0].startswith("OK")
    except Exception:
        d["verify_ok"] = False
    cnt = {}
    try:
        for r in csv.reader(open(pre + ".routes.csv")):
            cnt[int(r[4])] = cnt.get(int(r[4]), 0) + 1
    except Exception:
        pass
    d["rpd"] = cnt
    mech = {}
    try:
        for ln in open(pre + ".log"):
            t = ln.split()
            if t and t[0] in ("tabu", "pr"):
                for kv in t[1:]:
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        try: mech[t[0] + "." + k] = float(v)
                        except ValueError: pass
    except Exception:
        pass
    d["mech"] = mech
    return d

def msd(x): return (float(np.mean(x)), float(np.std(x, ddof=1)) if len(x) > 1 else float("nan"))

def boot_diff(x, c, B=20000, seed=1):
    rng = np.random.default_rng(seed); x = np.asarray(x); c = np.asarray(c)
    d = [rng.choice(x, len(x)).mean() - rng.choice(c, len(c)).mean() for _ in range(B)]
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))

def main():
    plan = json.load(open(sys.argv[1])); agg, out = sys.argv[2], sys.argv[3]
    arch = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith("--") else None
    limits = {}
    if "--limits" in sys.argv: limits = json.load(open(sys.argv[sys.argv.index("--limits") + 1]))
    os.makedirs(out, exist_ok=True)
    clus = {}
    if arch and os.path.exists(arch):
        with tarfile.open(arch) as tf:
            f = tf.extractfile("results_b1/tuzun/B1/run.csv")
            for row in csv.reader(l.decode() for l in f):
                if row and row[0] != "Instance": clus.setdefault(row[0], []).append((float(row[7]), int(row[21]), float(row[8])))
    md = ["# v8 pilots: results\n"]
    allrows = []
    for P in plan["pilots"]:
        nm = P["name"]; inst = os.path.basename(P["instance"]); arms = P["arms"]; C, X = arms[0], arms[1]
        lim = limits.get(nm, {}).get("cpu_limit_s")
        R = {a: [r for r in (readrun(p[:-8]) for p in sorted(glob.glob(os.path.join(agg, nm, a, inst + "_s*.run.csv")))) if r] for a in arms}
        md.append("## %s  (%s, %s vs %s%s)\n" % (nm, P["instance"], C, X, "" if P.get("primary", True) else ", EXPLORATORY"))
        md.append("CPU limit per run: %s s (cluster-equivalent budget x %s); BKS %.2f; Zou f_avg %.2f; Zou depots %s\n" % (lim, P["factor"], P["bks"], P["zou_avg"], P["zou_depots"]))
        if inst in clus:
            g = [x[0] for x in clus[inst]]; md.append("Cluster B1 reference (30 runs, 3n s CPU): mean gap %.3f, sd %.3f, best %.3f, mean iterations %.1f\n" % (np.mean(g), np.std(g, ddof=1), min(g), np.mean([x[1] for x in clus[inst]])))
        md.append("| arm | runs | feasible+verify | mean gap % | sd | median | best | runs <= BKS+0.005 | runs <= Zou f_avg | mean iters | CPU/limit mean (max) | final set = Zou set | allocation = Zou |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for a in arms:
            rs = R[a]
            if not rs: md.append("| %s | 0 | - |" % a); continue
            gaps = [r["gap"] for r in rs]
            hits = sum(1 for r in rs if r["cost"] <= P["bks"] + 0.005)
            zavg = sum(1 for r in rs if r["cost"] <= P["zou_avg"] + 1e-9)
            ok = sum(1 for r in rs if r["feasible"] and r["verify_ok"])
            zset = sum(1 for r in rs if r["open"] == sorted(P["zou_depots"]))
            zalloc = ""
            if "zou_routes_per_depot" in P:
                tgt = dict(zip(sorted(P["zou_depots"]), P["zou_routes_per_depot"]))
                zalloc = sum(1 for r in rs if r["rpd"] == tgt)
            ratio = [r["cpu"] / lim for r in rs] if lim else [float("nan")]
            m, s = msd(gaps)
            md.append("| %s | %d | %d | %.3f | %.3f | %.3f | %.3f | %d | %d | %.1f | %.3f (%.3f) | %d | %s |" % (a, len(rs), ok, m, s, np.median(gaps), min(gaps), hits, zavg, np.mean([r["iters"] for r in rs]), np.mean(ratio), max(ratio), zset, zalloc))
            for r in rs: allrows.append([nm, a, r["seed"], r["cost"], r["gap"], r["cpu"], r["iters"], ";".join(map(str, r["open"])), r["feasible"], r["verify_ok"]])
        if R[C] and R[X]:
            xc = [r["gap"] for r in R[C]]; xx = [r["gap"] for r in R[X]]
            delta = float(np.mean(xx) - np.mean(xc))
            u = stats.mannwhitneyu(xx, xc, alternative="less")
            lo, hi = boot_diff(xx, xc)
            pc = {r["seed"]: r["gap"] for r in R[C]}; px = {r["seed"]: r["gap"] for r in R[X]}
            common = sorted(set(pc) & set(px))
            w = stats.wilcoxon([px[s] - pc[s] for s in common]) if len(common) > 5 else None
            md.append("\nmean gap %s - %s = %+.3f points (bootstrap 95%% CI %+.3f .. %+.3f); one-sided Mann-Whitney U (%s < %s): p = %.4g; paired (same seed) Wilcoxon two-sided p = %s; seeds with %s better: %d / %d" % (
                X, C, delta, lo, hi, X, C, u.pvalue, "%.4g" % w.pvalue if w else "n/a", X, sum(1 for s in common if px[s] < pc[s]), len(common)))
            hc = sum(1 for r in R[C] if r["cost"] <= P["bks"] + 0.005); hx = sum(1 for r in R[X] if r["cost"] <= P["bks"] + 0.005)
            zc = sum(1 for r in R[C] if r["cost"] <= P["zou_avg"] + 1e-9); zx = sum(1 for r in R[X] if r["cost"] <= P["zou_avg"] + 1e-9)
            ok = all(r["feasible"] and r["verify_ok"] for a in arms for r in R[a]) and all(len(R[a]) == P["seeds"] for a in arms)
            cr = [r["cpu"] / lim for a in arms for r in R[a]] if lim else [1.0]
            P0 = delta <= -0.15 and u.pvalue < 0.01
            S = ok and np.mean(cr) <= 1.01 and max(cr) <= 1.07
            md.append("\n**Pre-registered criteria** (PLAN.md): P0 (mean gap drop >= 0.15 points and p < 0.01): **%s** | P1 (more runs at BKS+0.005: %d vs %d): **%s** | P2 (more runs <= Zou f_avg: %d vs %d): **%s** | S (30/30 feasible + verify OK per arm, CPU/limit mean <= 1.01 and max <= 1.07): **%s**" % (
                "PASS" if P0 else "fail", hx, hc, "PASS" if hx > hc else "fail", zx, zc, "PASS" if zx > zc else "fail", "PASS" if S else "FAIL"))
            md.append("\nVerdict: %s\n" % ("candidate for the generalisation test (single-instance pilot: not a result for the paper)" if (P0 and S) else "no adoption: P0 not met" if S else "safety criterion failed: inspect before reading the quality numbers"))
        for a in arms:
            ms = {}
            for r in R[a]:
                for k, v in r["mech"].items(): ms.setdefault(k, []).append(v)
            if ms: md.append("Mechanism counters, arm %s (mean per run): %s\n" % (a, ", ".join("%s=%.2f" % (k, np.mean(v)) for k, v in sorted(ms.items()))))
        md.append("")
    open(os.path.join(out, "pilot_summary.md"), "w").write("\n".join(md))
    with open(os.path.join(out, "pilot_runs.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["pilot", "arm", "seed", "cost", "gap_pct", "cpu_s", "iterations", "open_depots", "feasible", "verify_ok"]); w.writerows(allrows)
    print("\n".join(md))

main()
