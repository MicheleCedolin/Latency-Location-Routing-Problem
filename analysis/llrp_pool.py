"""Shared helpers for the post-hoc analyses (route pools + set partitioning, anytime curves).  Standard library + numpy (+ scipy for SP).

Result trees are the standard output of cpp/run_final.sh / run_extended.sh:  <family>/<tag>/{run,routes,trace}.csv  (see study_results/README.md).
Customer and depot indices in routes.csv are 0-based; the published solution files of Zou et al. (2024) are 1-based
(a line is  <n + 1 + depot> <customer> <customer> ...).
"""
import csv
import ctypes
import math
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOL = 0.005                        # published values have two decimals


# ------------------------------------------------------------------ instances, BKS, literature
def read_inst(path):
    L = [l.strip() for l in open(path) if l.strip()]
    hdr, i = {}, 0
    while L[i] != 'depots':
        k, *v = L[i].split()
        hdr[k] = v
        i += 1
    n, m = int(hdr['n'][0]), int(hdr['m'][0])
    dep = np.array([[float(t) for t in L[i + 1 + j].split()[:2]] for j in range(m)])
    i += 1 + m
    assert L[i] == 'customers'
    cu = np.array([[float(t) for t in L[i + 1 + j].split()[:3]] for j in range(n)])
    return dict(name=hdr['name'][0], n=n, m=m, Q=float(hdr['Q'][0]), Nv=int(hdr['Nv'][0]), Ng=int(hdr['Ng'][0]),
                dep=dep, xy=cu[:, :2], dem=cu[:, 2])


def load_manifest():
    rows = list(csv.DictReader(open(REPO / 'cpp' / 'manifest.tsv'), delimiter='\t'))
    return {r['name']: r for r in rows}


def load_instance(name, manifest, cache={}):
    if name not in cache:
        cache[name] = read_inst(REPO / 'cpp' / 'inst' / manifest[name]['family'] / (name + '.inst'))
    return cache[name]


def load_bks():
    return {r['instance']: float(r['bks']) for r in csv.DictReader(open(REPO / 'bks' / 'LLRP_BKS.csv'))}


def load_literature(algo='RLHEA'):
    out = {}
    for r in csv.DictReader(open(REPO / 'bks' / 'literature_results.csv')):
        if r['algorithm'] == algo:
            out[r['instance']] = dict(best=float(r['best']), avg=float(r['avg']) if r['avg'] else float('nan'),
                                      time=float(r['time_s']) if r['time_s'] else float('nan'))
    return out


def size_class(n):
    return '<=75' if n <= 75 else '100' if n <= 100 else '117-134' if n <= 134 else '150' if n <= 150 else '200'


CLASSES = ['<=75', '100', '117-134', '150', '200']


def gap(x, bks):
    return 100.0 * (x - bks) / bks


# ------------------------------------------------------------------ routes and costs
def route_cost(inst, depot, seq):
    t, tot, p = 0.0, 0.0, inst['dep'][depot]
    for c in seq:
        q = inst['xy'][c]
        t += math.hypot(q[0] - p[0], q[1] - p[1])
        tot += t
        p = q
    return tot


def check_solution(inst, routes):
    """routes = [(depot, [customers])]; returns a list of problems (empty = feasible for 'at most Ng depots, at most Nv routes')."""
    pr, seen = [], sorted(c for _, s in routes for c in s)
    if seen != list(range(inst['n'])):
        pr.append('customers not served exactly once')
    if any(inst['dem'][list(s)].sum() > inst['Q'] + 1e-9 for _, s in routes):
        pr.append('vehicle capacity')
    if len([1 for _, s in routes if s]) > inst['Nv']:
        pr.append('too many routes')
    if len({d for d, s in routes if s}) > inst['Ng']:
        pr.append('too many depots')
    return pr


# ------------------------------------------------------------------ exact DP (C++ via ctypes)
_LIB = None


def _dp_lib():
    global _LIB
    if _LIB is None:
        so = HERE / 'libdp_latency.so'
        if not so.exists():
            subprocess.check_call(['g++', '-O2', '-shared', '-fPIC', '-o', str(so), str(HERE / 'dp_latency.cpp')])
        _LIB = ctypes.CDLL(str(so))
        _LIB.dp_min_latency.restype = ctypes.c_double
    return _LIB


def dp_order(inst, depot, seq):
    """(cost, best order) of the customer set `seq` from `depot`."""
    k = len(seq)
    xy = inst['xy'][list(seq)]
    d0 = np.ascontiguousarray(np.hypot(xy[:, 0] - inst['dep'][depot][0], xy[:, 1] - inst['dep'][depot][1]))
    D = np.ascontiguousarray(np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1]))
    od = (ctypes.c_int * k)()
    c = _dp_lib().dp_min_latency(k, d0.ctypes.data_as(ctypes.c_void_p), D.ctypes.data_as(ctypes.c_void_p), od)
    return c, tuple(seq[i] for i in od)


# ------------------------------------------------------------------ result trees
def load_results(roots):
    """-> {algorithm: {instance: {seed: run}}}; run = dict(cost, feasible, cpu, iters, routes[(depot, tuple)], trace[(t, cost)]).
    Later roots override earlier ones for the same (algorithm, instance, seed)."""
    out = defaultdict(lambda: defaultdict(dict))
    for root in roots:
        for rp in sorted(Path(root).rglob('run.csv')):
            d = rp.parent
            if not (d / 'routes.csv').exists():
                continue
            for r in csv.DictReader(open(rp, newline='')):
                out[r['Algorithm']][r['Instance']][int(r['Seed'])] = dict(
                    cost=float(r['Total Latency']), feasible=r['Feasible'] == 'True', cpu=float(r['CPU Time']),
                    iters=int(r['Iterations']), routes=[], trace=[])
            for r in csv.DictReader(open(d / 'routes.csv', newline='')):
                run = out[r['Algorithm']][r['Instance']].get(int(r['Seed']))
                if run is not None:
                    run['routes'].append((int(r['Depot']), tuple(int(x) for x in r['Customers'].split(' -> '))))
            if (d / 'trace.csv').exists():
                for r in csv.DictReader(open(d / 'trace.csv', newline='')):
                    run = out[r['Algorithm']][r['Instance']].get(int(r['Seed']))
                    if run is not None:
                        run['trace'].append((float(r['CPU Seconds']), float(r['Best Latency'])))
    return out


# ------------------------------------------------------------------ published solutions (Zou et al. 2024)
_B = {'Christ': 'Ch', 'Gaskell': 'Gaskell', 'Min': 'Mi', 'Or': 'Or'}


def published_name(stem, m):
    """file stem of YujiZou/LLRP/solutions -> instance name of this repository"""
    g = re.match(r'^(Christ|Gaskell|Min|Or)_(\d+)_(\d+)b?$', stem)
    if g:
        return '%s%s-%s' % (_B[g.group(1)], g.group(2), g.group(3))
    return 'P%s-%d' % (stem, m) if re.fullmatch(r'\d{6}', stem) else '%s-%d' % (stem, m)


def load_published(sol_dir, manifest):
    """{instance: [(depot, tuple(customers))]} for every file that maps onto a known instance."""
    out = {}
    for f in sorted(Path(sol_dir).glob('*.txt')):
        for name, r in manifest.items():
            if published_name(f.stem, int(r['m'])) == name:
                n, m = int(r['n']), int(r['m'])
                routes = []
                for line in f.read_text().splitlines():
                    t = line.split()
                    if len(t) >= 2 and 0 <= int(t[0]) - (n + 1) < m:
                        routes.append((int(t[0]) - (n + 1), tuple(int(x) - 1 for x in t[1:])))
                out[name] = routes
    return out
