#!/usr/bin/env python3
"""Consistency check of bks/literature_results.csv against bks/LLRP_BKS.csv (standard library only).

Checks
  1. every one of the 76 instances is present and spelled as in LLRP_BKS.csv;
  2. n, m and Nv of every row equal the registry values;
  3. every instance has the seven algorithms MA, SA-VND0, SA-VND1, SA-VND2, M-ILS, RLHEA, MS-VNS;
     GBILS exists only for the Barreto and Prins instances (8 of the 10 Barreto instances);
  4. the best-known value of the registry equals the smallest published 'best' within 0.005 (values have two decimals),
     except for the documented differences below;
  5. no published average is below the published best of the same row by more than 0.01 (both are printed with two decimals
     and were rounded independently), no time is negative.

Exit code 0 = all checks passed.   Usage:  python3 bks/check_literature.py
"""
import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = ['MA', 'SA-VND0', 'SA-VND1', 'SA-VND2', 'M-ILS', 'RLHEA', 'MS-VNS']
# registry BKS differs from the smallest published best (see bks/README.md)
DOCUMENTED = {
    'Or117-14': 'registry 53798.53 (reproduced independently; the supplement prints 53798.5)',
    '20-5-1b-5': 'registry 608.05 (Zou et al. 2024; the unrounded value is 608.055), supplement 608.06',
    'Mi27-5': 'registry 5387.55 (six algorithms and our runs, 5387.5451); GBILS (Table 6) prints 5387.54',
}


def main():
    reg = {r['instance']: r for r in csv.DictReader(open(os.path.join(HERE, 'LLRP_BKS.csv'), newline=''))}
    lit = list(csv.DictReader(open(os.path.join(HERE, 'literature_results.csv'), newline='')))
    errors = []
    per = defaultdict(dict)
    for r in lit:
        k = r['instance']
        if k not in reg:
            errors.append(f'unknown instance {k}')
            continue
        g = reg[k]
        if (r['family'], int(r['n']), int(r['m']), int(r['Nv'])) != (g['family'], int(g['n']), int(g['m_depots']), int(g['Nv_max_routes'])):
            errors.append(f'{k}: family/n/m/Nv differ from LLRP_BKS.csv')
        if r['algorithm'] in per[k]:
            errors.append(f'{k}: duplicate row for {r["algorithm"]}')
        per[k][r['algorithm']] = r
        best = float(r['best'])
        if r['avg'] and float(r['avg']) < best - 0.0101:
            errors.append(f'{k}/{r["algorithm"]}: avg {r["avg"]} < best {r["best"]}')
        if r['time_s'] and float(r['time_s']) < 0:
            errors.append(f'{k}/{r["algorithm"]}: negative time')
    missing = sorted(set(reg) - set(per))
    if missing:
        errors.append(f'instances without literature rows: {missing}')
    n_gbils = 0
    for k, d in per.items():
        for a in CORE:
            if a not in d:
                errors.append(f'{k}: algorithm {a} missing')
        if 'GBILS' in d:
            n_gbils += 1
            if reg[k]['family'] == 'tuzun':
                errors.append(f'{k}: GBILS is not defined for Tuzun-Burke instances')
        lo = min(float(r['best']) for r in d.values())
        diff = float(reg[k]['bks']) - lo
        if abs(diff) > 0.005 + 1e-9 and k not in DOCUMENTED:
            errors.append(f'{k}: registry BKS {reg[k]["bks"]} vs smallest published best {lo:.2f} (diff {diff:+.2f})')
    if n_gbils != 38:
        errors.append(f'expected GBILS rows for 38 instances, found {n_gbils}')
    if errors:
        print('FAILED:')
        for e in errors:
            print('  -', e)
        return 1
    print(f'OK: {len(lit)} rows, {len(per)} instances, {n_gbils} with GBILS; '
          f'{len(DOCUMENTED)} documented BKS differences ({", ".join(sorted(DOCUMENTED))}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
