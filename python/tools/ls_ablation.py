#!/usr/bin/env python3
"""Post-hoc ablation of the local-search (VND) design on the stored final solutions of finished runs.

No re-run, no change of the search logic: the final solution of every finished run (column `solution_routes` of the
report.csv written by collect.py) is improved by a *configured* local search and the result is compared with other
configurations on the very same starting solutions (paired design).

A configuration = (driver, ordered list of operators). Operators are the 15 neighbourhoods of llrp_framework/neighborhoods.py,
grouped in six classes:  A intra-route (4) | B inter-route relocate (3) | C inter-route swap (4) | D tail exchange 2-opt* (2) |
E depot level (1) | F route count (1).  Drivers:
    vnd     basic sequential VND: after an improvement restart from the first neighbourhood (framework `vnd`)
    cyclic  after an improvement continue with the NEXT neighbourhood; stop after a whole cycle without improvement
    pipe    after an improvement stay in the SAME neighbourhood; stop after a whole pass without improvement
    rvnd    random neighbourhood order, list refilled and reshuffled on improvement (framework `rvnd`)
    best    steepest descent over all neighbourhoods ("union" VND, framework `best_descent`)
    first   first-improvement descent (framework `first_descent`; only 6 operators are implemented there)
(vnd, rvnd, best, first reproduce the framework functions exactly; this is checked by tests/test_ls_ablation.py.)

Stages (see ABLATION.md for the rationale and the decision rules)
    0  anchors                    5 configs   common5 / all-15 / all-15 RVND / literature 11-operator set / native first-descent
    1  class level               13 configs   leave-one-class-out from all 15 (6)  +  add-one-class to {intra_relocate1, inter_relocate1} (6 + base)
    2  within-class ladders      --keep ABCDE   nested levels of the classes retained after stage 1
    3  operator order            --set ...      canonical, 6 rule based orders, 3 random orders of one set
    4  driver / change rule      --set ...      vnd, cyclic, pipe, rvnd, best on one set (+ first vs vnd on the first-capable subset)

Sub-commands
    list       print the configurations of a stage
    profile    cost and single-scan potential of every operator on a sample of the stored solutions (needed by stage 3)
    run        run configurations (resume-safe: finished configurations are skipped)
    summarize  per-configuration tables, per-operator tables, paired contrasts with cluster-bootstrap intervals

    python3 tools/ls_ablation.py run --report analysis/phaseA_P50_120s_30seeds/report.csv --stage 0,1 --seeds 1-10 \
            --workers 15 --out analysis/phaseA_P50_120s_30seeds/ablation
    python3 tools/ls_ablation.py summarize --out analysis/phaseA_P50_120s_30seeds/ablation

Integrity: before polishing, the objective of the stored routes is recomputed and must equal the reported `objective`
(otherwise the row is flagged `objective_mismatch` and the tool exits with 1). A configuration never returns a worse or infeasible solution.
Cost is reported as the number of candidate moves evaluated (implementation independent) next to wall-clock seconds
(implementation specific: the operators recompute the whole objective, no delta evaluation, no granular pruning).
The framework source is not modified, so config_id / fingerprints of the runs are unchanged.
"""
from __future__ import annotations
import argparse, csv, json, math, multiprocessing as mp, pathlib, random, re, sys, time

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
from llrp_framework import core  # noqa: E402
from llrp_framework import local_search as LS  # noqa: E402
from llrp_framework import neighborhoods as NB  # noqa: E402
from llrp_framework.core import Route  # noqa: E402
from llrp_framework.params import REGISTERED  # noqa: E402

TOOL_VERSION = 'ls_ablation-1'
EPS = 1e-10

# ---------------------------------------------------------------------------------------------------------------------
# candidate counter: number of candidate moves handed to the acceptance step of a scan (feasible or not). Since the delta-evaluation
# layer (neighborhoods.Scan) the framework counts them itself (core._CTR[4]); the reference operators count them the same way, so the
# numbers are identical to the earlier wrapper of NB._accept / LS._accept_first. `_CNT[0]` is kept as the reading interface.
class _CandidateCounter:
    def __getitem__(self, i):
        return core._CTR[4]


_CNT = _CandidateCounter()

# ---------------------------------------------------------------------------------------------------------------------
# operators, classes, configurations
CLASSES = {
    'A': ['intra_relocate1', 'intra_relocate2', 'intra_swap11', 'intra_2opt'],
    'B': ['inter_relocate1', 'inter_relocate2', 'inter_relocate2_rev'],
    'C': ['inter_swap11', 'inter_swap21', 'inter_swap22', 'inter_swap22_rev'],
    'D': ['two_opt_star', 'two_opt_star_rev'],
    'E': ['depot_reassign'],
    'F': ['route_split'],
}
CANON = list(NB.PRESETS['hgamp'])                      # canonical (interleaved) order of the 15 operators
OP_CLASS = {op: c for c, ops in CLASSES.items() for op in ops}
assert sorted(OP_CLASS) == sorted(CANON) and len(CANON) == 15
LADDER = {                                             # nested levels used by stage 2 (simple before composite, 1-node before 2-node, plain before reversed)
    'A': ['intra_relocate1', 'intra_2opt', 'intra_swap11', 'intra_relocate2'],
    'B': ['inter_relocate1', 'inter_relocate2', 'inter_relocate2_rev'],
    'C': ['inter_swap11', 'inter_swap21', 'inter_swap22', 'inter_swap22_rev'],
    'D': ['two_opt_star', 'two_opt_star_rev'],
}
FIRST_OK = {'intra_relocate1', 'inter_relocate1', 'intra_swap11', 'inter_swap11', 'intra_2opt', 'depot_reassign',
            'intra_relocate2', 'inter_relocate2', 'inter_swap22', 'two_opt_star', 'route_split'}   # implemented in local_search._first_improving_move
LIT11 = [o for o in CANON if o not in ('inter_relocate2_rev', 'inter_swap22_rev', 'two_opt_star_rev', 'route_split')]
BASE2 = ['intra_relocate1', 'inter_relocate1']
DRIVERS = ('vnd', 'cyclic', 'pipe', 'rvnd', 'best', 'first')


def canon(ops):
    s = set(ops)
    return [o for o in CANON if o in s]


class Cfg:
    def __init__(self, name, driver, ops, stage, ref=None, note=''):
        assert driver in DRIVERS, driver
        bad = [o for o in ops if o not in OP_CLASS]
        if bad:
            raise ValueError(f'unknown operators {bad}')
        self.name, self.driver, self.ops, self.stage, self.ref, self.note = name, driver, list(ops), stage, ref, note

    def as_dict(self):
        return dict(name=self.name, driver=self.driver, ops=self.ops, stage=self.stage, ref=self.ref, note=self.note)


def stage0():
    return [
        Cfg('S0_full15_vnd', 'vnd', CANON, 0, None, 'all 15 operators, canonical order, sequential VND (reference of stage 0 and of the leave-one-class-out runs)'),
        Cfg('S0_common5_vnd', 'vnd', NB.PRESETS['common5'], 0, 'S0_full15_vnd', 'frozen Phase-B VND (5 operators)'),
        Cfg('S0_full15_rvnd', 'rvnd', CANON, 0, 'S0_full15_vnd', 'all 15, random order (ILS-RVND style driver)'),
        Cfg('S0_lit11_vnd', 'vnd', LIT11, 0, 'S0_full15_vnd', 'literature template: relocate/swap of 1-2 nodes, 2-opt, 2-opt*, depot move (no reversed variants, no route_split)'),
        Cfg('S0_baseline_first', 'first', NB.PRESETS['baseline_route'], 0, 'S0_full15_vnd', 'native Phase-A descent (first improvement, 5 moves)'),
    ]


def stage1():
    out = []
    for c in 'ABCDEF':
        out.append(Cfg(f'S1_LOCO_{c}', 'vnd', canon(set(CANON) - set(CLASSES[c])), 1, 'S0_full15_vnd', f'all 15 without class {c} ({",".join(CLASSES[c])})'))
    out.append(Cfg('S1_base2', 'vnd', canon(BASE2), 1, None, 'base set {intra_relocate1, inter_relocate1}'))
    for c in 'ABCDEF':
        out.append(Cfg(f'S1_ADD_{c}', 'vnd', canon(set(BASE2) | set(CLASSES[c])), 1, 'S1_base2', f'base set plus class {c} ({",".join(CLASSES[c])})'))
    return out


def stage2(keep):
    keep = sorted(set(keep))
    if not keep or any(k not in CLASSES for k in keep):
        raise ValueError('stage 2 needs --keep with class letters from A-F, e.g. --keep ABCDE')
    ref_ops = canon([o for c in keep for o in CLASSES[c]])
    ref = 'S2_ref_' + ''.join(keep)
    out = [Cfg(ref, 'vnd', ref_ops, 2, None, f'retained classes {"".join(keep)} in full')]
    for c in keep:
        lad = LADDER.get(c)
        if not lad:
            continue
        for k in range(1, len(lad)):
            ops = [o for o in ref_ops if OP_CLASS[o] != c or o in lad[:k]]
            out.append(Cfg(f'S2_{c}{k}of{len(lad)}', 'vnd', ops, 2, ref, f'class {c} cut to its first {k} of {len(lad)} operators ({",".join(lad[:k])})'))
    return out


def stage3(setops, profile, seeds=(101, 102, 103)):
    setops = canon(setops)
    if len(setops) < 3:
        raise ValueError('stage 3 needs a set with at least 3 operators')

    def by_class(order):
        return sorted(setops, key=lambda o: (order.index(OP_CLASS[o]), CANON.index(o)))
    out = [Cfg('S3_canonical', 'vnd', setops, 3, None, 'canonical order (reference)')]
    out.append(Cfg('S3_cheap_first', 'vnd', sorted(setops, key=lambda o: (profile[o]['mean_candidates'], CANON.index(o))), 3, 'S3_canonical', 'ascending candidates per scan (profile.csv)'))
    out.append(Cfg('S3_gain_first', 'vnd', sorted(setops, key=lambda o: (-profile[o]['mean_gain'], CANON.index(o))), 3, 'S3_canonical', 'descending single-scan gain on the stored solutions (profile.csv)'))
    out.append(Cfg('S3_intra_first', 'vnd', by_class('ABCDEF'), 3, 'S3_canonical', 'class order A,B,C,D,E,F'))
    out.append(Cfg('S3_inter_first', 'vnd', by_class('BCDAEF'), 3, 'S3_canonical', 'class order B,C,D,A,E,F'))
    out.append(Cfg('S3_depot_first', 'vnd', by_class('EFABCD'), 3, 'S3_canonical', 'class order E,F,A,B,C,D'))
    out.append(Cfg('S3_reverse', 'vnd', list(reversed(setops)), 3, 'S3_canonical', 'canonical order reversed'))
    for i, s in enumerate(seeds, 1):
        lst = list(setops)
        random.Random(s).shuffle(lst)
        out.append(Cfg(f'S3_random{i}', 'vnd', lst, 3, 'S3_canonical', f'random permutation (seed {s})'))
    return out


def stage4(setops):
    setops = canon(setops)
    out = [Cfg('S4_basic_vnd', 'vnd', setops, 4, None, 'basic VND (reference)'),
           Cfg('S4_cyclic', 'cyclic', setops, 4, 'S4_basic_vnd', 'cyclic VND'),
           Cfg('S4_pipe', 'pipe', setops, 4, 'S4_basic_vnd', 'pipe VND'),
           Cfg('S4_rvnd', 'rvnd', setops, 4, 'S4_basic_vnd', 'random order'),
           Cfg('S4_best', 'best', setops, 4, 'S4_basic_vnd', 'steepest over all neighbourhoods (union VND; control)')]
    s6 = [o for o in setops if o in FIRST_OK]
    if s6 and s6 != setops:
        out.append(Cfg('S4_firstcap_vnd', 'vnd', s6, 4, None, 'first-capable subset, best improvement per neighbourhood'))
        out.append(Cfg('S4_firstcap_first', 'first', s6, 4, 'S4_firstcap_vnd', 'first-capable subset, first improvement'))
    elif s6:
        out.append(Cfg('S4_first', 'first', s6, 4, 'S4_basic_vnd', 'first improvement (all operators first-capable)'))
    return out


def registry():
    return {c.name: c for c in stage0() + stage1()}


def parse_set(spec, regs=None):
    """'classes:ABCDE' | 'classes:A,B' | 'ops:a,b,c' (or a+b+c) | 'S2_ref_ABCDE' | name of a stage-0/1 configuration."""
    spec = spec.strip()
    if spec.startswith('classes:'):
        letters = [ch for ch in spec[8:].upper() if ch in CLASSES]
        if not letters:
            raise ValueError(f'no class letters in {spec!r}')
        return canon([o for c in letters for o in CLASSES[c]])
    if spec.startswith('ops:'):
        names = [x for x in re.split(r'[,+]', spec[4:]) if x]
        bad = [x for x in names if x not in OP_CLASS]
        if bad:
            raise ValueError(f'unknown operators {bad}')
        return canon(names)
    m = re.fullmatch(r'S2_ref_([A-F]+)', spec)
    if m:
        return parse_set('classes:' + m.group(1))
    regs = regs or registry()
    if spec in regs:
        return list(regs[spec].ops)
    raise ValueError(f'cannot interpret set {spec!r} (use classes:ABCDE, ops:a,b,c or a configuration name)')


def read_config_file(path):
    """Lines 'name | driver | op1,op2,... [| reference name]'; '#' starts a comment."""
    out = []
    for ln in pathlib.Path(path).read_text().splitlines():
        ln = ln.split('#', 1)[0].strip()
        if not ln:
            continue
        parts = [x.strip() for x in ln.split('|')]
        if len(parts) < 3:
            raise ValueError(f'bad line in {path}: {ln!r}')
        out.append(Cfg(parts[0], parts[1], [x for x in re.split(r'[,+ ]+', parts[2]) if x], 9, parts[3] if len(parts) > 3 and parts[3] else None, 'custom'))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# drivers with per-operator statistics
def _scan(op, inst, cur, K, p, allowed, ps):
    c0 = _CNT[0]
    t0 = time.perf_counter()
    try:
        return NB.NEIGHBORHOODS[op](inst, cur, K, p, allowed)
    finally:
        s = ps.setdefault(op, [0, 0, 0.0, 0, 0.0])      # scans, moves, gain, candidates, seconds
        s[0] += 1
        s[3] += _CNT[0] - c0
        s[4] += time.perf_counter() - t0


def _gain(ps, op, g):
    s = ps[op]
    s[1] += 1
    s[2] += g


def apply_ls(driver, inst, sol, ops, rng, deadline, K, p, allowed):
    """-> (solution, z, moves, scans, per-operator stats {op: [scans, moves, gain, candidates, seconds]}, timed_out)"""
    ops = list(ops)
    ps = {}
    cur = core.clone_solution(sol)
    z = core.objective(inst, cur)
    moves = 0
    timed = False
    if driver == 'first':
        s2, z2, mv = LS.first_descent(inst, sol, K, p, allowed, ','.join(ops), deadline)
        return s2, z2, mv, 0, ps, bool(deadline and time.perf_counter() >= deadline)
    NB.set_scan_deadline(deadline)
    try:
        if driver == 'vnd':
            k = 0
            while k < len(ops):
                if deadline and time.perf_counter() >= deadline:
                    timed = True
                    break
                res = _scan(ops[k], inst, cur, K, p, allowed, ps)
                if res is not None and res[0] < z - EPS:
                    _gain(ps, ops[k], z - res[0])
                    z, cur = res
                    moves += 1
                    k = 0
                else:
                    k += 1
        elif driver == 'cyclic':
            k, fails = 0, 0
            while fails < len(ops):
                if deadline and time.perf_counter() >= deadline:
                    timed = True
                    break
                res = _scan(ops[k], inst, cur, K, p, allowed, ps)
                if res is not None and res[0] < z - EPS:
                    _gain(ps, ops[k], z - res[0])
                    z, cur = res
                    moves += 1
                    fails = 0
                else:
                    fails += 1
                k = (k + 1) % len(ops)
        elif driver == 'pipe':
            k, improved_pass = 0, False
            while True:
                if k >= len(ops):
                    if not improved_pass:
                        break
                    k, improved_pass = 0, False
                if deadline and time.perf_counter() >= deadline:
                    timed = True
                    break
                res = _scan(ops[k], inst, cur, K, p, allowed, ps)
                if res is not None and res[0] < z - EPS:
                    _gain(ps, ops[k], z - res[0])
                    z, cur = res
                    moves += 1
                    improved_pass = True
                else:
                    k += 1
        elif driver == 'rvnd':
            active = ops.copy()
            rng.shuffle(active)
            while active:
                if deadline and time.perf_counter() >= deadline:
                    timed = True
                    break
                idx = rng.randrange(len(active))
                name = active[idx]
                res = _scan(name, inst, cur, K, p, allowed, ps)
                if res is not None and res[0] < z - EPS:
                    _gain(ps, name, z - res[0])
                    z, cur = res
                    moves += 1
                    active = ops.copy()
                    rng.shuffle(active)
                else:
                    active.pop(idx)
        elif driver == 'best':
            while True:
                if deadline and time.perf_counter() >= deadline:
                    timed = True
                    break
                best, best_op = None, None
                for name in ops:
                    if deadline and time.perf_counter() >= deadline:
                        break
                    res = _scan(name, inst, cur, K, p, allowed, ps)
                    if res is not None and (best is None or res[0] < best[0] - EPS):
                        best, best_op = res, name
                if best is None or best[0] >= z - EPS:
                    break
                _gain(ps, best_op, z - best[0])
                z, cur = best
                moves += 1
        else:
            raise ValueError(driver)
    except NB.ScanTimeout:
        timed = True
    finally:
        NB.set_scan_deadline(None)
    return cur, z, moves, sum(s[0] for s in ps.values()), ps, timed


# ---------------------------------------------------------------------------------------------------------------------
# data handling
_INST = {}


def _instance(name):
    if name not in _INST:
        prm = REGISTERED[name]
        _INST[name] = core.read_dat(KIT / 'data' / prm['family'] / prm['file'])
    return _INST[name]


def parse_routes(text):
    out = []
    for part in text.split('|'):
        d, seq = part.split(':')
        out.append(Route(int(d[1:]), [int(x) for x in seq.split('-')], 0.0))
    return out


def parse_seed_filter(text):
    if not text:
        return None
    keep = set()
    for tok in text.split(','):
        lo, _, hi = tok.partition('-')
        keep.update(range(int(lo), int(hi or lo) + 1))
    return keep


def load_rows(report, seeds='', instances='', methods=''):
    keep = parse_seed_filter(seeds)
    insts = {x for x in instances.split(',') if x} if instances else None
    meths = {x for x in methods.split(',') if x} if methods else None
    rows = []
    with pathlib.Path(report).open(newline='') as f:
        for r in csv.DictReader(f):
            if r.get('status') != 'ok' or not r.get('solution_routes'):
                continue
            ls = r.get('local_search') or 'none'
            method = r['heuristic'] + ('+' + ls if ls != 'none' else '')
            if keep is not None and int(r['seed']) not in keep:
                continue
            if insts is not None and r['instance'] not in insts:
                continue
            if meths is not None and method not in meths and r['heuristic'] not in meths:
                continue
            rows.append(dict(instance=r['instance'], heuristic=r['heuristic'], local_search=ls, method=method, seed=int(r['seed']),
                             objective=float(r['objective']), gap0=float(r['gap_pct']), reference_best=float(r['reference_best']),
                             reference_tol=float(r.get('reference_tol') or 0.01), solution_routes=r['solution_routes']))
    rows.sort(key=lambda x: (x['instance'], x['method'], x['seed']))
    keys = [(x['instance'], x['method'], x['seed']) for x in rows]
    if len(keys) != len(set(keys)):
        raise SystemExit('ERROR: duplicate (instance, method, seed) rows in the report')
    return rows


RES_FIELDS = ['config', 'instance', 'method', 'heuristic', 'local_search', 'seed', 'status', 'check_z', 'z0', 'z1', 'gap0', 'gap1', 'hit0', 'hit1', 'moves', 'scans',
              'candidates', 'secs', 'timeout', 'improved', 'depots_changed', 'routes1', 'op_stats']


def run_one(job):
    cname, driver, ops, row, max_s = job
    out = dict(config=cname, instance=row['instance'], method=row['method'], heuristic=row['heuristic'], local_search=row['local_search'], seed=row['seed'], status='ok')
    try:
        inst = _instance(row['instance'])
        sol = core.normalize(inst, parse_routes(row['solution_routes']))
        z0 = core.objective(inst, sol)
        K, pp = REGISTERED[row['instance']]['K'], REGISTERED[row['instance']]['p']          # LLRP: binding fleet and open-depot bounds
        if abs(z0 - row['objective']) > 1e-6 or not core.feasible(inst, sol, K, pp):
            out.update(status='objective_mismatch', check_z=z0)
            return out
        allowed = tuple(range(inst.m))
        c0 = _CNT[0]
        t0 = time.perf_counter()
        s2, z2, moves, scans, ps, timed = apply_ls(driver, inst, sol, ops, random.Random(row['seed']), t0 + max_s, K, pp, allowed)
        dt = time.perf_counter() - t0
        cands = _CNT[0] - c0
        s2 = core.normalize(inst, s2)
        z2 = core.objective(inst, s2)
        if not core.feasible(inst, s2, K, pp) or z2 > z0 + 1e-9:
            s2, z2 = sol, z0
        ref, tol = row['reference_best'], row['reference_tol']
        out.update(z0=z0, z1=z2, gap0=row['gap0'], gap1=(z2 - ref) / ref * 100.0, hit0=int(z0 <= ref + tol), hit1=int(z2 <= ref + tol), moves=moves, scans=scans,
                   candidates=cands, secs=round(dt, 5), timeout=int(timed), improved=int(z2 < z0 - 1e-9),
                   depots_changed=int(set(core.used_depots(s2)) != set(core.used_depots(sol))), routes1=len([r for r in s2 if r.seq]),
                   op_stats='|'.join(f'{o}:{s[0]}:{s[1]}:{s[2]:.3f}:{s[3]}:{s[4]:.4f}' for o, s in ps.items()))
    except Exception as e:  # noqa: BLE001
        out.update(status=f'error:{type(e).__name__}:{e}')
    return out


def profile_one(job):
    row, = job
    inst = _instance(row['instance'])
    sol = core.normalize(inst, parse_routes(row['solution_routes']))
    z0 = core.objective(inst, sol)
    K, pp, allowed = REGISTERED[row['instance']]['K'], REGISTERED[row['instance']]['p'], tuple(range(inst.m))
    res = {}
    for op in CANON:
        c0 = _CNT[0]
        t0 = time.perf_counter()
        r = NB.NEIGHBORHOODS[op](inst, sol, K, pp, allowed)
        res[op] = (_CNT[0] - c0, time.perf_counter() - t0, (z0 - r[0]) if r is not None else 0.0)
    return res


# ---------------------------------------------------------------------------------------------------------------------
# commands
def _csv_write(path, fields, rows):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def load_profile(out):
    path = out / 'profile.csv'
    if not path.exists():
        raise SystemExit(f'ERROR: {path} not found; run `ls_ablation.py profile` first (stage 3 orders need it)')
    return {r['op']: {k: float(v) for k, v in r.items() if k not in ('op', 'class')} for r in csv.DictReader(path.open())}


def cmd_profile(a):
    rows = load_rows(a.report, a.seeds, a.instances, a.methods)
    if not rows:
        raise SystemExit('ERROR: no rows after filtering')
    step = max(1, len(rows) // a.sample)
    sample = rows[::step][:a.sample]
    a.out.mkdir(parents=True, exist_ok=True)
    print(f'profile: {len(sample)} stored solutions of {len(rows)} (every {step}th), {len(CANON)} operators, {a.workers} workers', flush=True)
    t0 = time.time()
    with mp.get_context('spawn').Pool(a.workers) as pool:
        res = pool.map(profile_one, [(r,) for r in sample], chunksize=1)
    out = []
    for op in CANON:
        c = [x[op][0] for x in res]
        t = [x[op][1] for x in res]
        g = [x[op][2] for x in res]
        out.append(dict(op=op, **{'class': OP_CLASS[op]}, solutions=len(res), mean_candidates=round(sum(c) / len(c), 2), mean_time_s=round(sum(t) / len(t), 5),
                        mean_gain=round(sum(g) / len(g), 3), share_improvable=round(sum(1 for x in g if x > EPS) / len(g), 4)))
    _csv_write(a.out / 'profile.csv', ['op', 'class', 'solutions', 'mean_candidates', 'mean_time_s', 'mean_gain', 'share_improvable'], out)
    print(f'wrote {a.out / "profile.csv"} in {time.time() - t0:.0f}s')
    for r in out:
        print(f'  {r["op"]:22s} class {r["class"]}  candidates/scan {r["mean_candidates"]:9.1f}  time/scan {r["mean_time_s"]:.4f}s  single-scan gain {r["mean_gain"]:8.1f}  improvable {r["share_improvable"]:.2f}')


def build_configs(a, out):
    stages = [int(x) for x in re.split(r'[,:+ ]+', a.stage) if x != ''] if a.stage else []
    cfgs = []
    for s in stages:
        if s == 0:
            cfgs += stage0()
        elif s == 1:
            cfgs += stage1()
        elif s == 2:
            cfgs += stage2(a.keep or '')
        elif s in (3, 4):
            spec = a.set or (f'classes:{a.keep}' if a.keep else '')
            if not spec:
                raise SystemExit(f'ERROR: stage {s} needs --set (e.g. classes:ABCDE) or --keep')
            setops = parse_set(spec)
            cfgs += stage3(setops, load_profile(out)) if s == 3 else stage4(setops)
        else:
            raise SystemExit(f'ERROR: unknown stage {s}')
    if a.config_file:
        cfgs += read_config_file(a.config_file)
    byname = {}
    for c in cfgs:
        if c.name in byname and (byname[c.name].driver, byname[c.name].ops) != (c.driver, c.ops):
            raise SystemExit(f'ERROR: configuration name {c.name} defined twice with different content')
        byname[c.name] = c
    regs = registry()
    ordered = list(byname.values())
    for c in list(ordered):                                  # make sure every reference configuration is run as well
        if c.ref and c.ref not in byname:
            if c.ref not in regs:
                raise SystemExit(f'ERROR: reference {c.ref} of {c.name} is unknown')
            byname[c.ref] = regs[c.ref]
            ordered.insert(0, regs[c.ref])
    return ordered


def _signature(c, n_jobs, a, rep_size):
    return json.dumps(dict(driver=c.driver, ops=c.ops, jobs=n_jobs, max_seconds=a.max_seconds, report_bytes=rep_size, seeds=a.seeds, instances=a.instances,
                           methods=a.methods, tool=TOOL_VERSION), sort_keys=True)


def cmd_list(a):
    cfgs = build_configs(a, a.out)
    for c in cfgs:
        print(f'{c.name:22s} {c.driver:7s} {len(c.ops):2d} ops  ref={c.ref or "-":16s} {",".join(c.ops)}')
    print(f'{len(cfgs)} configurations')


def cmd_run(a):
    rows = load_rows(a.report, a.seeds, a.instances, a.methods)
    if not rows:
        raise SystemExit('ERROR: no rows after filtering')
    a.out.mkdir(parents=True, exist_ok=True)
    cfgdir = a.out / 'configs'
    cfgdir.mkdir(exist_ok=True)
    cfgs = build_configs(a, a.out)
    rep_size = pathlib.Path(a.report).stat().st_size
    reg_path = a.out / 'configs.json'
    reg = json.loads(reg_path.read_text()) if reg_path.exists() else {}
    for c in cfgs:
        reg[c.name] = c.as_dict()
    reg_path.write_text(json.dumps(reg, indent=1))
    print(f'{len(rows)} stored solutions, {len(cfgs)} configurations, {a.workers} workers, cap {a.max_seconds:.0f}s per solution', flush=True)
    bad_total = 0
    t_all = time.time()
    with mp.get_context('spawn').Pool(a.workers) as pool:
        for i, c in enumerate(cfgs, 1):
            f, done = cfgdir / f'{c.name}.csv', cfgdir / f'{c.name}.done'
            sig = _signature(c, len(rows), a, rep_size)
            if a.resume and f.exists() and done.exists() and done.read_text() == sig:
                print(f'[{i}/{len(cfgs)}] {c.name}: finished earlier, skipped', flush=True)
                continue
            if done.exists():
                done.unlink()
            t0 = time.time()
            jobs = [(c.name, c.driver, c.ops, r, a.max_seconds) for r in rows]
            res = list(pool.imap(run_one, jobs, chunksize=8))
            bad = [r for r in res if r['status'] != 'ok']
            _csv_write(f, RES_FIELDS, res)
            if not bad:
                done.write_text(sig)
            ok = [r for r in res if r['status'] == 'ok']
            g0 = sum(r['gap0'] for r in ok) / max(1, len(ok))
            g1 = sum(r['gap1'] for r in ok) / max(1, len(ok))
            print(f'[{i}/{len(cfgs)}] {c.name}: {c.driver}/{len(c.ops)} ops  gap {g0:.3f} -> {g1:.3f}  cand/sol {sum(r["candidates"] for r in ok) / max(1, len(ok)):.0f}  '
                  f'{time.time() - t0:.0f}s  problems {len(bad)}', flush=True)
            for b in bad[:3]:
                print('   problem:', {k: b.get(k) for k in ('instance', 'method', 'seed', 'status', 'check_z')})
            bad_total += len(bad)
    print(f'done in {time.time() - t_all:.0f}s, problems {bad_total}; results in {cfgdir}')
    sys.exit(1 if bad_total else 0)


# ---------------------------------------------------------------------------------------------------------------------
# summaries
NUM = ('seed', 'check_z', 'z0', 'z1', 'gap0', 'gap1', 'hit0', 'hit1', 'moves', 'scans', 'candidates', 'secs', 'timeout', 'improved', 'depots_changed', 'routes1')


def read_results(path):
    rows = []
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            if r['status'] != 'ok':
                continue
            for k in NUM:
                r[k] = float(r[k]) if r[k] != '' else 0.0
            r['seed'] = int(r['seed'])
            rows.append(r)
    return rows


def mean(x):
    x = list(x)
    return sum(x) / len(x) if x else float('nan')


def tertiles(vals):
    s = sorted(vals)
    return s[len(s) // 3], s[(2 * len(s)) // 3]


def strata_of(r, t1, t2):
    out = ['all', 'native_ls' if r['local_search'] != 'none' else 'native_none']
    out.append('start_T1' if r['gap0'] <= t1 else ('start_T2' if r['gap0'] <= t2 else 'start_T3'))
    return out


STRATA = ['all', 'native_none', 'native_ls', 'start_T1', 'start_T2', 'start_T3']


def boot_ci(d, B, alpha, rng):
    n = len(d)
    if n == 0:
        return float('nan'), float('nan')
    ms = sorted(sum(rng.choices(d, k=n)) / n for _ in range(B))
    lo = ms[max(0, int(B * alpha / 2))]
    hi = ms[min(B - 1, int(B * (1 - alpha / 2)))]
    return lo, hi


def label(lo, hi, margin):
    if lo > -margin and hi < margin:
        return 'equivalent'
    if hi < 0:
        return 'better'
    if lo > 0:
        return 'worse'
    return 'inconclusive'


def cmd_summarize(a):
    cfgdir = a.out / 'configs'
    reg = json.loads((a.out / 'configs.json').read_text()) if (a.out / 'configs.json').exists() else {}
    data = {}
    for p in sorted(cfgdir.glob('*.csv')):
        if (cfgdir / f'{p.stem}.done').exists():
            data[p.stem] = read_results(p)
    if not data:
        raise SystemExit(f'ERROR: no finished configuration in {cfgdir}')
    allgap0 = [r['gap0'] for rows in data.values() for r in rows[:2000]]
    t1, t2 = tertiles(allgap0)
    # per configuration
    summ = []
    for name, rows in data.items():
        for s in STRATA:
            sub = [r for r in rows if s in strata_of(r, t1, t2)]
            if not sub:
                continue
            summ.append(dict(config=name, driver=reg.get(name, {}).get('driver', ''), n_ops=len(reg.get(name, {}).get('ops', [])), stratum=s, blocks=len(sub),
                             mean_gap0=mean(r['gap0'] for r in sub), mean_gap1=mean(r['gap1'] for r in sub), mean_reduction_pp=mean(r['gap0'] - r['gap1'] for r in sub),
                             hit0=mean(r['hit0'] for r in sub), hit1=mean(r['hit1'] for r in sub), share_improved=mean(r['improved'] for r in sub),
                             mean_moves=mean(r['moves'] for r in sub), mean_candidates=mean(r['candidates'] for r in sub), mean_secs=mean(r['secs'] for r in sub),
                             share_depots_changed=mean(r['depots_changed'] for r in sub), timeouts=int(sum(r['timeout'] for r in sub))))
    sf = ['config', 'driver', 'n_ops', 'stratum', 'blocks', 'mean_gap0', 'mean_gap1', 'mean_reduction_pp', 'hit0', 'hit1', 'share_improved', 'mean_moves', 'mean_candidates',
          'mean_secs', 'share_depots_changed', 'timeouts']
    _csv_write(a.out / 'ablation_summary.csv', sf, [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()} for r in summ])
    # per operator
    ops_rows = []
    for name, rows in data.items():
        agg = {}
        for r in rows:
            for part in filter(None, r['op_stats'].split('|')):
                o, sc, mv, gn, cd, sec = part.split(':')
                x = agg.setdefault(o, [0, 0, 0.0, 0, 0.0])
                x[0] += int(sc); x[1] += int(mv); x[2] += float(gn); x[3] += int(cd); x[4] += float(sec)
        tg, tc, tt = sum(v[2] for v in agg.values()), sum(v[3] for v in agg.values()), sum(v[4] for v in agg.values())
        for o in reg.get(name, {}).get('ops', list(agg)):
            v = agg.get(o, [0, 0, 0.0, 0, 0.0])
            ops_rows.append(dict(config=name, op=o, op_class=OP_CLASS[o], solutions=len(rows), scans_per_sol=v[0] / len(rows), moves_per_sol=v[1] / len(rows), gain_per_sol=v[2] / len(rows),
                                 gain_share=v[2] / tg if tg else 0.0, candidates_per_sol=v[3] / len(rows), candidate_share=v[3] / tc if tc else 0.0, time_share=v[4] / tt if tt else 0.0,
                                 gain_per_1000_candidates=1000 * v[2] / v[3] if v[3] else 0.0))
    of = ['config', 'op', 'op_class', 'solutions', 'scans_per_sol', 'moves_per_sol', 'gain_per_sol', 'gain_share', 'candidates_per_sol', 'candidate_share', 'time_share', 'gain_per_1000_candidates']
    _csv_write(a.out / 'ablation_ops.csv', of, [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()} for r in ops_rows])
    # paired contrasts against the reference configuration
    pairs = [(n, reg[n]['ref']) for n in data if reg.get(n, {}).get('ref') in data]
    m = max(1, len(pairs))
    alpha = a.alpha / m
    rng = random.Random(20261022)
    con = []
    for name, ref in pairs:
        A = {(r['instance'], r['method'], r['seed']): r for r in data[name]}
        Bm = {(r['instance'], r['method'], r['seed']): r for r in data[ref]}
        keys = sorted(set(A) & set(Bm))
        for s in STRATA:
            ks = [k for k in keys if s in strata_of(Bm[k], t1, t2)]
            if not ks:
                continue
            cells = {}
            for k in ks:
                cells.setdefault((k[0], k[1]), []).append(A[k]['gap1'] - Bm[k]['gap1'])
            d = [mean(v) for v in cells.values()]
            inst = {}
            for (i, _meth), v in zip(cells.keys(), d):
                inst.setdefault(i, []).append(v)
            idiff = [mean(v) for v in inst.values()]
            lo, hi = boot_ci(d, a.boot, alpha, rng)
            est = mean(d)
            con.append(dict(config=name, reference=ref, stratum=s, blocks=len(ks), cells=len(d), diff_gap_pp=est, ci_low=lo, ci_high=hi, decision=label(lo, hi, a.margin),
                            instances_better=sum(1 for x in idiff if x < -a.margin), instances_worse=sum(1 for x in idiff if x > a.margin), instances=len(idiff),
                            diff_hit_pp=100 * mean(A[k]['hit1'] - Bm[k]['hit1'] for k in ks),
                            candidate_ratio=mean(A[k]['candidates'] for k in ks) / max(1e-9, mean(Bm[k]['candidates'] for k in ks)),
                            time_ratio=mean(A[k]['secs'] for k in ks) / max(1e-9, mean(Bm[k]['secs'] for k in ks))))
    cf = ['config', 'reference', 'stratum', 'blocks', 'cells', 'diff_gap_pp', 'ci_low', 'ci_high', 'decision', 'instances_better', 'instances_worse', 'instances', 'diff_hit_pp', 'candidate_ratio', 'time_ratio']
    _csv_write(a.out / 'ablation_contrasts.csv', cf, [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()} for r in con])
    # human readable report
    L = ['# LS ablation report', '',
         f'configurations: {len(data)}; contrasts: {len(pairs)}; equivalence margin {a.margin} pp; cluster bootstrap over (instance, method) cells, {a.boot} resamples, '
         f'Bonferroni level {alpha:.4g} per contrast ({a.alpha} / {m}).', '',
         'diff = gap(config) - gap(reference) in percentage points after the local search, so NEGATIVE is better. decision: equivalent = whole interval inside +-margin; '
         'better / worse = interval entirely below / above 0; inconclusive otherwise.', '']
    by_stage = {}
    for r in con:
        if r['stratum'] == 'all':
            by_stage.setdefault(reg.get(r['config'], {}).get('stage', '?'), []).append(r)
    for stg in sorted(by_stage, key=str):
        L += [f'## Stage {stg}', '', '| config | reference | diff pp | interval | decision | instances better/worse | hit diff pp | candidates x | time x |', '|---|---|---|---|---|---|---|---|---|']
        for r in sorted(by_stage[stg], key=lambda x: x['diff_gap_pp']):
            L.append(f'| {r["config"]} | {r["reference"]} | {r["diff_gap_pp"]:+.3f} | [{r["ci_low"]:+.3f}, {r["ci_high"]:+.3f}] | {r["decision"]} | '
                     f'{r["instances_better"]}/{r["instances_worse"]} of {r["instances"]} | {r["diff_hit_pp"]:+.2f} | {r["candidate_ratio"]:.2f} | {r["time_ratio"]:.2f} |')
        L.append('')
    L += ['## Configurations (stratum all)', '', '| config | driver | ops | gap before | gap after | reduction pp | BKS hit after | candidates/sol | s/sol |', '|---|---|---|---|---|---|---|---|---|']
    for r in sorted([x for x in summ if x['stratum'] == 'all'], key=lambda x: x['mean_gap1']):
        L.append(f'| {r["config"]} | {r["driver"]} | {r["n_ops"]} | {r["mean_gap0"]:.3f} | {r["mean_gap1"]:.3f} | {r["mean_reduction_pp"]:.3f} | {r["hit1"]:.3f} | {r["mean_candidates"]:.0f} | {r["mean_secs"]:.3f} |')
    (a.out / 'ablation_report.md').write_text('\n'.join(L) + '\n')
    print(f'wrote ablation_summary.csv, ablation_ops.csv, ablation_contrasts.csv, ablation_report.md in {a.out}')
    for r in sorted([x for x in con if x['stratum'] == 'all'], key=lambda x: (str(reg.get(x["config"], {}).get("stage", "")), x['diff_gap_pp'])):
        print(f'  {r["config"]:22s} vs {r["reference"]:16s} {r["diff_gap_pp"]:+8.3f} pp [{r["ci_low"]:+.3f}, {r["ci_high"]:+.3f}]  {r["decision"]:12s} cand x{r["candidate_ratio"]:.2f}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, report=True):
        if report:
            p.add_argument('--report', required=True, type=pathlib.Path)
            p.add_argument('--seeds', default='', help='seed filter, e.g. 1-10 or 1,2,3 (default: all)')
            p.add_argument('--instances', default='', help='comma separated instance filter')
            p.add_argument('--methods', default='', help='comma separated method filter (e.g. lns,tabu,grasp+first)')
            p.add_argument('--workers', type=int, default=max(1, mp.cpu_count() or 1))
        p.add_argument('--out', required=True, type=pathlib.Path)

    def stage_args(p):
        p.add_argument('--stage', default='', help='stages to run, e.g. 0,1 (2 needs --keep; 3 and 4 need --set or --keep)')
        p.add_argument('--keep', default='', help='classes retained after stage 1, e.g. ABCDE')
        p.add_argument('--set', default='', help="operator set for stages 3/4: classes:ABCDE | ops:a,b,c | configuration name")
        p.add_argument('--config-file', default='', help="extra configurations, lines 'name | driver | op1,op2 | reference'")

    p = sub.add_parser('profile'); common(p); p.add_argument('--sample', type=int, default=60); p.set_defaults(fn=cmd_profile)
    p = sub.add_parser('run'); common(p); stage_args(p)
    p.add_argument('--max-seconds', type=float, default=120.0, help='safety cap per solution')
    p.add_argument('--no-resume', dest='resume', action='store_false'); p.set_defaults(fn=cmd_run, resume=True)
    p = sub.add_parser('list'); common(p, report=False); stage_args(p); p.set_defaults(fn=cmd_list)
    p = sub.add_parser('summarize'); common(p, report=False)
    p.add_argument('--margin', type=float, default=0.05, help='equivalence margin in percentage points of gap')
    p.add_argument('--boot', type=int, default=4000); p.add_argument('--alpha', type=float, default=0.05, help='family-wise level (Bonferroni over contrasts)')
    p.set_defaults(fn=cmd_summarize)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
