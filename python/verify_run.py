#!/usr/bin/env python3
"""Audit a results folder. Two questions: is every stored result correct, and is the campaign complete?

    python3 verify_run.py analysis/<run folder> [--manifest jobs.txt | --no-manifest] [--allow-extra] [--kit-root .]

Completeness. The launcher writes <run folder>/jobs.txt (one line per expected job: instance method local_search
neighbourhoods seed). Every expected job must have: exit_code.txt = 0, exactly one matching row in its summary.csv,
trajectory.csv, config.json whose fingerprint equals the one in the summary row and, when the run has status ok, exactly
one *.solution.json. A run that finished without a reportable incumbent carries an explicit status
(no_incumbent_within_budget / no_solution) and is listed, not silently dropped. Result files of jobs that are not in the
manifest are an error unless --allow-extra is given. Without a manifest completeness cannot be established, so the
audit refuses to pass unless --no-manifest is given (then only the stored solutions are checked, as in earlier versions).

Correctness. For each stored solution: feasible (indices validated first), objective recomputed from the .dat file equals
the reported objective, route and depot costs add up, open-depot list and summary columns agree with the solution, every
checkpoint solution reproduces its checkpoint objective, and the BKS flags follow the one-sided rule
hit = objective <= reference + tol, beats = objective < reference - tol.
"""
import argparse, csv, json, math
from pathlib import Path
from llrp_framework.core import Route, read_dat, feasible, objective
from llrp_framework.params import REGISTERED


def close(a, b, tol=1e-7):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def routes_of(records):
    return [Route(r['depot'], list(r['customers']), r['load']) for r in records]


def number(x):
    try:
        return float(x) if x not in (None, '') else None
    except ValueError:
        return None


def check(root, path, rows_override=None):
    err = []
    d = json.loads(path.read_text())
    prm = REGISTERED[d['instance']]
    inst = read_dat(root / 'data' / prm['family'] / prm['file'], depot_capacity=d.get('depot_capacity', 'ignore'))
    K, p = d['K'], d['p']                       # the bounds the run declared (registry values unless --K / --p were given)
    sol = routes_of(d['routes'])
    if not feasible(inst, sol, K, p):
        # Do not evaluate an infeasible (possibly out-of-range) solution: array reads would be meaningless.
        return ['stored solution is infeasible (coverage, capacity, bounds or index range)']
    z = objective(inst, sol)
    if not close(z, d['objective']):
        err.append(f"objective {d['objective']} != recomputed {z}")
    if d['open_depots'] != sorted({r.depot for r in sol}):
        err.append('open_depots does not match the routes')
    total = sum(r['cost'] for r in d['routes']) + sum(x.get('opening_cost', 0.0) for x in d['depots'])
    if not close(total, z):
        err.append(f'route and depot costs add up to {total}, objective is {z}')
    limit = d.get('time_limit_s')
    if d['time_to_best_s'] is None or d['time_to_best_s'] < 0.0 or (limit is not None and d['time_to_best_s'] > limit + 1e-6):
        err.append(f"time_to_best_s {d['time_to_best_s']} outside [0, time limit]")
    ref, tol = d['reference_best'], d['reference_tol']
    if d['reference_hit'] != (z <= ref + tol) or d['beats_reference'] != (z < ref - tol):
        err.append('reference_hit / beats_reference do not follow the one-sided rule')
    for lab, c in d['checkpoints'].items():
        if c is None:
            continue
        cs = routes_of(c['routes'])
        if not feasible(inst, cs, K, p):
            err.append(f'checkpoint {lab}: infeasible solution')
        elif not close(objective(inst, cs), c['objective']):
            err.append(f"checkpoint {lab}: objective {c['objective']} != recomputed {objective(inst, cs)}")
        if c['objective'] < z - 1e-7:
            err.append(f'checkpoint {lab} is better than the final solution')
    rows = rows_override
    if rows is None:
        rows = []
        summary = path.parent / 'summary.csv'
        if summary.exists():
            with summary.open(newline='') as f:
                rows = [r for r in csv.DictReader(f) if r['instance'] == d['instance'] and int(r['seed']) == d['seed']
                        and r['heuristic'] == d['heuristic'] and r['local_search'] == d['local_search']
                        and r['neighborhoods'] == d['neighborhoods']]
    if len(rows) != 1:
        err.append(f'expected exactly one matching summary.csv row, found {len(rows)}')
    else:
        r = rows[0]
        if r.get('status', 'ok') != 'ok':
            err.append(f"summary status is {r.get('status')} but a solution file exists")
        if not close(float(r['objective']), z):
            err.append(f"summary objective {r['objective']} != solution objective {z}")
        if r['open_depot_ids'] != ';'.join(map(str, d['open_depots'])):
            err.append('summary open_depot_ids differs from solution.json')
        if int(r['routes']) != len(d['routes']) or int(r['open_depots']) != len(d['open_depots']):
            err.append('summary route / depot counts differ from solution.json')
        if r['solution_routes'] != '|'.join(f"d{x['depot']}:" + '-'.join(map(str, x['customers'])) for x in d['routes']):
            err.append('summary solution_routes differs from solution.json')
        if d.get('config_id') is not None and r.get('config_id') not in (None, '', d['config_id']):
            err.append('summary config_id differs from solution.json')
        for lab, c in d['checkpoints'].items():
            col = number(r.get(f'objective_{lab}s'))
            if (c is None) != (col is None) or (c is not None and not close(c['objective'], col)):
                err.append(f'checkpoint {lab}: summary objective {col} differs from solution.json')
    return err


def read_manifest(path):
    jobs = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts or parts[0].startswith('#'):
            continue
        if len(parts) != 5:
            raise ValueError(f'bad manifest line: {line!r}')
        jobs.append(tuple(parts[:4]) + (int(parts[4]),))
    return jobs


def job_dir(run, job):
    inst, heur, ls, neigh, seed = job
    return run / inst / f'{heur}_{ls}_{neigh}' / f'seed_{seed}'


def audit_job(root, run, job):
    """Return (outcome, messages). outcome: ok | status:<code> | missing | failed | inconsistent."""
    inst, heur, ls, neigh, seed = job
    odir = job_dir(run, job)
    if not odir.is_dir():
        return 'missing', ['run folder does not exist']
    rc_file = odir / 'exit_code.txt'
    if not rc_file.exists():
        return 'missing', ['no exit_code.txt (job did not finish)']
    rc = rc_file.read_text().strip()
    if rc != '0':
        return 'failed', [f'exit code {rc}']
    msgs = []
    summary = odir / 'summary.csv'
    all_rows = []
    if summary.exists():
        with summary.open(newline='') as f:
            all_rows = list(csv.DictReader(f))
    # One job folder = one run = exactly one summary row, and it must be this job's (a stray row, e.g. another
    # seed, would be picked up by collect.py).
    rows = [r for r in all_rows if r['instance'] == inst and r['heuristic'] == heur and r['local_search'] == ls
            and r['neighborhoods'] == neigh and int(r['seed']) == seed]
    if len(all_rows) != 1 or len(rows) != 1:
        return 'inconsistent', [f'expected exactly one summary row (this job), found {len(all_rows)} row(s), {len(rows)} for this job']
    row = rows[0]
    for name in ('trajectory.csv', 'config.json'):
        if not (odir / name).exists():
            msgs.append(f'{name} missing')
    cfg = odir / 'config.json'
    if cfg.exists():
        fp = json.loads(cfg.read_text()).get('fingerprint')
        if row.get('fingerprint') not in (None, '') and fp != row['fingerprint']:
            msgs.append('config.json fingerprint differs from the summary row')
    status = row.get('status', 'ok')
    sols = sorted(odir.glob('*.solution.json'))
    if status == 'ok':
        if len(sols) != 1:
            msgs.append(f'status ok but {len(sols)} solution files')
        else:
            msgs += check(root, sols[0], rows_override=[row])
        return ('inconsistent' if msgs else 'ok'), msgs
    if row.get('objective') not in (None, ''):
        msgs.append(f'status {status} but the row carries an objective')
    return ('inconsistent' if msgs else f'status:{status}'), msgs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run', type=Path)
    ap.add_argument('--kit-root', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--manifest', type=Path, default=None, help='expected jobs (default: <run>/jobs.txt)')
    ap.add_argument('--no-manifest', action='store_true', help='check stored solutions only; completeness is NOT established')
    ap.add_argument('--allow-extra', action='store_true', help='do not fail on result folders that are not in the manifest')
    a = ap.parse_args()
    root = a.kit_root.resolve(); run = a.run.resolve()
    if a.no_manifest:
        files = sorted(run.rglob('*.solution.json'))
        bad = 0
        for path in files:
            errs = check(root, path)
            if errs:
                bad += 1
                print(f'FAIL {path}')
                for e in errs:
                    print('   ', e)
        print(f'verify_run: {len(files)} solutions checked, {bad} inconsistent  (no manifest: completeness NOT established)')
        raise SystemExit(1 if bad or not files else 0)
    manifest = a.manifest or (run / 'jobs.txt')
    if not manifest.exists():
        print(f'verify_run: no manifest at {manifest}; completeness cannot be established (use --manifest or --no-manifest)')
        raise SystemExit(2)
    jobs = read_manifest(manifest)
    dupes = len(jobs) - len(set(jobs))
    counts = {}
    problems = 0
    for job in jobs:
        outcome, msgs = audit_job(root, run, job)
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome in ('missing', 'failed', 'inconsistent'):
            problems += 1
            print(f'{outcome.upper():12s} {job_dir(run, job)}')
            for m in msgs:
                print('   ', m)
        elif outcome.startswith('status:'):
            print(f'NOTE         {job_dir(run, job)}: {outcome[7:]}')
    expected_dirs = {job_dir(run, j).resolve() for j in jobs}
    extra = []
    for path in sorted(run.rglob('summary.csv')):
        if path.parent.resolve() not in expected_dirs and path.parent.resolve() != run:
            extra.append(path.parent)
    if extra and not a.allow_extra:
        problems += len(extra)
        for e in extra:
            print(f'UNEXPECTED   {e}: result folder is not in the manifest')
    if dupes:
        problems += dupes
        print(f'manifest lists {dupes} job(s) twice')
    ok = counts.get('ok', 0)
    nostat = sum(v for k, v in counts.items() if k.startswith('status:'))
    print(f'verify_run: expected {len(jobs)} | ok {ok} | explicit non-ok status {nostat} | missing {counts.get("missing", 0)} | '
          f'failed {counts.get("failed", 0)} | inconsistent {counts.get("inconsistent", 0)} | unexpected {0 if a.allow_extra else len(extra)}')
    raise SystemExit(1 if problems or not jobs else 0)


if __name__ == '__main__':
    main()
