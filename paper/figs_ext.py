#!/usr/bin/env python3
"""Result figures with the standard and the extended budget: fig_gap_instances (gap per instance), fig_ttt (time to target), fig_anytime (anytime behaviour).
Reads <out>/data/inst.csv, inst_ext.csv, anytime_grid.csv (standard campaign) and anytime_grid_iter.csv (extended campaign, iteration space).  usage: figs_ext.py [--out DIR]"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figs import *            # palette, helpers, D (data dir), F (figure dir) and the standard-budget table I

E = pd.read_csv(os.path.join(D, "inst_ext.csv"), index_col=0)
J = I.copy()                                                          # plotted values: standard budget for n <= 50, extended budget for n >= 75
J["pb"] = J.gap_best; J["pm"] = J.gap_mean; J["std_m"] = np.nan
J["zou_avg_gap"] = J.zou_gap_avg
for k in E.index:
    J.loc[k, "pb"] = E.loc[k, "ext_gap_best"]; J.loc[k, "pm"] = E.loc[k, "ext_gap_mean"]; J.loc[k, "std_m"] = E.loc[k, "base_gap_mean"]


def fig_gap_instances2():
    fams = ["prins", "barreto", "tuzun"]
    cnt = [int((J.family == f).sum()) for f in fams]
    fig, axs = plt.subplots(1, 3, figsize=(6.6, 2.8), sharey=True, gridspec_kw={"width_ratios": cnt, "wspace": 0.05})
    for ax, fam in zip(axs, fams):
        c, mk, lab = FAM[fam]
        d = J[J.family == fam].sort_values(["n", "bks"]).reset_index()
        x = np.arange(len(d))
        ax.vlines(x, d.pb.clip(lower=0), d.pm.clip(lower=0), color=c, lw=0.9, zorder=2)
        ax.scatter(x, d.std_m, s=9, marker="_", color=MUTED, linewidth=1.0, zorder=3)
        ax.scatter(x, d.pm.clip(lower=0), s=14, marker=mk, facecolor="white", edgecolor=c, linewidth=0.9, zorder=3)
        ax.scatter(x, d.pb.clip(lower=0), s=14, marker=mk, facecolor=c, edgecolor=c, linewidth=0.9, zorder=4)
        ax.scatter(x, d.zou_avg_gap, s=22, marker="x", color=INK2, linewidth=0.8, zorder=5)
        ax.axhline(0, color=INK2, lw=0.6)
        ns = d.n.values
        edges = [0] + [i for i in range(1, len(ns)) if ns[i] != ns[i - 1]] + [len(ns)]
        for a, b in zip(edges[:-1], edges[1:]):
            if fam == "barreto": continue
            ax.text((a + b - 1) / 2, -0.03, f"{ns[a]}", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6.8, color=INK2)
            if a > 0: ax.axvline(a - 0.5, color="#c9c8c3", lw=0.5, ls=":")
        if fam == "barreto":
            for xi, t in ((0, ns[0]), (len(ns) - 1, ns[-1])):
                ax.text(xi, -0.03, f"{t}", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6.8, color=INK2)
        ax.set_xticks([]); ax.set_xlim(-0.8, len(d) - 0.2)
        ax.set_title(f"{lab} ({len(d)})", fontsize=8.5, loc="left", color=INK)
        ax.grid(axis="x", visible=False)
    axs[0].set_ylabel("gap to BKS (%)")
    axs[1].set_xlabel(r"instances, grouped by number of customers $n$ (Barreto: from 21 to 134)", labelpad=16)
    axs[0].set_yscale("symlog", linthresh=0.1, linscale=0.5)
    axs[0].set_ylim(0, 14)
    axs[0].set_yticks([0, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]); axs[0].set_yticklabels(["0", "0.05", "0.1", "0.2", "0.5", "1", "2", "5", "10"])
    axs[0].yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    h = [Line2D([], [], marker="o", color=INK, mfc=INK, ls="", ms=4, label="best of 30 runs"), Line2D([], [], marker="o", color=INK, mfc="white", ls="", ms=4, label="mean of 30 runs"),
         Line2D([], [], marker="_", color=MUTED, ls="", ms=5, label=r"mean at standard budget ($n\geq 75$)"),
         Line2D([], [], marker="x", color=INK2, ls="", ms=4.5, label="mean of RLHEA (Zou et al.)")]
    axs[0].legend(handles=h, loc="upper left", frameon=False, handletextpad=0.1, borderaxespad=0.2)
    save(fig, "fig_gap_instances")


def fig_ttt2():
    fig, ax = plt.subplots(figsize=(4.4, 3.5))
    lo, hi = 0.008, 700
    ax.plot([lo, hi], [lo, hi], color=INK2, lw=0.8)
    ax.plot([lo, hi], [lo / 10, hi / 10], color=INK2, lw=0.6, ls="--")
    K = I.copy()
    for c in ("succ_zou_avg", "tq50_zou_avg", "tmed_zou_avg", "budget"):
        pass
    for k in E.index:
        K.loc[k, "succ_zou_avg"] = E.loc[k, "esucc_zou_avg"]; K.loc[k, "tq50_zou_avg"] = E.loc[k, "etq50_zou_avg"]
        K.loc[k, "tmed_zou_avg"] = E.loc[k, "etmed_zou_avg"]; K.loc[k, "budget"] = 3.0 * E.loc[k, "n"]
    for fam, (c, m, lab) in FAM.items():
        d = K[K.family == fam]
        full = d[d.succ_zou_avg >= 15]; part = d[(d.succ_zou_avg > 0) & (d.succ_zou_avg < 15)]; none = d[d.succ_zou_avg == 0]
        ax.scatter(full.zou_tavg, full.tq50_zou_avg, s=22, marker=m, facecolor=c, edgecolor=c, linewidth=0.9, zorder=4)
        ax.scatter(part.zou_tavg, part.tmed_zou_avg, s=22, marker=m, facecolor="white", edgecolor=c, linewidth=0.9, zorder=4)
        ax.scatter(none.zou_tavg, none.budget, s=14, marker="x", color=c, linewidth=0.8, zorder=3, alpha=0.8)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(2.5, 700); ax.set_ylim(lo, 1000)
    for a in (ax.xaxis, ax.yaxis): a.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter()); ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel(r"average run time $T_{\mathrm{avg}}$ of RLHEA (s)")
    ax.set_ylabel("median CPU time of our runs\nto reach the RLHEA mean value (s)")
    ax.text(5.0, 4.2, "equal time", fontsize=7.5, color=INK2, rotation=33, ha="center", va="center", rotation_mode="anchor")
    ax.text(4.0, 0.18, r"10$\times$ faster", fontsize=7.5, color=INK2, rotation=33, ha="center", va="center", rotation_mode="anchor")
    h = [Line2D([], [], marker=m, color=c, mfc=c, ls="", ms=5, label=lab) for _, (c, m, lab) in FAM.items()]
    h += [Line2D([], [], marker="o", color=INK2, mfc="white", ls="", ms=5, label="reached by 1–14 of 30 runs"),
          Line2D([], [], marker="x", color=INK2, ls="", ms=5, label="never reached (plotted at budget)")]
    ax.legend(handles=h, loc="lower right", frameon=False, handletextpad=0.2, borderaxespad=0.2, fontsize=7)
    save(fig, "fig_ttt")


def fig_anytime2():
    A0 = pd.read_csv(os.path.join(D, "anytime_grid.csv")); A0["cls"] = pd.cut(A0.n, [0, 50, 134, 150, 200], labels=[c[0] for c in CLS])
    A1 = pd.read_csv(os.path.join(D, "anytime_grid_iter.csv")); A1["cls"] = pd.cut(A1.n, [0, 50, 134, 150, 200], labels=[c[0] for c in CLS])
    fig, ax = plt.subplots(figsize=(4.8, 3.1))
    for key, col, mk, ls, lab in CLS:
        if key == "n<=50": s, xc = A0[A0.cls == key], "frac"
        else: s, xc = A1[A1.cls == key], "mult"
        avail = s.groupby(xc)["gap"].apply(lambda x: x.notna().mean()); ok = avail[avail >= 0.9].index; s = s[s[xc].isin(ok)]
        pi = s.groupby(["Instance", xc])["gap"].mean().reset_index(); m = pi.groupby(xc)["gap"].mean().clip(lower=1e-3)
        ax.plot(m.index, m.values, color=col, ls=ls, lw=1.3, marker=mk, ms=3.2, markevery=5, mfc=col, zorder=3)
        if key == "n<=50": ax.text(0.0245, 2.3, lab, color=INK, fontsize=7.5, va="center", ha="left")
        else: ax.text(m.index[-1] * 1.04, m.values[-1], lab, color=INK, fontsize=7.5, va="center", ha="left")
    ax.axvline(1.0, color=INK2, lw=0.7, ls=":"); ax.text(1.0, 0.93, "standard\nbudget", transform=ax.get_xaxis_transform(), fontsize=7, color=INK2, ha="left", va="top")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(0.02, 7.0); ax.set_ylim(0.01, 30)
    ax.set_xticks([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5]); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}")); ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("budget as a multiple of the standard budget")
    ax.set_ylabel("mean gap to BKS of the incumbent (%)")
    save(fig, "fig_anytime")


if __name__ == "__main__":
    fig_gap_instances2(); fig_ttt2(); fig_anytime2()
