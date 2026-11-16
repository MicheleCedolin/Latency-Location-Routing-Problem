#!/usr/bin/env python3
"""Validate the C++ solver `llrp_fast` against exact optima on tiny random instances (standard library only).

For every random instance (n customers, m depots, fleet bound Nv, depot bound Ng) the optimum is computed with the exact dynamic
program of `llrp_framework/exact.py`; the instance is written in the `.inst` format of cpp/inst and solved with `llrp_fast` for
several seeds. Two properties are checked:

  1. SOUNDNESS: no run returns a feasible solution that is cheaper than the optimum (this would mean that the evaluator, the
     move evaluation or the feasibility test is wrong). Any violation makes the script exit with status 1.
  2. QUALITY: the best of the seeds reaches the optimum (tolerance 1e-6). Failures are reported; with --require-all they also
     make the exit status 1 (the default only requires the hit rate given by --min-hit, since GRASP is a heuristic).

The exact optimum is the one of the problem as defined in python/FORMULATION_LLRP.md: AT MOST Ng open depots. The solver therefore runs
with `--atmost` by default. Without that flag `llrp_fast` forces EXACTLY Ng open depots (the convention of the published solutions),
which differs from the exact optimum whenever the optimum uses fewer depots or Nv < Ng: in the default random set below 3 of 29
instances (and 0 with --atmost) were affected, e.g. an instance with Nv = 2 routes and Ng = 3, where "exactly 3 depots" is infeasible.
Pass other flags after `--` to test other configurations (then add --atmost yourself if you want to compare with the exact optimum).

Usage (from the repository root, after `cpp/build.sh`):
  python3 python/tools/exact_vs_engine.py                         # 30 instances, n = 7..10, 5 seeds each, a few seconds
  python3 python/tools/exact_vs_engine.py --instances 100 --seeds 8 -- --ops legacy5 --atmost
"""
import argparse
import math
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
ROOT = os.path.dirname(KIT)
sys.path.insert(0, KIT)

from llrp_framework.exact import INF, dp_optimum, random_instance  # noqa: E402


def write_inst(path, inst, nv, ng, name):
    lines = ['LLRP_INSTANCE 1', f'name {name}', f'n {inst.n}', f'm {inst.m}', f'Q {inst.Q}', f'Nv {nv}', f'Ng {ng}', 'bks 0', 'depots']
    lines += [f'{x!r} {y!r}' for x, y in inst.dep]
    lines.append('customers')
    lines += [f'{x!r} {y!r} {d!r}' for (x, y), d in zip(inst.cust, inst.demand)]
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def run_engine(binary, path, seed, extra, max_iter):
    out = subprocess.run([binary, '--instance', path, '--seed', str(seed), '--max-iter', str(max_iter), '--quiet'] + extra,
                         capture_output=True, text=True, timeout=120)
    kv = dict(line.split(None, 1) for line in out.stdout.splitlines() if line and line[0].islower() and ' ' in line)
    if out.returncode != 0 or 'final_cost' not in kv:
        raise RuntimeError(f'llrp_fast failed on {path} (seed {seed}): rc={out.returncode}\n{out.stdout[-400:]}\n{out.stderr[-400:]}')
    return float(kv['final_cost']), kv.get('feasible', '0').strip() == '1'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--binary', default=os.path.join(ROOT, 'cpp', 'bin', 'llrp_fast'))
    ap.add_argument('--instances', type=int, default=30)
    ap.add_argument('--n-min', type=int, default=7)
    ap.add_argument('--n-max', type=int, default=10)
    ap.add_argument('--seeds', type=int, default=5, help='engine seeds per instance')
    ap.add_argument('--max-iter', type=int, default=30, help='GRASP iterations per run')
    ap.add_argument('--first-seed', type=int, default=1000, help='seed of the instance generator (instance k uses first-seed + k)')
    ap.add_argument('--min-hit', type=float, default=0.9, help='required share of instances whose best seed reaches the optimum')
    ap.add_argument('--require-all', action='store_true', help='every instance must reach its optimum')
    ap.add_argument('engine_flags', nargs=argparse.REMAINDER, help='llrp_fast flags after --, default: --ops full --so --ds --atmost')
    a = ap.parse_args()
    if not os.path.exists(a.binary):
        sys.exit(f'{a.binary} not found; build it with cpp/build.sh')
    extra = [f for f in a.engine_flags if f != '--'] or ['--ops', 'full', '--so', '--ds', '--atmost']

    rng = random.Random(a.first_seed)
    unsound, missed, checked, hits = [], [], 0, 0
    with tempfile.TemporaryDirectory(prefix='llrp_exact_') as tmp:
        for k in range(a.instances):
            seed = a.first_seed + k
            n = rng.randint(a.n_min, a.n_max)
            m = rng.randint(3, 4)
            tight = rng.choice([0.3, 0.4, 0.5])
            inst = random_instance(seed, n=n, m=m, q_tightness=tight)
            ng = rng.randint(1, min(3, m))
            nv = max(2, math.ceil(sum(inst.demand) / inst.Q)) + rng.randint(0, 2)
            opt, _ = dp_optimum(inst, nv, ng)
            if opt == INF:
                continue
            name = f'rand-{seed}'
            path = os.path.join(tmp, name + '.inst')
            write_inst(path, inst, nv, ng, name)
            best = INF
            for s in range(1, a.seeds + 1):
                z, feas = run_engine(a.binary, path, s, extra, a.max_iter)
                if not feas:
                    continue
                best = min(best, z)
                if z < opt - 1e-6:
                    unsound.append((name, s, z, opt))
            checked += 1
            ok = best <= opt + 1e-6
            hits += ok
            if not ok:
                missed.append((name, best, opt))
    print(f'{checked} instances (n = {a.n_min}..{a.n_max}), {a.seeds} seeds each, flags: {" ".join(extra)}')
    print(f'best seed reached the optimum on {hits}/{checked} instances')
    for name, best, opt in missed:
        print(f'  missed {name}: best {best:.6f} vs optimum {opt:.6f} (+{100 * (best - opt) / opt:.3f} %)')
    for name, s, z, opt in unsound:
        print(f'  UNSOUND {name} seed {s}: {z:.6f} < optimum {opt:.6f}')
    if unsound:
        print('FAILED: a run beat the exact optimum')
        return 1
    if checked == 0:
        print('FAILED: no instance was checked')
        return 1
    if (a.require_all and missed) or hits < a.min_hit * checked:
        print('FAILED: too few instances reached the optimum')
        return 1
    print('OK: no run is cheaper than the exact optimum')
    return 0


if __name__ == '__main__':
    sys.exit(main())
