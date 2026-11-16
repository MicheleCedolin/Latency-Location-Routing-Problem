#!/usr/bin/env python3
"""Equal-CPU comparison: one long run versus several short independent runs whose routes are pooled and recombined.

short = the 1x archive (budget max(5, 0.3 n) s per run), long = the ext10 archive (3 n s per run); one long run costs as much CPU
as k = 10 short runs.  Per instance:
  long_mean   mean over the long runs of the final latency                                   (what one long run delivers)
  short_best  mean over random draws of the best of k short runs                              (restarts, no recombination)
  short_sp    mean over random draws of SP + exact DP over the pooled routes of k short runs  (restarts + shared pool)
The SP time (a few seconds) is not charged to the short runs.
Usage: restart_pool.py SHORT_ROOT LONG_ROOT [--k 10] [--draws 10] [--jobs 4] [--out DIR]
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llrp_pool as P
from pool_sp import Pool, solve_sp

CTX = {}


def process(name):
    a, M, bks, res, lit = (CTX[k] for k in ('a', 'M', 'bks', 'res', 'lit'))
    inst = P.load_instance(name, M)
    short = [r for r in res[a.short_alg][name].values() if r['feasible'] and r['routes']]
    long_ = [r for r in res[a.long_alg][name].values() if r['feasible']]
    if len(short) < a.k or not long_:
        return None
    rng = np.random.RandomState(2026)
    dp_cache, best, sps = {}, [], []
    for _ in range(a.draws):
        sub = [short[i] for i in rng.choice(len(short), a.k, replace=False)]
        pool = Pool(inst, 18, dp_cache)
        for r in sub:
            for d, s in r['routes']:
                pool.add(d, s)
        c, routes, st = solve_sp(inst, pool.columns(True), a.time_limit)
        best.append(min(r['cost'] for r in sub))
        sps.append(c if c is not None else min(r['cost'] for r in sub))
    g = lambda x: 100.0 * (x - bks[name]) / bks[name]
    row = dict(instance=name, n=inst['n'], cls=P.size_class(inst['n']), bks=bks[name], long_mean=np.mean([r['cost'] for r in long_]),
               long_best=min(r['cost'] for r in long_), short_best=float(np.mean(best)), short_sp=float(np.mean(sps)),
               zou_avg=lit.get(name, {}).get('avg', float('nan')))
    for k in ('long_mean', 'long_best', 'short_best', 'short_sp'):
        row['gap_' + k] = g(row[k])
    print(name, file=sys.stderr, flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('short_root')
    ap.add_argument('long_root')
    ap.add_argument('--short-alg', default='tuned')
    ap.add_argument('--long-alg', default='ext10')
    ap.add_argument('--k', type=int, default=10)
    ap.add_argument('--draws', type=int, default=10)
    ap.add_argument('--jobs', type=int, default=1)
    ap.add_argument('--time-limit', type=float, default=120.0)
    ap.add_argument('--instances', default='')
    ap.add_argument('--out', default='restart_out')
    a = ap.parse_args()
    res = P.load_results([a.short_root, a.long_root])
    global CTX
    CTX = dict(a=a, M=P.load_manifest(), bks=P.load_bks(), res=res, lit=P.load_literature())
    names = sorted(set(res[a.short_alg]) & set(res[a.long_alg]))
    if a.instances:
        names = [x for x in names if x in set(a.instances.split(','))]
    if a.jobs > 1:
        import multiprocessing as mp
        with mp.get_context('fork').Pool(a.jobs) as pl:
            rows = [r for r in pl.imap_unordered(process, names) if r]
    else:
        rows = [r for r in map(process, names) if r]
    rows.sort(key=lambda r: r['instance'])
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    keys = list(rows[0].keys())
    with open(out / 'restart_pool_instances.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    from scipy.stats import wilcoxon
    L = ['# Equal CPU: one long run (%s) vs %d pooled short runs (%s); %d draws; %d instances\n' % (a.long_alg, a.k, a.short_alg, a.draws, len(rows)),
         '| class | inst | long run mean gap % | short best-of-k gap % | short SP+DP gap % | SP < long | long best-of-30 gap % |\n|---|---|---|---|---|---|---|']
    for cl in P.CLASSES + [None]:
        rr = [r for r in rows if cl is None or r['cls'] == cl]
        if not rr:
            continue
        m = lambda k: np.mean([r[k] for r in rr])
        L.append('| %s | %d | %.3f | %.3f | %.3f | %d/%d | %.3f |' % (cl or 'ALL', len(rr), m('gap_long_mean'), m('gap_short_best'), m('gap_short_sp'),
                                                                     sum(r['short_sp'] < r['long_mean'] for r in rr), len(rr), m('gap_long_best')))
    d = [r['long_mean'] - r['short_sp'] for r in rows]
    if len(d) > 5 and any(x != 0 for x in d):
        L.append('\nWilcoxon (long mean vs SP+DP of %d short runs, paired by instance): p = %.2e; median difference in latency %.3f' %
                 (a.k, wilcoxon(d).pvalue, float(np.median(d))))
    z = [r for r in rows if r['zou_avg'] == r['zou_avg']]
    L.append('\nInstances whose mean is at most the published average of RLHEA: long run %d, SP of short runs %d (of %d).' % (
        sum(r['long_mean'] <= r['zou_avg'] + 0.005 for r in z), sum(r['short_sp'] <= r['zou_avg'] + 0.005 for r in z), len(z)))
    (out / 'restart_pool_summary.md').write_text('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
