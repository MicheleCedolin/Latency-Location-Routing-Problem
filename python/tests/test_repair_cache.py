"""The insertion table of the greedy / regret repairs and the fast destroy_worst scores are pure speed-ups.

On random tiny instances (tight vehicle and depot capacities, binding K, restricted allowed-depot sets) and on P20/P50 instances, the
table-based repairs must return exactly the solution of the original recomputing repairs (same random numbers consumed, same loads,
same None when no repair exists), with the same effort counters; destroy_worst scores must be bit-identical.
"""
import random, unittest
from common import ROOT, PKG  # noqa: F401
from llrp_framework import core, heuristics as H
from llrp_framework.params import REGISTERED
from llrp_framework.meta_utils import solution_signature
from test_delta_equivalence import random_instance, random_solution, sig


def eff():
    return tuple(core._CTR[:4])


def diff(a, b):
    return tuple(y - x for x, y in zip(a, b))


class RepairTests(unittest.TestCase):
    def check_case(self, inst, sol, K, allowed, q, seed, label):
        rng = random.Random(seed)
        allc = [c for r in sol for c in r.seq]
        removed = rng.sample(allc, min(q, len(allc)))
        partial = H._partial_remove(inst, sol, removed)
        for fast, ref in ((H._repair_greedy, H._repair_greedy_ref), (H._repair_regret2, H._repair_regret2_ref)):
            r1 = random.Random(seed + 5); r2 = random.Random(seed + 5)
            e0 = eff(); a = ref(inst, partial, removed, K, allowed, r1); da = diff(e0, eff())
            e0 = eff(); b = fast(inst, partial, removed, K, allowed, r2); db = diff(e0, eff())
            self.assertEqual(a is None, b is None, label)
            if a is not None:
                self.assertEqual(sig(a), sig(b), label)
            self.assertEqual(r1.getstate(), r2.getstate(), label)
            self.assertEqual(da, db, f'counters {label} {fast.__name__}')
        return partial

    def test_random_instances(self):
        n_none = n_ok = 0
        for seed in range(150):
            rng = random.Random(7000 + seed)
            n = rng.randint(4, 16); m = rng.randint(2, 4)
            inst = random_instance(rng, n, m, rng.choice(['ceil100_euclidean', 'real_euclidean']))
            sol = random_solution(inst, rng)
            if sol is None: continue
            K = rng.choice([n, n, len(sol) + 1, len(sol)])
            allowed = tuple(sorted(rng.sample(range(m), rng.randint(1, m))))
            q = rng.randint(1, max(1, n - 1))
            partial = self.check_case(inst, sol, K, allowed, q, seed, f'seed {seed}')
            r = random.Random(seed + 5)
            n_ok += 1
        self.assertGreater(n_ok, 100)

    def test_destroy_worst_scores(self):
        for seed in range(80):
            rng = random.Random(9000 + seed)
            n = rng.randint(3, 16); m = rng.randint(2, 4)
            inst = random_instance(rng, n, m, rng.choice(['ceil100_euclidean', 'real_euclidean']))
            sol = random_solution(inst, rng)
            if sol is None: continue
            e0 = eff(); a = H._destroy_worst_scores_ref(inst, sol); da = diff(e0, eff())
            e0 = eff(); b = H._destroy_worst_scores(inst, sol); db = diff(e0, eff())
            self.assertEqual([(repr(x), c) for x, c in a], [(repr(x), c) for x, c in b], f'seed {seed}')
            self.assertEqual(da, db, f'counters seed {seed}')

    def test_benchmark_instances(self):
        for name in ('coord20-5-1', 'coord50-5-1b', 'coord50-5-3'):
            prm = REGISTERED[name]
            inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
            K, p = inst.n, inst.m
            from llrp_framework.construction import grasp_construct
            for s in range(6):
                rng = random.Random(s)
                sol = grasp_construct(inst, K, tuple(range(inst.m)), rng, 0.3)
                self.assertIsNotNone(sol)
                for q in (2, inst.n // 5, inst.n // 2):
                    self.check_case(inst, sol, K, tuple(range(inst.m)), q, 100 * s + q, f'{name} s{s} q{q}')
                a = H._destroy_worst_scores_ref(inst, sol); b = H._destroy_worst_scores(inst, sol)
                self.assertEqual([(repr(x), c) for x, c in a], [(repr(x), c) for x, c in b])

    def test_non_integer_instance_uses_reference(self):
        rng = random.Random(3)
        inst = random_instance(rng, 9, 3, 'real_euclidean')
        inst.demand = [d + 0.5 for d in inst.demand]; inst._fast = None
        inst.Q += 20; inst.depot_cap = [c + 100 for c in inst.depot_cap]
        sol = random_solution(inst, rng)
        self.assertFalse(H._fast_repair(inst))
        self.check_case(inst, sol, inst.n, tuple(range(inst.m)), 4, 1, 'non-integer')
        a = H._destroy_worst_scores_ref(inst, sol); b = H._destroy_worst_scores(inst, sol)
        self.assertEqual([(repr(x), c) for x, c in a], [(repr(x), c) for x, c in b])


if __name__ == '__main__':
    unittest.main()
