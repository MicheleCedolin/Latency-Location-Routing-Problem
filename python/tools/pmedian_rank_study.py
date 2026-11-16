"""Where does the depot set of a published best solution sit in the p-median ordering of all C(m,p) depot sets?

The ordering is the one the solvers use for `--depot-mode pmedian` (heuristics._pmedian_ranking: ascending sum_c min_{d in S} d(d,c), a valid lower
bound on the latency of any solution that uses only the depots of S). Rank 1 = best set. If the depot set of every best-known solution lies within
the first `--depot-sample` sets, restricting the solvers to those sets loses none of the published best solutions.

    python3 tools/pmedian_rank_study.py --published <RLHEA clone>/solutions [--out reference/pmedian_rank_of_published_depot_sets.csv]

Published files that do not reproduce the registry BKS (truncated / empty / different instance) are skipped.
"""
from __future__ import annotations
import argparse, csv, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tools'))
from llrp_framework import core, heuristics as H          # noqa: E402
from indep_check import parse_dat, parse_published, latency   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--published', required=True)
    ap.add_argument('--out', default=None)
    ap.add_argument('--sample', type=int, default=50, help='the --depot-sample of the solvers (default 50)')
    a = ap.parse_args()
    rows = []
    for r in csv.DictReader(open(ROOT / 'reference' / 'LLRP_reference.csv')):
        f = Path(a.published) / r['published_file']
        d = parse_dat(ROOT / 'data' / r['group'] / r['file'])
        try:
            routes = parse_published(f, d['n'], d['m'])
        except Exception:
            continue
        if not routes or sorted(c for _, s in routes for c in s) != list(range(d['n'])): continue
        if abs(latency(d, routes) - float(r['bks'])) / float(r['bks']) > 1e-4: continue
        S = tuple(sorted({dp for dp, s in routes if s})); p = int(r['p']); m = int(r['m'])
        inst = core.read_dat(ROOT / 'data' / r['group'] / r['file'])
        rk = H._pmedian_ranking(inst, p)
        rank = rk.index(S) + 1 if (len(S) == p and S in rk) else ''
        rows.append(dict(name=r['name'], n=r['n'], m=m, p=p, depots_used=len(S), subsets=math.comb(m, p), pmedian_rank=rank,
                         in_sample=(rank != '' and rank <= a.sample) or math.comb(m, p) <= a.sample))
    big = [x for x in rows if x['subsets'] > a.sample and x['pmedian_rank'] != '']
    print(f"instances with a usable published solution: {len(rows)}")
    print(f"rank 1: {sum(x['pmedian_rank'] == 1 for x in rows)}   covered by the first {a.sample} sets (or by enumeration): {sum(x['in_sample'] for x in rows)}")
    if big: print(f"C(m,p) > {a.sample}: {len(big)} instances, worst rank {max(x['pmedian_rank'] for x in big)}")
    if a.out:
        with open(a.out, 'w', newline='') as fh:
            w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    main()
