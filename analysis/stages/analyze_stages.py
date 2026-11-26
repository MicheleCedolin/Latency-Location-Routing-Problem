#!/usr/bin/env python3
"""Stage-by-stage comparison of the method on the 57 instances with n >= 100 (stages 2, 3 and 4 of the manuscript) and the pre-registered criteria of stages 3 and 4.

  python3 -I analyze_stages.py --base DIR_EXT10 --depot DIR_DEPOT --pool DIR_B1 --manifest cpp/manifest.tsv --literature bks/literature_results.csv --instances cpp/stages/instances_n100.txt --out OUTDIR
  (DIR_EXT10 = extracted study_results/ext10_tuned.tar.gz, DIR_DEPOT = extracted depot_tuned.tar.gz, DIR_B1 = extracted b1_tuned.tar.gz; the layout is <dir>/<family>/<arm>/run.csv)

Arms (cumulative flags of one engine, see cpp/stages/):  ext10 = base method at the budget 3n s (stage 2)  ->  V1 = + depot-aware diversification (stage 3)  ->  B1 = + route pool (stage 4).
Every arm: 57 instances x 30 seeds (1..30), CPU limit max(5, 3n) s per run.  Instance gap = mean over the 30 runs of the gap (%) to the best-known value of cpp/manifest.tsv.
hit = best of the 30 runs <= BKS + 0.005.  Zou f_avg / Zou best = average / best value of RLHEA (Zou et al. 2024) in bks/literature_results.csv (hardware not normalised).

Stage 3, V1 against ext10 (plans/PLAN_stage3_depot.md; fixed 15 Nov 2026 before any result of the 57 instances existed):
  G0  overall improvement:  one-sided Wilcoxon signed-rank on the 57 instance gaps (V1 < ext10) p < 0.01  AND  mean drop >= 0.15 points
  G1  hard class:           mean gap of V1 over the 30 instances with n >= 150 <= 0.60 %
  G2  Zou average:          number of instances whose mean latency over the 30 runs is <= Zou f_avg is >= 10 of 57
  Z   harm:                 number of instances whose gap is more than 0.2 points WORSE than ext10 is <= 5 of 57 (each is listed)
  Reading rule: G0 and G1 met -> "V1 generalises to n > 75"; only G0 -> "partially"; none -> the pilot result is read as selection bias.
Stage 4, B1 against V1 (plans/PLAN_stage4_pool.md; criteria recorded on 15 Nov 2026 before the 57-instance results existed):
  G1  hard class:           mean gap drop over the 30 instances with n >= 150 >= 0.10 points
  G0  overall improvement:  one-sided Wilcoxon p < 0.01 on the 57 instance gaps (B1 < V1)  AND  mean drop >= 0.10 points
  Z   harm:                 number of instances more than 0.2 points WORSE than V1 is <= 5 of 57
Descriptive only (never replaces a criterion): class tables, hits, Zou comparison, same-seed counts, instance bootstrap intervals, anytime values, run-time integrity, set-partitioning log.
"""
import argparse, csv, math, os, random, sys
from collections import defaultdict

try:
    from scipy.stats import wilcoxon
except Exception:
    sys.exit("analyze_stages.py needs scipy (python3 -m pip install scipy)")

TOL = 0.005                 # hit tolerance (latency units)
TC, TMIN = 300.0, 5.0       # CPU limit max(TMIN, TC * n / 100) s = 3n s
SEEDS = list(range(1, 31))
ARMS = ["ext10", "V1", "B1"]
BOOT_B, BOOT_SEED = 10000, 20261116
STAGE3 = dict(g0_p=0.01, g0_drop=0.15, g1_max=0.60, g2_min=10, z_margin=0.2, z_max=5)
STAGE4 = dict(g1_drop=0.10, g0_p=0.01, g0_drop=0.10, z_margin=0.2, z_max=5)
CLASSES = [("n=100", lambda n: n == 100), ("n=117/134", lambda n: n in (117, 134)), ("n=150", lambda n: n == 150), ("n=200", lambda n: n == 200),
           ("n>=150", lambda n: n >= 150), ("all", lambda n: True)]
PILOT = "P121122-20"        # instance on which the depot mechanism was selected (kept in every criterion; shown without it as a robustness check)


def mean(a):
    a = list(a)
    return sum(a) / len(a) if a else float("nan")


def wx(d, alt):
    """one-sided Wilcoxon signed-rank p value of the paired differences d (zero differences are dropped, scipy's default zero_method)"""
    if len(d) < 2 or all(abs(x) < 1e-12 for x in d):
        return float("nan")
    return float(wilcoxon(d, alternative=alt, method="approx").pvalue)     # normal approximation, fixed so that the printed p does not depend on the scipy version (52 non-zero differences)


def boot_ci(d, b=BOOT_B, seed=BOOT_SEED):
    """95 % percentile interval of the mean of the instance differences d (instances resampled with replacement)"""
    rnd, n, ms = random.Random(seed), len(d), []
    for _ in range(b):
        ms.append(sum(d[int(rnd.random() * n)] for _ in range(n)) / n)
    ms.sort()
    return ms[int(0.025 * b)], ms[int(0.975 * b) - 1]


def fp(p):
    return "nan" if p != p else "%.2g" % p


def read_manifest(path):
    with open(path) as fh:
        return {r["name"]: dict(family=r["family"], n=int(r["n"]), bks=float(r["bks"])) for r in csv.DictReader(fh, delimiter="\t")}


def read_instances(path):
    with open(path) as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def read_literature(path):
    out = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            if r["algorithm"] == "RLHEA":
                out[r["instance"]] = dict(best=float(r["best"]), avg=float(r["avg"]), time=float(r["time_s"]))
    return out


def read_arm(root, arm, man, insts):
    """{instance: [run dicts sorted by seed]} of one archive in the merged layout; only the instances of the list are kept"""
    runs, bks_mismatch, ver = defaultdict(list), 0, {}
    for fam in sorted(os.listdir(root)):
        d = os.path.join(root, fam, arm)
        if not os.path.isfile(os.path.join(d, "run.csv")):
            continue
        if os.path.isfile(os.path.join(d, "verify.txt")):
            for ln in open(os.path.join(d, "verify.txt"), encoding="utf-8"):
                p = ln.split()
                if len(p) >= 2:
                    ver[p[1]] = p[0]
        with open(os.path.join(d, "run.csv"), encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                name = r["Instance"]
                if name not in insts:
                    continue
                if abs(float(r["Reference BKS"]) - man[name]["bks"]) > 1e-6:
                    bks_mismatch += 1
                n = man[name]["n"]
                runs[name].append(dict(seed=int(r["Seed"]), cost=float(r["Total Latency"]), feasible=r["Feasible"] == "True", cpu=float(r["CPU Time"]), iters=int(r["Iterations"]),
                                       stop=r["Stop Reason"], limit=max(TMIN, TC * n / 100.0), verified=(ver.get("%s_s%s_%s" % (name, r["Seed"], arm)) == "OK") if ver else None))
    for name in runs:
        runs[name].sort(key=lambda x: x["seed"])
    return runs, bks_mismatch, bool(ver)


def read_traces(root, arm, insts):
    """{(instance, seed): [(cpu, best latency), ...]}"""
    tr = defaultdict(list)
    for fam in sorted(os.listdir(root)):
        fn = os.path.join(root, fam, arm, "trace.csv")
        if not os.path.isfile(fn):
            continue
        with open(fn, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["Instance"] in insts:
                    tr[(r["Instance"], int(r["Seed"]))].append((float(r["CPU Seconds"]), float(r["Best Latency"])))
    return tr


def read_pool(root, arm, insts):
    rows = []
    for fam in sorted(os.listdir(root)):
        fn = os.path.join(root, fam, arm, "pool.csv")
        if os.path.isfile(fn):
            with open(fn, encoding="utf-8") as fh:
                rows += [r for r in csv.DictReader(fh) if r["Instance"] in insts]
    return rows


def best_at(trace, t):
    """best latency of a run at CPU time t (last trace point not after t), or None if the run has no point yet"""
    v = None
    for c, b in trace:
        if c > t + 1e-9:
            break
        v = b
    return v


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="extracted ext10 archive (tag ext10)")
    ap.add_argument("--depot", required=True, help="extracted depot archive (tag V1)")
    ap.add_argument("--pool", required=True, help="extracted b1 archive (tag B1)")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--literature", required=True)
    ap.add_argument("--instances", required=True, help="list of the 57 instances (cpp/stages/instances_n100.txt)")
    ap.add_argument("--pmedian", default=None, help="bks/reference/pmedian_rank_of_published_depot_sets.csv (optional; adds the rank of the published depot set to the list of harmed instances)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    man, lit, names = read_manifest(a.manifest), read_literature(a.literature), read_instances(a.instances)
    insts = set(names)
    roots = dict(zip(ARMS, [a.base, a.depot, a.pool]))
    runs, mism, hasver = {}, {}, {}
    for arm in ARMS:
        runs[arm], mism[arm], hasver[arm] = read_arm(roots[arm], arm, man, insts)
    incomplete = sorted({"%s:%s(%d)" % (arm, nm, len(runs[arm].get(nm, []))) for arm in ARMS for nm in names
                         if [r["seed"] for r in runs[arm].get(nm, []) if r["feasible"]] != SEEDS})
    if incomplete:
        sys.exit("incomplete instances (need 30 feasible runs with seeds 1..30): " + ", ".join(incomplete))

    gap = {arm: {} for arm in ARMS}        # instance -> mean gap %
    bestgap, hit, mlat, bestlat = ({arm: {} for arm in ARMS} for _ in range(4))
    for arm in ARMS:
        for nm in names:
            b = man[nm]["bks"]
            g = [(r["cost"] - b) / b * 100.0 for r in runs[arm][nm]]
            gap[arm][nm] = mean(g)
            bestlat[arm][nm] = min(r["cost"] for r in runs[arm][nm])
            bestgap[arm][nm] = (bestlat[arm][nm] - b) / b * 100.0
            hit[arm][nm] = bestlat[arm][nm] <= b + TOL
            mlat[arm][nm] = mean(r["cost"] for r in runs[arm][nm])
    size = {nm: man[nm]["n"] for nm in names}
    hard = [nm for nm in names if size[nm] >= 150]

    L = []
    add = L.append
    add("# Stage-by-stage comparison, 57 instances with n >= 100, 30 seeds per arm (regenerated by analysis/stages/analyze_stages.py)")
    add("")
    add("Gap = percentage above the best-known value, mean over 30 runs per instance, then mean over instances; hit = best of 30 <= BKS + 0.005.")
    add("")
    add("## Integrity of the three archives")
    rows = []
    for arm in ARMS:
        allr = [r for nm in names for r in runs[arm][nm]]
        ratio = [r["cpu"] / r["limit"] for r in allr]
        ver = ("%d/%d" % (sum(1 for r in allr if r["verified"]), len(allr))) if hasver[arm] else "no verify.txt in the archive"
        rows.append((arm, len(allr), "%d/%d" % (sum(r["feasible"] for r in allr), len(allr)), ver, "%.4f" % mean(ratio), "%.4f" % max(ratio),
                     "%d/%d" % (sum(r["stop"] == "time" for r in allr), len(allr)), mism[arm]))
    L += md_table(["arm", "runs", "feasible", "independently verified", "CPU / limit mean", "CPU / limit max", "stop reason time", "BKS differs from manifest"], rows)
    add("")

    # ---------- criteria
    def crit_pair(first, second, label):
        """differences second - first per instance (negative = second better)"""
        return [gap[second][nm] - gap[first][nm] for nm in names]

    d3 = crit_pair("ext10", "V1", "stage 3")
    d4 = crit_pair("V1", "B1", "stage 4")
    d34 = crit_pair("ext10", "B1", "stages 3+4")
    gmean = lambda arm, sel=names: mean(gap[arm][nm] for nm in sel)

    add("## Stage 3: depot-aware diversification (V1 against ext10), pre-registered criteria")
    s = STAGE3
    p3, drop3 = wx(d3, "less"), gmean("ext10") - gmean("V1")
    g0 = p3 < s["g0_p"] and drop3 >= s["g0_drop"]
    g1v = gmean("V1", hard)
    g1 = g1v <= s["g1_max"]
    zou_n = {arm: sum(mlat[arm][nm] <= lit[nm]["avg"] + 1e-9 for nm in names if nm in lit) for arm in ARMS}
    g2 = zou_n["V1"] >= s["g2_min"]
    harmed3 = sorted((nm for nm in names if gap["V1"][nm] - gap["ext10"][nm] > s["z_margin"]), key=lambda x: -(gap["V1"][x] - gap["ext10"][x]))
    z = len(harmed3) <= s["z_max"]
    ci3 = boot_ci(d3)
    better3, worse3 = sum(x < -1e-9 for x in d3), sum(x > 1e-9 for x in d3)
    rows = [("G0 overall (p < 0.01 and drop >= 0.15)", "MET" if g0 else "NOT MET", "mean gap %.3f -> %.3f (drop %.3f); one-sided Wilcoxon p = %s; V1 better on %d, worse on %d, equal on %d instances"
             % (gmean("ext10"), gmean("V1"), drop3, fp(p3), better3, worse3, len(names) - better3 - worse3)),
            ("G1 hard class (n >= 150 mean <= 0.60)", "MET" if g1 else "NOT MET", "V1 %.3f (ext10 %.3f), %d instances" % (g1v, gmean("ext10", hard), len(hard))),
            ("G2 Zou average (>= 10 of 57)", "MET" if g2 else "NOT MET", "%d of %d instances with mean <= Zou f_avg (ext10: %d)" % (zou_n["V1"], len(names), zou_n["ext10"])),
            ("Z harm (<= 5 of 57 worse by > 0.2)", "WITHIN THE LIMIT" if z else "EXCEEDED", "%d of %d: %s" % (len(harmed3), len(names), ", ".join("%s (%+.3f)" % (x, gap["V1"][x] - gap["ext10"][x]) for x in harmed3) or "none"))]
    L += md_table(["criterion", "verdict", "value"], rows)
    add("")
    reading3 = "V1 generalises to n > 75" if (g0 and g1) else ("V1 generalises partially" if g0 else "the pilot result is read as selection bias")
    add("Reading rule of the plan: %s.  Instance-bootstrap 95 %% interval of the mean difference: %.3f ... %.3f (%d resamples, seed %d)." % (reading3, ci3[0], ci3[1], BOOT_B, BOOT_SEED))
    nopilot = [nm for nm in names if nm != PILOT]
    add("Without the pilot instance %s (%d instances): %.3f -> %.3f, p = %s; n >= 150 (%d instances): %.3f -> %.3f." % (
        PILOT, len(nopilot), gmean("ext10", nopilot), gmean("V1", nopilot), fp(wx([gap["V1"][x] - gap["ext10"][x] for x in nopilot], "less")),
        len([x for x in hard if x != PILOT]), gmean("ext10", [x for x in hard if x != PILOT]), gmean("V1", [x for x in hard if x != PILOT])))
    if harmed3 and a.pmedian and os.path.isfile(a.pmedian):
        with open(a.pmedian) as fh:
            pm = {r["name"].lstrip("P"): r for r in csv.DictReader(fh)}
        for x in harmed3:
            key = x.rsplit("-", 1)[0].lstrip("P")
            if key in pm:
                add("Harmed instance %s: the published depot set is number %s of %s in the p-median ranking of the depot subsets (the focus window of V1 is the best 10)." % (x, pm[key]["pmedian_rank"], pm[key]["subsets"]))
    add("")

    add("## Stage 4: route pool with set partitioning (B1 against V1), pre-registered criteria")
    s = STAGE4
    drop4 = gmean("V1") - gmean("B1")
    dh4 = gmean("V1", hard) - gmean("B1", hard)
    p4 = wx(d4, "less")
    g1b = dh4 >= s["g1_drop"]
    g0b = p4 < s["g0_p"] and drop4 >= s["g0_drop"]
    harmed4 = sorted((nm for nm in names if gap["B1"][nm] - gap["V1"][nm] > s["z_margin"]), key=lambda x: -(gap["B1"][x] - gap["V1"][x]))
    zb = len(harmed4) <= s["z_max"]
    ci4 = boot_ci(d4)
    better4, worse4 = sum(x < -1e-9 for x in d4), sum(x > 1e-9 for x in d4)
    rows = [("G1 hard class (n >= 150 drop >= 0.10)", "MET" if g1b else "NOT MET", "V1 %.3f -> B1 %.3f (drop %.3f), %d instances" % (gmean("V1", hard), gmean("B1", hard), dh4, len(hard))),
            ("G0 overall (p < 0.01 and drop >= 0.10)", "MET" if g0b else "NOT MET", "mean gap %.3f -> %.3f (drop %.3f); one-sided Wilcoxon p = %s; B1 better on %d, worse on %d, equal on %d instances"
             % (gmean("V1"), gmean("B1"), drop4, fp(p4), better4, worse4, len(names) - better4 - worse4)),
            ("Z harm (<= 5 of 57 worse by > 0.2)", "WITHIN THE LIMIT" if zb else "EXCEEDED", "%d of %d: %s" % (len(harmed4), len(names), ", ".join("%s (%+.3f)" % (x, gap["B1"][x] - gap["V1"][x]) for x in harmed4) or "none"))]
    L += md_table(["criterion", "verdict", "value"], rows)
    add("")
    worst4 = max(gap["B1"][nm] - gap["V1"][nm] for nm in names)
    add("Worst single instance: B1 - V1 = %+.3f.  Instance-bootstrap 95 %% interval of the mean difference: %.3f ... %.3f.  Instances worse than V1 by any amount: %s." % (
        worst4, ci4[0], ci4[1], ", ".join("%s (%+.4f)" % (x, gap["B1"][x] - gap["V1"][x]) for x in names if gap["B1"][x] - gap["V1"][x] > 1e-9) or "none"))
    add("Without the pilot instance %s (%d instances): %.3f -> %.3f, p = %s." % (PILOT, len(nopilot), gmean("V1", nopilot), gmean("B1", nopilot),
                                                                                    fp(wx([gap["B1"][x] - gap["V1"][x] for x in nopilot], "less"))))
    add("")

    # ---------- descriptive tables
    add("## Mean gap (%) by size class, and instances reaching the best-known value (hit)")
    rows = []
    for lab, f in CLASSES:
        sel = [nm for nm in names if f(size[nm])]
        if sel:
            rows.append((lab, len(sel)) + tuple("%.3f" % gmean(arm, sel) for arm in ARMS) + ("%.3f" % (gmean("V1", sel) - gmean("ext10", sel)), "%.3f" % (gmean("B1", sel) - gmean("V1", sel)))
                        + ("%d / %d / %d" % tuple(sum(hit[arm][nm] for nm in sel) for arm in ARMS), "%.3f" % mean(bestgap["B1"][nm] for nm in sel)))
    L += md_table(["class", "#", "ext10", "V1", "B1", "V1 - ext10", "B1 - V1", "hit ext10 / V1 / B1", "best-of-30 gap B1"], rows)
    add("")
    add("## Mean gap (%) by instance family")
    rows = []
    for fam in sorted({man[nm]["family"] for nm in names}):
        sel = [nm for nm in names if man[nm]["family"] == fam]
        rows.append((fam, len(sel)) + tuple("%.3f" % gmean(arm, sel) for arm in ARMS))
    L += md_table(["family", "#", "ext10", "V1", "B1"], rows)
    add("")

    add("## Comparison with the published RLHEA values (hardware not normalised; descriptive)")
    rows = []
    for arm in ARMS:
        rows.append((arm, "%d / %d" % (zou_n[arm], len(names)), "%d / %d" % (sum(bestlat[arm][nm] <= lit[nm]["best"] + 1e-9 for nm in names if nm in lit), len(names)),
                     "%d / %d" % (sum(hit[arm][nm] for nm in names), len(names)), sum(1 for nm in names for r in runs[arm][nm] if r["cost"] < man[nm]["bks"] - TOL)))
    L += md_table(["arm", "mean latency <= Zou f_avg", "best of 30 <= Zou best", "best of 30 <= BKS + 0.005", "runs below the BKS"], rows)
    add("")

    add("## Same-seed comparison (the seed paths separate in the first iteration, so this is descriptive)")
    rows = []
    for x, y in (("ext10", "V1"), ("V1", "B1"), ("ext10", "B1")):
        bet = wor = eq = 0
        for nm in names:
            for rx, ry in zip(runs[x][nm], runs[y][nm]):
                dlt = ry["cost"] - rx["cost"]
                if dlt < -1e-6:
                    bet += 1
                elif dlt > 1e-6:
                    wor += 1
                else:
                    eq += 1
        dd = {("ext10", "V1"): d3, ("V1", "B1"): d4, ("ext10", "B1"): d34}[(x, y)]
        lo, hi = boot_ci(dd)
        rows.append(("%s -> %s" % (x, y), "%d / %d / %d" % (sum(v < -1e-9 for v in dd), sum(v > 1e-9 for v in dd), sum(abs(v) <= 1e-9 for v in dd)), fp(wx(dd, "less")),
                     "%.3f (%.3f ... %.3f)" % (mean(dd), lo, hi), "%d / %d / %d" % (bet, wor, eq)))
    L += md_table(["step", "instances better / worse / equal", "Wilcoxon p (one-sided)", "mean difference (95 % bootstrap)", "same-seed runs better / worse / equal"], rows)
    add("")

    # ---------- anytime
    add("## Anytime: mean gap (%) of the incumbent at multiples of b = max(5, 0.3 n) s CPU and at the average run time of RLHEA")
    tr = {arm: read_traces(roots[arm], arm, insts) for arm in ARMS}
    points = [("1b", lambda nm: 1 * max(5.0, 0.3 * size[nm])), ("2b", lambda nm: 2 * max(5.0, 0.3 * size[nm])), ("5b", lambda nm: 5 * max(5.0, 0.3 * size[nm])),
              ("10b", lambda nm: 10 * max(5.0, 0.3 * size[nm])), ("Zou T_avg", lambda nm: lit[nm]["time"] if nm in lit else float("nan"))]
    rows, skipped = [], defaultdict(int)
    for lab, tf in points:
        vals = {}
        for arm in ARMS:
            per = []
            for nm in names:
                lim = max(TMIN, TC * size[nm] / 100.0)
                t = tf(nm)
                if not t < lim - 1e-9:                       # the end of the run: the CPU limit is checked at the end of an iteration (for B1 also of a set-partitioning call), so the last
                    t = float("inf")                         # trace point can lie a little after the limit; the point is then the final value of the run
                g = []
                for sd in SEEDS:
                    v = best_at(tr[arm].get((nm, sd), []), t)
                    if v is None:
                        skipped[arm] += 1
                    else:
                        g.append((v - man[nm]["bks"]) / man[nm]["bks"] * 100.0)
                if g:
                    per.append(mean(g))
            vals[arm] = mean(per)
        rows.append((lab,) + tuple("%.3f" % vals[arm] for arm in ARMS) + ("%.3f" % (vals["V1"] - vals["ext10"]), "%.3f" % (vals["B1"] - vals["V1"])))
    L += md_table(["point", "ext10", "V1", "B1", "V1 - ext10", "B1 - V1"], rows)
    add("")
    add("Runs without a trace point yet at an evaluation time (left out of that mean): %s.  The trace of B1 includes the improvements accepted by the set-partitioning step. "
        "Zou T_avg is the published average run time of RLHEA on another machine. A point at or beyond the run limit (10b, and Zou T_avg when it is longer than the limit) is the final value of the run." % (", ".join("%s %d" % (k, v) for k, v in sorted(skipped.items())) or "none"))
    add("")

    # ---------- set-partitioning log
    pool = read_pool(roots["B1"], "B1", insts)
    add("## Set-partitioning step of B1 (pool.csv, descriptive)")
    if pool:
        per_run = defaultdict(list)
        for r in pool:
            per_run[(r["Instance"], r["Seed"])].append(r)
        calls = [len(v) for v in per_run.values()]
        spcpu = [sum(float(r["sp_cpu_s"]) for r in v) for v in per_run.values()]
        share = [sum(float(r["sp_cpu_s"]) for r in per_run[(nm, str(sd))]) / max(TMIN, TC * size[nm] / 100.0) for nm in names for sd in SEEDS if (nm, str(sd)) in per_run]
        improved = sum(any(r["improved"] == "1" for r in v) for v in per_run.values())
        add("Runs with a log: %d.  Calls per run: mean %.2f.  Set-partitioning CPU per run: mean %.2f s, median %.2f s, max %.2f s (mean share of the CPU limit %.2f %%).  Runs with at least one improving call: %.1f %%."
            % (len(per_run), mean(calls), mean(spcpu), sorted(spcpu)[len(spcpu) // 2], max(spcpu), 100.0 * mean(share), 100.0 * improved / len(per_run)))
        rows = []
        for k in (1, 2, 3, 4):
            sel = [r for r in pool if int(r["call"]) == k] if k < 4 else [r for r in pool if int(r["call"]) >= 4]
            if sel:
                rows.append(("%d%s" % (k, "+" if k == 4 else ""), len(sel), "%.1f %%" % (100.0 * sum(r["complete"] == "1" for r in sel) / len(sel)), "%.1f %%" % (100.0 * sum(r["improved"] == "1" for r in sel) / len(sel))))
        L += md_table(["call", "calls", "proved optimal (complete)", "improved the incumbent"], rows)
    else:
        add("No pool.csv in the archive.")
    add("")

    with open(os.path.join(a.out, "stages_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(a.out, "stages_instances.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["instance", "family", "n", "bks", "zou_avg", "zou_best"] + ["gap_" + arm for arm in ARMS] + ["bestgap_" + arm for arm in ARMS] + ["hit_" + arm for arm in ARMS])
        for nm in names:
            w.writerow([nm, man[nm]["family"], size[nm], "%.2f" % man[nm]["bks"], lit[nm]["avg"] if nm in lit else "", lit[nm]["best"] if nm in lit else ""]
                       + ["%.4f" % gap[arm][nm] for arm in ARMS] + ["%.4f" % bestgap[arm][nm] for arm in ARMS] + [int(hit[arm][nm]) for arm in ARMS])
    print("\n".join(L))
    return dict(g0=g0, g1=g1, g2=g2, z=z, g1b=g1b, g0b=g0b, zb=zb)


if __name__ == "__main__":
    main()
