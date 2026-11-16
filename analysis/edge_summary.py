#!/usr/bin/env python3
"""Markdown summary of edge_granularity.py (edge_granularity_instances.csv, edge_diff_instances.csv) and edge_candidates.py output.
Usage: edge_summary.py GRANULARITY_DIR [CANDIDATE_DIR ...] > summary.md"""
import csv
import statistics as st
import sys
from pathlib import Path

g = Path(sys.argv[1])
R = list(csv.DictReader(open(g / 'edge_granularity_instances.csv')))
by = {(r['group'], r['instance']): r for r in R}
F = lambda r, k: float(r[k])
print('# Edge structure of the final solutions versus the published solutions of Zou et al.\n')
print('Neighbour rank of an edge = min over its two ends of the position of the other end in the end\'s distance-ordered customer list. '
      'delta* = largest rank in a solution. Groups: `<alg>_best` = best run of each instance, `<alg>_all` = all runs. Paired with Zou on the common instances.\n')
print('| group | instances | rank>10 % | rank>20 % | rank>30 % | delta* mean | delta* median | Zou rank>20 % (same instances) | Zou delta* mean |\n|---|---|---|---|---|---|---|---|---|')
for grp in sorted({r['group'] for r in R if r['group'] != 'ZOU_best'}):
    inst = sorted(i for (gg, i) in by if gg == grp and ('ZOU_best', i) in by)
    if not inst:
        continue
    key = 'max_either' if grp.endswith('_best') else 'delta_star_mean'
    m = lambda gg, k: 100 * st.mean(F(by[(gg, i)], k) for i in inst)
    print('| %s | %d | %.2f | %.2f | %.2f | %.1f | %.0f | %.2f | %.1f |' % (
        grp, len(inst), m(grp, 'out_either_10'), m(grp, 'out_either_20'), m(grp, 'out_either_30'),
        st.mean(F(by[(grp, i)], key) for i in inst), st.median(F(by[(grp, i)], key) for i in inst),
        m('ZOU_best', 'out_either_20'), st.mean(F(by[('ZOU_best', i)], 'max_either') for i in inst)))
D = list(csv.DictReader(open(g / 'edge_diff_instances.csv')))
print('\n## Zou edges (directed) found in our runs\n')
print('| algorithm | instances | Zou edges | in the best run % | in at least one run % | in no run | of those: rank>20 % | found edges: rank>20 % |\n|---|---|---|---|---|---|---|---|')
for alg in sorted({d['alg'] for d in D}):
    rs = [d for d in D if d['alg'] == alg]
    tot = sum(F(d, 'n_zou_edges') for d in rs)
    miss = sum(F(d, 'n_miss_any_dir') for d in rs)
    print('| %s | %d | %d | %.1f | %.2f | %d | %.1f | %.2f |' % (
        alg, len(rs), tot, 100 * sum(F(d, 'n_in_best') for d in rs) / tot, 100 * (1 - miss / tot), miss,
        100 * sum(F(d, 'out20_miss_any_dir') for d in rs) / max(miss, 1), 100 * sum(F(d, 'out20_in_any') for d in rs) / max(sum(F(d, 'n_in_any') for d in rs), 1)))
for c in sys.argv[2:]:
    p = Path(c) / 'edge_candidates_instances.csv'
    if not p.exists():
        continue
    C = list(csv.DictReader(open(p)))
    print('\n## Candidate edge sets (%s): coverage of the Zou edges versus size (undirected pairs per customer)\n' % c)
    print('| candidate set | coverage % | size | coverage n=200 % |\n|---|---|---|---|')
    names = []
    for r in C:
        if r['cand'] not in names:
            names.append(r['cand'])
    for nm in names:
        rr = [r for r in C if r['cand'] == nm]
        r2 = [r for r in rr if r['cls'] == '200']
        print('| %s | %.2f | %.1f | %s |' % (nm, 100 * st.mean(F(r, 'coverage') for r in rr), st.mean(F(r, 'size_per_cust') for r in rr),
                                              '%.2f' % (100 * st.mean(F(r, 'coverage') for r in r2)) if r2 else '-'))
