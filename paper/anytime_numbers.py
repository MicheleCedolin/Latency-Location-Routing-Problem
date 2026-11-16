#!/usr/bin/env python3
"""Numbers quoted in the 'Anytime behavior' paragraph, computed exactly from the anytime traces (not from the plotting grid).
Class mean of the instance means of the gap of the incumbent at a given share of the standard budget max{5, 0.3 n}; a class is reported at a share
only if at least 90% of its runs have a feasible incumbent then (as in the figure).  'end' = final solution of the run (gap of the mean, as in the tables).  usage: anytime_numbers.py --base DIR [--atmost DIR | --no-atmost] [--exclude INSTANCE]"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paperlib import FAMS, make_parser, need, reference
from prep import with_atmost
_p = make_parser(__doc__.split("\n")[0])
_p.add_argument("--atmost", default="/tmp/results_atmost", help="extracted atmost archive (directory results_atmost/); its runs replace those of Prins 50-5-2BIS-5, as in prep.py")
_p.add_argument("--no-atmost", action="store_true", help="use the default-setting runs of 50-5-2BIS-5")
_p.add_argument("--exclude", default=None, help="leave one instance out")
_a = _p.parse_args()
EXCL = _a.exclude
T = reference()
TR = pd.concat([pd.read_csv(need(os.path.join(_a.base, f, "tuned", "trace.csv"), "extract study_results/final_1x_tuned.tar.gz")) for f in FAMS], ignore_index=True)
RUN = pd.concat([pd.read_csv(os.path.join(_a.base, f, "tuned", "run.csv")) for f in FAMS], ignore_index=True)
if not _a.no_atmost:
    TR, RUN = with_atmost(TR, _a.atmost, "trace"), with_atmost(RUN, _a.atmost, "run")
if EXCL:
    TR = TR[TR.Instance != EXCL]; RUN = RUN[RUN.Instance != EXCL]
CLS = [("n<=50", 0, 50), ("75<=n<=134", 51, 134), ("n=150", 135, 150), ("n=200", 151, 200)]
tr = {k: (v["CPU Seconds"].to_numpy(), v["Best Latency"].to_numpy()) for k, v in TR.sort_values(["Instance", "Seed", "CPU Seconds"]).groupby(["Instance", "Seed"])}
FR = (0.10, 0.25, 0.50)
print("%-11s %5s   " % ("class", "n_inst") + "  ".join("%5.0f%%" % (100 * f) for f in FR) + "     end")
for lab, lo, hi in CLS:
    inst = [i for i in T.index if lo <= T.loc[i, "n"] <= hi and i != EXCL]
    row = []
    for f in FR:
        per, avail = [], []
        for i in inst:
            bks, bud = T.loc[i, "bks"], max(5.0, 0.3 * T.loc[i, "n"])
            g = []
            for (ii, s), (t, b) in tr.items():
                if ii != i: continue
                k = np.searchsorted(t, f * bud, side="right") - 1
                g.append(np.nan if k < 0 else 100 * (b[k] - bks) / bks)
            g = np.array(g); avail.append(np.isfinite(g).mean()); per.append(np.nanmean(g) if np.isfinite(g).any() else np.nan)
        row.append((np.nanmean(per), np.mean(avail)))
    end = np.mean([100 * (RUN[RUN.Instance == i]["Total Latency"].mean() - T.loc[i, "bks"]) / T.loc[i, "bks"] for i in inst])
    print("%-11s %5d   " % (lab, len(inst)) + "  ".join("%6.3f%s" % (v, "" if a >= .9 else "*") for v, a in row) + "   %6.3f" % end)
