#!/usr/bin/env python3
"""Final method against the published algorithms: per-instance table and the paired comparisons (win / tie / loss, Wilcoxon), regenerated from the result archives.

  python3 -I analysis/final/final_vs_published.py [--archives study_results] [--out DIR] [--no-atmost]

"Final method" = the method as reported in the manuscript, one source per instance:
    n <= 50      base method, standard budget  (final_1x_tuned.tar.gz, tag `tuned`, CPU limit max(5, 0.3 n) s)
    n == 75      base method, extended budget  (ext10_tuned.tar.gz,   tag `ext10`,  3 n s)        [Ch75-10: the layers were run for n >= 100 only]
    n >  75      base method + depot layer + route pool (b1_tuned.tar.gz, arm `B1`, 3 n s including the set-partitioning time)
  Every source: 30 seeds, all runs feasible.  Prins 50-5-2BIS-5 is reported with the 30 runs of atmost_50-5-2BIS-5.tar.gz (at most Ng open depots, 945.45 = BKS),
  as in the manuscript; `--no-atmost` keeps the runs of the default setting (exactly Ng open depots) of final_1x_tuned.tar.gz for this instance.

Published values: bks/literature_results.csv (best, average of every algorithm; GBILS has best values only, 38 instances).  Gap = 100 (x - BKS) / BKS, BKS of cpp/manifest.tsv.
Rules (fixed, the same for every algorithm):
  * ours: best of the 30 runs and mean of the 30 runs, both rounded to two decimals (the precision of the published values and of the tables);
  * win / tie / loss: |ours - theirs| <= 0.005 is a tie; our mean is compared with their Avg, our best with their Best;
  * Wilcoxon signed-rank test on the paired gap differences, ties dropped, two-sided, normal approximation without continuity correction (scipy, method="approx");
  * subsets: all 76 instances; n >= 75 (58); held-out n >= 75 (45; the instances not in cpp/selection/train.txt); n >= 150 (30); n = 200 (18).
SA-VND is reported per variant and as "best variant" (per instance the smaller of the three variant averages / best values).

Writes  DIR/final_per_instance.csv, DIR/final_per_instance.tex (longtable) and DIR/final_vs_published.md.  CI compares the three files with analysis/final/reference/.
"""
import argparse, csv, io, os, sys, tarfile
from collections import defaultdict

try:
    from scipy.stats import wilcoxon
except Exception:
    sys.exit("final_vs_published.py needs scipy (python3 -m pip install scipy)")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
TIE = 0.005
FAMILIES = ("barreto", "prins", "tuzun")
ALGOS = ["RLHEA", "MS-VNS", "M-ILS", "SA-VND0", "SA-VND1", "SA-VND2", "MA", "GBILS"]
SOURCES = [("final_1x_tuned.tar.gz", "results_final/{fam}/tuned/run.csv", "1x"),
           ("ext10_tuned.tar.gz", "results_extended10/{fam}/ext10/run.csv", "ext10"),
           ("b1_tuned.tar.gz", "results_b1/{fam}/B1/run.csv", "B1")]
ATMOST = ("atmost_50-5-2BIS-5.tar.gz", "results_atmost/run.csv")
AT_INSTANCE = "50-5-2BIS-5"
# GBILS (Nucamendi-Guillen et al. 2022) lists Christofides69 50x5 / 75x10 / 100x10 with best values (1719.89 / 2399.28 / 3984.05) that do not belong to this repository's Ch50-5 / Ch75-10 / Ch100-10
# (BKS 1661.64 / 2362.48 / 3788.96: a different variant of the same base network); the other 35 GBILS rows agree with the BKS table.  The three are left out of every comparison.
GBILS_UNMATCHED = {"Ch50-5", "Ch75-10", "Ch100-10"}


def gap(x, bks):
    return 100.0 * (x - bks) / bks


def f2(x):
    return "%.2f" % x


def f3(x):
    """three decimals, never a negative zero"""
    t = "%.3f" % x
    return "0.000" if t == "-0.000" else t


def fp(p):
    return "nan" if p != p else ("%.2g" % p if p < 0.01 else "%.3f" % p)


def read_member(tar_path, member):
    with tarfile.open(tar_path) as tf:
        return io.TextIOWrapper(tf.extractfile(member), encoding="utf-8", newline="").read()


def read_runs(text):
    runs = defaultdict(list)
    for r in csv.DictReader(io.StringIO(text)):
        if r["Feasible"] == "True":
            runs[r["Instance"]].append(float(r["Total Latency"]))
    return runs


def read_manifest(path):
    with open(path) as fh:
        return {r["name"]: dict(family=r["family"], n=int(r["n"]), bks=float(r["bks"])) for r in csv.DictReader(fh, delimiter="\t")}


def read_literature(path):
    lit = defaultdict(dict)
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["algorithm"] == "GBILS" and r["instance"] in GBILS_UNMATCHED:
                continue
            lit[r["instance"]][r["algorithm"]] = (float(r["best"]) if r["best"] else None, float(r["avg"]) if r["avg"] else None)
    return lit


def read_list(path):
    with open(path) as fh:
        return {ln.strip().split("/")[-1].replace(".inst", "") for ln in fh if ln.strip() and not ln.startswith("#")}


def load_final(archives, manifest, atmost):
    per = {}                                           # instance -> (arm, [30 latencies])
    for tar_name, member, arm in SOURCES:
        for fam in FAMILIES:
            for k, v in read_runs(read_member(os.path.join(archives, tar_name), member.format(fam=fam))).items():
                per.setdefault(k, {})[arm] = v
    out = {}
    for k, m in manifest.items():
        arms = per.get(k, {})
        arm = "B1" if "B1" in arms else ("ext10" if (m["n"] == 75 and "ext10" in arms) else "1x")
        if arm not in arms:
            sys.exit("no runs for %s (arm %s)" % (k, arm))
        out[k] = (arm, arms[arm])
    if atmost:
        out[AT_INSTANCE] = ("1x --atmost", read_runs(read_member(os.path.join(archives, ATMOST[0]), ATMOST[1]))[AT_INSTANCE])
    for k, (arm, v) in out.items():
        if len(v) != 30:
            sys.exit("%s (%s): %d feasible runs instead of 30" % (k, arm, len(v)))
    return out


def classify(a, b):
    if abs(a - b) <= TIE + 1e-9:
        return "T"
    return "W" if a < b else "L"


def compare(rows, key_ours, theirs, bks):
    """rows: instances; theirs: instance -> published value or None.  Returns (n, W, T, L, mean gap ours, mean gap theirs, p)"""
    ks = [k for k in rows if theirs.get(k) is not None]
    if not ks:
        return None
    cls, d = [], []
    for k in ks:
        a, b = key_ours[k], theirs[k]
        c = classify(a, b)
        cls.append(c)
        if c != "T":
            d.append(gap(a, bks[k]) - gap(b, bks[k]))
    p = float(wilcoxon(d, method="approx", correction=False).pvalue) if len(d) > 1 else float("nan")
    mg = lambda f: sum(gap(f(k), bks[k]) for k in ks) / len(ks)
    return len(ks), cls.count("W"), cls.count("T"), cls.count("L"), mg(lambda k: key_ours[k]), mg(lambda k: theirs[k]), p


def sa_best(lit, k, idx):
    v = [lit[k][a][idx] for a in ("SA-VND0", "SA-VND1", "SA-VND2") if lit[k].get(a) and lit[k][a][idx] is not None]
    return min(v) if v else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--archives", default=os.path.join(ROOT, "study_results"))
    ap.add_argument("--manifest", default=os.path.join(ROOT, "cpp", "manifest.tsv"))
    ap.add_argument("--literature", default=os.path.join(ROOT, "bks", "literature_results.csv"))
    ap.add_argument("--train", default=os.path.join(ROOT, "cpp", "selection", "train.txt"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-atmost", action="store_true", help="report Prins 50-5-2BIS-5 with the runs of the default setting (exactly Ng open depots) instead of the --atmost runs")
    a = ap.parse_args()

    man, lit, train = read_manifest(a.manifest), read_literature(a.literature), read_list(a.train)
    final = load_final(a.archives, man, not a.no_atmost)
    order = sorted(man, key=lambda k: (FAMILIES.index(man[k]["family"]), man[k]["n"], k))
    bks = {k: man[k]["bks"] for k in man}
    best = {k: round(min(final[k][1]), 2) for k in man}
    mean = {k: round(sum(final[k][1]) / 30.0, 2) for k in man}
    os.makedirs(a.out, exist_ok=True)

    # ---- per-instance CSV
    cols = ["instance", "family", "n", "source", "bks", "best", "mean", "gap_best", "gap_mean"] + [x for al in ALGOS + ["SA-VND(best variant)"] for x in (al + "_best", al + "_avg")]
    with open(os.path.join(a.out, "final_per_instance.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for k in order:
            row = [k, man[k]["family"], man[k]["n"], final[k][0], "%.2f" % bks[k], f2(best[k]), f2(mean[k]), f3(gap(best[k], bks[k])), f3(gap(mean[k], bks[k]))]
            for al in ALGOS:
                v = lit[k].get(al)
                row += [f2(v[0]) if v and v[0] is not None else "", f2(v[1]) if v and v[1] is not None else ""]
            sb, sa = sa_best(lit, k, 0), sa_best(lit, k, 1)
            row += [f2(sb) if sb is not None else "", f2(sa) if sa is not None else ""]
            w.writerow(row)

    # ---- per-instance LaTeX (own layout; not the layout of the manuscript table)
    with open(os.path.join(a.out, "final_per_instance.tex"), "w", newline="") as fh:
        fh.write("% Generated by analysis/final/final_vs_published.py -- own layout, not the table of the manuscript.\n")
        fh.write("\\begin{longtable}{llrrrrrrr}\n\\hline\n Instance & Source & $n$ & BKS & Best & Mean & RLHEA best & RLHEA avg & GBILS best \\\\\n\\hline\n\\endhead\n")
        for k in order:
            r, g = lit[k].get("RLHEA"), lit[k].get("GBILS")
            fh.write(" %s & %s & %d & %.2f & %.2f & %.2f & %s & %s & %s \\\\\n" % (
                k.replace("_", "\\_"), final[k][0], man[k]["n"], bks[k], best[k], mean[k],
                f2(r[0]) if r and r[0] is not None else "--", f2(r[1]) if r and r[1] is not None else "--", f2(g[0]) if g and g[0] is not None else "--"))
        fh.write("\\hline\n\\end{longtable}\n")

    # ---- summary
    sel = {"all 76 instances": order, "n >= 75 (58)": [k for k in order if man[k]["n"] >= 75],
           "held-out n >= 75 (45)": [k for k in order if man[k]["n"] >= 75 and k not in train],
           "n >= 150 (30)": [k for k in order if man[k]["n"] >= 150], "n = 200 (18)": [k for k in order if man[k]["n"] == 200]}
    L = []
    L.append("# Final method against the published algorithms\n")
    L.append("Source per instance: n <= 50 base method (standard budget), n = 75 base method (extended budget), n > 75 route-pool method B1 (extended budget). 30 runs each%s.\n" %
             ("; Prins 50-5-2BIS-5 with the default rule (exactly Ng open depots)" if a.no_atmost else "; Prins 50-5-2BIS-5 with --atmost"))
    L.append("## Quality by instance size (gap in % to the BKS)\n")
    L.append("| class | instances | source | gap of best | gap of mean | best <= BKS + 0.005 |\n|---|---|---|---|---|---|")
    classes = [("n <= 50", lambda n: n <= 50, "1x"), ("n = 75", lambda n: n == 75, "ext10"), ("n = 100", lambda n: n == 100, "B1"), ("n = 117/134", lambda n: n in (117, 134), "B1"),
               ("n = 150", lambda n: n == 150, "B1"), ("n = 200", lambda n: n == 200, "B1"), ("all", lambda n: True, "")]
    for name, f, src in classes:
        ks = [k for k in order if f(man[k]["n"])]
        hit = sum(1 for k in ks if best[k] <= bks[k] + TIE + 1e-9)
        L.append("| %s | %d | %s | %.3f | %.3f | %d / %d |" % (name, len(ks), src, sum(gap(best[k], bks[k]) for k in ks) / len(ks), sum(gap(mean[k], bks[k]) for k in ks) / len(ks), hit, len(ks)))
    L.append("\n## RLHEA (Zou et al. 2024), paired comparison\n")
    L.append("| instances | our mean vs RLHEA avg: W / T / L | p | our best vs RLHEA best: W / T / L | p | mean gap ours / RLHEA (avg) | mean <= avg strict | mean <= avg (rounded) |\n|---|---|---|---|---|---|---|---|")
    rl_avg = {k: lit[k]["RLHEA"][1] for k in order}
    rl_best = {k: lit[k]["RLHEA"][0] for k in order}
    for name, ks in sel.items():
        cm, cb = compare(ks, mean, rl_avg, bks), compare(ks, best, rl_best, bks)
        strict = sum(1 for k in ks if sum(final[k][1]) / 30.0 <= rl_avg[k])
        rnd = sum(1 for k in ks if mean[k] <= rl_avg[k] + 1e-9)
        L.append("| %s | %d / %d / %d | %s | %d / %d / %d | %s | %.3f / %.3f | %d / %d | %d / %d |" % (name, cm[1], cm[2], cm[3], fp(cm[6]), cb[1], cb[2], cb[3], fp(cb[6]), cm[4], cm[5], strict, len(ks), rnd, len(ks)))
    L.append("\n## Other published algorithms (all instances for which the algorithm has values)\n")
    L.append("| algorithm | instances | mean gap ours / theirs (Avg) | mean vs Avg: W / T / L | p | best vs Best: W / T / L | p |\n|---|---|---|---|---|---|---|")
    others = [(al, {k: (lit[k].get(al) or (None, None))[1] for k in order}, {k: (lit[k].get(al) or (None, None))[0] for k in order}) for al in ["MS-VNS", "M-ILS", "SA-VND0", "SA-VND1", "SA-VND2", "MA", "GBILS"]]
    others.insert(5, ("SA-VND (best variant)", {k: sa_best(lit, k, 1) for k in order}, {k: sa_best(lit, k, 0) for k in order}))
    others = [(al + " (our mean vs their best)", bst, bst) if al == "GBILS" else (al, avg, bst) for al, avg, bst in others]       # GBILS reports best values only: conservative comparison
    for al, avg, bst in others:
        cm, cb = compare(order, mean, avg, bks), compare(order, best, bst, bks)
        gb = al.startswith("GBILS")
        L.append("| %s | %d | %.3f / %.3f | %d / %d / %d | %s | %s |" % (al, cm[0], cm[4], cm[5], cm[1], cm[2], cm[3], fp(cm[6]),
                 "(same comparison)" if gb else "%d / %d / %d | %s" % (cb[1], cb[2], cb[3], fp(cb[6]))))
    L.append("\nGBILS publishes best values only (35 usable instances: Prins 30 and 5 of the 10 Barreto instances). Its Christofides69 rows (50x5, 75x10, 100x10) are values of another variant of the instance "
             "and are left out (`GBILS_UNMATCHED`); Min-134-8 and Or-117-14 are not in its table; no Tuzun-Burke instance is.\n")
    L.append("Rules: ties |ours - theirs| <= 0.005; our best and mean rounded to two decimals; Wilcoxon signed-rank, two-sided, normal approximation without continuity correction on the paired gap differences, ties dropped; "
             "published times are not used (different hardware).\n")
    text = "\n".join(L).replace("-0.000", "0.000") + "\n"
    with open(os.path.join(a.out, "final_vs_published.md"), "w", newline="") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
