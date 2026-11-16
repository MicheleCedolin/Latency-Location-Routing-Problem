#!/usr/bin/env python3
"""Edge-neighbourhood-rank analysis of route solutions (Zou et al. published vs. ours).

For every consecutive customer pair (i -> j) of a route we compute
  * the length d(i, j) and its percentile in the instance's customer-customer distance distribution,
  * the directed neighbour rank r_i(j)  (1 = nearest customer of i),
  * the "either" rank   min(r_i(j), r_j(i))   -> smallest delta for which the pair is in a granular
    neighbourhood if EITHER endpoint lists the other (Toth & Vigo style),
  * the "both" rank     max(r_i(j), r_j(i))   -> smallest delta if BOTH endpoints must list each other.
Depot edges (depot -> first customer) are reported separately: rank of the first customer among all
customers ordered by distance from that depot.

delta*(solution) = max "either" rank over its customer edges = the smallest granularity that still
contains the whole solution.

Usage: edge_granularity.py --published DIR --ours ROOT [ROOT ...] [--out DIR]
"""
import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llrp_pool as P

DELTAS = [5, 10, 15, 20, 25, 30, 40]
EXCLUDE = {'Or117-14', 'P112222-20', 'P122122-20', 'P131122-20'}   # defective published files (see bks/README)


def geometry(inst):
    xy = inst['xy']
    D = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
    n = len(xy)
    big = D + np.eye(n) * 1e18
    order = np.argsort(big, axis=1, kind='stable')[:, :n - 1]          # neighbours of i, nearest first
    rank = np.zeros((n, n), dtype=np.int32)                           # rank[i, j] = position of j in i's list (1-based)
    for i in range(n):
        rank[i, order[i]] = np.arange(1, n)
    return D, rank


def depot_rank(inst):
    dd = np.hypot(inst['xy'][None, :, 0] - inst['dep'][:, None, 0], inst['xy'][None, :, 1] - inst['dep'][:, None, 1])
    rk = np.zeros_like(dd, dtype=np.int32)
    for d in range(dd.shape[0]):
        rk[d, np.argsort(dd[d], kind='stable')] = np.arange(1, dd.shape[1] + 1)
    return dd, rk


def solution_edges(inst, routes, geo, dgeo):
    D, rank = geo
    dd, drk = dgeo
    E = []     # (len, pct_len, r_dir, r_either, r_both, weight) ; weight = customers after the edge (latency weight)
    DE = []    # (len, rank) of depot edges
    allD = D[np.triu_indices(len(D), 1)]
    allD.sort()
    for dep, seq in routes:
        if not seq:
            continue
        DE.append((dd[dep, seq[0]], int(drk[dep, seq[0]])))
        k = len(seq)
        for t in range(k - 1):
            i, j = seq[t], seq[t + 1]
            ri, rj = int(rank[i, j]), int(rank[j, i])
            pct = np.searchsorted(allD, D[i, j]) / len(allD)
            E.append((D[i, j], pct, ri, min(ri, rj), max(ri, rj), k - 1 - t))
    return E, DE


def summarize(E):
    a = np.array(E, dtype=float)
    if len(a) == 0:
        return None
    s = dict(n_edges=len(a), max_len=a[:, 0].max(), max_pct=a[:, 1].max(),
             max_dir=int(a[:, 2].max()), max_either=int(a[:, 3].max()), max_both=int(a[:, 4].max()),
             p99_either=float(np.percentile(a[:, 3], 99)), mean_either=float(a[:, 3].mean()))
    w = a[:, 5]
    for dl in DELTAS:
        s['out_either_%d' % dl] = float((a[:, 3] > dl).mean())
        s['out_both_%d' % dl] = float((a[:, 4] > dl).mean())
        s['wout_either_%d' % dl] = float(w[a[:, 3] > dl].sum() / w.sum()) if w.sum() else 0.0
    return s


def edge_sets(routes):
    """directed customer edges (i, j), depot edges (depot, first)"""
    ce, de = set(), set()
    for dep, seq in routes:
        if seq:
            de.add((dep, seq[0]))
        ce.update(zip(seq[:-1], seq[1:]))
    return ce, de


def diff_row(inst, zroutes, ours_runs, geo):
    """Zou edges that appear in none / in the best / in some of our runs, with their neighbour ranks."""
    D, rank = geo
    zc, zd = edge_sets(zroutes)
    ok = [r for r in ours_runs.values() if r['feasible'] and r['routes']]
    best = min(ok, key=lambda r: r['cost'])
    bc, bd = edge_sets(best['routes'])
    anyc, anyd = set(), set()
    for r in ok:
        c, d = edge_sets(r['routes'])
        anyc |= c
        anyd |= d
    und_any = anyc | {(j, i) for i, j in anyc}                      # undirected view
    out = dict(n_zou_edges=len(zc), n_depot_edges=len(zd))
    groups = {'in_best': [e for e in zc if e in bc], 'miss_best': [e for e in zc if e not in bc],
              'miss_any_dir': [e for e in zc if e not in anyc], 'miss_any_und': [e for e in zc if e not in und_any],
              'in_any': [e for e in zc if e in anyc]}
    for g, es in groups.items():
        r = [min(int(rank[i, j]), int(rank[j, i])) for i, j in es]
        out['n_' + g] = len(es)
        out['maxrank_' + g] = max(r) if r else 0
        out['medrank_' + g] = float(np.median(r)) if r else 0
        out['out20_' + g] = sum(x > 20 for x in r)
        out['out10_' + g] = sum(x > 10 for x in r)
    out['depot_miss_best'] = len([e for e in zd if e not in bd])
    out['depot_miss_any'] = len([e for e in zd if e not in anyd])
    out['our_best_gap_vs_zou'] = 100.0 * (best['cost'] - sum(P.route_cost(inst, d, s) for d, s in zroutes)) / sum(P.route_cost(inst, d, s) for d, s in zroutes)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--published', required=True)
    ap.add_argument('--ours', nargs='+', required=True)
    ap.add_argument('--out', default='edge_granularity_out')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(exist_ok=True)

    M = P.load_manifest()
    pub = P.load_published(a.published, M)
    res = P.load_results(a.ours)
    lit = P.load_literature()
    rows = []
    diffs = []
    for name in sorted(M):
        if name in EXCLUDE:
            continue
        inst = P.load_instance(name, M)
        geo, dgeo = geometry(inst), depot_rank(inst)
        groups = {}
        if name in pub:
            c = sum(P.route_cost(inst, d, s) for d, s in pub[name])
            if not P.check_solution(inst, pub[name]) and abs(c - lit[name]['best']) < 0.006:
                groups['ZOU_best'] = [pub[name]]
        for alg, byinst in res.items():
            runs = byinst.get(name)
            if not runs:
                continue
            ok = {s: r for s, r in runs.items() if r['feasible'] and r['routes']}
            if not ok:
                continue
            best = min(ok.values(), key=lambda r: r['cost'])
            groups['%s_best' % alg] = [best['routes']]
            groups['%s_all' % alg] = [r['routes'] for r in ok.values()]
        if 'ZOU_best' in groups:
            for alg, byinst in res.items():
                if byinst.get(name):
                    dr = diff_row(inst, pub[name], byinst[name], geo)
                    dr.update(instance=name, n=inst['n'], cls=P.size_class(inst['n']), alg=alg)
                    diffs.append(dr)
        for g, sols in groups.items():
            E, DE = [], []
            for routes in sols:
                e, de = solution_edges(inst, routes, geo, dgeo)
                E += e
                DE += de
            s = summarize(E)
            if s is None:
                continue
            per_sol_max = [summarize(solution_edges(inst, r, geo, dgeo)[0])['max_either'] for r in sols]
            s.update(group=g, instance=name, n=inst['n'], cls=P.size_class(inst['n']), n_sol=len(sols),
                     delta_star_mean=float(np.mean(per_sol_max)), delta_star_max=int(np.max(per_sol_max)),
                     depot_max_rank=max(r for _, r in DE), depot_max_len=max(l for l, _ in DE),
                     depot_p95_rank=float(np.percentile([r for _, r in DE], 95)))
            rows.append(s)
    keys = ['group', 'instance', 'n', 'cls', 'n_sol', 'n_edges', 'max_len', 'max_pct', 'max_dir', 'max_either', 'max_both',
            'p99_either', 'mean_either', 'delta_star_mean', 'delta_star_max', 'depot_max_rank', 'depot_p95_rank',
            'depot_max_len'] + ['%s_%s_%d' % (p, q, d) for p in ('out', 'wout') for q in ('either',) for d in DELTAS] \
        + ['out_both_%d' % d for d in DELTAS]
    with open(out / 'edge_granularity_instances.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, keys, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})
    print('wrote', out / 'edge_granularity_instances.csv', len(rows), 'rows')
    if diffs:
        with open(out / 'edge_diff_instances.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, list(diffs[0].keys()))
            w.writeheader()
            for r in diffs:
                w.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})
        print('wrote', out / 'edge_diff_instances.csv', len(diffs), 'rows')


if __name__ == '__main__':
    main()
