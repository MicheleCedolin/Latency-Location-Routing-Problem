"""Shared helpers of the paper pipeline: repository paths, the per-instance reference table and the output layout.

The reference table replaces the pickled `T.pkl` of the original (private) pipeline. Every column is read from files of this repository:

    cpp/manifest.tsv             family, instance name, n, best-known latency (BKS)
    bks/literature_results.csv   best / average value and average run time of RLHEA (Zou et al. 2024), published values
    cpp/selection/train.txt      the 17 instances used to tune the parameters with irace
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
TOL = 0.005                                    # reference values carry two decimals
FAMS = ["prins", "barreto", "tuzun"]
FAMNAME = {"prins": "Prins", "barreto": "Barreto", "tuzun": "Tuzun"}


def reference(repo=REPO):
    """Per-instance reference table, index `Instance`, columns family, n, bks, zou_best, zou_avg, zou_tavg, train."""
    repo = Path(repo)
    man = pd.read_csv(repo / "cpp" / "manifest.tsv", sep="\t")
    lit = pd.read_csv(repo / "bks" / "literature_results.csv")
    z = lit[lit["algorithm"] == "RLHEA"].set_index("instance")
    with open(repo / "cpp" / "selection" / "train.txt") as fh:
        train = {ln.strip().split("/")[1] for ln in fh if ln.strip()}
    T = man.set_index("name")[["family", "n", "bks"]].copy()
    T.index.name = "Instance"
    T["zou_best"] = z["best"]
    T["zou_avg"] = z["avg"]
    T["zou_tavg"] = z["time_s"]
    T["train"] = T.index.isin(train)
    # two published values that differ by rounding between the sources: the manuscript tables use the values of reference_overrides.csv
    for _, o in pd.read_csv(Path(__file__).with_name("reference_overrides.csv")).iterrows():
        T.loc[o["instance"], o["column"]] = float(o["value"])
    if T.isna().any().any():
        raise SystemExit("reference table incomplete:\n%s" % T[T.isna().any(axis=1)])
    if len(T) != 76 or int(T["train"].sum()) != 17:
        raise SystemExit("expected 76 instances with 17 tuning instances, found %d / %d" % (len(T), int(T["train"].sum())))
    return T


def make_parser(description, need_base=True, need_ext=False):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--out", default=str(REPO / "paper" / "out"), help="output root: data/, tables/ and figs/ are created below it (default paper/out)")
    if need_base:
        p.add_argument("--base", default="/tmp/results_final", help="extracted 1x archive: directory results_final/ (default /tmp/results_final)")
    if need_ext:
        p.add_argument("--ext", default="/tmp/results_extended10", help="extracted ext10 archive: directory results_extended10/ (default /tmp/results_extended10)")
    return p


def dirs(out):
    out = Path(out)
    d = {k: out / k for k in ("data", "tables", "figs")}
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d


def need(path, hint):
    if not Path(path).exists():
        sys.exit("missing %s\n%s" % (path, hint))
    return Path(path)
