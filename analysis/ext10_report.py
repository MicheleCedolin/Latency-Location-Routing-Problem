#!/usr/bin/env python3
"""Base (1x) versus extended budget ("ext10") analysis and the paired comparison with RLHEA (standard library only).

Inputs (the archives of study_results/ unpacked, e.g. `tar xzf study_results/final_1x_tuned.tar.gz -C /tmp`):
  --base DIR  results_final       with <family>/<tag>/{run,trace}.csv   (tag: --base-tag, default tuned)
  --ext  DIR  results_extended10  with <family>/<tag>/{run,trace}.csv   (tag: --ext-tag,  default ext10)
Reference data: bks/LLRP_BKS.csv (best-known values), bks/literature_results.csv (published RLHEA), cpp/selection/test.txt (held-out set).

What it reports
  1. Budget: iterations of the extended run relative to the 1x run of the same seed (CPU-time budget 10x; the extended runs
     were made on a node whose CPU time per iteration is higher, so the effective budget in iterations is lower than 10x).
  2. Continuation check: the extended run with a given seed repeats the 1x run up to its last iteration; the best-so-far of the
     extended trace at the iteration where the 1x run stopped must equal the 1x result.
  3. Base versus extended per family: runs / instances at the BKS, mean gap of the best run and of the mean, share of runs at the BKS.
  4. Anytime behaviour in ITERATION space (machine independent): mean gap after f x the iterations of the 1x run, f = 0.25 ... 10,
     from the extended traces; a column uses only the instances for which every run has reached that many iterations.
  5. Paired comparison with RLHEA (published best and average, other hardware): win / tie / loss per instance (tie: difference
     <= 0.005, the values have two decimals) and the Wilcoxon signed-rank test over instances after dropping ties. Both the exact
     p-value (distribution of the signed rank sum, valid with tied ranks) and the normal approximation (tie-corrected, no continuity
     correction) are printed.

Examples
  python3 analysis/ext10_report.py --base /tmp/results_final --ext /tmp/results_extended10
  python3 analysis/ext10_report.py --base /tmp/results_final --ext /tmp/results_extended10 --heldout     # held-out instances only
  python3 analysis/ext10_report.py --base ... --ext ... --out-dir report/                                    # also writes CSV files
"""
import argparse
import bisect
import csv
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAMILIES = ('barreto', 'prins', 'tuzun')
TOL = 0.005
FRACS = (0.25, 0.5, 1, 2, 3, 4, 5, 6, 8, 10)


# ---------------------------------------------------------------------------------------------------------------- input
def load_runs(root, tag):
    runs = {}
    for fam in FAMILIES:
        p = os.path.join(root, fam, tag, 'run.csv')
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, newline='')):
            if r['Feasible'] != 'True':
                continue
            runs[(r['Instance'], int(r['Seed']))] = dict(lat=float(r['Total Latency']), iters=int(r['Iterations']),
                                                         cpu=float(r['CPU Time']))
    if not runs:
        sys.exit(f'no run.csv found under {root}/<family>/{tag}/')
    return runs


def load_traces(root, tag):
    tr = defaultdict(list)
    for fam in FAMILIES:
        p = os.path.join(root, fam, tag, 'trace.csv')
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, newline='')):
            tr[(r['Instance'], int(r['Seed']))].append((int(r['Iteration']), float(r['Best Latency'])))
    for v in tr.values():
        v.sort()
    return tr


def best_after(events, its, n_iters):
    """Best-so-far latency after n_iters completed iterations (step function of the improvement events; the iteration index of an
    event is 0-based, so the events with index <= n_iters - 1 count). None if no iteration has been completed."""
    k = bisect.bisect_right(its, n_iters - 1) - 1
    return events[k][1] if k >= 0 else None


# ----------------------------------------------------------------------------------------------------------- statistics
def wilcoxon(diffs):
    """Two-sided Wilcoxon signed-rank test of paired differences (zeros must be removed by the caller).

    Returns (n, W_plus, W_minus, p_exact, p_normal). p_exact enumerates the distribution of the signed rank sum with the mid-ranks of
    the data (conditional on the ties); p_normal uses the tie-corrected variance without continuity correction."""
    n = len(diffs)
    if n == 0:
        return 0, 0.0, 0.0, 1.0, 1.0
    order = sorted(range(n), key=lambda i: abs(diffs[i]))
    ranks = [0.0] * n
    i = 0
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(abs(diffs[order[j + 1]]) - abs(diffs[order[i]])) <= 1e-12:
            j += 1
        mid = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = mid
        t = j - i + 1
        tie_term += t ** 3 - t
        i = j + 1
    wp = sum(r for r, d in zip(ranks, diffs) if d > 0)
    wm = sum(r for r, d in zip(ranks, diffs) if d < 0)
    total = wp + wm
    w = min(wp, wm)
    # exact: number of sign patterns with rank sum <= w, ranks doubled to integers
    r2 = [int(round(2 * r)) for r in ranks]
    top = sum(r2)
    cnt = [0] * (top + 1)
    cnt[0] = 1
    for r in r2:
        for s in range(top, r - 1, -1):
            cnt[s] += cnt[s - r]
    p_exact = min(1.0, 2.0 * sum(cnt[: int(2 * w) + 1]) / 2.0 ** n)
    mean = total / 2
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_term / 48.0
    z = (w - mean) / math.sqrt(var) if var > 0 else 0.0
    p_norm = math.erfc(abs(z) / math.sqrt(2))
    return n, wp, wm, p_exact, p_norm


def fmt_p(p):
    return f'{p:.2e}' if p < 1e-3 else f'{p:.4f}'


# ------------------------------------------------------------------------------------------------------------- reporting
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', required=True)
    ap.add_argument('--ext', required=True)
    ap.add_argument('--base-tag', default='tuned')
    ap.add_argument('--ext-tag', default='ext10')
    ap.add_argument('--heldout', action='store_true', help='restrict to the held-out instances of cpp/selection/test.txt')
    ap.add_argument('--min-n', type=int, default=0, help='restrict to instances with at least this many customers')
    ap.add_argument('--out-dir', help='write ext10_instances.csv and ext10_anytime_iter.csv to this directory')
    a = ap.parse_args()

    reg = {r['instance']: r for r in csv.DictReader(open(os.path.join(ROOT, 'bks', 'LLRP_BKS.csv'), newline=''))}
    rl = {r['instance']: r for r in csv.DictReader(open(os.path.join(ROOT, 'bks', 'literature_results.csv'), newline=''))
          if r['algorithm'] == 'RLHEA'}
    held = None
    if a.heldout:
        held = {line.strip().split('/')[-1] for line in open(os.path.join(ROOT, 'cpp', 'selection', 'test.txt')) if line.strip()}

    base, ext = load_runs(a.base, a.base_tag), load_runs(a.ext, a.ext_tag)
    tr = load_traces(a.ext, a.ext_tag)
    seeds = defaultdict(set)
    for (k, s) in ext:
        if (k, s) in base:
            seeds[k].add(s)
    inst = [k for k in reg if k in seeds and int(reg[k]['n']) >= a.min_n and (held is None or k in held)]
    if not inst:
        sys.exit('no instance is present in both result sets (after the filters)')
    bks = {k: float(reg[k]['bks']) for k in inst}
    gap = lambda x, k: 100.0 * (x - bks[k]) / bks[k]
    fam_of = {k: reg[k]['family'] for k in inst}
    groups = [(f, [k for k in inst if fam_of[k] == f]) for f in FAMILIES]
    groups = [(f, ks) for f, ks in groups if ks] + [('ALL', inst)]
    npairs = sum(len(seeds[k]) for k in inst)
    print(f'{len(inst)} instances, {npairs} (instance, seed) pairs; base = {a.base_tag}, extended = {a.ext_tag}')

    # 1. budget ---------------------------------------------------------------------------------------------------------
    cpu_ratio = [ext[(k, s)]['cpu'] / base[(k, s)]['cpu'] for k in inst for s in seeds[k]]
    it_ratio = [ext[(k, s)]['iters'] / base[(k, s)]['iters'] for k in inst for s in seeds[k]]
    qs = statistics.quantiles(it_ratio, n=20)
    print('\n1. Budget of the extended runs relative to the 1x run of the same seed')
    print(f'   CPU time ratio:   median {statistics.median(cpu_ratio):.2f}')
    print(f'   iteration ratio:  median {statistics.median(it_ratio):.2f}  (5 % - 95 %: {qs[0]:.2f} - {qs[-1]:.2f}, min {min(it_ratio):.2f}, max {max(it_ratio):.2f})')

    # 2. continuation ---------------------------------------------------------------------------------------------------
    bad = []
    missing = 0
    for k in inst:
        for s in seeds[k]:
            ev = tr.get((k, s))
            if not ev:
                missing += 1
                continue
            v = best_after(ev, [e[0] for e in ev], base[(k, s)]['iters'])
            if v is None or abs(v - base[(k, s)]['lat']) > 1e-6 * max(1.0, abs(v)):
                bad.append((k, s, v, base[(k, s)]['lat']))
    print('\n2. Continuation check (extended trace at the iteration where the 1x run stopped == 1x result)')
    print(f'   {npairs - len(bad) - missing}/{npairs} pairs agree; {len(bad)} differ; {missing} without trace')
    for k, s, v, b in bad[:5]:
        print(f'     {k} seed {s}: trace {v} vs 1x {b}')
    print('   (same seed, same binary and flags: the extended run is the continuation of the 1x run; only the CPU-time limit differs.)')

    # 3. base vs extended -----------------------------------------------------------------------------------------------
    def block(runs, ks):
        bestgap = [gap(min(runs[(k, s)]['lat'] for s in seeds[k]), k) for k in ks]
        meangap = [statistics.fmean(gap(runs[(k, s)]['lat'], k) for s in seeds[k]) for k in ks]
        hit_inst = sum(1 for k in ks if min(runs[(k, s)]['lat'] for s in seeds[k]) <= bks[k] + TOL)
        hit_run = [runs[(k, s)]['lat'] <= bks[k] + TOL for k in ks for s in seeds[k]]
        return statistics.fmean(bestgap), statistics.fmean(meangap), hit_inst, 100.0 * sum(hit_run) / len(hit_run)

    print('\n3. Base versus extended budget (gap in % to the BKS; "new BKS" would be best < BKS - 0.01)')
    print('   group     n | at BKS (best run)   | gap best run %      | gap mean %          | runs at BKS %')
    print('                 |  base    ext        |  base     ext       |  base     ext       |  base    ext')
    rows = []
    for f, ks in groups:
        b, e = block(base, ks), block(ext, ks)
        print(f'   {f:8s} {len(ks):3d} | {b[2]:3d}/{len(ks):<3d} {e[2]:3d}/{len(ks):<3d}   | {b[0]:7.3f} {e[0]:7.3f}     | {b[1]:7.3f} {e[1]:7.3f}     | {b[3]:6.1f} {e[3]:6.1f}')
    new_bks = [k for k in inst if min(ext[(k, s)]['lat'] for s in seeds[k]) < bks[k] - 0.01]
    print(f'   instances where the extended best beats the registry BKS by more than 0.01: {len(new_bks)} {new_bks[:6]}')
    for k in inst:
        bl = min(base[(k, s)]['lat'] for s in seeds[k])
        el = min(ext[(k, s)]['lat'] for s in seeds[k])
        rows.append(dict(instance=k, family=fam_of[k], n=reg[k]['n'], bks=bks[k], runs=len(seeds[k]),
                         base_best=bl, base_gap_best=gap(bl, k),
                         base_gap_mean=statistics.fmean(gap(base[(k, s)]['lat'], k) for s in seeds[k]),
                         ext_best=el, ext_gap_best=gap(el, k),
                         ext_gap_mean=statistics.fmean(gap(ext[(k, s)]['lat'], k) for s in seeds[k]),
                         iter_ratio_median=statistics.median(ext[(k, s)]['iters'] / base[(k, s)]['iters'] for s in seeds[k])))

    # 4. anytime in iteration space -------------------------------------------------------------------------------------
    print('\n4. Anytime behaviour in iteration space: mean gap (%) after f x the iterations of the 1x run (extended traces)')
    print('   f      instances   mean gap   (instances where every run reached f x its 1x iterations)')
    any_rows = []
    evs = {key: (v, [e[0] for e in v]) for key, v in tr.items()}
    for f in FRACS:
        per = []
        for k in inst:
            vals = []
            for s in seeds[k]:
                ev = evs.get((k, s))
                if ev is None:
                    vals = None
                    break
                t = int(math.floor(f * base[(k, s)]['iters']))
                if t > ext[(k, s)]['iters']:
                    vals = None
                    break
                v = best_after(ev[0], ev[1], t)
                if v is None:
                    vals = None
                    break
                vals.append(gap(v, k))
            if vals:
                per.append((k, statistics.fmean(vals)))
        if per:
            print(f'   {f:5g}  {len(per):9d}   {statistics.fmean(g for _, g in per):8.3f}')
            for k, g in per:
                any_rows.append(dict(f=f, instance=k, mean_gap=g))

    # 5. comparison with RLHEA ------------------------------------------------------------------------------------------
    print('\n5. Paired comparison with the published RLHEA (other hardware and run counts; differences <= 0.005 are ties)')
    for label, ours, key in (('best of the runs vs RLHEA best', lambda k: min(ext[(k, s)]['lat'] for s in seeds[k]), 'best'),
                             ('mean of the runs vs RLHEA avg ', lambda k: statistics.fmean(ext[(k, s)]['lat'] for s in seeds[k]), 'avg')):
        d = []
        for k in inst:
            r = rl.get(k)
            if r and r[key]:
                d.append(ours(k) - float(r[key]))
        nonzero = [x for x in d if abs(x) > TOL]
        w, t, l = sum(x < -TOL for x in d), sum(abs(x) <= TOL for x in d), sum(x > TOL for x in d)
        n, wp, wm, pe, pn = wilcoxon(nonzero)
        print(f'   {label}: {len(d)} instances, win/tie/loss {w}/{t}/{l}; Wilcoxon on {n} non-tied: W+ = {wp:g}, W- = {wm:g}, '
              f'p exact = {fmt_p(pe)}, p normal approx. = {fmt_p(pn)}')
    print('   (ours = extended budget; a win is a lower latency than RLHEA.)')

    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        for name, rr in (('ext10_instances.csv', rows), ('ext10_anytime_iter.csv', any_rows)):
            with open(os.path.join(a.out_dir, name), 'w', newline='') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rr[0].keys()), lineterminator='\n')
                w.writeheader()
                w.writerows(rr)
        print(f'\nCSV files written to {a.out_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
