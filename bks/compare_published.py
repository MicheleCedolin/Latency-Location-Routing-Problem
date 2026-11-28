#!/usr/bin/env python3
"""Compare per-instance results of this repository with the published algorithms (standard library only).

Input: one or more `summary.csv` files written by the experiment scripts (columns instance, best, mean, cpu_mean, ...; the
`<family>/<tag>/summary.csv` of `cpp/run_final.sh`, `cpp/run_config.sh`, `study_results/*`).  The published values are read from
`literature_results.csv`; all gaps are relative to the best-known values of `LLRP_BKS.csv`:   gap = 100 (x - BKS) / BKS.

Output: per family and overall (over the instances that are in the input)
  * mean gap of our best run and of our mean, and the same for every published algorithm (Best, Avg);
  * number of instances at the BKS (<= BKS + 0.005);
  * win / tie / loss of our *best* against the *best* of each published algorithm, and of our *mean* against its *Avg*
    (a tie is a difference of at most 0.005, the published values have two decimals);
  * mean published time vs. mean CPU time per run of ours.
Published times come from other machines, run counts and stopping rules (see bks/README.md); they are context, not a speed comparison.

If an instance occurs in several input files, the last file wins.  Prins 50-5-2BIS-5 is reported with its --atmost runs in the manuscript: pass the summary.csv of
study_results/atmost_50-5-2BIS-5.tar.gz (results_atmost/summary.csv) after the summary files of final_1x_tuned.tar.gz.

Usage:
  python3 bks/compare_published.py study_results_extracted/results_final/*/tuned/summary.csv results_atmost/summary.csv
  python3 bks/compare_published.py summary.csv --per-instance per_instance.csv --only-n-ge 75
"""
import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 0.005
ALGOS = ['MA', 'GBILS', 'SA-VND0', 'SA-VND1', 'SA-VND2', 'M-ILS', 'RLHEA', 'MS-VNS']
# GBILS values of Christofides69 50x5 / 75x10 / 100x10 belong to another variant of the instance (see README.md): left out of the comparison
GBILS_UNMATCHED = {('Ch50-5', 'GBILS'), ('Ch75-10', 'GBILS'), ('Ch100-10', 'GBILS')}


def gap(x, bks):
    return 100.0 * (x - bks) / bks


def load_ours(paths):
    ours = {}
    for p in paths:
        for r in csv.DictReader(open(p, newline='')):
            if not r.get('instance'):
                continue
            ours[r['instance']] = dict(best=float(r['best']), mean=float(r['mean']),
                                       cpu=float(r['cpu_mean']) if r.get('cpu_mean') else float('nan'))
    return ours


def wtl(a, b):
    if a < b - TOL:
        return 'win'
    if a > b + TOL:
        return 'loss'
    return 'tie'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('summary', nargs='+', help='summary.csv file(s) of our runs')
    ap.add_argument('--only-n-ge', type=int, default=0, help='restrict to instances with at least this many customers')
    ap.add_argument('--per-instance', help='write a per-instance CSV (ours and published gaps) to this file')
    ap.add_argument('--algos', default=','.join(ALGOS), help='published algorithms to include (default: all)')
    a = ap.parse_args()
    algos = [s for s in a.algos.split(',') if s]

    reg = {r['instance']: r for r in csv.DictReader(open(os.path.join(HERE, 'LLRP_BKS.csv'), newline=''))}
    lit = defaultdict(dict)
    for r in csv.DictReader(open(os.path.join(HERE, 'literature_results.csv'), newline='')):
        if (r['instance'], r['algorithm']) in GBILS_UNMATCHED:
            continue
        lit[r['instance']][r['algorithm']] = r
    ours = load_ours(a.summary)
    unknown = sorted(set(ours) - set(reg))
    if unknown:
        sys.exit(f'instances not in LLRP_BKS.csv: {unknown}')
    inst = [k for k in reg if k in ours and int(reg[k]['n']) >= a.only_n_ge]
    if not inst:
        sys.exit('no instance of the input is in the selected set')

    groups = [(f, [k for k in inst if reg[k]['family'] == f]) for f in ('barreto', 'prins', 'tuzun')]
    groups = [(f, ks) for f, ks in groups if ks] + [('ALL', inst)]

    rows = []
    for k in inst:
        b = float(reg[k]['bks'])
        d = dict(instance=k, family=reg[k]['family'], n=reg[k]['n'], bks=reg[k]['bks'],
                 ours_best=ours[k]['best'], ours_mean=ours[k]['mean'], ours_cpu=ours[k]['cpu'],
                 ours_gap_best=gap(ours[k]['best'], b), ours_gap_mean=gap(ours[k]['mean'], b))
        for al in algos:
            r = lit[k].get(al)
            d[al + '_best'] = float(r['best']) if r and r['best'] else ''
            d[al + '_avg'] = float(r['avg']) if r and r['avg'] else ''
            d[al + '_time'] = float(r['time_s']) if r and r['time_s'] else ''
        rows.append(d)
    byk = {d['instance']: d for d in rows}

    def mean(v):
        v = [x for x in v if x != '' and x == x]
        return statistics.fmean(v) if v else float('nan')

    print(f'{len(inst)} instances; gap in % to the BKS of LLRP_BKS.csv; negative = better than the BKS')
    print('\nOurs (columns: gap of best run | gap of mean | instances with best at BKS | mean CPU s per run)')
    for f, ks in groups:
        hit = sum(1 for k in ks if ours[k]['best'] <= float(reg[k]['bks']) + TOL)
        print(f'  {f:8s} n={len(ks):2d}  {mean([byk[k]["ours_gap_best"] for k in ks]):7.3f} | {mean([byk[k]["ours_gap_mean"] for k in ks]):7.3f} | '
              f'{hit:2d}/{len(ks):2d} | {mean([byk[k]["ours_cpu"] for k in ks]):8.1f}')

    print('\nPublished algorithms on the same instances (gap of Best | gap of Avg | at BKS | mean published time s | '
          'ours best vs their Best  W/T/L | ours mean vs their Avg  W/T/L)')
    for f, ks in groups:
        print(f'  [{f}]')
        for al in algos:
            ik = [k for k in ks if byk[k][al + '_best'] != '']
            if not ik:
                continue
            gb = mean([gap(byk[k][al + '_best'], float(reg[k]['bks'])) for k in ik])
            ia = [k for k in ik if byk[k][al + '_avg'] != '']
            ga = mean([gap(byk[k][al + '_avg'], float(reg[k]['bks'])) for k in ia]) if ia else float('nan')
            hit = sum(1 for k in ik if byk[k][al + '_best'] <= float(reg[k]['bks']) + TOL)
            tm = mean([byk[k][al + '_time'] for k in ik])
            wb = [wtl(ours[k]['best'], byk[k][al + '_best']) for k in ik]
            wa = [wtl(ours[k]['mean'], byk[k][al + '_avg']) for k in ia]
            c = lambda w: f'{w.count("win")}/{w.count("tie")}/{w.count("loss")}'
            print(f'    {al:8s} n={len(ik):2d}  {gb:7.3f} | {ga:7.3f} | {hit:2d}/{len(ik):2d} | {tm:8.1f} | {c(wb):>9s} | {c(wa) if wa else "-":>9s}')
    print('\nNote: published times are measured on other hardware with the run counts and stopping rules of the original papers; '
          'they are not comparable with the CPU-time budgets of this repository.')

    if a.per_instance:
        with open(a.per_instance, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
        print(f'per-instance table: {a.per_instance}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
