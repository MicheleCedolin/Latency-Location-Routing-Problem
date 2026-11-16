#!/usr/bin/env python3
"""Figures of the GRASP-RVND paper (vector PDF + 300 dpi PNG) that do not depend on the extended budget: fig_effort, fig_ops, fig_irace_ops.
The three result figures (fig_gap_instances, fig_ttt, fig_anytime) are drawn by figs_ext.py, which uses the standard and the extended budget.
Reads <out>/data/*.csv (written by prep.py).  usage: figs.py [effort] [ops] [irace] [--out DIR] [--irace DIR]
Palette: validated with the dataviz validate_palette.js (3 categorical slots all-pairs; 4-step ordinal blue ramp).
Every encoding is redundant (marker shape / line style / direct label) so that the figures survive grayscale printing."""
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paperlib import dirs, make_parser
_p = make_parser(__doc__.split("\n")[0], need_base=False)
_p.add_argument("which", nargs="*", help="figures to draw: effort ops irace (default: all three)")
_p.add_argument("--irace", default="/tmp/irace", help="extracted irace_logs.tar.gz (directory with irace/irace_stdout.txt); only for the figure `irace`")
_a = _p.parse_args()
_d = dirs(_a.out); D = str(_d["data"]); F = str(_d["figs"])

plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 8, "axes.labelsize": 8.5,
    "axes.titlesize": 8.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 3, "ytick.major.size": 3,
    "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 150, "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.5, "axes.axisbelow": True,
    "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b", "text.color": "#0b0b0b", "xtick.color": "#52514e", "ytick.color": "#52514e",
})
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8a8985"
FAM = {"prins": ("#2a78d6", "o", "Prins"), "barreto": ("#eb6834", "s", "Barreto"), "tuzun": ("#1baf7a", "^", "Tuzun")}
CLS = [("n<=50", "#86b6ef", "o", "-", r"$n\leq 50$"), ("75-134", "#3987e5", "s", "--", r"$75\leq n\leq 134$"),
       ("150", "#1c5cab", "^", "-.", r"$n=150$"), ("200", "#0d366b", "D", ":", r"$n=200$")]
OPS = ["relocate", "oropt2", "swap11", "swap21", "2opt*", "swapstar", "dexch", "rdepot", "ds"]
OPLAB = {"relocate": "relocate", "oropt2": "oropt2", "swap11": "swap11", "swap21": "swap21", "2opt*": "2opt*", "swapstar": "swapstar",
         "dexch": "dexch", "rdepot": "rdepot", "ds": "ds"}


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(F, f"{name}.{ext}"), bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    print("wrote", name)


def panel_label(ax, s):
    ax.text(-0.02, 1.04, s, transform=ax.transAxes, fontsize=9, fontweight="bold", va="bottom", ha="right")


I = pd.read_csv(os.path.join(D, "inst.csv"), index_col=0)


# --------------------------------------------------------------------------------------------------------------------------
def fig_effort():
    """(a) CPU-time budgets against the average run time of Zou et al.; (b) GRASP iterations that fit into the standard budget."""
    fig, axs = plt.subplots(1, 2, figsize=(6.4, 2.75), gridspec_kw={"wspace": 0.30})
    ax = axs[0]
    nn = np.linspace(15, 215, 300)
    ax.plot(nn, np.maximum(5, 0.3 * nn), color=INK, lw=1.4, label="")
    ax.plot(nn[nn >= 70], 3 * nn[nn >= 70], color=INK, lw=1.4, ls="--")
    for fam, (c, m, lab) in FAM.items():
        d = I[I.family == fam]
        ax.scatter(d.n, d.zou_tavg, s=16, marker=m, facecolor="none", edgecolor=c, linewidth=0.9, label=lab, zorder=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(15, 260); ax.set_ylim(2, 1200)
    ax.set_xticks([20, 30, 50, 75, 100, 150, 200]); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel(r"customers $n$"); ax.set_ylabel("CPU time per run (s)")
    ax.text(40, 3.6, r"standard budget $\max\{5,0.3n\}$", color=INK, fontsize=7.5, rotation=27, ha="left", va="center", rotation_mode="anchor")
    ax.text(108, 430, r"extended budget $3n$", color=INK, fontsize=7.5, rotation=34, ha="center", va="center", rotation_mode="anchor")
    handles = [Line2D([], [], marker=m, mfc="none", mec=c, ls="", ms=5, label=lab) for _, (c, m, lab) in FAM.items()]
    lg = ax.legend(handles=handles, loc="upper left", frameon=False, handletextpad=0.2, borderaxespad=0.1,
                   title=r"$T_{\mathrm{avg}}$ of RLHEA (Zou et al.)", alignment="left")
    lg.get_title().set_fontsize(7.5)
    panel_label(ax, "(a)")
    ax = axs[1]
    for fam, (c, m, lab) in FAM.items():
        d = I[I.family == fam]
        ax.scatter(d.n, d.iters, s=16, marker=m, facecolor="none", edgecolor=c, linewidth=0.9, zorder=3)
    med = I.groupby("n")["iters"].median()
    ax.plot(med.index, med.values, color=INK, lw=0.9, zorder=2)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([20, 30, 50, 75, 100, 150, 200]); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}")); ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel(r"customers $n$"); ax.set_ylabel("GRASP iterations per run")
    ax.set_xlim(15, 260)
    ax.text(30, 3.0e1, "median over\ninstances of the\nsame size", color=INK, fontsize=7.5, ha="left", va="center")
    panel_label(ax, "(b)")
    save(fig, "fig_effort")


# --------------------------------------------------------------------------------------------------------------------------
def fig_ops():
    B = pd.read_csv(os.path.join(D, "ops_by_class.csv"), index_col=[0, 1])
    a = B.loc["all"].loc[OPS]
    cpu = 100 * a["CPU Seconds"] / a["CPU Seconds"].sum()
    app = 100 * a["Applied"] / a["Applied"].sum()
    hit = 100 * a["Applied"] / a["Calls"]
    order = list(cpu.sort_values(ascending=True).index)
    y = np.arange(len(order))
    fig, axs = plt.subplots(1, 2, figsize=(6.2, 2.9), gridspec_kw={"width_ratios": [1.5, 1], "wspace": 0.08}, sharey=True)
    ax = axs[0]
    hgt = 0.36
    ax.barh(y + hgt / 2, cpu[order], height=hgt, color="#3987e5", label="CPU time")
    ax.barh(y - hgt / 2, app[order], height=hgt, color="#ffffff", edgecolor="#3987e5", hatch="////", linewidth=0.8, label="applied moves")
    for i, o in enumerate(order):
        ax.text(cpu[o] + 0.6, i + hgt / 2, f"{cpu[o]:.1f}", va="center", fontsize=6.8, color=INK2)
        ax.text(app[o] + 0.6, i - hgt / 2, f"{app[o]:.1f}", va="center", fontsize=6.8, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels([r"\texttt{x}".replace("x", OPLAB[o]) if False else OPLAB[o] for o in order], family="monospace", fontsize=7.2)
    ax.set_xlabel("share of the total over all runs (%)"); ax.set_xlim(0, 44)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, handlelength=1.4, borderaxespad=0.2)
    panel_label(ax, "(a)")
    ax = axs[1]
    ax.hlines(y, 0, hit[order], color="#c9c8c3", lw=0.9)
    isdep = [o in ("dexch", "rdepot", "ds") for o in order]
    ax.scatter(hit[order], y, s=24, marker="o", color=["#eb6834" if d else "#2a78d6" for d in isdep], zorder=3)
    for i, o in enumerate(order):
        ax.text(hit[o] + 4.5, i, f"{hit[o]:.1f}", va="center", fontsize=6.8, color=INK2)
    ax.set_xlim(0, 110); ax.set_xlabel("calls that apply a move (%)")
    ax.grid(axis="y", visible=False)
    h = [Line2D([], [], marker="o", color="#2a78d6", ls="", ms=4.5, label="route-level"), Line2D([], [], marker="o", color="#eb6834", ls="", ms=4.5, label="depot-level")]
    ax.legend(handles=h, loc="lower right", frameon=False, handletextpad=0.1, borderaxespad=0.2)
    panel_label(ax, "(b)")
    save(fig, "fig_ops")


# --------------------------------------------------------------------------------------------------------------------------
def elite_counts(stdout):
    """Operator counts over the elite configurations after the last iteration of irace (the last block of 6 elites in irace_stdout.txt)."""
    import re
    L = open(stdout).read().split("\n")
    blocks, i = [], 0
    while i < len(L):
        if "Elite configurations" in L[i]:
            hdr, rows, j = L[i + 1].split(), [], i + 2
            while j < len(L) and re.match(r"^\d+\s", L[j]):
                rows.append(L[j].split()); j += 1
            blocks.append((hdr, rows)); i = j
        else:
            i += 1
    top = max(len(r) for _, r in blocks)
    hdr, rows = [b for b in blocks if len(b[1]) == top][-1]
    return {h[3:].replace("2optstar", "2opt*"): sum(int(r[1 + hdr.index(h)]) for r in rows) for h in hdr if h.startswith("op_")}, top


def fig_irace_ops():
    log = os.path.join(_a.irace, "irace", "irace_stdout.txt")
    if not os.path.exists(log):
        print("skip irace figure: %s not found (extract study_results/irace_logs.tar.gz and pass --irace DIR)" % log)
        return
    cnt, nelite = elite_counts(log)
    tuned = {"relocate", "oropt2", "swap11", "swap21", "2opt*", "swapstar", "dexch", "rdepot", "ds"}
    depot = {"dexch", "rdepot", "ds"}
    names = sorted(cnt, key=lambda k: (-cnt[k], k))
    y = np.arange(len(names))[::-1]
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    for yi, o in zip(y, names):
        col = "#eb6834" if o in depot else "#2a78d6"
        ax.barh(yi, cnt[o], height=0.62, color=col if o in tuned else "white", edgecolor=col, linewidth=1.0, hatch="" if o in tuned else "////")
        ax.text(cnt[o] + 0.1, yi, str(cnt[o]), va="center", fontsize=7.2, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels(names, family="monospace", fontsize=7.2)
    ax.set_xlim(0, nelite + 0.8); ax.set_xticks(range(0, nelite + 1)); ax.set_xlabel("elite configurations containing the operator (out of %d)" % nelite)
    ax.grid(axis="y", visible=False)
    h = [matplotlib.patches.Patch(facecolor="#2a78d6", edgecolor="#2a78d6", label="route-level, in tuned pool"),
         matplotlib.patches.Patch(facecolor="#eb6834", edgecolor="#eb6834", label="depot-level, in tuned pool"),
         matplotlib.patches.Patch(facecolor="white", edgecolor="#2a78d6", hatch="////", label="not in tuned pool")]
    ax.legend(handles=h, loc="lower right", frameon=False, fontsize=7, handlelength=1.4)
    save(fig, "fig_irace_ops")


if __name__ == "__main__":
    fn = {"effort": fig_effort, "ops": fig_ops, "irace": fig_irace_ops}
    for w in _a.which or list(fn):
        fn[w]()
