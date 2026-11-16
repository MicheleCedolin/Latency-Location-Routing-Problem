#!/usr/bin/env python3
"""Post-hoc local-search polish of finished runs (no re-run, search logic untouched).

Reads the `report.csv` written by collect.py (one row per finished run, column `solution_routes` holds the final
best solution), applies one local-search module to every solution and writes the before/after comparison.

    python3 tools/polish_report.py --report analysis/phaseA_P20_60s_30seeds/report.csv \
            --ls vnd --preset common5 --workers 15 --out analysis/phaseA_P20_60s_30seeds/polish_vnd_common5

Outputs (in --out): polished_report.csv (all input columns + polish columns), polish_by_heuristic.csv,
polish_by_instance_heuristic.csv, polish_settings.txt.

What this is and is not
  * It is a *post-processing stage*: result of the metaheuristic -> one deterministic local-search descent.
    It is NOT the same as Phase B (local search embedded inside every method, which changes the trajectory and needs a new run).
  * The polish time is NOT part of the run's time budget; it is reported separately (polish_s).
  * Integrity: before polishing, the objective of the stored routes is recomputed and must equal the reported `objective`
    (rows that do not match are listed with polish_status = 'objective_mismatch' and are not polished).
  * `vnd`, `first`, `best` are deterministic. `rvnd` draws its neighbourhood order from random.Random(seed of the run).
  * The tool never writes into the run folders; the framework source (and therefore config_id / fingerprint of the runs) is unchanged.
"""
from __future__ import annotations
import argparse, csv, math, multiprocessing as mp, pathlib, random, sys, time

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
from llrp_framework import core  # noqa: E402
from llrp_framework.core import Route  # noqa: E402
from llrp_framework.local_search import run_local_search  # noqa: E402
from llrp_framework.neighborhoods import PRESETS  # noqa: E402
from llrp_framework.params import REGISTERED  # noqa: E402

_INST = {}


def _instance(name):
    if name not in _INST:
        prm = REGISTERED[name]
        _INST[name] = core.read_dat(KIT / 'data' / prm['family'] / prm['file'])
    return _INST[name]


def parse_routes(text):
    """'d0:3-5-9|d2:1-4' -> [Route(0,[3,5,9]), Route(2,[1,4])] (depot index, customer indices as written by run_llrp)."""
    out = []
    for part in text.split('|'):
        d, seq = part.split(':')
        out.append(Route(int(d[1:]), [int(x) for x in seq.split('-')], 0.0))
    return out


def fmt_routes(sol):
    return '|'.join(f"d{r.depot}:{'-'.join(map(str, r.seq))}" for r in sorted(sol, key=lambda r: (r.depot, r.seq)) if r.seq)


def polish_one(job):
    idx, row, ls, preset, max_s = job
    res = dict(idx=idx, polish_status='ok')
    try:
        inst = _instance(row['instance'])
        sol = core.normalize(inst, parse_routes(row['solution_routes']))
        z0 = core.objective(inst, sol)
        K0, p0 = REGISTERED[row['instance']]['K'], REGISTERED[row['instance']]['p']          # LLRP: binding fleet and open-depot bounds
        if abs(z0 - float(row['objective'])) > 1e-6 or not core.feasible(inst, sol, K0, p0):
            res.update(polish_status='objective_mismatch', polish_check_z=z0)
            return res
        t0 = time.perf_counter()
        s2, z2, moves = run_local_search(ls, inst, sol, K0, p0, tuple(range(inst.m)), preset,
                                         random.Random(int(row['seed'])), time.perf_counter() + max_s)
        dt = time.perf_counter() - t0
        s2 = core.normalize(inst, s2)
        z2 = core.objective(inst, s2)
        if not core.feasible(inst, s2, K0, p0) or z2 > z0 + 1e-9:   # never report worse / infeasible
            s2, z2 = sol, z0
        ref = float(row['reference_best'])
        used = sorted(core.used_depots(s2))
        res.update(objective_polished=z2, gap_polished_pct=(z2 - ref) / ref * 100.0, hit_polished=bool(z2 <= ref + float(row.get('reference_tol') or 0.01)),
                   routes_polished=len([r for r in s2 if r.seq]), open_depot_ids_polished=';'.join(map(str, used)),
                   ls_moves_polished=int(moves), polish_s=dt, polish_timeout=bool(dt >= max_s), improved=bool(z2 < z0 - 1e-9), solution_routes_polished=fmt_routes(s2))
    except Exception as e:  # noqa: BLE001
        res.update(polish_status=f'error:{type(e).__name__}:{e}')
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--report', required=True, type=pathlib.Path)
    ap.add_argument('--ls', default='vnd', choices=['vnd', 'rvnd', 'best', 'first'])
    ap.add_argument('--preset', default='common5', choices=sorted(PRESETS))
    ap.add_argument('--workers', type=int, default=max(1, (mp.cpu_count() or 1)))
    ap.add_argument('--max-seconds', type=float, default=60.0, help='safety cap per solution')
    ap.add_argument('--seeds', default='', help='optional seed filter, e.g. 1-10 or 1,2,3 (default: all rows)')
    ap.add_argument('--out', required=True, type=pathlib.Path)
    a = ap.parse_args()
    with a.report.open(newline='') as f:
        rows = list(csv.DictReader(f))
    keep = None
    if a.seeds:
        keep = set()
        for tok in a.seeds.split(','):
            lo, _, hi = tok.partition('-'); keep.update(range(int(lo), int(hi or lo) + 1))
    todo = [(i, r, a.ls, a.preset, a.max_seconds) for i, r in enumerate(rows)
            if r.get('status') == 'ok' and r.get('solution_routes') and (keep is None or int(r['seed']) in keep)]
    print(f'{len(rows)} rows, {len(todo)} to polish with {a.ls}/{a.preset} on {a.workers} workers', flush=True)
    t0 = time.time()
    # 'spawn' = fresh interpreters on every Python version (3.14 changed the Linux default to forkserver); each worker caches its instances
    with mp.get_context('spawn').Pool(a.workers) as pool:
        out = {}
        for k, res in enumerate(pool.imap_unordered(polish_one, todo, chunksize=8), 1):
            out[res['idx']] = res
            if k % 500 == 0:
                print(f'  {k}/{len(todo)}  {time.time() - t0:.0f}s', flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    new_cols = ['polish_ls', 'polish_preset', 'polish_status', 'polish_check_z', 'objective_polished', 'gap_polished_pct', 'hit_polished', 'routes_polished',
                'open_depot_ids_polished', 'ls_moves_polished', 'polish_s', 'polish_timeout', 'improved', 'solution_routes_polished']
    fields = list(rows[0].keys()) + new_cols
    with (a.out / 'polished_report.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for i, r in enumerate(rows):
            r = dict(r); r['polish_ls'] = a.ls; r['polish_preset'] = a.preset
            r.update({k: v for k, v in out.get(i, {'polish_status': 'skipped'}).items() if k != 'idx'})
            w.writerow(r)
    bad = [r for r in out.values() if r['polish_status'] != 'ok']
    # summaries
    import statistics as st
    def summ(keyf, name):
        groups = {}
        for i, r in enumerate(rows):
            o = out.get(i)
            if o and o['polish_status'] == 'ok':
                groups.setdefault(keyf(r), []).append((float(r['gap_pct']), o['gap_polished_pct'], str(r['reference_hit']) == 'True', o['hit_polished'], o['polish_s'], o['improved']))
        with (a.out / name).open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['group', 'runs', 'mean_gap_before_pct', 'mean_gap_after_pct', 'median_gap_after_pct', 'best_gap_after_pct', 'hit_rate_before', 'hit_rate_after', 'share_improved', 'mean_polish_s', 'max_polish_s'])
            for k, g in sorted(groups.items(), key=lambda kv: st.mean(x[1] for x in kv[1])):
                n = len(g)
                w.writerow([k if isinstance(k, str) else '|'.join(k), n, round(st.mean(x[0] for x in g), 4), round(st.mean(x[1] for x in g), 4),
                            round(st.median(x[1] for x in g), 4), round(min(x[1] for x in g), 4), round(sum(x[2] for x in g) / n, 4),
                            round(sum(x[3] for x in g) / n, 4), round(sum(x[5] for x in g) / n, 4), round(st.mean(x[4] for x in g), 4), round(max(x[4] for x in g), 4)])
    summ(lambda r: r['heuristic'] + ('+' + r['local_search'] if r['local_search'] != 'none' else ''), 'polish_by_heuristic.csv')
    summ(lambda r: (r['instance'], r['heuristic'] + ('+' + r['local_search'] if r['local_search'] != 'none' else '')), 'polish_by_instance_heuristic.csv')
    (a.out / 'polish_settings.txt').write_text(f'report={a.report}\nls={a.ls}\npreset={a.preset}\nmax_seconds={a.max_seconds}\nrows={len(rows)}\npolished={len(out) - len(bad)}\nproblems={len(bad)}\ntimeouts={sum(1 for o in out.values() if o.get("polish_timeout"))}\nseeds={a.seeds or "all"}\nwall_s={time.time() - t0:.1f}\n')
    n_to = sum(1 for o in out.values() if o.get('polish_timeout'))
    print(f'done in {time.time() - t0:.0f}s; polished {len(out) - len(bad)}, problems {len(bad)}, hit the {a.max_seconds:.0f}s cap: {n_to}; wrote {a.out}')
    if n_to: print('  note: capped solutions keep the best point reached (still valid); raise --max-seconds to let them finish')
    for b in bad[:10]:
        print('  problem:', b)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
