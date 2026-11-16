"""walker.Walker must be a pure speed-up of random_feasible_neighbor.

For long random walks on random tiny instances (tight vehicle/depot capacities, binding K and p, all seven move families),
the Walker and the original sampler, started from the same state and the same random seed, must produce the same neighbours
(identical normalised solutions, loads included) from the same random numbers (the random generators stay in lock step), with the
same objective (bit for bit), the same effort counters, the same tabu signature and the same incumbent trace; and after every
accepted move the incremental state must equal a state rebuilt from scratch.
"""
import random, unittest
from common import ROOT, PKG  # noqa: F401
from llrp_framework import core, neighborhoods as NB
from llrp_framework.core import clone_solution, objective
from llrp_framework.meta_utils import random_feasible_neighbor, solution_signature
from llrp_framework.walker import Walker
from test_delta_equivalence import random_instance, random_solution, sig


def counters():
    return tuple(core._CTR[:4])


class WalkerTests(unittest.TestCase):
    def run_walk(self, inst, K, p, allowed, seed, steps, accept_prob):
        rng0 = random.Random(seed)
        cur = random_solution(inst, rng0)
        if cur is None:
            return 0
        wk = Walker(inst, cur, K, p, allowed)
        r_ref = random.Random(seed * 7 + 1); r_new = random.Random(seed * 7 + 1)
        acc = random.Random(seed * 11 + 3)
        n_none = n_moves = 0
        for t in range(steps):
            ref = random_feasible_neighbor(inst, cur, K, p, allowed, r_ref)
            mv = wk.propose(r_new)
            self.assertEqual(r_ref.getstate(), r_new.getstate(), f'rng desynchronised at step {t}')
            if ref is None:
                self.assertIsNone(mv); n_none += 1
                continue
            self.assertIsNotNone(mv)
            c0 = counters(); zr = objective(inst, ref); dref = tuple(a - b for a, b in zip(counters(), c0))
            c0 = counters(); wk.evaluated(mv); dnew = tuple(a - b for a, b in zip(counters(), c0))
            self.assertEqual(repr(zr), repr(mv.z), f'objective differs at step {t}')
            self.assertEqual(dref, dnew, f'effort counters differ at step {t}')
            self.assertEqual(solution_signature(ref), wk.signature(mv))
            self.assertEqual(sig(ref), sig(wk.solution(mv)))
            n_moves += 1
            if acc.random() < accept_prob:
                wk.accept(mv); cur = ref
                self.assertEqual(sig(cur), sig(wk.routes), f'state differs after accept at step {t}')
                if wk.sc is not None:                       # incremental aggregates == a scan built from scratch
                    fresh = NB.Scan(inst, cur, K, p)
                    for f in ('R', 'dep', 'ld', 'dist', 'w', 'DL', 'cnt', 'nused', 'opening', 'ov'):
                        self.assertEqual(repr(getattr(fresh, f)), repr(getattr(wk.sc, f)), f'{f} at step {t}')
        return n_moves

    def test_random_walks_match_original(self):
        total = 0
        for seed in range(60):
            rng = random.Random(1000 + seed)
            n = rng.randint(4, 14); m = rng.randint(2, 4)
            inst = random_instance(rng, n, m, rng.choice(['ceil100_euclidean', 'real_euclidean']))
            K = rng.choice([n, n, max(2, n // 2)]); p = rng.choice([m, m, max(1, m - 1)])
            allowed = tuple(sorted(rng.sample(range(m), rng.randint(1, m))))
            total += self.run_walk(inst, K, p, allowed, seed, 150, rng.choice([0.2, 0.6, 1.0]))
        self.assertGreater(total, 3000)

    def test_non_integer_demand_falls_back(self):
        rng = random.Random(5)
        inst = random_instance(rng, 8, 3, 'real_euclidean')
        inst.demand = [d + 0.5 for d in inst.demand]; inst._fast = None
        inst.Q += 20; inst.depot_cap = [c + 100 for c in inst.depot_cap]
        sol = random_solution(inst, rng)
        wk = Walker(inst, sol, inst.n, inst.m, tuple(range(inst.m)))
        self.assertIsNone(wk.sc)
        r1 = random.Random(3); r2 = random.Random(3)
        for _ in range(50):
            a = random_feasible_neighbor(inst, sol, inst.n, inst.m, tuple(range(inst.m)), r1)
            mv = wk.propose(r2)
            self.assertEqual(sig(a), sig(wk.solution(mv)))
            wk.evaluated(mv); self.assertEqual(repr(objective(inst, a)), repr(mv.z))
            wk.accept(mv); sol = a

    def test_reset_after_external_change(self):
        rng = random.Random(9)
        inst = random_instance(rng, 10, 3, 'ceil100_euclidean')
        a = random_solution(inst, rng); b = random_solution(inst, rng)
        al = tuple(range(inst.m))
        wk = Walker(inst, a, inst.n, inst.m, al); wk.reset(b)
        r1 = random.Random(4); r2 = random.Random(4)
        for _ in range(30):
            ref = random_feasible_neighbor(inst, b, inst.n, inst.m, al, r1)
            mv = wk.propose(r2)
            self.assertEqual(sig(ref), sig(wk.solution(mv)))


if __name__ == '__main__':
    unittest.main()
