"""Stand-alone LLRP solution checker: reads only the .dat file and a route description, imports nothing from llrp_framework.

A solution is a list of routes (depot index 0-based, customer indices 0-based in visiting order).
latency = sum over routes of the arrival times of the customers (vehicle leaves the depot at time 0, no return arc),
distances are real-valued Euclidean (hypot). Checks: every customer once, vehicle capacity Q, depot capacity,
number of routes <= K, number of used depots <= p (when K / p are given).

    python3 tools/indep_check.py --published DIR_WITH_RLHEA_TXT [--out reference/published_check.csv]
"""
from __future__ import annotations
import argparse, csv, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_dat(path):
    lines = [l.split() for l in Path(path).read_text().splitlines() if l.strip()]
    if Path(path).name == 'coordOr117.dat':            # two extra zero fields on each depot row
        lines[2:16] = [r[:2] for r in lines[2:16]]
    it = iter(v for r in lines for v in r)
    n = int(next(it)); m = int(next(it))
    dep = [(float(next(it)), float(next(it))) for _ in range(m)]
    cust = [(float(next(it)), float(next(it))) for _ in range(n)]
    Q = float(next(it))
    cap = [float(next(it)) for _ in range(m)]
    dem = [float(next(it)) for _ in range(n)]
    return dict(n=n, m=m, dep=dep, cust=cust, Q=Q, cap=cap, dem=dem)


def latency(d, routes):
    """sum of arrival times; routes = [(depot, [customers])]"""
    tot = 0.0
    for dp, seq in routes:
        t = 0.0; px, py = d['dep'][dp]
        for c in seq:
            x, y = d['cust'][c]
            t += math.hypot(x - px, y - py)
            tot += t
            px, py = x, y
    return tot


def check(d, routes, K=None, p=None):
    probs = []
    seen = [c for _, s in routes for c in s]
    if sorted(seen) != list(range(d['n'])):
        probs.append('customers not served exactly once')
    load = [0.0] * d['m']
    for dp, s in routes:
        q = sum(d['dem'][c] for c in s)
        if q > d['Q'] + 1e-9: probs.append(f'vehicle capacity: {q} > {d["Q"]}')
        load[dp] += q
    for k in range(d['m']):
        if load[k] > d['cap'][k] + 1e-9: probs.append(f'depot {k} capacity {load[k]} > {d["cap"][k]}')
    nr = sum(1 for _, s in routes if s); nd = len({dp for dp, s in routes if s})
    if K is not None and nr > K: probs.append(f'{nr} routes > K={K}')
    if p is not None and nd > p: probs.append(f'{nd} depots > p={p}')
    return probs, nr, nd


def parse_published(path, n, m):
    routes = []
    for line in Path(path).read_text().splitlines():
        t = line.split()
        if not t: continue
        dp = int(t[0]) - (n + 1)
        assert 0 <= dp < m, (path, line)
        routes.append((dp, [int(x) - 1 for x in t[1:]]))
    return routes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--published', required=True)
    ap.add_argument('--reference', default=str(ROOT / 'reference' / 'LLRP_reference.csv'))
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.reference)))
    out = []; bad = 0
    for r in rows:
        d = parse_dat(ROOT / 'data' / r['group'] / (r['file']))
        f = Path(a.published) / r['published_file']
        if not f.exists():
            out.append(dict(name=r['name'], status='missing')); continue
        routes = parse_published(f, d['n'], d['m'])
        probs, nr, nd = check(d, routes, int(r['K']), int(r['p']))
        z = latency(d, routes)
        bks = float(r['bks'])
        out.append(dict(name=r['name'], n=d['n'], K=r['K'], p=r['p'], routes=nr, depots=nd, latency=f'{z:.4f}', bks=r['bks'],
                        rel_to_bks=f'{(z - bks) / bks:+.2e}', problems=';'.join(probs) or 'ok'))
        bad += bool(probs)
    keys = ['name', 'n', 'K', 'p', 'routes', 'depots', 'latency', 'bks', 'rel_to_bks', 'problems', 'status']
    if a.out:
        with open(a.out, 'w', newline='') as fh:
            w = csv.DictWriter(fh, keys, extrasaction='ignore'); w.writeheader(); w.writerows(out)
    for o in out: print({k: o.get(k) for k in keys if o.get(k) is not None})
    print('instances:', len(out), 'with problems:', bad)


if __name__ == '__main__':
    main()
