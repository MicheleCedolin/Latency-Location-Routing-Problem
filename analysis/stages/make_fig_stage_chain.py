#!/usr/bin/env python3
"""Stage chain by instance size: mean gap to the best-known value of every stage of the method and of RLHEA (Supporting Information, stage-chain figure).

  python3 -I analysis/stages/make_fig_stage_chain.py [--stages CSV] [--memetic CSV] [--out DIR]

Inputs (defaults: the reference output that CI regenerates from the archives)
  analysis/stages/reference/stages_instances.csv   from analyze_stages.py   : gap_ext10, gap_V1, gap_B1 and zou_avg per instance (57 instances, n > 75)
  analysis/memetic/reference/y_instances.csv       from analyze_y.py        : mean_new = mean gap of the exploratory memetic phase per instance

Bars: base method (stage 2, extended budget 3n s) -> + depot-aware diversification (stage 3) -> + route pool = final method (stage 4) -> + memetic phase (stage 5, exploratory),
and the published average of RLHEA (Zou et al. 2024; hardware not normalised).  Gap = mean over the 30 runs of the gap in % to the BKS of cpp/manifest.tsv; class value = mean over the instances of the class.

Writes  DIR/fig_stage_chain.pdf, DIR/fig_stage_chain.png  and  DIR/stage_chain_classes.csv  (the plotted numbers; CI compares it with analysis/stages/reference/stage_chain_classes.csv).
The figure is not byte-checked (matplotlib versions differ in the last pixel); the CSV is.
"""
import argparse, csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CLASSES = [("n=100", lambda n: n == 100), ("n=117/134", lambda n: n in (117, 134)), ("n=150", lambda n: n == 150), ("n=200", lambda n: n == 200), ("all", lambda n: True)]
SERIES = [("base", "Base method"), ("depot", "+ Depot-aware diversification"), ("pool", "+ Route pool (final method)"),
          ("memetic", "+ Memetic phase (exploratory)"), ("rlhea", "RLHEA (published)")]


def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def class_table(stages, memetic):
    mem = {r["inst"]: float(r["mean_new"]) for r in memetic}
    rows = []
    for r in stages:
        n, bks = int(r["n"]), float(r["bks"])
        if r["instance"] not in mem:
            sys.exit("instance %s of the stage table is missing in the memetic table" % r["instance"])
        rows.append(dict(n=n, base=float(r["gap_ext10"]), depot=float(r["gap_V1"]), pool=float(r["gap_B1"]), memetic=mem[r["instance"]],
                         rlhea=(float(r["zou_avg"]) - bks) / bks * 100.0))
    if len(rows) != len(mem):
        sys.exit("stage table has %d instances, memetic table %d" % (len(rows), len(mem)))
    out = []
    for name, sel in CLASSES:
        sub = [r for r in rows if sel(r["n"])]
        out.append(dict(cls=name, instances=len(sub), **{k: sum(r[k] for r in sub) / len(sub) for k, _ in SERIES}))
    return out


def f3(x):
    """three decimals, never a negative zero"""
    s = "%.3f" % x
    return "0.000" if s == "-0.000" else s


def write_csv(path, table):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["class", "instances"] + [k for k, _ in SERIES])
        for r in table:
            w.writerow([r["cls"], r["instances"]] + [f3(r[k]) for k, _ in SERIES])


def draw(table, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, muted = "#222222", "#8a8a85"
    cols = ["#b9b8b2", "#7fa6c9", "#1f5f99", "#d98f2b", "#2b2b2b"]
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    k, w = len(SERIES), 0.16
    for j, (key, label) in enumerate(SERIES):
        xs = [i + (j - (k - 1) / 2) * w for i in range(len(table))]
        vals = [r[key] for r in table]
        ax.bar(xs, vals, width=w * 0.92, color=cols[j], label=label, edgecolor="white", linewidth=0.4, zorder=3,
               hatch="//" if key == "memetic" else None)
        for x, v in zip(xs, vals):
            ax.text(x, max(v, 0) + 0.02, f3(v) if abs(v) >= 0.0005 else "0", ha="center", va="bottom", fontsize=5.6, color=ink, rotation=90)
    ax.set_xticks(range(len(table)))
    ax.set_xticklabels(["%s\n(%d)" % (r["cls"], r["instances"]) for r in table], fontsize=8)
    ax.set_ylabel("mean gap to BKS (%)", fontsize=8.5)
    ax.set_ylim(0, max(r[key] for r in table for key, _ in SERIES) * 1.18)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", color="#e4e3df", lw=0.5, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper left", fontsize=7, frameon=False, handlelength=1.2)
    fig.tight_layout()
    os.makedirs(out, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, "fig_stage_chain." + ext), dpi=200)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stages", default=os.path.join(ROOT, "analysis", "stages", "reference", "stages_instances.csv"))
    ap.add_argument("--memetic", default=os.path.join(ROOT, "analysis", "memetic", "reference", "y_instances.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "analysis", "stages", "out"))
    ap.add_argument("--no-figure", action="store_true", help="write the CSV only (no matplotlib needed)")
    a = ap.parse_args()
    table = class_table(read_csv(a.stages), read_csv(a.memetic))
    os.makedirs(a.out, exist_ok=True)
    write_csv(os.path.join(a.out, "stage_chain_classes.csv"), table)
    if not a.no_figure:
        draw(table, a.out)
    print("class".ljust(10), "inst", *[k.rjust(8) for k, _ in SERIES])
    for r in table:
        print(r["cls"].ljust(10), str(r["instances"]).rjust(4), *[f3(r[k]).rjust(8) for k, _ in SERIES])


if __name__ == "__main__":
    main()
