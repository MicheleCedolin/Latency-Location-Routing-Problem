#!/usr/bin/env python3
"""Stage 0 of the "edge backbone" idea: routes built from the union of the edges used by many runs.

For every instance
  1. backbone = undirected customer-customer edges used by the final solutions of our runs (+ optionally the k nearest neighbours);
  2. enumerate all capacity-feasible elementary paths of the backbone (C++, enum_paths.cpp) and keep, per (customer set, depot),
     the cheapest path; depots = the `ndep` depots nearest to the first customer;
  3. diagnostics against the published routes of Zou et al.: share of their edges inside the backbone, share of their routes that
     appear as a column (same customer set and depot);
  4. set partitioning (HiGHS) over the columns (if there are more than --sp-max, the columns with the smallest reduced cost of the
     LP without depot constraints are kept), then exact DP polish of the selected routes.
No information of the published solutions is used to build the backbone or to select columns; it is only compared afterwards.

Usage: backbone_sp.py ROOT [ROOT ...] --published DIR --alg ext10 [--instances a,b] [--knn 0] [--out DIR]
"""
import argparse
import csv
import subprocess
import sys
import time
from array import array
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import llrp_pool as P
from pool_sp import solve_sp
from edge_granularity import EXCLUDE, geometry


def backbone_edges(runs, inst, knn, minfreq=1):
    cnt = {}
    for r in runs:
        seen = set()
        for _, seq in r['routes']:
            for a, b in zip(seq[:-1], seq[1:]):
                seen.add((min(a, b), max(a, b)))
        for e in seen:
            cnt[e] = cnt.get(e, 0) + 1
    E = {e for e, c in cnt.items() if c >= minfreq}
    if knn:
        D, rank = geometry(inst)
        either = np.minimum(rank, rank.T)
        iu = np.triu_indices(inst['n'], 1)
        E |= {(int(i), int(j)) for i, j in zip(*iu) if either[i, j] <= knn}
    return E


def run_enum(exe, inst, E, kmax, maxpaths, maxcols, ndep):
    n, m = inst['n'], inst['m']
    adj = [[] for _ in range(n)]
    for a, b in E:
        adj[a].append(b)
        adj[b].append(a)
    lines = ['%d %d %g %d %d %d %d' % (n, m, inst['Q'], kmax, maxpaths, maxcols, ndep)]
    lines += ['%g %g %g' % (inst['dem'][i], inst['xy'][i][0], inst['xy'][i][1]) for i in range(n)]
    lines += ['%g %g' % (inst['dep'][d][0], inst['dep'][d][1]) for d in range(m)]
    lines += [' '.join(map(str, [len(adj[i])] + sorted(adj[i]))) for i in range(n)]
    p = subprocess.run([exe], input='\n'.join(lines) + '\n', capture_output=True, text=True, check=True)
    out = p.stdout.split('\n')
    head = out[0].split()
    dep, cost, off, flat = array('i'), array('d'), array('i', [0]), array('i')
    for ln in out[1:]:
        if not ln:
            continue
        t = ln.split()
        k = int(t[2])
        dep.append(int(t[0]))
        cost.append(float(t[1]))
        flat.extend(int(x) for x in t[3:3 + k])
        off.append(len(flat))
    return dict(paths=int(head[2]), capped_paths=int(head[4]), dep=np.frombuffer(dep, dtype=np.int32),
                cost=np.frombuffer(cost, dtype=np.float64), off=np.frombuffer(off, dtype=np.int32),
                flat=np.frombuffer(flat, dtype=np.int32), capped_cols=int(head[8]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('roots', nargs='+')
    ap.add_argument('--published', required=True)
    ap.add_argument('--alg', default='ext10')
    ap.add_argument('--instances', default='')
    ap.add_argument('--knn', type=int, default=0)
    ap.add_argument('--minfreq', type=int, default=1, help='keep edges used by at least this many runs')
    ap.add_argument('--ndep', type=int, default=3)
    ap.add_argument('--maxpaths', type=int, default=400_000_000)
    ap.add_argument('--maxcols', type=int, default=1_500_000)
    ap.add_argument('--sp-max', type=int, default=60_000)
    ap.add_argument('--time-limit', type=float, default=600.0)
    ap.add_argument('--no-sp', action='store_true', help='enumeration and Zou-containment diagnostics only')
    ap.add_argument('--out', default='backbone_out')
    ap.add_argument('--exe', default=str(HERE / 'enum_paths'))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(exist_ok=True)

    M = P.load_manifest()
    pub = P.load_published(a.published, M)
    lit = P.load_literature()
    res = P.load_results(a.roots)
    names = [x for x in a.instances.split(',') if x] or sorted(res[a.alg])
    rng = np.random.RandomState(7)
    rows = []
    for name in names:
        if name in EXCLUDE or name not in pub or name not in res[a.alg]:
            continue
        t0 = time.time()
        inst = P.load_instance(name, M)
        runs = [r for r in res[a.alg][name].values() if r['feasible'] and r['routes']]
        best = min(runs, key=lambda r: r['cost'])
        zc = sum(P.route_cost(inst, d, s) for d, s in pub[name])
        if P.check_solution(inst, pub[name]) or abs(zc - lit[name]['best']) > 0.006:
            continue
        kmax = min(18, max(len(s) for r in runs for _, s in r['routes']) + 2)
        E = backbone_edges(runs, inst, a.knn, a.minfreq)
        zedges = [(min(x, y), max(x, y)) for _, s in pub[name] for x, y in zip(s[:-1], s[1:])]
        en = run_enum(a.exe, inst, E, kmax, a.maxpaths, a.maxcols, a.ndep)
        R = len(en['dep'])
        z = rng.randint(0, 2 ** 62, size=inst['n']).astype(np.uint64)
        h = np.bitwise_xor.reduceat(z[en['flat']], en['off'][:-1]) if R else np.zeros(0, np.uint64)
        hk = {(int(hh), int(d)) for hh, d in zip(h, en['dep'])}
        hs = {int(hh) for hh in h}
        runh = [{(int(np.bitwise_xor.reduce(z[list(sq)])), d) for d, sq in r['routes'] if sq} for r in runs]
        ph = set().union(*runh)
        zkeys = [(hh, d) for d, _, hh in [(d, s_, int(np.bitwise_xor.reduce(z[list(s_)]))) for d, s_ in pub[name] if s_]]
        growth = {}
        for mm in (1, 3, 10):
            if mm <= len(runh):
                growth[mm] = float(np.mean([len(set(zkeys) & set().union(*[runh[i] for i in rng.choice(len(runh), mm, replace=False)])) for _ in range(20)]))
        zr = [(d, s, int(np.bitwise_xor.reduce(z[list(s)]))) for d, s in pub[name] if s]
        row = dict(instance=name, n=inst['n'], backbone_per_cust=round(len(E) / inst['n'], 2), kmax=kmax,
                   paths=en['paths'], capped_paths=en['capped_paths'], columns=R, capped_cols=en['capped_cols'],
                   zou_edges_in=round(sum(e in E for e in zedges) / len(zedges), 4),
                   zou_routes=len(zr), pool_set_dep=sum((int(hh), d) in ph for d, _, hh in zr), pool_cols=len(ph), pool_m1=round(growth.get(1, 0), 2), pool_m3=round(growth.get(3, 0), 2), pool_m10=round(growth.get(10, 0), 2), zou_set_dep=sum((hh, d) in hk for d, _, hh in zr), zou_set_any=sum(hh in hs for _, _, hh in zr),
                   our_best=round(best['cost'], 3), zou_best=round(zc, 3))
        t1 = time.time()
        row['enum_s'] = round(t1 - t0, 1)
        if R == 0 or a.no_sp:
            rows.append(row)
            print(row, flush=True)
            continue
        # ---- column selection by reduced cost of the LP without depot constraints
        n = inst['n']
        sel = np.arange(R)
        if R > a.sp_max:
            ri = en['flat']
            ci = np.repeat(np.arange(R), np.diff(en['off']))
            A = coo_matrix((np.ones(len(ri)), (ri, ci)), shape=(n, R)).tocsr()
            lp = linprog(en['cost'], A_eq=A, b_eq=np.ones(n), A_ub=csr_matrix(np.ones((1, R))), b_ub=[inst['Nv']],
                         bounds=(0, None), method='highs')
            if lp.status == 0:
                rc = lp.lower.marginals
                sel = np.argsort(rc, kind='stable')[:a.sp_max]
                row['lp_value'] = round(float(lp.fun), 3)
            else:
                sel = np.argsort(en['cost'] / np.diff(en['off']), kind='stable')[:a.sp_max]
        selected = np.zeros(R, dtype=bool)
        selected[sel] = True
        hkeep = {(int(h[c]), int(en['dep'][c])) for c in sel}
        row['zou_set_dep_kept'] = sum((hh, d) in hkeep for d, _, hh in zr)
        cols = [(int(en['dep'][c]), frozenset(int(v) for v in en['flat'][en['off'][c]:en['off'][c + 1]]), float(en['cost'][c]),
                 tuple(int(v) for v in en['flat'][en['off'][c]:en['off'][c + 1]])) for c in sel]
        t2 = time.time()
        cost, routes, status = solve_sp(inst, cols, a.time_limit)
        row['sp_status'] = status
        row['sp_cols'] = len(cols)
        if cost is not None:
            pol = [(d, P.dp_order(inst, d, s)[1] if len(s) <= 18 else s) for d, s in routes]
            pc = sum(P.route_cost(inst, d, s) for d, s in pol)
            row['sp_raw'] = round(cost, 3)
            row['sp_dp'] = round(pc, 3)
            row['sp_feasible'] = not P.check_solution(inst, pol)
            row['gap_vs_zou'] = round(100 * (pc - zc) / zc, 4)
            row['gap_vs_ours'] = round(100 * (pc - best['cost']) / best['cost'], 4)
        row['sp_s'] = round(time.time() - t2, 1)
        rows.append(row)
        print(row, flush=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(out / 'backbone_sp_instances.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)
    with open(out / 'backbone_sp_summary.md', 'w') as f:
        f.write('# Edge backbone: path enumeration and set partitioning (%s, minfreq=%d, knn=%d, ndep=%d, sp-max=%d)\n\n' % (a.alg, a.minfreq, a.knn, a.ndep, a.sp_max))
        f.write('| instance | n | bb/cust | paths | capped | columns | Zou edges in | Zou routes in: run-pool / backbone set+depot / backbone set / kept for SP | our best | Zou | SP+DP | gap vs Zou % | gap vs ours % |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n')
        for r in rows:
            f.write('| %s | %d | %s | %s | %s | %s | %s | %s / %s / %s / %s of %s | %s | %s | %s | %s | %s |\n' % (
                r['instance'], r['n'], r['backbone_per_cust'], r['paths'], r['capped_paths'], r['columns'], r['zou_edges_in'],
                r['pool_set_dep'], r['zou_set_dep'], r['zou_set_any'], r.get('zou_set_dep_kept', '-'), r['zou_routes'], r['our_best'], r['zou_best'],
                r.get('sp_dp', '-'), r.get('gap_vs_zou', '-'), r.get('gap_vs_ours', '-')))
        tot = lambda k: sum(r.get(k, 0) for r in rows)
        f.write('\n**Totals over %d instances:** Zou routes %d; present in pool of 1 / 3 / 10 / all runs: %.1f / %.1f / %.1f / %d; backbone columns (set+depot): %d (set only: %d); instances with truncated enumeration: %d; SP solutions: %d.\n' % (
            len(rows), tot('zou_routes'), tot('pool_m1'), tot('pool_m3'), tot('pool_m10'), tot('pool_set_dep'), tot('zou_set_dep'), tot('zou_set_any'),
            sum(1 for r in rows if r['capped_paths'] or r['capped_cols']), sum(1 for r in rows if 'sp_dp' in r)))
    print('done', len(rows))


if __name__ == '__main__':
    main()
