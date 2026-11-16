#!/usr/bin/env python3
"""Route pool + exact DP polish + set partitioning (SP) over the final solutions of many runs  (post-hoc multi-start recombination).

For every instance and every result group (the `Algorithm` column, e.g. tuned / ext10 / B1) and for the union of all groups:
  best-of-30      best final solution of the group
  SP raw          set partitioning over all routes of the final solutions (routes as found)
  SP+DP           the same after every route was re-ordered optimally (Held-Karp, up to --kmax customers per route)
  SP+DP+pub       SP+DP with the routes of the published solution of Zou et al. (2024) added to the pool (--published DIR)
SP minimises the total latency over the pool; each customer once, <= Nv routes, <= Ng open depots (HiGHS, exact inside the pool).
A pooled result is a multi-start recombination, NOT the result of a single run; report it in its own column.

The coverage columns answer a different question: are the routes of the published solution *generated* by the group
(exact: same depot and visiting order; set: same depot and customer set, other order; other: same customer set, other depot)?

  python3 analysis/pool_sp.py TREE [TREE ...] --published /path/to/LLRP/solutions --out analysis_out
"""
import argparse
import csv
import math
import sys
from collections import defaultdict

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, csr_matrix

import llrp_pool as L


def solve_sp(inst, cols, time_limit):
    """cols = [(depot, frozenset, cost, order)] -> (cost, routes, status) with routes = [(depot, order)]; exact inside the pool."""
    R, n, m = len(cols), inst['n'], inst['m']
    ri, ci = [], []
    for r, (_, S, _, _) in enumerate(cols):
        ri += list(S)
        ci += [r] * len(S)
    cover = coo_matrix((np.ones(len(ri)), (ri, ci)), shape=(n, R + m)).tocsr()
    nv = csr_matrix(np.r_[np.ones(R), np.zeros(m)].reshape(1, -1))
    ng = csr_matrix(np.r_[np.zeros(R), np.ones(m)].reshape(1, -1))
    link = coo_matrix((np.r_[np.ones(R), -np.ones(R)], (np.r_[np.arange(R), np.arange(R)],
                                                        np.r_[np.arange(R), R + np.array([c[0] for c in cols])])),
                      shape=(R, R + m)).tocsr()
    res = milp(c=np.r_[[c[2] for c in cols], np.zeros(m)], integrality=np.ones(R + m), bounds=Bounds(0, 1),
               constraints=[LinearConstraint(cover, 1, 1), LinearConstraint(nv, -np.inf, inst['Nv']),
                            LinearConstraint(ng, -np.inf, inst['Ng']), LinearConstraint(link, -np.inf, 0)],
               options=dict(time_limit=time_limit, mip_rel_gap=0.0))
    if res.x is None:
        return None, [], res.status
    sel = [cols[r] for r in range(R) if res.x[r] > 0.5]
    return sum(c[2] for c in sel), [(c[0], c[3]) for c in sel], res.status


class Pool:
    def __init__(self, inst, kmax, dp_cache):
        self.inst, self.kmax, self.dp_cache = inst, kmax, dp_cache
        self.raw, self.orders, self.by_set = {}, set(), defaultdict(set)

    def add(self, depot, seq):
        seq = tuple(seq)
        key = (depot, frozenset(seq))
        c = L.route_cost(self.inst, depot, seq)
        self.orders.add((depot, seq))
        self.by_set[key[1]].add(depot)
        if key not in self.raw or c < self.raw[key][0] - 1e-12:
            self.raw[key] = (c, seq)

    def copy(self):
        p = Pool(self.inst, self.kmax, self.dp_cache)
        p.raw, p.orders = dict(self.raw), set(self.orders)
        p.by_set = defaultdict(set, {k: set(v) for k, v in self.by_set.items()})
        return p

    def columns(self, polish):
        cols = []
        for (d, S), (c, seq) in self.raw.items():
            if polish and len(S) <= self.kmax:
                if (d, S) not in self.dp_cache:
                    self.dp_cache[(d, S)] = L.dp_order(self.inst, d, sorted(S))
                c2, seq2 = self.dp_cache[(d, S)]
                if c2 < c - 1e-12:
                    c, seq = c2, seq2
            cols.append((d, S, c, seq))
        return cols

    def coverage(self, routes):
        ex = st = ot = no = 0
        cust_ex = 0
        for d, s in routes:
            S = frozenset(s)
            if (d, tuple(s)) in self.orders:
                ex += 1
                cust_ex += len(s)
            elif d in self.by_set.get(S, ()):
                st += 1
            elif S in self.by_set:
                ot += 1
            else:
                no += 1
        return ex, st, ot, no, cust_ex / max(1, sum(len(s) for _, s in routes))


CTX = {}


def process(name):
    a, manifest, bks, res, pub, labels = (CTX[k] for k in ('a', 'manifest', 'bks', 'res', 'pub', 'labels'))
    rows, bad_cost, n_runs, audit_fail = [], 0, 0, 0
    inst = L.load_instance(name, manifest)
    dp_cache = {}
    zr = pub.get(name, [])
    zr_ok = [(d, s) for d, s in zr if s and inst['dem'][list(s)].sum() <= inst['Q'] + 1e-9]
    zcost = sum(L.route_cost(inst, d, s) for d, s in zr) if zr else float('nan')
    zprob = L.check_solution(inst, zr) if zr else ['no file']
    zok = not zprob and abs(zcost - bks[name]) <= 0.011
    for label in labels + ['UNION']:
        runs = [r for lb in (labels if label == 'UNION' else [label]) for r in res[lb].get(name, {}).values()
                if r['feasible'] and r['routes']]
        if not runs or (label == 'UNION' and len(labels) < 2):
            continue
        pool = Pool(inst, a.kmax, dp_cache)
        for r in runs:
            n_runs += 1
            if abs(sum(L.route_cost(inst, d, s) for d, s in r['routes']) - r['cost']) > 1e-6 * max(1.0, r['cost']):
                bad_cost += 1
            for d, s in r['routes']:
                pool.add(d, s)
        row = dict(group=label, instance=name, family=manifest[name]['family'], n=inst['n'], runs=len(runs), bks=bks[name],
                   best_run=min(r['cost'] for r in runs), pub_cost=zcost, pub_ok=int(zok))
        for key, polish in (('sp_raw', False), ('sp_dp', True)):
            c, routes, st = solve_sp(inst, pool.columns(polish), a.time_limit)
            row[key], row[key + '_status'] = c, st
            audit_fail += audit_bad(inst, routes, c)
        if zr_ok:
            p2 = pool.copy()
            for d, s in zr_ok:
                p2.add(d, s)
            c, routes, st = solve_sp(inst, p2.columns(True), a.time_limit)
            row['sp_dp_pub'] = c
            audit_fail += audit_bad(inst, routes, c)
            row['pub_routes'] = len(zr_ok)
            (row['cov_exact'], row['cov_set'], row['cov_other_depot'], row['cov_none'],
             row['cov_cust_exact']) = pool.coverage(zr_ok)
        for k in ('best_run', 'sp_raw', 'sp_dp', 'sp_dp_pub'):
            row['gap_' + k] = L.gap(row[k], bks[name]) if row.get(k) is not None else None
        rows.append(row)
    print(name, file=sys.stderr, flush=True)
    return rows, bad_cost, n_runs, audit_fail


def audit_bad(inst, routes, c):
    """1 if an SP solution fails the independent audit (feasibility, recomputed latency = objective)."""
    return int(c is not None and (bool(L.check_solution(inst, routes)) or
                                  abs(sum(L.route_cost(inst, d, s) for d, s in routes) - c) > 1e-6 * max(1.0, c)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('trees', nargs='+', help='extracted result trees (directories that contain run.csv / routes.csv)')
    ap.add_argument('--published', help='directory with the published solution files (YujiZou/LLRP, solutions/)')
    ap.add_argument('--out', default='analysis_out')
    ap.add_argument('--kmax', type=int, default=18, help='longest route that is re-ordered by the exact DP')
    ap.add_argument('--time-limit', type=float, default=120.0, help='seconds per SP solve')
    ap.add_argument('--jobs', type=int, default=1, help='instances processed in parallel')
    ap.add_argument('--instances', default='', help='comma-separated subset (default: all that occur in the trees)')
    a = ap.parse_args()

    manifest, bks = L.load_manifest(), L.load_bks()
    res = L.load_results(a.trees)
    pub = L.load_published(a.published, manifest) if a.published else {}
    labels = sorted(res)
    names = sorted({i for g in res.values() for i in g})
    if a.instances:
        names = [i for i in names if i in set(a.instances.split(','))]

    global CTX
    CTX = dict(a=a, manifest=manifest, bks=bks, res=res, pub=pub, labels=labels)
    rows, bad_cost, n_runs, audit_fail = [], 0, 0, 0
    if a.jobs > 1:
        import multiprocessing as mp
        with mp.get_context('fork').Pool(a.jobs) as pl:
            outs = list(pl.imap_unordered(process, names))
    else:
        outs = [process(nm) for nm in names]
    for r_, b_, n_, f_ in outs:
        rows += r_
        bad_cost += b_
        n_runs += n_
        audit_fail += f_
    rows.sort(key=lambda r: (r['group'] == 'UNION', r['group'], r['instance']))

    import os
    os.makedirs(a.out, exist_ok=True)
    keys = ['group', 'instance', 'family', 'n', 'runs', 'bks', 'pub_cost', 'pub_ok', 'best_run', 'sp_raw', 'sp_dp', 'sp_dp_pub',
            'gap_best_run', 'gap_sp_raw', 'gap_sp_dp', 'gap_sp_dp_pub', 'sp_raw_status', 'sp_dp_status', 'pub_routes',
            'cov_exact', 'cov_set', 'cov_other_depot', 'cov_none', 'cov_cust_exact']
    with open(os.path.join(a.out, 'pool_sp_instances.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, keys, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    write_summary(a, rows, n_runs, bad_cost, audit_fail, bool(pub))


def hit(x, b):
    return x is not None and x <= b + L.TOL


def write_summary(a, rows, n_runs, bad_cost, audit_fail, have_pub):
    import os
    out = ['# Route pool + DP + set partitioning (post-hoc multi-start recombination)', '',
           'Runs read: %d; runs whose recomputed latency differs from `Total Latency` by > 1e-6 (relative): %d; '
           'SP solutions that failed the independent audit: %d. A hit is a value <= BKS + %.3f.' % (n_runs, bad_cost, audit_fail, L.TOL), '']
    for g in sorted({r['group'] for r in rows}, key=lambda x: (x == 'UNION', x)):
        R = [r for r in rows if r['group'] == g]
        out += ['## Group `%s`  (%d instances)' % (g, len(R)), '',
                '| n class | # | hit best | hit SP raw | hit SP+DP | hit SP+DP+pub | gap best | gap SP+DP | gap SP+DP+pub |',
                '|---|---|---|---|---|---|---|---|---|']
        for cl in L.CLASSES + ['all']:
            S = [r for r in R if cl == 'all' or L.size_class(r['n']) == cl]
            if not S:
                continue
            mg = lambda k: np.mean([r['gap_' + k] for r in S if r.get('gap_' + k) is not None]) if any(
                r.get('gap_' + k) is not None for r in S) else float('nan')
            out.append('| %s | %d | %d | %d | %d | %s | %.3f | %.3f | %s |' % (
                cl, len(S), sum(hit(r['best_run'], r['bks']) for r in S), sum(hit(r['sp_raw'], r['bks']) for r in S),
                sum(hit(r['sp_dp'], r['bks']) for r in S),
                sum(hit(r.get('sp_dp_pub'), r['bks']) for r in S) if have_pub else '-', mg('best_run'), mg('sp_dp'),
                '%.3f' % mg('sp_dp_pub') if have_pub else '-'))
        out.append('')
        better = [r for r in R if r.get('sp_dp_pub') is not None and r['pub_ok'] and r['sp_dp_pub'] < r['pub_cost'] - 1e-6]
        if have_pub:
            out += ['Published solution improved by SP+DP+pub (file valid and its cost matches the BKS): %d instance(s)%s' % (
                len(better), ''.join('\n- %s: %.4f -> %.4f (BKS %.2f)%s' % (
                    r['instance'], r['pub_cost'], r['sp_dp_pub'], r['bks'],
                    ' **below BKS - 0.005**' if r['sp_dp_pub'] < r['bks'] - L.TOL else '') for r in better)), '']
            hard = [r for r in R if r['gap_sp_dp'] is not None and r['gap_sp_dp'] > 0.3 and r.get('pub_routes')]
            if hard:
                out += ['Coverage of the published routes by the pool of `%s` (instances with SP+DP gap > 0.3 %%):' % g, '',
                        '| instance | gap best | gap SP+DP | gap SP+DP+pub | pub routes | exact | same set | other depot | none | customers on exact routes |',
                        '|---|---|---|---|---|---|---|---|---|---|']
                for r in sorted(hard, key=lambda r: -r['gap_sp_dp']):
                    out.append('| %s | %.3f | %.3f | %.3f | %d | %d | %d | %d | %d | %.0f %% |' % (
                        r['instance'], r['gap_best_run'], r['gap_sp_dp'], r['gap_sp_dp_pub'], r['pub_routes'], r['cov_exact'],
                        r['cov_set'], r['cov_other_depot'], r['cov_none'], 100 * r['cov_cust_exact']))
                out.append('')
    if have_pub:
        bad = sorted({r['instance'] for r in rows if not r['pub_ok']})
        out += ['Published files that are missing, infeasible or whose cost differs from the BKS (their routes are still used as '
                'columns when each route is feasible): ' + (', '.join(bad) or 'none'), '']
    with open(os.path.join(a.out, 'pool_sp_summary.md'), 'w') as fh:
        fh.write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
