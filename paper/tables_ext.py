#!/usr/bin/env python3
"""LaTeX tables and quoted numbers of the extended-budget results.  Reads <out>/data/inst_ext.csv (written by prep.py).  usage: tables_ext.py [--out DIR]"""
import os, sys
import numpy as np, pandas as pd
from scipy import stats
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paperlib import dirs, make_parser
_a = make_parser(__doc__.split("\n")[0], need_base=False).parse_args()
_d = dirs(_a.out); D = str(_d["data"]); T = str(_d["tables"]); F = str(_d["figs"])
E = pd.read_csv(os.path.join(D, "inst_ext.csv"), index_col=0); TOL = 0.005
E["zou_gap_best"] = 100 * (E.zou_best - E.bks) / E.bks; E["zou_gap_avg"] = 100 * (E.zou_avg - E.bks) / E.bks
CAVEAT = {"P131122-20", "P112222-20", "P122122-20", "Or117-14"}          # published solution file defective or empty: reference value not re-verified from the file
FAM = {"prins": "Prins", "barreto": "Barreto", "tuzun": "Tuzun"}


def f(x, d=2, thousands=True):
    if pd.isna(x): return "--"
    s = f"{x:,.{d}f}" if thousands else f"{x:.{d}f}"
    if float(s.replace(",", "")) == 0: s = s.lstrip("-")
    return s.replace(",", "{,}") if thousands else s


def gap(x, d=3):
    s = f"{x:.{d}f}"
    if float(s) == 0: return s.lstrip("-")
    return "$-$" + s[1:] if s.startswith("-") else s


def agg(d):
    return dict(k=len(d), b1=d.base_gap_best.mean(), m1=d.base_gap_mean.mean(), h1=int((d.base_best <= d.bks + TOL).sum()),
                b10=d.ext_gap_best.mean(), m10=d.ext_gap_mean.mean(), h10=int((d.ext_best <= d.bks + TOL).sum()), za=d.zou_gap_avg.mean(),
                m10le=int(d.ext_mean_le_zou_avg.sum()))


rows, groups = [], []
for fam in ("prins", "barreto", "tuzun"):
    for tr, lab in ((True, "tuning"), (False, "held out")):
        d = E[(E.family == fam) & (E.train == tr)]
        groups.append((FAM[fam], lab, d))
body = []
for name, lab, d in groups:
    a = agg(d)
    body.append(" & ".join([name, lab, str(a["k"]), gap(a["b1"]), gap(a["m1"]), f"{a['h1']}", gap(a["b10"]), gap(a["m10"]), f"{a['h10']}", gap(a["za"]), f"{a['m10le']}"]) + r" \\")
body.append(r"\midrule")
for lab, d in (("tuning", E[E.train]), ("held out", E[~E.train]), ("all", E)):
    a = agg(d)
    body.append(" & ".join(["All" if lab != "all" else r"\textbf{All}", lab, str(a["k"]), gap(a["b1"]), gap(a["m1"]), f"{a['h1']}", gap(a["b10"]), gap(a["m10"]), f"{a['h10']}", gap(a["za"]), f"{a['m10le']}"]) + r" \\")
tab = r"""\begin{table}[htbp]
\centering
\caption{Results on the 58 instances with $n \geq 75$ at the standard budget $\max\{5, 0.3\,n\}$ s and at the extended budget $3n$ s (30 runs per instance and budget), by family and set. $k$: number of instances; Gap: mean over the instances of the percentage gap of the best and of the mean of the 30 runs to BKS; \#BKS: instances on which the best run reaches $f \leq \mathrm{BKS} + 0.005$; RLHEA: mean over the instances of the gap of the average value published by \citet{zou2024reinforcement} (the best value of RLHEA is the reference value on every one of these instances); \#$\leq$RLHEA: instances on which the mean of the 30 runs at the extended budget does not exceed the published average. No run improves a reference value by more than 0.01.}
\label{tab:large_instances}
\small
\setlength{\tabcolsep}{3.4pt}
\begin{adjustbox}{max width=\textwidth}
\begin{tabular}{@{}llrrrrrrrrr@{}}
\toprule
 & & & \multicolumn{3}{c}{Standard budget} & \multicolumn{3}{c}{Extended budget} & & \\
\cmidrule(lr){4-6}\cmidrule(lr){7-9}
Family & Set & $k$ & \makecell{Gap\\best} & \makecell{Gap\\mean} & \#BKS & \makecell{Gap\\best} & \makecell{Gap\\mean} & \#BKS & \makecell{Gap\\RLHEA} & \#$\leq$RLHEA \\
\midrule
""" + "\n".join(body) + r"""
\bottomrule
\end{tabular}
\end{adjustbox}
\end{table}
"""
open(os.path.join(T, "tab_large.tex"), "w").write(tab)

# ---- Appendix: 58 instances at the extended budget -----------------------------------------------------------------------------------------
ordr = E.assign(_f=E.family.map({"prins": 0, "barreto": 1, "tuzun": 2}), _nm=E.index.str.lower()).sort_values(["_f", "n", "_nm"])
lines, last = [], None
def nm(name, tr): return name + (r"$^{\dagger}$" if tr else "") + (r"$^{\S}$" if name in CAVEAT else "")
for name, r in ordr.iterrows():
    if last is not None and r.family != last: lines.append(r"\midrule")
    last = r.family
    lines.append(" & ".join([nm(name, r.train), f"{int(r.n)}", f(r.bks, 2), f(r.zou_avg, 2), f(r.ext_best, 2), f(r.ext_mean, 2), f(r.ext_std, 2), gap(r.ext_gap_best, 2), gap(r.ext_gap_mean, 2),
                             f"{r.ext_hit:.0f}", f"{r.ext_iters:.0f}", f"{r.iter_ratio:.1f}" if "iter_ratio" in r else ""]) + r" \\")
R = pd.read_csv(os.path.join(D, "ext_runs.csv")); ir = R.groupby("Instance")["iter_ratio"].median()
lines = []; last = None
for name, r in ordr.iterrows():
    if last is not None and r.family != last: lines.append(r"\midrule")
    last = r.family
    lines.append(" & ".join([nm(name, r.train), f"{int(r.n)}", f(r.bks, 2), f(r.zou_avg, 2), f(r.ext_best, 2), f(r.ext_mean, 2), f(r.ext_std, 2), gap(r.ext_gap_best, 2), gap(r.ext_gap_mean, 2),
                             f"{r.ext_hit:.0f}", f"{r.ext_iters:.0f}", f"{ir[name]:.1f}"]) + r" \\")
H = r"Instance & $n$ & BKS & \makecell{RLHEA\\avg} & Best & Mean & SD & \makecell{Gap\\best} & \makecell{Gap\\mean} & \makecell{Hit\\(\%)} & Iter. & \makecell{Iter.\\ratio} \\"
longtab = r"""\begin{longtable}{@{}lrrrrrrrrrrr@{}}
\caption{Instance-level results of the tuned GRASP--RVND at the extended budget $3n$ s on the 58 instances with $n \geq 75$, 30 runs per instance. Columns as in Table~\ref{tab:appendix_instances}; Iter.: mean number of GRASP iterations per run; Iter. ratio: median over the 30 seeds of the ratio of the iterations of the extended run to those of the standard run of the same seed (the CPU-time budget is ten times larger, but one iteration took 1.33 times as much CPU time in the extended campaign, see Section~\ref{sec:setup}). Instances marked with $\dagger$ belong to the tuning set. Instances marked with $\S$: the solution file published with the reference value is incomplete, inconsistent with the published value, or empty, so that the reference value could not be recomputed from it (Section~\ref{sec:quality}).}
\label{tab:appendix_extended} \\
\toprule
""" + H + r"""
\midrule
\endfirsthead
\toprule
""" + H + r"""
\midrule
\endhead
\midrule \multicolumn{12}{r}{\small continued on the next page} \\
\endfoot
\bottomrule
\endlastfoot
""" + "\n".join(lines) + "\n" + r"\end{longtable}" + "\n"
open(os.path.join(T, "tab_appendix_ext.tex"), "w").write(longtab)

# ---- numbers quoted in the text -------------------------------------------------------------------------------------------------------------
Hh = E[~E.train]; out = []
def w(a_abs, b_abs, lab, tol):
    d = a_abs - b_abs; d = np.where(np.abs(d) <= tol, 0.0, d)
    p = stats.wilcoxon(d, zero_method="wilcox").pvalue if (d != 0).any() else np.nan
    out.append(f"{lab}: ours better {int((d < 0).sum())}, tie {int((d == 0).sum())}, ours worse {int((d > 0).sum())}; Wilcoxon (ties dropped, n={int((d != 0).sum())}) p={p:.2e}")
for tag, bcol, mcol in (("standard", "base_best", "base_mean"), ("extended", "ext_best", "ext_mean")):
    for lab, S in (("held-out", Hh), ("all 58", E)):
        w(S[bcol], S.zou_best, f"[{tag}, {lab}] best of 30 vs RLHEA best", TOL)
        w(S[mcol], S.zou_avg, f"[{tag}, {lab}] mean of 30 vs RLHEA avg", TOL)
for lab, S in (("held-out", Hh), ("all 58", E)):
    w(S["best_v@Tavg"], S.zou_best, f"[at T_avg, {lab}] best of 30 vs RLHEA best", TOL); w(S["mean_v@Tavg"], S.zou_avg, f"[at T_avg, {lab}] mean of 30 vs RLHEA avg", TOL)
out.append(f"instances: {len(E)} (tuning {int(E.train.sum())}, held-out {len(Hh)}); T_avg within the extended budget: {int(E.Tavg_in_budget.sum())}")
out.append(f"extended: best reaches BKS+0.005 on {int((E.ext_best <= E.bks + TOL).sum())} (held-out {int((Hh.ext_best <= Hh.bks + TOL).sum())}); standard {int((E.base_best <= E.bks + TOL).sum())} (held-out {int((Hh.base_best <= Hh.bks + TOL).sum())})")
out.append(f"extended: mean<=RLHEA avg on {int(E.ext_mean_le_zou_avg.sum())} (held-out {int(Hh.ext_mean_le_zou_avg.sum())}); mean hit rate {E.ext_hit.mean():.1f}% (standard {E.base_hit.mean():.1f}%); hit>0 on {int((E.ext_hit > 0).sum())}")
out.append(f"mean gaps (all 58): best {E.base_gap_best.mean():.3f}->{E.ext_gap_best.mean():.3f}; mean {E.base_gap_mean.mean():.3f}->{E.ext_gap_mean.mean():.3f}; RLHEA avg {E.zou_gap_avg.mean():.3f}")
for lab, (lo, hi) in {"75-134": (75, 134), "150": (150, 150), "200": (200, 200)}.items():
    S = E[(E.n >= lo) & (E.n <= hi)]
    out.append(f"class n={lab} (k={len(S)}): mean gap std {S.base_gap_mean.mean():.3f} ext {S.ext_gap_mean.mean():.3f}; best gap std {S.base_gap_best.mean():.3f} ext {S.ext_gap_best.mean():.3f}; RLHEA avg {S.zou_gap_avg.mean():.3f}; hit>0 {int((S.ext_hit>0).sum())}/{len(S)}")
out.append(f"mean gap > 1% at extended budget: {int((E.ext_gap_mean > 1).sum())} instances; > 2%: {int((E.ext_gap_mean > 2).sum())} ({', '.join(E[E.ext_gap_mean > 2].index)})")
out.append(f"iteration-space slices (mean over 58 of mean gap): 1x {E['itgapmean_it@1x'].mean():.3f} 2x {E['itgapmean_it@2x'].mean():.3f} 3x {E['itgapmean_it@3x'].mean():.3f} 5x {E['itgapmean_it@5x'].mean():.3f} final {E['itgapmean_it@final'].mean():.3f}")
out.append(f"at T_avg of RLHEA (CPU time of the loaded node): mean gap {E['gapmean_v@Tavg'].mean():.3f}, best gap {E['gapbest_v@Tavg'].mean():.3f}; best<=RLHEA best on {int(E.Tavg_best_le_zou_best.sum())}; mean<=RLHEA avg on {int(E.Tavg_mean_le_zou_avg.sum())}")
out.append(f"time to RLHEA avg (extended traces): >=1 run reaches on {int((E.esucc_zou_avg>0).sum())}; >=15 runs on {int((E.esucc_zou_avg>=15).sum())}; to RLHEA best/BKS: {int((E.esucc_zou_best>0).sum())}/{int((E.esucc_bks>0).sum())}")
q = E[E.esucc_zou_avg >= 15]; out.append(f"median tq50/T_avg among those {len(q)}: {(q.etq50_zou_avg/q.zou_tavg).median():.2f}; instances reaching RLHEA avg in >=1 run with t_med<=T_avg: {int(((E.etmed_zou_avg<=E.zou_tavg)&(E.esucc_zou_avg>0)).sum())}")
open(os.path.join(T, "numbers_ext.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
