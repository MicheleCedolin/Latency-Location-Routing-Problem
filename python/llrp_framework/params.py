"""LLRP instance registry: the 76 benchmark instances, with the fleet bound K (N_v) and the open-depot bound p (N_d).

The registry is read from reference/LLRP_reference.csv (written by reference/make_reference_table.py):
  Tuzun-Burke (T, 36 instances), Prodhon (P, 30 instances), Barreto (B, 10 instances; Or-117-14 included),
  real-valued Euclidean distances for all families. Instance ids are the file stems (coordP111112, coord50-5-1, coordChrist50, ...);
  the literature name (111112, 50-5-1, Christ-50-5, ...) is in the registry entry under 'name'.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_CSV = ROOT / 'reference' / 'LLRP_reference.csv'


def _load():
    reg = {}
    with open(REFERENCE_CSV, newline='') as fh:
        for r in csv.DictReader(fh):
            reg[r['instance']] = dict(family=r['group'], file=r['file'], name=r['name'], n=int(r['n']), m=int(r['m']), Q=int(r['Q']),
                                      K=int(r['K']), p=int(r['p']), bks=float(r['bks']), published_file=r['published_file'])
    return reg


REGISTERED = _load()

P_PARAMS = {k: v for k, v in REGISTERED.items() if v['family'] == 'P'}
B_PARAMS = {k: v for k, v in REGISTERED.items() if v['family'] == 'B'}
T_PARAMS = {k: v for k, v in REGISTERED.items() if v['family'] == 'T'}
P20_PARAMS = {k: v for k, v in P_PARAMS.items() if v['n'] == 20}
P50_PARAMS = {k: v for k, v in P_PARAMS.items() if v['n'] == 50}
P100_PARAMS = {k: v for k, v in P_PARAMS.items() if v['n'] == 100}
P200_PARAMS = {k: v for k, v in P_PARAMS.items() if v['n'] == 200}
SMALL_PARAMS = {**P20_PARAMS, **P50_PARAMS}

# Named instance groups for the launcher (INSTANCES=P20, P50, P100, P200, B, T, T100, T150, T200, ALL; combine with colons, e.g. P20:B).
GROUPS = {
    'P20': list(P20_PARAMS), 'P50': list(P50_PARAMS), 'P100': list(P100_PARAMS), 'P200': list(P200_PARAMS),
    'B': list(B_PARAMS), 'T': list(T_PARAMS),
    'T100': [i for i, v in T_PARAMS.items() if v['n'] == 100], 'T150': [i for i, v in T_PARAMS.items() if v['n'] == 150],
    'T200': [i for i, v in T_PARAMS.items() if v['n'] == 200],
    'ALL': list(REGISTERED),
}


def reference_kp(instance_id):
    """(K, p) of the instance: at most K routes, at most p open depots."""
    v = REGISTERED[instance_id]
    return v['K'], v['p']
