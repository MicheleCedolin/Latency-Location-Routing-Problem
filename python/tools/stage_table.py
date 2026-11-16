#!/usr/bin/env python3
"""Per-method result table of one finished stage (standard library only).

    python3 tools/stage_table.py analysis/llrp_campaign/P20_60s_30seeds            # reads <dir>/report.csv (collect.py), else all summary.csv
    python3 tools/stage_table.py <dir> --hit-pct 0.01 --out <dir>

Definitions (all gaps are 100*(objective - reference_best)/reference_best with the registry BKS of the instance):
  mean_gap   mean over the instances of the instance mean gap (every instance has the same weight, whatever the number of seeds)
  best_gap   mean over the instances of the best gap found by any seed of the method
  hits       runs with gap <= --hit-pct (default 0.01 %) / runs
  passes     mean number of depot-subset passes (a method that spends the whole budget on the first subsets shows passes ~ 1)
  overrun    largest budget_overrun_s of the method (wall-clock time above the limit)
Rows are sorted by mean_gap. This is a descriptive table; the ranking tests are in tools/rank_stats.py.
Writes stage_table_by_method.csv and stage_table_by_instance.csv into --out (default: the stage folder).
"""
from __future__ import annotations
import argparse, csv, statistics, sys
from collections import defaultdict
from pathlib import Path


def num(x, default=None):
    try:
        v = float(x)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


def load(run: Path):
    rep = run / 'report.csv'
    files = [rep] if rep.is_file() else sorted(run.rglob('summary.csv'))
    rows = []
    for f in files:
        with f.open(newline='') as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run', type=Path)
    ap.add_argument('--hit-pct', type=float, default=0.01)
    ap.add_argument('--out', type=Path, default=None)
    a = ap.parse_args()
    rows = [r for r in load(a.run) if (r.get('status') or 'ok') == 'ok' and num(r.get('objective')) is not None]
    if not rows:
        print('stage_table: no result rows found')
        return 1
    cfgs = defaultdict(set)
    for r in rows:
        cfgs[r['heuristic']].add((r.get('local_search', ''), r.get('neighborhoods', '')))
    def label(r):
        h = r['heuristic']
        return h if len(cfgs[h]) == 1 else f"{h}[{r.get('local_search','')}/{r.get('neighborhoods','')}]"
    cell = defaultdict(list)
    for r in rows:
        ref = num(r.get('reference_best'))
        obj = num(r.get('objective'))
        gap = num(r.get('gap_pct'))
        if gap is None and ref:
            gap = 100.0 * (obj - ref) / ref
        if gap is None:
            continue
        cell[(label(r), r['instance'])].append(dict(
            gap=gap, ttb=num(r.get('time_to_best_s')), trials=num(r.get('trials')), passes=num(r.get('passes')),
            over=num(r.get('budget_overrun_s'), 0.0), seed=r.get('seed')))
    methods = sorted({m for m, _ in cell})
    insts = sorted({i for _, i in cell})

    by_inst = []
    for (m, i), v in sorted(cell.items()):
        g = [x['gap'] for x in v]
        by_inst.append(dict(method=m, instance=i, runs=len(v), mean_gap=statistics.mean(g), best_gap=min(g), worst_gap=max(g),
                            sd_gap=statistics.pstdev(g), hits=sum(x <= a.hit_pct for x in g)))
    by_m = []
    for m in methods:
        cells = [cell[(m, i)] for i in insts if (m, i) in cell]
        allv = [x for c in cells for x in c]
        def mean_of(key):
            xs = [x[key] for x in allv if x[key] is not None]
            return statistics.mean(xs) if xs else float('nan')
        by_m.append(dict(
            method=m, instances=len(cells), runs=len(allv),
            mean_gap=statistics.mean(statistics.mean(x['gap'] for x in c) for c in cells),
            best_gap=statistics.mean(min(x['gap'] for x in c) for c in cells),
            hits=sum(x['gap'] <= a.hit_pct for x in allv),
            time_to_best_s=mean_of('ttb'), trials=mean_of('trials'), passes=mean_of('passes'),
            overrun_max_s=max(x['over'] for x in allv)))
    by_m.sort(key=lambda r: r['mean_gap'])

    out = a.out or a.run
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (('stage_table_by_method.csv', by_m), ('stage_table_by_instance.csv', by_inst)):
        with (out / name).open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)

    print(f"stage table | {a.run} | {len(rows)} runs, {len(insts)} instances, {len(methods)} methods | hit = gap <= {a.hit_pct} %")
    print(f"{'method':10} {'runs':>5} {'mean_gap%':>9} {'best_gap%':>9} {'hits':>11} {'t_best_s':>8} {'trials':>8} {'passes':>7} {'overrun_s':>9}")
    for r in by_m:
        print(f"{r['method']:10} {r['runs']:5d} {r['mean_gap']:9.3f} {r['best_gap']:9.3f} {r['hits']:5d}/{r['runs']:<5d} "
              f"{r['time_to_best_s']:8.1f} {r['trials']:8.0f} {r['passes']:7.1f} {r['overrun_max_s']:9.2f}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
