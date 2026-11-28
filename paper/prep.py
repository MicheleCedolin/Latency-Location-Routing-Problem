#!/usr/bin/env python3
"""Data layer of the paper: turns the raw result files of the final evaluation into the analysis tables used by `tables*.py` and `figs*.py`.

Input   --base  results_final/<family>/tuned/{run,trace,ops}.csv      (standard budget max{5, 0.3 n} s, 76 instances x 30 seeds = 2280 runs)
        --atmost results_atmost/{run,trace,ops}.csv                    (--atmost re-run of Prins 50-5-2BIS-5; replaces the default-setting runs of that instance)
        --ext   results_extended10/<family>/ext10/{run,trace}.csv     (extended budget 3 n s, the 58 instances with n >= 75, 1740 runs; optional)
        the per-instance reference table of this repository (`paperlib.reference`)
Output  <out>/data/   runs.csv inst.csv ttt_runs.csv anytime_grid.csv ops_by_class.csv best_iter_depot_moves.csv
                      ext_runs.csv inst_ext.csv slices_ext.csv slices_iter.csv ttt_ext_runs.csv anytime_grid_ext.csv anytime_grid_iter.csv

Extract the archives first (each into /tmp):  final_1x_tuned.tar.gz, ext10_tuned.tar.gz, atmost_50-5-2BIS-5.tar.gz from study_results/
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paperlib import FAMS, TOL, dirs, make_parser, need, reference


def load(root, sub, name):
    return pd.concat([pd.read_csv(need(os.path.join(root, f, sub, name + ".csv"), "extract the study archive first (see --help)")).assign(family=f) for f in FAMS],
                     ignore_index=True)


def time_to_target(trace, I, targets):
    """First CPU second at which the incumbent of a run is at most target + TOL (NaN if never), for every (instance, seed)."""
    rows = []
    for (inst, seed), (t, b) in trace.items():
        row = I.loc[inst]
        rec = {"Instance": inst, "Seed": seed}
        for name in targets:
            idx = np.nonzero(b <= row[name] + TOL)[0]
            rec["t_" + name] = t[idx[0]] if len(idx) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def ttt_summary(TT, I, targets, prefix):
    for name in targets:
        gg = TT.groupby("Instance")["t_" + name]
        I[prefix[0] + name] = gg.apply(lambda x: x.notna().sum())
        I[prefix[1] + name] = gg.median()                              # median over the successful runs
        I[prefix[2] + name] = gg.apply(lambda x: np.nanmedian(np.where(x.isna(), np.inf, x)) if x.notna().sum() >= len(x) / 2 else np.nan)   # median over all runs


def val_at(t, b, x):
    k = np.searchsorted(t, x, side="right") - 1
    return b[k] if k >= 0 else np.nan


ATMOST_INSTANCE = "50-5-2BIS-5"     # solved with --atmost (at most Ng open depots); every other instance uses the default "exactly Ng depots" setting


def with_atmost(df, atmost_dir, name):
    """Replace the default-setting rows of `ATMOST_INSTANCE` by the rows of the --atmost re-run (same flags + --atmost, 30 seeds)."""
    am = pd.read_csv(need(os.path.join(atmost_dir, name + ".csv"), "extract study_results/atmost_50-5-2BIS-5.tar.gz (or pass --no-atmost)"))
    am["family"] = "prins"
    assert set(am["Instance"]) == {ATMOST_INSTANCE}, "the --atmost archive must contain only " + ATMOST_INSTANCE
    return pd.concat([df[df["Instance"] != ATMOST_INSTANCE], am], ignore_index=True)


def standard(base, T, D, atmost=None):
    R = load(base, "tuned", "run")
    TR = load(base, "tuned", "trace")
    O = load(base, "tuned", "ops")
    if atmost:
        R, TR, O = (with_atmost(x, atmost, n) for x, n in ((R, "run"), (TR, "trace"), (O, "ops")))
    R = R.merge(T[["n", "bks", "zou_best", "zou_avg", "zou_tavg", "train"]], left_on="Instance", right_index=True)
    R["budget"] = np.maximum(5.0, 0.3 * R["n"])
    R["gap"] = 100.0 * (R["Total Latency"] - R["bks"]) / R["bks"]
    assert len(R) == 2280 and R["Feasible"].all(), "expected 2280 feasible runs of the standard-budget campaign"
    R.to_csv(D / "runs.csv", index=False)

    g = R.groupby("Instance")
    I = pd.DataFrame({
        "family": g["family"].first(), "n": g["n"].first(), "train": g["train"].first(), "bks": g["bks"].first(),
        "zou_best": g["zou_best"].first(), "zou_avg": g["zou_avg"].first(), "zou_tavg": g["zou_tavg"].first(),
        "best": g["Total Latency"].min(), "mean": g["Total Latency"].mean(), "std": g["Total Latency"].std(ddof=1),
        "worst": g["Total Latency"].max(), "iters": g["Iterations"].mean(), "cpu": g["CPU Time"].mean(), "budget": g["budget"].first(),
    })
    I["gap_best"] = 100 * (I["best"] - I["bks"]) / I["bks"]
    I["gap_mean"] = 100 * (I["mean"] - I["bks"]) / I["bks"]
    I["zou_gap_best"] = 100 * (I["zou_best"] - I["bks"]) / I["bks"]
    I["zou_gap_avg"] = 100 * (I["zou_avg"] - I["bks"]) / I["bks"]
    I["hit"] = R.assign(h=(R["Total Latency"] <= R["bks"] + TOL)).groupby("Instance")["h"].mean() * 100     # % of runs at the BKS

    # time to target from the anytime trace
    tr = {k: (v["CPU Seconds"].to_numpy(), v["Best Latency"].to_numpy()) for k, v in TR.sort_values(["Instance", "Seed", "CPU Seconds"]).groupby(["Instance", "Seed"])}
    TT = time_to_target(tr, I, ("bks", "zou_avg", "zou_best"))
    TT.to_csv(D / "ttt_runs.csv", index=False)
    ttt_summary(TT, I, ("bks", "zou_avg", "zou_best"), ("succ_", "tmed_", "tq50_"))
    I.to_csv(D / "inst.csv")

    # anytime grid: mean gap of the incumbent at fractions of the budget
    fr = np.round(np.geomspace(0.02, 1.0, 40), 5)
    rows = []
    for (inst, seed), (t, b) in tr.items():
        r = I.loc[inst]
        for f in fr:
            k = np.searchsorted(t, f * r.budget, side="right") - 1
            rows.append((inst, seed, f, np.nan if k < 0 else 100 * (b[k] - r.bks) / r.bks))
    A = pd.DataFrame(rows, columns=["Instance", "Seed", "frac", "gap"]).merge(I[["n", "family"]], left_on="Instance", right_index=True)
    A.to_csv(D / "anytime_grid.csv", index=False)

    # operator statistics
    O = O.merge(I[["n"]], left_on="Instance", right_index=True)
    O["cls"] = pd.cut(O["n"], [0, 50, 134, 150, 200], labels=["n<=50", "75-134", "150", "200"])
    cols = ["Calls", "Evaluations", "Applied", "Gain Latency", "CPU Seconds"]
    byc = O.groupby(["cls", "Operator"], sort=False, observed=True)[cols].sum()
    tot = O.groupby("Operator", sort=False)[cols].sum()
    tot["cls"] = "all"
    tot = tot.set_index("cls", append=True).swaplevel()
    pd.concat([byc, tot]).to_csv(D / "ops_by_class.csv")
    bi = O.assign(dep=O["Operator"].isin(["dexch", "rdepot", "ds"])).groupby(["Instance", "Seed", "dep"])["Best Iteration Applied"].sum().unstack(fill_value=0)
    bi.columns = ["route_applied_best_iter", "depot_applied_best_iter"]
    bi.reset_index().merge(I[["n"]], left_on="Instance", right_index=True).to_csv(D / "best_iter_depot_moves.csv", index=False)
    print("standard budget: %d instances, %d runs, %d trace rows, %d operator rows" % (len(I), len(R), len(TR), len(O)))
    return I, R


def extended(ext, I, R1, D):
    R = pd.concat([pd.read_csv(need(os.path.join(ext, f, "ext10", "run.csv"), "extract the ext10 archive first")) for f in ("barreto", "prins", "tuzun")], ignore_index=True)
    TR = pd.concat([pd.read_csv(os.path.join(ext, f, "ext10", "trace.csv")) for f in ("barreto", "prins", "tuzun")], ignore_index=True)
    R = R.merge(I[["family", "n", "bks", "train"]], left_on="Instance", right_index=True)
    assert len(R) == 1740 and R.Instance.nunique() == 58 and R["Feasible"].all() and (R["Stop Reason"] == "time").all(), "expected 1740 feasible runs on 58 instances"
    R["limit"] = 3.0 * R["n"]
    R["gap"] = 100 * (R["Total Latency"] - R["bks"]) / R["bks"]

    g = R.groupby("Instance")
    E = pd.DataFrame({"ext_best": g["Total Latency"].min(), "ext_mean": g["Total Latency"].mean(), "ext_std": g["Total Latency"].std(ddof=1),
                      "ext_iters": g["Iterations"].mean(), "ext_cpu": g["CPU Time"].mean()})
    E = I.loc[E.index].join(E)
    E = E.rename(columns={"best": "base_best", "mean": "base_mean", "gap_best": "base_gap_best", "gap_mean": "base_gap_mean", "hit": "base_hit", "iters": "base_iters", "std": "base_std"})
    E["ext_gap_best"] = 100 * (E.ext_best - E.bks) / E.bks
    E["ext_gap_mean"] = 100 * (E.ext_mean - E.bks) / E.bks
    E["ext_hit"] = R.assign(h=R["Total Latency"] <= R.bks + TOL).groupby("Instance")["h"].mean() * 100
    E["ext_new_bks"] = E.ext_best < E.bks - 0.01
    E["ext_mean_le_zou_avg"] = E.ext_mean <= E.zou_avg + 1e-9
    E["ext_best_le_zou_best"] = E.ext_best <= E.zou_best + TOL

    # slices of the anytime trace in CPU seconds: multiples of the standard budget and the average run time of RLHEA.
    # NOTE: the extended campaign ran on a node with 1.33 x the CPU time per iteration of the standard campaign, so CPU-second slices are conservative for the method;
    # the machine-independent comparison is in iteration space (below).
    tr = {k: (v["CPU Seconds"].to_numpy(), v["Best Latency"].to_numpy()) for k, v in TR.sort_values(["Instance", "Seed", "CPU Seconds"]).groupby(["Instance", "Seed"])}
    rows = []
    for (inst, seed), (t, b) in tr.items():
        r = E.loc[inst]
        rec = {"Instance": inst, "Seed": seed}
        for m in (1, 2, 3, 5, 10):
            rec["v@%dx" % m] = val_at(t, b, m * r.budget)
        rec["v@Tavg"] = val_at(t, b, r.zou_tavg)
        rows.append(rec)
    S = pd.DataFrame(rows)
    S.to_csv(D / "slices_ext.csv", index=False)
    for c in [c for c in S.columns if c.startswith("v@")]:
        gg = S.groupby("Instance")[c]
        E["mean_" + c] = gg.mean()
        E["best_" + c] = gg.min()
        E["gapmean_" + c] = 100 * (E["mean_" + c] - E.bks) / E.bks
        E["gapbest_" + c] = 100 * (E["best_" + c] - E.bks) / E.bks
    E["Tavg_mean_le_zou_avg"] = E["mean_v@Tavg"] <= E.zou_avg + 1e-9
    E["Tavg_best_le_zou_best"] = E["best_v@Tavg"] <= E.zou_best + TOL
    E["Tavg_in_budget"] = E.zou_tavg <= 3 * E.n

    # time to target from the extended traces
    TT = time_to_target(tr, E, ("bks", "zou_avg", "zou_best"))
    TT.to_csv(D / "ttt_ext_runs.csv", index=False)
    ttt_summary(TT, E, ("bks", "zou_avg", "zou_best"), ("esucc_", "etmed_", "etq50_"))

    # anytime grid in CPU seconds (multiples of the standard budget, 0.1 .. 10)
    fr = np.round(np.geomspace(0.1, 10.0, 41), 5)
    rows = []
    for (inst, seed), (t, b) in tr.items():
        r = E.loc[inst]
        for f in fr:
            v = val_at(t, b, f * r.budget)
            rows.append((inst, seed, f, np.nan if np.isnan(v) else 100 * (v - r.bks) / r.bks))
    pd.DataFrame(rows, columns=["Instance", "Seed", "mult", "gap"]).merge(E[["n", "family"]], left_on="Instance", right_index=True).to_csv(D / "anytime_grid_ext.csv", index=False)

    # iteration-space slices (machine independent): value after m x (iterations of the standard run of the same seed).
    # The extended run of a seed continues the standard run of that seed (its incumbent at the standard iteration count equals the standard result in all
    # 1740 pairs), so slices in iteration space put the standard budget at exactly 1 and are independent of the node load.
    TRI = {k: (v["Iteration"].to_numpy(), v["Best Latency"].to_numpy()) for k, v in TR.sort_values(["Instance", "Seed", "Iteration"]).groupby(["Instance", "Seed"])}
    R = R.merge(R1[["Instance", "Seed", "Iterations", "CPU Time"]].rename(columns={"Iterations": "iters_1x", "CPU Time": "cpu_1x"}), on=["Instance", "Seed"])
    R["iter_ratio"] = R["Iterations"] / R["iters_1x"]
    R["cpu_per_iter_ratio"] = (R["CPU Time"] / R["Iterations"]) / (R["cpu_1x"] / R["iters_1x"])
    R.to_csv(D / "ext_runs.csv", index=False)

    def val_it(it, b, k):
        j = np.searchsorted(it, k, side="right") - 1
        return b[j] if j >= 0 else np.nan

    rows = []
    for _, r in R.iterrows():
        it, b = TRI[(r.Instance, r.Seed)]
        rec = {"Instance": r.Instance, "Seed": r.Seed, "iters_1x": r.iters_1x, "iters_ext": r.Iterations}
        for m in (1, 2, 3, 5):
            tgt = int(np.floor(m * r.iters_1x)) - 1
            rec["it@%dx" % m] = val_it(it, b, tgt) if tgt <= r.Iterations - 1 else np.nan        # NaN: the extended run is shorter than m standard runs
        rec["it@final"] = r["Total Latency"]
        rows.append(rec)
    SI = pd.DataFrame(rows)
    SI.to_csv(D / "slices_iter.csv", index=False)
    for c in ("it@1x", "it@2x", "it@3x", "it@5x", "it@final"):
        gg = SI.groupby("Instance")[c]
        E["itmean_" + c] = gg.mean()
        E["itbest_" + c] = gg.min()
        E["itgapmean_" + c] = 100 * (E["itmean_" + c] - E.bks) / E.bks
        E["itgapbest_" + c] = 100 * (E["itbest_" + c] - E.bks) / E.bks
    E["itn_it@5x"] = SI.groupby("Instance")["it@5x"].apply(lambda x: x.notna().sum())
    fr = np.round(np.geomspace(0.1, 7.0, 36), 5)
    rows = []
    for _, r in R.iterrows():
        it, b = TRI[(r.Instance, r.Seed)]
        bks = E.loc[r.Instance, "bks"]
        for f in fr:
            tgt = int(np.floor(f * r.iters_1x)) - 1
            v = val_it(it, b, tgt) if (0 <= tgt <= r.Iterations - 1) else np.nan
            rows.append((r.Instance, r.Seed, f, np.nan if np.isnan(v) else 100 * (v - bks) / bks))
    pd.DataFrame(rows, columns=["Instance", "Seed", "mult", "gap"]).merge(E[["n", "family"]], left_on="Instance", right_index=True).to_csv(D / "anytime_grid_iter.csv", index=False)
    E.to_csv(D / "inst_ext.csv")
    print("extended budget: %d instances, %d runs; iteration ratio ext/1x: median %.2f (min %.2f, max %.2f); CPU per iteration ratio median %.2f"
          % (len(E), len(R), R.iter_ratio.median(), R.iter_ratio.min(), R.iter_ratio.max(), R.cpu_per_iter_ratio.median()))
    print("mean gaps over the 58 instances:", E[["base_gap_mean", "ext_gap_mean", "base_gap_best", "ext_gap_best"]].mean().round(3).to_dict())


def main():
    p = make_parser(__doc__.split("\n")[0], need_base=True, need_ext=True)
    p.add_argument("--atmost", default="/tmp/results_atmost", help="extracted atmost archive: directory results_atmost/ (default /tmp/results_atmost); its runs replace those of 50-5-2BIS-5")
    p.add_argument("--no-atmost", action="store_true", help="keep the default-setting runs of 50-5-2BIS-5 (exactly Ng open depots) instead of the --atmost runs")
    p.add_argument("--no-ext", action="store_true", help="skip the extended-budget layer")
    a = p.parse_args()
    D = dirs(a.out)["data"]
    I, R = standard(a.base, reference(), D, None if a.no_atmost else a.atmost)
    if not a.no_ext:
        extended(a.ext, I, R, D)


if __name__ == "__main__":
    main()
