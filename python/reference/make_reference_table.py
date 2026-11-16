"""Writes reference/LLRP_reference.csv: one row per LLRP benchmark instance (76 = Tuzun-Burke 36 + Prodhon 30 + Barreto 10).

K (fleet bound N_v), p (open-depot bound N_d) and bks (best-known latency) are the values transcribed from the benchmark tables
(see ref_raw.py); n, m, Q, total demand and the minimum number of depots by capacity are read from the .dat files here.
Validation of K, p and bks: tools/indep_check.py recomputes the 76 published solutions of Zou et al. (2024) from scratch.

    python3 reference/make_reference_table.py
"""
import csv, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'tools'))
import ref_raw
from indep_check import parse_dat

def published_name(group, name):
    return (name.replace('-', '_') if group == 'B' else name) + '.txt'

def main():
    rows = []
    for g, nm, iid, n, m, K, p, bks in ref_raw.rows():
        d = parse_dat(HERE.parent / 'data' / g / (iid + '.dat'))
        assert (d['n'], d['m']) == (n, m), (nm, d['n'], d['m'])
        tot = sum(d['dem'])
        caps = sorted(d['cap'], reverse=True); s = 0.0; k = 0
        while s < tot - 1e-9: s += caps[k]; k += 1
        rows.append(dict(group=g, name=nm, instance=iid, file=iid + '.dat', published_file=published_name(g, nm), n=n, m=m, Q=int(d['Q']),
                         total_demand=int(tot), min_vehicles=math.ceil(tot / d['Q']), min_depots_by_capacity=k, K=K, p=p, bks=bks))
    with open(HERE / 'LLRP_reference.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    print(len(rows), 'rows written')

if __name__ == '__main__':
    main()
