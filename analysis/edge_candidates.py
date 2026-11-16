#!/usr/bin/env python3
"""Coverage of Zou et al.'s published edges by candidate-edge sets of different kind and size.

Candidate sets (undirected customer-customer pairs; depot edges are always allowed):
  knn-k      : pairs with min(r_i(j), r_j(i)) <= k            (granular neighbourhood, Toth & Vigo)
  union-m    : pairs used (in either direction) by the final solutions of m of our runs (random subset)
  union-m+knn-k : union of the two
Out-of-sample: our runs never saw Zou's solutions.  Coverage = share of Zou's customer edges (undirected) in the set;
size = number of candidate pairs per customer (undirected pairs / n).

Usage: edge_candidates.py --published DIR --ours ROOT [ROOT ...] --alg ext10 [--draws 20] [--out DIR]
"""
import argparse
import csv
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llrp_pool as P
from edge_granularity import EXCLUDE, geometry

KS = [5, 10, 15, 20, 30]
MS = [1, 3, 5, 10, 30]


def und(routes):
    s = set()
    for _, seq in routes:
        for a, b in zip(seq[:-1], seq[1:]):
            s.add((a, b) if a < b else (b, a))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--published', required=True)
    ap.add_argument('--ours', nargs='+', required=True)
    ap.add_argument('--alg', default='ext10')
    ap.add_argument('--draws', type=int, default=20)
    ap.add_argument('--out', default='edge_candidates_out')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    M = P.load_manifest()
    pub = P.load_published(a.published, M)
    lit = P.load_literature()
    byinst = P.load_results(a.ours)[a.alg]
    rng = random.Random(2026)
    rows = []
    for name in sorted(byinst):
        if name in EXCLUDE or name not in pub:
            continue
        inst = P.load_instance(name, M)
        zc = sum(P.route_cost(inst, d, s) for d, s in pub[name])
        if P.check_solution(inst, pub[name]) or abs(zc - lit[name]['best']) > 0.006:
            continue
        n = inst['n']
        D, rank = geometry(inst)
        either = np.minimum(rank, rank.T)
        Z = und(pub[name])
        runs = [r for r in byinst[name].values() if r['feasible'] and r['routes']]
        sets = [und(r['routes']) for r in runs]
        for k in KS:
            iu = np.triu_indices(n, 1)
            size = int((either[iu] <= k).sum())
            cov = sum(either[i, j] <= k for i, j in Z) / len(Z)
            rows.append(dict(instance=name, n=n, cls=P.size_class(n), cand='knn-%d' % k, size_per_cust=size / n, coverage=cov))
        for m in MS:
            if m > len(sets):
                continue
            for withk in (None, 5, 10):
                cs, cv = [], []
                for _ in range(a.draws if m < len(sets) else 1):
                    U = set().union(*rng.sample(sets, m))
                    if withk:
                        iu = np.triu_indices(n, 1)
                        U |= {(int(i), int(j)) for i, j in zip(*iu) if either[i, j] <= withk}
                    cs.append(len(U) / n)
                    cv.append(len(Z & U) / len(Z))
                rows.append(dict(instance=name, n=n, cls=P.size_class(n),
                                 cand='union-%d%s' % (m, '+knn-%d' % withk if withk else ''),
                                 size_per_cust=float(np.mean(cs)), coverage=float(np.mean(cv))))
    with open(out / 'edge_candidates_instances.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, ['instance', 'n', 'cls', 'cand', 'size_per_cust', 'coverage'])
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()})
    print('wrote', out / 'edge_candidates_instances.csv', len(rows), 'rows')


if __name__ == '__main__':
    main()
