"""Exact reference solvers: brute force == dynamic program, and neither the evaluator nor the heuristics of the kit can beat the optimum."""
import itertools, sys, unittest
from common import ROOT  # noqa: F401  (puts the kit on sys.path)
from llrp_framework import core, depot_impact, heuristics as H
from llrp_framework.core import feasible, objective, route_latency, Route
from llrp_framework.exact import INF, brute_force, dp_optimum, random_instance, has_depot_cap


class DPvsBruteForce(unittest.TestCase):
    def test_agree_on_random_tiny_instances(self):
        for seed in range(10):
            for kw, K, p in ((dict(), 6, 3), (dict(), 3, 2), (dict(q_tightness=0.35), 4, 1), (dict(q_tightness=0.8), 2, 3)):
                inst = random_instance(seed, n=5, m=3, **kw)
                a, sa = dp_optimum(inst, K, p)
                b, sb = brute_force(inst, K, p)
                if a == INF or b == INF:
                    self.assertEqual(a, b, (seed, kw, K, p))
                    continue
                self.assertAlmostEqual(a, b, places=7, msg=(seed, kw, K, p))
                for sol in (sa, sb):
                    self.assertTrue(feasible(inst, sol, K, p), (seed, kw, K, p))
                self.assertAlmostEqual(objective(inst, sa), a, places=7)
                self.assertAlmostEqual(objective(inst, sb), b, places=7)

    def test_hand_computed_toy(self):
        # depot (0,0); customers (3,0), (3,4), (0,4); one vehicle may serve all three
        inst = random_instance(0, n=3, m=1)
        inst.cust[:] = [(3.0, 0.0), (3.0, 4.0), (0.0, 4.0)]
        inst.dep[:] = [(0.0, 0.0)]
        inst.dcc[:] = [[0.0, 4.0, 5.0], [4.0, 0.0, 3.0], [5.0, 3.0, 0.0]]
        inst.ddc[:] = [[3.0, 5.0, 4.0]]
        inst.demand[:] = [1.0, 1.0, 1.0]
        inst.Q = 10.0
        v1, s1 = dp_optimum(inst, K=1, p=1)
        self.assertAlmostEqual(v1, min(route_latency(inst, Route(0, list(q), 3.0)) for q in itertools.permutations(range(3))))
        self.assertAlmostEqual(v1, 20.0)             # (3,0) at 3, (3,4) at 7, (0,4) at 10
        v3, _ = dp_optimum(inst, K=3, p=1)
        self.assertAlmostEqual(v3, 3 + 5 + 4)         # one customer per route: the arrival times are the depot distances
        self.assertAlmostEqual(brute_force(inst, 3, 1)[0], 12.0)

    def test_bounds_bind_and_infeasibility_is_reported(self):
        for seed in range(6):
            inst = random_instance(seed, n=6, m=3, q_tightness=0.4)
            loose, _ = dp_optimum(inst, 6, 3)
            self.assertLessEqual(loose, dp_optimum(inst, 4, 3)[0] + 1e-9)       # fewer routes never help
            self.assertLessEqual(loose, dp_optimum(inst, 6, 1)[0] + 1e-9)       # fewer depots never help
            self.assertEqual(dp_optimum(inst, 1, 3)[0], INF)                    # Q = 40 % of the demand: one route cannot serve all
            self.assertEqual(dp_optimum(inst, 1, 3)[1], None)

    def test_unlimited_depots_and_fleet_give_one_customer_per_route_from_the_best_depot(self):
        inst = random_instance(3, n=6, m=3, q_tightness=1.0)
        v, _ = dp_optimum(inst, K=6, p=3)
        self.assertAlmostEqual(v, sum(min(inst.ddc[d][j] for d in range(3)) for j in range(6)))

    def test_depot_capacity_needs_brute_force(self):
        inst = random_instance(2, n=5, m=3, depot_cap=True)
        self.assertTrue(has_depot_cap(inst))
        with self.assertRaises(NotImplementedError):
            dp_optimum(inst, 5, 3)
        capped, sol = brute_force(inst, 5, 3)
        self.assertTrue(feasible(inst, sol, 5, 3))
        free = random_instance(2, n=5, m=3)
        self.assertLessEqual(brute_force(free, 5, 3)[0], capped + 1e-9)

    def test_opening_and_vehicle_cost_in_brute_force(self):
        inst = random_instance(4, n=5, m=3, open_cost=True, vehicle_cost=7.0)
        v, sol = brute_force(inst, 5, 3)
        self.assertAlmostEqual(objective(inst, sol), v)
        base = random_instance(4, n=5, m=3)
        self.assertGreater(v, brute_force(base, 5, 3)[0])
        with self.assertRaises(NotImplementedError):
            dp_optimum(inst, 5, 3)

    def test_size_guards(self):
        with self.assertRaises(ValueError):
            brute_force(random_instance(0, n=7), 7, 3)
        with self.assertRaises(ValueError):
            dp_optimum(random_instance(0, n=12), 12, 3)


class HeuristicsVsOptimum(unittest.TestCase):
    """A heuristic that returns a feasible solution can never be below the optimum (a check of the evaluator and of the feasibility
    test); on tiny instances the kit's GRASP and ILS should reach it."""

    def setUp(self):
        # other test modules switch the global depot-layer mode on and leave its elite sets of other instances behind
        depot_impact.configure('off', 5, seed=1, every=1)

    def test_never_below_and_usually_equal(self):
        reached = total = 0
        for seed in range(6):
            inst = random_instance(seed, n=8, m=3, q_tightness=0.4)
            K, p = 4, 2
            opt, _ = dp_optimum(inst, K, p)
            for solve, kw in ((H.solve_grasp, dict()), (H.solve_ils, dict(ils_iters=10))):
                best, z, *_ = solve(inst, K, p, seed, 6, 0.3, 'first', 'loffler9', **kw)
                self.assertTrue(feasible(inst, best, K, p))
                self.assertAlmostEqual(objective(inst, best), z, places=7)
                self.assertGreaterEqual(z, opt - 1e-7, (seed, solve.__name__))   # cannot beat the exact optimum
                total += 1
                reached += z <= opt + 1e-7
        self.assertGreaterEqual(reached, total // 2, f'only {reached}/{total} heuristic runs reached the optimum on n = 8')


if __name__ == '__main__':
    unittest.main()
