#!/usr/bin/env python3
"""Hierarchical decomposition of the difference between our solutions and a reference solution (e.g. the solutions published with RLHEA, Zou et al. 2024).

For every (instance, seed) run the final solution is compared with the reference solution of the instance and assigned to the first class that applies:

    A  the sets of open depots differ
    B  same depot set, but some customer is served from another depot
    C  same customer-to-depot assignment, but the customers are partitioned into routes differently
    D  same partition into routes, but the visiting order inside some route differs
    E  identical solutions

The question behind it: when the engine ends above the reference value, is it because it opens the wrong depots (A), assigns customers to the wrong depots (B),
or builds the wrong routes for the right depots (C, D)?

A reference solution is used only if it can be trusted: the file must exist, cover every customer exactly once, and its latency, recomputed here from the
instance file, must agree with the best value published for that instance (`bks/literature_results.csv`, RLHEA) within the relative tolerance --rel-tol. Instances that fail
the test are listed with the reason and left out; with the published files these are Tuzun P112222-20 (the file covers 90 of 100 customers), Tuzun P131122-20 (its latency
is 8 times the published value) and Barreto Or117-14 (empty file). Tuzun P122122-20 passes: its file is valid but 0.004 % above the best published value.

The reference solutions are third-party files and are not part of this repository: pass the directory with --ref-solutions. Format of `<name>.txt`: one route per line,
the first integer is n + d + 1 for the (0-based) depot d, followed by the 1-based customer numbers in visiting order.  Our solutions are read from the `run.csv` and
`routes.csv` files of a result directory (`results_final/<family>/tuned/` of study_results/final_1x_tuned.tar.gz, `results_extended10/<family>/ext10/` of the ext10 archive).

usage:  depot_decomp.py DIR [DIR ...] --ref-solutions SOLUTION_DIR [--out decomp.csv] [--inst-dir cpp/inst] [--literature bks/literature_results.csv] [--rel-tol 0.001]
Standard library only.
"""
import argparse
import collections
import csv
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BARRETO_FILES = {"Ch50-5": "Christ_50_5", "Ch75-10": "Christ_75_10", "Ch100-10": "Christ_100_10", "Gaskell21-5": "Gaskell_21_5", "Gaskell29-5": "Gaskell_29_5",
                 "Gaskell32-5": "Gaskell_32_5b", "Gaskell36-5": "Gaskell_36_5", "Mi27-5": "Min_27_5", "Mi134-8": "Min_134_8", "Or117-14": "Or_117_14"}
CLASSES = "ABCDE"


def ref_file(name, family):
    """File stem of the published solution of one of our instances: Prins `20-5-1b-5` -> `20-5-1b`, Tuzun `P111112-10` -> `111112`, Barreto by table."""
    if family == "barreto":
        return BARRETO_FILES[name]
    stem = name.rsplit("-", 1)[0]
    return stem[1:] if family == "tuzun" and stem.startswith("P") else stem


def parse_inst(path):
    """(depots, customers) of an `.inst` file: lists of (x, y) and (x, y, demand)."""
    with open(path) as fh:
        lines = [ln.split() for ln in fh if ln.strip()]
    i = next(k for k, t in enumerate(lines) if t[0] == "depots") + 1
    dep = []
    while lines[i][0] != "customers":
        dep.append((float(lines[i][0]), float(lines[i][1])))
        i += 1
    cus = [(float(t[0]), float(t[1]), float(t[2])) for t in lines[i + 1:]]
    return dep, cus


def parse_reference(path, n):
    """Routes [(depot, (customers...)), ...], 0-based, or None if the file is missing or empty."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    routes = []
    with open(path) as fh:
        for ln in fh:
            t = [int(x) for x in ln.split()]
            if t:
                routes.append((t[0] - n - 1, tuple(c - 1 for c in t[1:])))
    return routes


def latency(routes, dep, cus):
    """Sum of the arrival times of all customers; vehicles do not return to the depot."""
    total = 0.0
    for d, r in routes:
        x, y = dep[d]
        t = 0.0
        for c in r:
            t += math.hypot(x - cus[c][0], y - cus[c][1])
            x, y = cus[c][0], cus[c][1]
            total += t
    return total


def trust(routes, n, dep, cus, published_best, rel_tol):
    """Reason why a reference solution cannot be used, or None."""
    if routes is None:
        return "no published solution"
    served = [c for _, r in routes for c in r]
    if sorted(served) != list(range(n)):
        return "covers %d of %d customers" % (len(set(served)), n) if len(served) == len(set(served)) else "serves a customer twice or more"
    if any(not 0 <= d < len(dep) for d, _ in routes):
        return "unknown depot"
    cost = latency(routes, dep, cus)
    if published_best is not None and abs(cost - published_best) > rel_tol * published_best:
        return "latency %.3f differs from the published best %.2f" % (cost, published_best)
    return None


def classify(ref, ours):
    """(class, fraction of customers served from another depot, fraction of reference routes that are also routes of `ours`) for two route lists."""
    rd = {c: d for d, r in ref for c in r}
    od = {c: d for d, r in ours for c in r}
    nd = sum(rd[c] != od.get(c) for c in rd) / len(rd)
    rparts, oparts = {frozenset(r) for _, r in ref}, {frozenset(r) for _, r in ours}
    common = len(rparts & oparts) / max(len(rparts), 1)
    if {d for d, _ in ref} != {d for d, _ in ours}:
        cls = "A"
    elif nd > 0:
        cls = "B"
    elif rparts != oparts:
        cls = "C"
    elif {(d, r) for d, r in ref} != {(d, r) for d, r in ours}:
        cls = "D"
    else:
        cls = "E"
    return cls, nd, common


def read_runs(d):
    """{(instance, seed): (gap %, our latency)} of the feasible runs and {(instance, seed): routes} of a result directory."""
    runs, routes = {}, collections.defaultdict(list)
    with open(os.path.join(d, "run.csv")) as fh:
        for r in csv.DictReader(fh):
            if r["Feasible"] == "True":
                runs[(r["Instance"], int(r["Seed"]))] = (float(r["Gap to BKS (%)"]), float(r["Total Latency"]))
    with open(os.path.join(d, "routes.csv")) as fh:
        for r in csv.DictReader(fh):
            routes[(r["Instance"], int(r["Seed"]))].append((int(r["Depot"]), tuple(int(x) for x in r["Customers"].split(" -> "))))
    return runs, routes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog="See the module docstring for the classes.")
    ap.add_argument("dirs", nargs="+", metavar="DIR", help="result directories with run.csv and routes.csv")
    ap.add_argument("--ref-solutions", required=True, help="directory with the reference solutions <name>.txt")
    ap.add_argument("--inst-dir", default=os.path.join(REPO, "cpp", "inst"))
    ap.add_argument("--literature", default=os.path.join(REPO, "bks", "literature_results.csv"), help="published best values (rows of algorithm RLHEA)")
    ap.add_argument("--rel-tol", type=float, default=1e-3, help="allowed relative difference between the recomputed latency of a reference solution and the published best value (default 0.1 %%)")
    ap.add_argument("--out", default="decomp.csv")
    a = ap.parse_args(argv)

    with open(a.literature) as fh:
        pub = {r["instance"]: float(r["best"]) for r in csv.DictReader(fh) if r["algorithm"] == "RLHEA"}
    inst_files = {}
    for fam in sorted(os.listdir(a.inst_dir)):
        for f in os.listdir(os.path.join(a.inst_dir, fam)):
            if f.endswith(".inst"):
                inst_files[f[:-5]] = (fam, os.path.join(a.inst_dir, fam, f))

    rows, cache, excluded = [], {}, {}
    for d in a.dirs:
        runs, routes = read_runs(d)
        for (name, seed), (gap, cost) in sorted(runs.items()):
            if name not in inst_files:
                sys.exit("instance %s of %s is not in %s" % (name, d, a.inst_dir))
            if name not in cache:
                fam, path = inst_files[name]
                dep, cus = parse_inst(path)
                n = len(cus)
                ref = parse_reference(os.path.join(a.ref_solutions, ref_file(name, fam) + ".txt"), n)
                why = trust(ref, n, dep, cus, pub.get(name), a.rel_tol)
                cache[name] = (fam, n, ref, why)
                if why:
                    excluded[name] = why
            fam, n, ref, why = cache[name]
            if why or (name, seed) not in routes:
                continue
            cls, nd, common = classify(ref, routes[(name, seed)])
            rows.append((name, fam, n, seed, gap, cls, nd, common, cost))

    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["instance", "family", "n", "seed", "gap", "class", "frac_customers_other_depot", "frac_ref_routes_same_set", "latency"])
        w.writerows(rows)
    # summary
    print("%d runs on %d instances written to %s" % (len(rows), len({r[0] for r in rows}), a.out))
    for name, why in sorted(excluded.items()):
        print("  left out: %-12s %s" % (name, why))
    print("\n%-9s %6s" % ("family", "runs") + "".join("%8s" % c for c in CLASSES) + "   (% of runs)")
    for fam in [None] + sorted({r[1] for r in rows}):
        sel = [r for r in rows if fam is None or r[1] == fam]
        if sel:
            cnt = collections.Counter(r[5] for r in sel)
            print("%-9s %6d" % (fam or "ALL", len(sel)) + "".join("%8.1f" % (100.0 * cnt[c] / len(sel)) for c in CLASSES))
    print("\n%-5s %6s %12s %12s" % ("class", "runs", "mean gap %", "median gap %"))
    for c in CLASSES:
        g = sorted(r[4] for r in rows if r[5] == c)
        if g:
            print("%-5s %6d %12.3f %12.3f" % (c, len(g), sum(g) / len(g), g[len(g) // 2]))
    return rows


if __name__ == "__main__":
    main()
