#!/usr/bin/env python3
"""Pre-registered analysis of the converged-set-tabu generalisation test (stages G1 and G2; see PLAN_G.md).

  python3 -I analyze_g.py --res results_g_g1 [--res results_g_g2] --manifest manifest.tsv [--bks LLRP_BKS.csv] [--zou literature_results.csv] \
          [--archive b1_tuned.tar.gz] --out OUTDIR

Each --res directory is the result tree of one stage (tar/<family>/<instance>_s<seed>_<arm>.tar written by g_worker.sh; the stage is detected from the
arms present).  The criteria below were fixed before any result of this test existed:

  G1 (7 instances, arms B1, B1_tabu [primary]; B1_tabudraw, B1_tabuskip [exploratory decomposition]); gap = % above the BKS
     R : discovery instance P111122-20: one-sided Mann-Whitney U (B1_tabu < B1) over the 30 runs, p < 0.05
     H : the other 6 instances: mean over instances of (mean gap B1_tabu - mean gap B1) <= -0.10 points AND B1_tabu better on >= 5 of the 6 instances
     S : every run feasible and independently verified (verify OK) in every arm; CPU time / limit: mean <= 1.01 and max <= 1.07 per arm
  G2 (the remaining 50 instances, arms B1, B1_tabu)
     Z : harm counter: instances where B1_tabu is worse than B1 by >= 0.10 points (difference of instance means) AND one-sided Mann-Whitney U (B1_tabu > B1) p < 0.05  ->  <= 3 of 50
     S : as above
     G0: (secondary, not required for adoption) one-sided Wilcoxon signed-rank over the 50 instance-mean differences p < 0.01 AND mean difference <= -0.03 points
  Adoption candidate: R, H, Z and S all hold.  Anything else: not adopted.  Exploratory results never replace a primary criterion.
"""
import argparse, csv, io, math, os, re, sys, tarfile, statistics as st
from collections import defaultdict

try:
    from scipy.stats import mannwhitneyu, wilcoxon
except Exception:                                   # scipy missing: report without p-values
    mannwhitneyu = wilcoxon = None

RUN_HEADER = ["Instance", "Algorithm", "Run", "Seed", "Feasible", "Total Latency", "Reference BKS", "Gap to BKS (%)", "CPU Time", "Open Depots", "Number of Routes", "Actual Open Depot Count",
              "Required Ng", "Actual Route Count", "Required Nv", "Max Route Load", "Vehicle Capacity", "Total Demand", "Total Vehicle Capacity", "Nv", "Ng", "Iterations", "Stop Reason",
              "Last Improvement Iteration", "Last Improvement CPU", "Wall Time", "Move Evaluations"]

G1_INSTANCES = ["P111122-20", "P122112-10", "P121112-10", "P122212-10", "P121212-10", "P123112-10", "P122122-20"]
DISCOVERY = "P111122-20"
CTRL, TAB, TABD, TABS = "B1", "B1_tabu", "B1_tabudraw", "B1_tabuskip"


def read_runs(res_dir, manifest, tc, tmin):
    """-> list of dict, one per run."""
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
                raw = list(csv.reader(io.TextIOWrapper(tf.extractfile(names[rc[0]]), encoding="utf-8")))
                raw = [x for x in raw if x]
                if raw and raw[0][0] == "Instance":              # merged run.csv with header
                    raw = raw[1:]
                if not raw:
                    continue
                r = dict(zip(RUN_HEADER, raw[0]))                # per-run run.csv written by llrp_fast has no header line
                ver = tf.extractfile(names[stem + ".verify"]).read().decode() if stem + ".verify" in names else ""
                log = tf.extractfile(names[stem + ".log"]).read().decode() if stem + ".log" in names else ""
                inst = r["Instance"]; arm = r["Algorithm"]
                n = int(manifest[inst]["n"]) if inst in manifest else 0
                lim = max(tmin, tc * n / 100.0)
                cnt = {}
                m = re.search(r"^tabu on=1 (.*)$", log, re.M)
                if m:
                    for kv in m.group(1).split():
                        k, _, v = kv.partition("=")
                        try: cnt[k] = float(v)
                        except ValueError: pass
                runs.append(dict(inst=inst, arm=arm, seed=int(r["Seed"]), cost=float(r["Total Latency"]), bks_run=float(r["Reference BKS"]),
                                 feasible=r["Feasible"] == "True", cpu=float(r["CPU Time"]), iters=int(r["Iterations"]), limit=lim,
                                 verify=ver.lstrip().startswith("OK"), counters=cnt, n=n))
    return runs


def mw(a, b, alt):
    if mannwhitneyu is None or not a or not b:
        return float("nan")
    try:
        return float(mannwhitneyu(a, b, alternative=alt).pvalue)
    except ValueError:
        return 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", action="append", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bks"); ap.add_argument("--zou"); ap.add_argument("--archive")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tc", type=float, default=300.0); ap.add_argument("--tmin", type=float, default=5.0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    manifest = {r["name"]: r for r in csv.DictReader(open(a.manifest), delimiter="\t")}
    bks = {r["instance"]: float(r["bks"]) for r in csv.DictReader(open(a.bks))} if a.bks else {}
    zou = {}
    if a.zou:
        for r in csv.DictReader(open(a.zou)):
            if r["algorithm"] == "RLHEA" and r["avg"]:
                zou[r["instance"]] = float(r["avg"])
    runs = []
    for d in a.res:
        runs += read_runs(d, manifest, a.tc, a.tmin)
    if not runs:
        sys.exit("no runs found")
    for r in runs:
        b = bks.get(r["inst"], r["bks_run"]); r["bks"] = b; r["gap"] = 100.0 * (r["cost"] - b) / b
    by = defaultdict(list)                                    # (inst, arm) -> runs
    for r in runs:
        by[(r["inst"], r["arm"])].append(r)
    insts = sorted({r["inst"] for r in runs}); arms = sorted({r["arm"] for r in runs})
    out = []; P = out.append
    P("# Converged-set tabu: generalisation test (G1/G2), pre-registered analysis\n")
    P(f"runs read: {len(runs)}; arms: {', '.join(arms)}; instances: {len(insts)}\n")

    # ---------------- per instance / arm table ----------------
    P("## Per instance (mean over the runs of the arm; gap in % above BKS)\n")
    P("| instance | n | arm | runs | verify OK | mean gap | sd | median | best | <= BKS+0.005 | < BKS-0.005 | <= Zou f_avg | mean iters | CPU/limit mean (max) |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows_csv = []
    for i in insts:
        for arm in arms:
            R = by.get((i, arm), [])
            if not R:
                continue
            g = [x["gap"] for x in R]
            hit = sum(x["cost"] <= x["bks"] + 0.005 for x in R); newb = sum(x["cost"] < x["bks"] - 0.005 for x in R)
            zh = sum(x["cost"] <= zou[i] for x in R) if i in zou else None
            vok = sum(x["feasible"] and x["verify"] for x in R)
            cl = [x["cpu"] / x["limit"] for x in R]
            P(f"| {i} | {R[0]['n']} | {arm} | {len(R)} | {vok} | {st.mean(g):.3f} | {st.pstdev(g) if len(g) < 2 else st.stdev(g):.3f} | {st.median(g):.3f} | {min(g):.3f} | {hit} | {newb} | {zh if zh is not None else '-'} | {st.mean(x['iters'] for x in R):.0f} | {st.mean(cl):.3f} ({max(cl):.3f}) |")
            rows_csv.append([i, R[0]["n"], arm, len(R), vok, st.mean(g), st.median(g), min(g), hit, newb, zh, st.mean(x["iters"] for x in R), st.mean(cl), max(cl)])
    with open(os.path.join(a.out, "g_instances.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["instance", "n", "arm", "runs", "verify_ok", "mean_gap", "median_gap", "best_gap", "hits_bks", "new_bks", "hits_zou_avg", "mean_iters", "cpu_ratio_mean", "cpu_ratio_max"]); w.writerows(rows_csv)
    with open(os.path.join(a.out, "g_runs.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["instance", "arm", "seed", "cost", "gap_pct", "cpu_s", "limit_s", "iterations", "feasible", "verify_ok"])
        for r in sorted(runs, key=lambda x: (x["inst"], x["arm"], x["seed"])):
            w.writerow([r["inst"], r["arm"], r["seed"], r["cost"], r["gap"], r["cpu"], r["limit"], r["iters"], r["feasible"], r["verify"]])

    # ---------------- safety ----------------
    P("\n## S: safety\n")
    S_ok = True
    for arm in arms:
        R = [r for r in runs if r["arm"] == arm]
        bad = sum(not (r["feasible"] and r["verify"]) for r in R); cl = [r["cpu"] / r["limit"] for r in R]
        ok = bad == 0 and st.mean(cl) <= 1.01 and max(cl) <= 1.07
        S_ok &= ok
        P(f"- {arm}: {len(R)} runs, not feasible/verified: {bad}, CPU/limit mean {st.mean(cl):.3f}, max {max(cl):.3f} -> {'PASS' if ok else 'FAIL'}")
    if CTRL in arms and TAB in arms:
        ratios = [st.mean(x["iters"] for x in by[(i, TAB)]) / st.mean(x["iters"] for x in by[(i, CTRL)]) for i in insts if by.get((i, TAB)) and by.get((i, CTRL))]
        P(f"- iteration parity (mean over instances of mean iterations {TAB} / {CTRL}): {st.mean(ratios):.3f} (range {min(ratios):.3f}..{max(ratios):.3f}); note only, outside 0.85..1.15 the quality numbers are read with caution")
    P("")

    verdict = {}
    # ---------------- G1 ----------------
    g1 = [i for i in G1_INSTANCES if by.get((i, TAB)) and by.get((i, CTRL))]
    if len(g1) == len(G1_INSTANCES):
        P("## G1: hard instances (B1 vs B1_tabu)\n")
        c = [x["gap"] for x in by[(DISCOVERY, CTRL)]]; t = [x["gap"] for x in by[(DISCOVERY, TAB)]]
        pR = mw(t, c, "less"); R_ok = (not math.isnan(pR)) and pR < 0.05
        P(f"- R (replication on {DISCOVERY}, fresh seeds): mean gap {st.mean(c):.3f} -> {st.mean(t):.3f} ({st.mean(t) - st.mean(c):+.3f}); one-sided MWU p = {pR:.4f} -> **{'PASS' if R_ok else 'FAIL'}**")
        d6 = {i: st.mean(x["gap"] for x in by[(i, TAB)]) - st.mean(x["gap"] for x in by[(i, CTRL)]) for i in G1_INSTANCES if i != DISCOVERY}
        mean_d = st.mean(d6.values()); nb = sum(v < 0 for v in d6.values()); H_ok = mean_d <= -0.10 and nb >= 5
        P(f"- H (other 6): per-instance difference of means (B1_tabu - B1): " + ", ".join(f"{k} {v:+.3f}" for k, v in d6.items()))
        P(f"  mean {mean_d:+.3f} points, B1_tabu better on {nb}/6 -> **{'PASS' if H_ok else 'FAIL'}**")
        verdict["R"], verdict["H"] = R_ok, H_ok
        if TABD in arms or TABS in arms:
            P("\n### Decomposition (exploratory; no criterion)\n")
            P("| arm | mean gap over the 7 instances | difference to B1 | difference to B1_tabu | mean cycles | mean skipped intensifications | mean draw skips |")
            P("|---|---|---|---|---|---|---|")
            mb = st.mean(st.mean(x["gap"] for x in by[(i, CTRL)]) for i in G1_INSTANCES); mt = st.mean(st.mean(x["gap"] for x in by[(i, TAB)]) for i in G1_INSTANCES)
            for arm in (CTRL, TAB, TABD, TABS):
                if not all(by.get((i, arm)) for i in G1_INSTANCES):
                    continue
                m = st.mean(st.mean(x["gap"] for x in by[(i, arm)]) for i in G1_INSTANCES)
                cn = [x["counters"] for i in G1_INSTANCES for x in by[(i, arm)] if x["counters"]]
                f = lambda k: f"{st.mean(c.get(k, 0.0) for c in cn):.1f}" if cn else "-"
                P(f"| {arm} | {m:.3f} | {m - mb:+.3f} | {m - mt:+.3f} | {f('cycles')} | {f('skipped_int')} | {f('draw_skips')} |")
            P("\nReading rule (stated in advance): if B1_tabuskip is about as good as B1_tabu and B1_tabudraw about as bad as B1, the gain comes from skipping intensification (budget shift), not from the tabu on start sets.\n")
    else:
        P("## G1: not evaluated (instances or arms missing)\n")

    # ---------------- G2 ----------------
    g2 = [i for i in insts if i not in G1_INSTANCES and by.get((i, TAB)) and by.get((i, CTRL))]
    if g2:
        P(f"## G2: remaining instances ({len(g2)}; B1 vs B1_tabu)\n")
        diffs = {}; harm = []
        for i in g2:
            c = [x["gap"] for x in by[(i, CTRL)]]; t = [x["gap"] for x in by[(i, TAB)]]
            diffs[i] = st.mean(t) - st.mean(c)
            if diffs[i] >= 0.10:
                p = mw(t, c, "greater")
                if not math.isnan(p) and p < 0.05:
                    harm.append((i, diffs[i], p))
        Z_ok = len(harm) <= 3 and len(g2) == 50
        P(f"- Z (harm: difference >= +0.10 and one-sided MWU p < 0.05): {len(harm)} of {len(g2)} instances (limit 3)" + ("" if len(g2) == 50 else " [stage incomplete: Z not decidable]") + f" -> **{'PASS' if Z_ok else 'FAIL / open'}**")
        for i, d, p in harm:
            P(f"  - {i}: {d:+.3f} points, p = {p:.4f}")
        vals = list(diffs.values()); better = sum(v < 0 for v in vals); worse = sum(v > 0 for v in vals)
        if wilcoxon is not None and any(v != 0 for v in vals):
            try: pw = float(wilcoxon(vals, alternative="less").pvalue)
            except ValueError: pw = 1.0
        else:
            pw = float("nan")
        G0_ok = (not math.isnan(pw)) and pw < 0.01 and st.mean(vals) <= -0.03
        P(f"- G0 (secondary): mean difference {st.mean(vals):+.3f} points, better {better} / worse {worse} / equal {len(vals) - better - worse}; one-sided Wilcoxon p = {pw:.4f} -> {'PASS' if G0_ok else 'not met'} (not required)")
        by_n = defaultdict(list)
        for i in g2: by_n[manifest[i]["n"]].append(diffs[i])
        P("- by n: " + ", ".join(f"n={n}: {st.mean(v):+.3f} ({len(v)} inst)" for n, v in sorted(by_n.items(), key=lambda kv: int(kv[0]))))
        verdict["Z"] = Z_ok
    # ---------------- overall ----------------
    P("\n## Verdict\n")
    if {"R", "H"} <= set(verdict) and "Z" in verdict:
        ok = S_ok and verdict["R"] and verdict["H"] and verdict["Z"]
        label = "ADOPTION CANDIDATE (the decision is the author's; the manuscript needs a new pre-registered label)" if ok else "NOT ADOPTED"
        P(f"R {verdict['R']}, H {verdict['H']}, Z {verdict['Z']}, S {S_ok} -> **{label}**")
    elif {"R", "H"} <= set(verdict):
        ok = S_ok and verdict["H"]
        P(f"G1 only: R {verdict['R']}, H {verdict['H']}, S {S_ok} -> " + ("**G1 passes (H and S): G2 is warranted**" if ok else "**G1 fails: do not run G2; mechanism not adopted**") + (" (R failed: the discovery-instance effect did not replicate)" if not verdict["R"] else ""))
    else:
        P("incomplete data: no verdict")
    # ---------------- reference: B1 cluster archive ----------------
    if a.archive and os.path.exists(a.archive):
        with tarfile.open(a.archive) as tf:
            arch = defaultdict(list)
            for m in tf.getmembers():
                if m.name.endswith("/B1/run.csv"):
                    for r in csv.DictReader(io.TextIOWrapper(tf.extractfile(m), encoding="utf-8")):
                        arch[r["Instance"]].append((float(r["Gap to BKS (%)"]), int(r["Iterations"])))
        P("\n## Reference: B1 cluster archive (seeds 1..30, different time; drift check of the concurrent control)\n")
        P("| instance | archive B1 mean gap | concurrent B1 mean gap | archive mean iters | concurrent mean iters |")
        P("|---|---|---|---|---|")
        for i in insts:
            if i in arch and by.get((i, CTRL)):
                P(f"| {i} | {st.mean(x[0] for x in arch[i]):.3f} | {st.mean(x['gap'] for x in by[(i, CTRL)]):.3f} | {st.mean(x[1] for x in arch[i]):.0f} | {st.mean(x['iters'] for x in by[(i, CTRL)]):.0f} |")
    txt = "\n".join(out) + "\n"
    open(os.path.join(a.out, "g_summary.md"), "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
