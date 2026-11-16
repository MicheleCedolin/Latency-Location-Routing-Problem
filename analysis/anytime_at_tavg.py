#!/usr/bin/env python3
"""Equal-time comparison with the published RLHEA (Zou et al. 2024) from the anytime traces, and time-to-target.

For every result group (the `Algorithm` column) and instance: the best latency of every run at  f * T_RLHEA  CPU seconds
(T_RLHEA = published mean run time of RLHEA, bks/literature_results.csv), for f in --factors, and the first time a run reaches
the published RLHEA average (+0.005) -- the "time to target".  Runs whose CPU limit is shorter than f * T_RLHEA are not extrapolated;
an instance counts for a factor only if >= 90 % of its runs reach that time.
The times are measured on different machines (see bks/README.md): the factors f show how the picture moves if the hardware
difference is larger or smaller than 1; they are not a hardware normalisation.

  python3 analysis/anytime_at_tavg.py TREE [TREE ...] --out analysis_out
"""
import argparse
import bisect
import csv
import os
import statistics

import numpy as np

import llrp_pool as L


def at(times, costs, t):
    i = bisect.bisect_right(times, t) - 1
    return costs[i] if i >= 0 else None


def first_hit(times, costs, target):
    for t, c in zip(times, costs):
        if c <= target:
            return t
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('trees', nargs='+')
    ap.add_argument('--out', default='analysis_out')
    ap.add_argument('--factors', default='0.5,1,1.2,1.5,2')
    ap.add_argument('--algo', default='RLHEA', help='published algorithm used as the reference')
    a = ap.parse_args()
    F = [float(x) for x in a.factors.split(',')]
    manifest, bks, lit = L.load_manifest(), L.load_bks(), L.load_literature(a.algo)
    res = L.load_results(a.trees)

    rows = []
    for label in sorted(res):
        for name, runs in sorted(res[label].items()):
            feas = [r for r in runs.values() if r['feasible'] and r['trace']]
            if not feas or name not in lit or not (lit[name]['time'] > 0):
                continue
            b, p, n = bks[name], lit[name], int(manifest[name]['n'])
            row = dict(group=label, instance=name, family=manifest[name]['family'], n=n, runs=len(feas), T_pub=p['time'],
                       pub_gap_avg=L.gap(p['avg'], b), pub_gap_best=L.gap(p['best'], b), budget=statistics.median(r['cpu'] for r in feas),
                       mean_gap_end=np.mean([L.gap(r['cost'], b) for r in feas]), best_gap_end=L.gap(min(r['cost'] for r in feas), b))
            tr = [([t for t, _ in sorted(r['trace'])], [c for _, c in sorted(r['trace'])]) for r in feas]
            for f in F:
                v = [at(ts, cs, f * p['time']) for (ts, cs), r in zip(tr, feas) if r['cpu'] >= f * p['time']]
                v = [x for x in v if x is not None]
                ok = len(v) >= 0.9 * len(feas)
                row['mean_gap_%g' % f] = float(np.mean([L.gap(x, b) for x in v])) if ok else None
                row['best_gap_%g' % f] = L.gap(min(v), b) if ok else None
            hits = [first_hit(ts, cs, p['avg'] + L.TOL) for ts, cs in tr]
            hit_t = [h / p['time'] for h in hits if h is not None]
            row['ttt_runs'] = len(hit_t)
            row['ttt_median_ratio'] = statistics.median(hit_t) if hit_t else None
            row['_ratios'] = hit_t
            rows.append(row)

    os.makedirs(a.out, exist_ok=True)
    keys = ['group', 'instance', 'family', 'n', 'runs', 'T_pub', 'budget', 'pub_gap_avg', 'pub_gap_best', 'mean_gap_end', 'best_gap_end'] + \
           ['%s_gap_%g' % (k, f) for f in F for k in ('mean', 'best')] + ['ttt_runs', 'ttt_median_ratio']
    with open(os.path.join(a.out, 'anytime_at_tavg_instances.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, keys, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)

    out = ['# Equal-time comparison with %s and time to target' % a.algo, '',
           'Time reference = published mean run time of %s (other machine, other stopping rule; see bks/README.md). '
           'Gap = 100 (x - BKS) / BKS. `mean` = mean over instances of the per-instance 30-run mean; `best` = of the best of the runs; '
           '`pub` = the same quantity of %s on the same instances. Only instances where >= 90 %% of the runs reach f * T.' % (a.algo, a.algo), '']
    for g in sorted({r['group'] for r in rows}):
        R = [r for r in rows if r['group'] == g]
        out += ['## Group `%s`' % g, '',
                '| f | instances | mean gap (ours) | mean gap (pub) | best gap (ours) | best gap (pub) | # mean <= pub avg | # best <= pub best |',
                '|---|---|---|---|---|---|---|---|']
        for f in F:
            S = [r for r in R if r['mean_gap_%g' % f] is not None]
            if not S:
                out.append('| %g | 0 | - | - | - | - | - | - |' % f)
                continue
            out.append('| %g | %d | %.3f | %.3f | %.3f | %.3f | %d | %d |' % (
                f, len(S), np.mean([r['mean_gap_%g' % f] for r in S]), np.mean([r['pub_gap_avg'] for r in S]),
                np.mean([r['best_gap_%g' % f] for r in S]), np.mean([r['pub_gap_best'] for r in S]),
                sum(r['mean_gap_%g' % f] <= r['pub_gap_avg'] + 1e-9 + 100 * L.TOL / bks[r['instance']] for r in S),
                sum(r['best_gap_%g' % f] <= r['pub_gap_best'] + 100 * L.TOL / bks[r['instance']] for r in S)))
        out += ['', 'f = 1 by size class:', '', '| n class | # | mean gap (ours) | mean gap (pub) | best gap (ours) | # mean <= pub avg |', '|---|---|---|---|---|---|']
        for cl in L.CLASSES:
            S = [r for r in R if r['mean_gap_1'] is not None and L.size_class(r['n']) == cl] if 1.0 in F else []
            if S:
                out.append('| %s | %d | %.3f | %.3f | %.3f | %d |' % (
                    cl, len(S), np.mean([r['mean_gap_1'] for r in S]), np.mean([r['pub_gap_avg'] for r in S]),
                    np.mean([r['best_gap_1'] for r in S]),
                    sum(r['mean_gap_1'] <= r['pub_gap_avg'] + 100 * L.TOL / bks[r['instance']] for r in S)))
        h = [r for r in R if r['ttt_runs'] is not None]
        med = [r['ttt_median_ratio'] for r in h if r['ttt_median_ratio'] is not None]
        pooled = [x for r in h for x in r['_ratios']]
        out += ['', 'Time to the published average (+%.3f): >= 1 run reaches it on %d of %d instances, >= half of the runs on %d; '
                'median hit time / T_pub: %s over all reaching runs, %s over the instance medians.' % (
                    L.TOL, sum(r['ttt_runs'] >= 1 for r in h), len(h), sum(r['ttt_runs'] >= r['runs'] / 2 for r in h),
                    '%.2f' % statistics.median(pooled) if pooled else '-', '%.2f' % statistics.median(med) if med else '-'), '']
    with open(os.path.join(a.out, 'anytime_at_tavg_summary.md'), 'w') as fh:
        fh.write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
