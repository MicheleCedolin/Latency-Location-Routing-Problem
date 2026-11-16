"""Is a final solution a local optimum of the ruin-and-recreate neighbourhood?

For a solution stored in a run's summary.csv (column `solution_routes`), remove EVERY set of q customers (q = qmin..qmax), repair it with the greedy and the
regret-2 repair of the ALNS / LNS / IG methods, and count how many repairs improve the objective. A solution with 0 improving repairs for all q <= q0 can
not be left by any destroy fraction below q0 / n, whatever the acceptance rule or the number of iterations.

    python3 tools/ruin_neighbourhood_probe.py --summary <run dir>/summary.csv --qmin 2 --qmax 6

C(n,q) grows fast: n = 20, q = 7 is 155 039 repairs (about 27 s); use it for small instances.
"""
from __future__ import annotations
import argparse, csv, itertools, random, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from llrp_framework import core, heuristics as H            # noqa: E402
from llrp_framework.core import Route                        # noqa: E402
from llrp_framework.params import REGISTERED                 # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--summary', required=True)
    ap.add_argument('--qmin', type=int, default=2)
    ap.add_argument('--qmax', type=int, default=6)
    a = ap.parse_args()
    r = next(csv.DictReader(open(a.summary)))
    prm = REGISTERED[r['instance']]; K = prm['K']
    inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
    sol = []
    for t in r['solution_routes'].split('|'):
        d, seq = t.split(':'); seq = [int(x) for x in seq.split('-')]
        sol.append(Route(int(d[1:]), seq, sum(inst.demand[c] for c in seq)))
    allowed = tuple(sorted({rt.depot for rt in sol}))
    z0 = core.objective(inst, sol); rng = random.Random(1)
    print(f"{r['instance']} {r['heuristic']} seed {r['seed']}: z = {z0:.4f}, reference {prm['bks']}, depots {allowed}")
    for q in range(a.qmin, a.qmax + 1):
        t0 = time.perf_counter(); best = float('inf'); nimp = tot = 0
        for rem in itertools.combinations(range(inst.n), q):
            part = H._partial_remove(inst, sol, list(rem))
            for rf in (H._repair_greedy, H._repair_regret2):
                c = rf(inst, part, list(rem), K, allowed, rng)
                if c is None: continue
                tot += 1; z = core.objective(inst, c); best = min(best, z); nimp += z < z0 - 1e-9
        print(f"  q={q}: {tot} repairs, improving {nimp}, best {best:.4f} ({(best - z0) / z0 * 100:+.2f} %)  [{time.perf_counter() - t0:.1f} s]", flush=True)


if __name__ == '__main__':
    main()
