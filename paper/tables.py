#!/usr/bin/env python3
"""LaTeX tables of the GRASP-RVND paper (standard budget), generated from <out>/data/*.csv (written by prep.py).  usage: tables.py [--out DIR]"""
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paperlib import dirs, make_parser
_a = make_parser(__doc__.split("\n")[0], need_base=False).parse_args()
_d = dirs(_a.out); D = str(_d["data"]); T = str(_d["tables"]); F = str(_d["figs"])
I = pd.read_csv(os.path.join(D, "inst.csv"), index_col=0)
FAMNAME = {"prins": "Prins", "barreto": "Barreto", "tuzun": "Tuzun"}


def f(x, d=2, thousands=True):
    if pd.isna(x):
        return "--"
    s = f"{x:,.{d}f}" if thousands else f"{x:.{d}f}"
    if float(s.replace(",", "")) == 0:
        s = s.lstrip("-")
    return s.replace(",", "{,}") if thousands else s


def gap(x, d=3):
    s = f"{x:.{d}f}"
    if float(s) == 0:
        return s.lstrip("-")
    return "$-$" + s[1:] if s.startswith("-") else s


ATMOST = {"50-5-2BIS-5"}      # solved with the at-most setting of the depot count (all other instances: default setting, exactly N_g depots)


def inst_tex(name, train):
    return name + (r"$^{\dagger}$" if train else "") + (r"$^{\ddagger}$" if name in ATMOST else "")


def order(df):
    fam = {"prins": 0, "barreto": 1, "tuzun": 2}
    return df.assign(_f=df.family.map(fam), _nm=df.index.str.lower()).sort_values(["_f", "n", "_nm"]).drop(columns=["_f", "_nm"])


# ---- Table: instances with n <= 50 ----------------------------------------------------------------------------------------------
S = order(I[I.n <= 50])
rows = []
for name, r in S.iterrows():
    t = f(r.tmed_bks, 2, False) if r.succ_bks > 0 else "--"
    rows.append(" & ".join([inst_tex(name, r.train), f"{int(r.n)}", f(r.bks, 2), f(r.zou_avg, 2), f(r.best, 2), f(r["mean"], 2),
                            gap(r.gap_best), gap(r.gap_mean), f"{r.hit:.1f}".rstrip("0").rstrip(".") if r.hit not in (0, 100) else f"{int(r.hit)}",
                            t, f(r.zou_tavg, 1, False)]) + r" \\")
# insert family rules
out = []
last = None
for (name, r), row in zip(S.iterrows(), rows):
    if last is not None and r.family != last:
        out.append(r"\midrule")
    out.append(row); last = r.family
tab = r"""\begin{table}[htbp]
\centering
\caption{Results on the 18 instances with $n \leq 50$ at the standard budget $\max\{5, 0.3\,n\}$ s (30 runs per instance). BKS: reference value; RLHEA: average value published by \citet{zou2024reinforcement}; Hit: percentage of runs with $f \leq \mathrm{BKS} + 0.005$; $t_{\mathrm{BKS}}$: median CPU time of the runs that reach the BKS (\texttt{--}: none does); $T_{\mathrm{avg}}$: average run time of RLHEA, on a different machine. Instances marked with $\dagger$ belong to the tuning set; the instance marked with $\ddagger$ was solved with the at-most setting of the depot count (Section~\ref{sec:representation}). Gaps in \%.}
\label{tab:small_instances}
\small
\setlength{\tabcolsep}{3.2pt}
\begin{adjustbox}{max width=\textwidth}
\begin{tabular}{@{}lrrrrrrrrrr@{}}
\toprule
Instance & $n$ & BKS & \makecell{RLHEA\\avg} & \makecell{Best\\of 30} & \makecell{Mean\\of 30} & \makecell{Gap\\best} & \makecell{Gap\\mean} & \makecell{Hit\\(\%)} & \makecell{$t_{\mathrm{BKS}}$\\(s)} & \makecell{$T_{\mathrm{avg}}$\\(s)} \\
\midrule
""" + "\n".join(out) + r"""
\bottomrule
\end{tabular}
\end{adjustbox}
\end{table}
"""
open(os.path.join(T, "tab_small.tex"), "w").write(tab)

# ---- Table: operator statistics ---------------------------------------------------------------------------------------------------
B = pd.read_csv(os.path.join(D, "ops_by_class.csv"), index_col=[0, 1])
OPS = ["relocate", "oropt2", "swap11", "swap21", "2opt*", "swapstar", "dexch", "rdepot", "ds"]
CL = ["n<=50", "75-134", "150", "200", "all"]
rows = []
for o in OPS:
    a = B.loc[("all", o)]
    hit = 100 * a.Applied / a.Calls
    cells = [r"\texttt{%s}" % o, "depot" if o in ("dexch", "rdepot", "ds") else "route", f"{hit:.1f}"]
    for c in CL:
        t = B.loc[c]
        cells.append(f"{100 * t.loc[o, 'CPU Seconds'] / t['CPU Seconds'].sum():.1f}")
    for c in CL:
        t = B.loc[c]
        cells.append(f"{100 * t.loc[o, 'Applied'] / t['Applied'].sum():.1f}")
    rows.append(" & ".join(cells) + r" \\")
rows.insert(6, r"\midrule")
tab = r"""\begin{table}[htbp]
\centering
\caption{Share of the CPU time spent in each operator and of the moves it applies, by instance size, over the 2{,}280 runs of the standard-budget campaign; Hit is the percentage of calls of the operator that apply a move. The shares are relative to the nine operators of the pool; the remaining CPU time of a run (about 4--8\%) is spent outside the nine operators.}
\label{tab:operator_stats}
\small
\setlength{\tabcolsep}{3.6pt}
\begin{adjustbox}{max width=\textwidth}
\begin{tabular}{@{}llrrrrrrrrrrr@{}}
\toprule
 & & & \multicolumn{5}{c}{CPU time (\%)} & \multicolumn{5}{c}{Applied moves (\%)} \\
\cmidrule(lr){4-8}\cmidrule(lr){9-13}
Operator & Level & Hit (\%) & $\leq 50$ & 75--134 & 150 & 200 & All & $\leq 50$ & 75--134 & 150 & 200 & All \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\end{adjustbox}
\end{table}
"""
open(os.path.join(T, "tab_ops.tex"), "w").write(tab)

# ---- Appendix: all 76 instances ---------------------------------------------------------------------------------------------------
A = order(I)
lines = []
last = None
for name, r in A.iterrows():
    if last is not None and r.family != last:
        lines.append(r"\midrule")
    last = r.family
    lines.append(" & ".join([inst_tex(name, r.train), f"{int(r.n)}", f(r.bks, 2), f(r.zou_best, 2), f(r.zou_avg, 2), f(r.best, 2), f(r["mean"], 2), f(r["std"], 2),
                             gap(r.gap_best, 2), gap(r.gap_mean, 2), f"{r.hit:.0f}", f"{r.iters:.0f}"]) + r" \\")
longtab = r"""\begin{longtable}{@{}lrrrrrrrrrrr@{}}
\caption{Instance-level results of the tuned GRASP--RVND at the standard budget $\max\{5, 0.3\,n\}$ s, 30 runs per instance. BKS: reference value; RLHEA: best and average values published by \citet{zou2024reinforcement}; Best, Mean, SD: best, mean, and standard deviation of the 30 final objective values; Gap: percentage gap of the best and of the mean value to BKS; Hit: percentage of runs with $f \leq \mathrm{BKS} + 0.005$; Iter.: mean number of GRASP iterations per run. Instances marked with $\dagger$ belong to the tuning set; the instance marked with $\ddagger$ was solved with the at-most setting of the depot count (Section~\ref{sec:representation}).}
\label{tab:appendix_instances} \\
\toprule
Instance & $n$ & BKS & \makecell{RLHEA\\best} & \makecell{RLHEA\\avg} & Best & Mean & SD & \makecell{Gap\\best} & \makecell{Gap\\mean} & \makecell{Hit\\(\%)} & Iter. \\
\midrule
\endfirsthead
\toprule
Instance & $n$ & BKS & \makecell{RLHEA\\best} & \makecell{RLHEA\\avg} & Best & Mean & SD & \makecell{Gap\\best} & \makecell{Gap\\mean} & \makecell{Hit\\(\%)} & Iter. \\
\midrule
\endhead
\midrule \multicolumn{12}{r}{\small continued on the next page} \\
\endfoot
\bottomrule
\endlastfoot
""" + "\n".join(lines) + "\n" + r"\end{longtable}" + "\n"
open(os.path.join(T, "tab_appendix.tex"), "w").write(longtab)

# ---- numbers used in the text (printed for the record) ---------------------------------------------------------------------------
S50 = I[I.n <= 50]
H = S50[~S50.train]
with open(os.path.join(T, "numbers_n50.txt"), "w") as fh:
    fh.write(f"instances n<=50: {len(S50)} (tuning {int(S50.train.sum())}, held-out {len(H)})\n")
    fh.write(f"reach BKS (best<=BKS+0.005): {(S50.best <= S50.bks + 0.005).sum()} of {len(S50)}; held-out {(H.best <= H.bks + 0.005).sum()} of {len(H)}\n")
    fh.write(f"mean best gap {S50.gap_best.mean():.4f}, mean mean gap {S50.gap_mean.mean():.4f}; held-out {H.gap_best.mean():.4f}/{H.gap_mean.mean():.4f}\n")
    ex = S50.drop(index="50-5-2BIS-5")
    fh.write(f"excluding 50-5-2BIS-5: best {ex.gap_best.mean():.4f}, mean {ex.gap_mean.mean():.4f}\n")
    fh.write(f"mean<=RLHEA avg+0.005: {(S50['mean'] <= S50.zou_avg + 0.005).sum()} of {len(S50)}\n")
    fh.write(f"hit 100%: {(S50.hit == 100).sum()}; hit<100 & >0: {((S50.hit < 100) & (S50.hit > 0)).sum()}; hit==0: {(S50.hit == 0).sum()}\n")
    fh.write(f"median tmed/Tavg: {(S50.tmed_bks / S50.zou_tavg).median():.4f}; max {(S50.tmed_bks / S50.zou_tavg).max():.4f}; max tmed {S50.tmed_bks.max():.3f}\n")
print(open(os.path.join(T, "numbers_n50.txt")).read())
