"""Coordinated depot operators (depot_ops.py): contract, hand-made cases where one move changes the depot set, VND with the depot presets."""
import random, time, unittest
from common import ROOT, PKG  # noqa: F401
from test_delta_equivalence import random_instance, random_solution, sig
from llrp_framework import core, neighborhoods as NB, depot_ops as DO, local_search as LS, construction
from llrp_framework.core import Route, clone_solution
from llrp_framework.params import REGISTERED

EPS = 1e-10


def tiny_line_instance(open_cost, cust_x, demand, dep_x, Q=100.0, cap=1000.0, vehicle=0.0):
    rule = 'ceil100_euclidean'
    cust = [(x, 0.0) for x in cust_x]; dep = [(x, 0.0) for x in dep_x]
    dcc = [[core._metric(a, b, rule) for b in cust] for a in cust]; ddc = [[core._metric(a, b, rule) for b in cust] for a in dep]
    return core.Instance(len(cust), len(dep), cust, dep, [float(d) for d in demand], Q, dcc, ddc, [cap] * len(dep), [float(o) for o in open_cost], vehicle, 'P', rule)


class Contract(unittest.TestCase):
    def check(self, inst, sol, K, p, label):
        allowed = list(range(inst.m)); z0 = core.objective(inst, sol); found = 0
        for polish in (False, True):
            DO.POLISH = polish
            try:
                for name in DO.DEPOT_OPERATORS:
                    a = clone_solution(sol)
                    res = NB.NEIGHBORHOODS[name](inst, a, K, p, allowed)
                    self.assertEqual(sig(a), sig(sol), f'{label} {name}: input modified')
                    again = NB.NEIGHBORHOODS[name](inst, clone_solution(sol), K, p, allowed)
                    self.assertEqual(None if res is None else (repr(res[0]), sig(res[1])), None if again is None else (repr(again[0]), sig(again[1])), f'{label} {name}: not deterministic')
                    if res is None: continue
                    found += 1
                    z, s = res
                    self.assertTrue(core.feasible(inst, s, K, p), f'{label} {name}: infeasible')
                    self.assertEqual(repr(z), repr(core.objective(inst, s)), f'{label} {name}: objective mismatch')
                    self.assertLess(z, z0 - EPS)
                    self.assertEqual(sorted(c for r in s for c in r.seq), list(range(inst.n)))
            finally:
                DO.POLISH = True
        return found

    def test_random_tiny_instances(self):
        rng = random.Random(99); found = 0
        for t in range(120):
            inst = random_instance(rng, rng.randint(5, 12), rng.randint(2, 4), 'real_euclidean' if t % 2 else 'ceil100_euclidean')
            sol = random_solution(inst, rng)
            if sol is None: continue
            found += self.check(inst, sol, inst.n, inst.m, f'tiny{t}')
        self.assertGreater(found, 20)

    def test_benchmark_instances(self):
        construction.set_rcl_policy('cardinality', 7); rng = random.Random(3); found = 0
        for nm in ('coord20-5-1', 'coord50-5-3'):
            prm = REGISTERED[nm]; inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
            for _ in range(3):
                s = None
                while s is None: s = construction.grasp_construct(inst, inst.n, list(range(inst.m)), rng, 0.02)
                found += self.check(inst, core.normalize(inst, s), inst.n, inst.m, nm)
        self.assertGreater(found, 3)

    def test_deadline_propagates(self):
        rng = random.Random(1); inst = random_instance(rng, 8, 3, 'ceil100_euclidean'); sol = random_solution(inst, rng)
        NB.set_scan_deadline(time.perf_counter() - 1.0)
        try:
            raised = 0
            for name in DO.DEPOT_OPERATORS:
                try: NB.NEIGHBORHOODS[name](inst, clone_solution(sol), inst.n, inst.m, list(range(inst.m)))
                except NB.ScanTimeout: raised += 1
            self.assertGreaterEqual(raised, 1)
        finally:
            NB.set_scan_deadline(None)


class HandMade(unittest.TestCase):
    """Three depots on a line at x = 0, 100, 200, vehicle capacity 2 (two routes per depot): a depot cannot be closed by moving one route or one customer."""

    def test_close_removes_a_remote_depot(self):
        inst = tiny_line_instance([100000, 100000, 100000], [5, 10, 15, 20, 95, 98, 101, 195, 198, 201], [1] * 10, [0, 100, 200], Q=2.0)
        sol = core.normalize(inst, [Route(0, [0, 1], 0), Route(0, [2, 3], 0), Route(1, [4, 5], 0), Route(1, [6], 0), Route(2, [7, 8], 0), Route(2, [9], 0)])
        z0 = core.objective(inst, sol)
        res = NB.NEIGHBORHOODS['depot_close'](inst, sol, inst.n, inst.m, [0, 1, 2])
        self.assertIsNotNone(res); self.assertLess(res[0], z0)
        self.assertLess(len(core.used_depots(res[1])), 3)
        # lock-in: the common Core-5 descent cannot close a depot (each single relocation is uphill), see the VND test below
        _, z_core, _ = LS.vnd(inst, clone_solution(sol), inst.n, inst.m, [0, 1, 2], 'common5')
        self.assertGreater(z_core, res[0])

    def test_move_all_relocates_a_whole_depot(self):
        inst = tiny_line_instance([1000, 1000, 1000], [3, 6, 9, 12], [1] * 4, [0, 100, 200])
        sol = core.normalize(inst, [Route(2, [0, 1], 0), Route(2, [2, 3], 0)])      # everything served from the far depot 2
        res = NB.NEIGHBORHOODS['depot_move_all'](inst, sol, inst.n, inst.m, [0, 1, 2])
        self.assertIsNotNone(res)
        self.assertEqual({r.depot for r in res[1]}, {0})
        self.assertLess(res[0], core.objective(inst, sol))

    def test_open_builds_routes_at_a_closed_depot(self):
        inst = tiny_line_instance([100, 100, 100], [3, 6, 9, 12, 15], [1] * 5, [0, 100, 200])
        sol = core.normalize(inst, [Route(1, [0, 1, 2, 3, 4], 0)])                  # all customers served from depot 1, 100 away
        res = NB.NEIGHBORHOODS['depot_open'](inst, sol, inst.n, inst.m, [0, 1, 2])
        self.assertIsNotNone(res); self.assertEqual({r.depot for r in res[1]}, {0})

    def test_vnd_with_depot_preset_changes_the_depot_set(self):
        inst = tiny_line_instance([100000, 100000, 100000], [5, 10, 15, 20, 95, 98, 101, 195, 198, 201], [1] * 10, [0, 100, 200], Q=2.0)
        sol = core.normalize(inst, [Route(0, [0, 1], 0), Route(0, [2, 3], 0), Route(1, [4, 5], 0), Route(1, [6], 0), Route(2, [7, 8], 0), Route(2, [9], 0)])
        base, z_base, _ = LS.vnd(inst, clone_solution(sol), inst.n, inst.m, [0, 1, 2], 'common5')
        dep, z_dep, _ = LS.vnd(inst, clone_solution(sol), inst.n, inst.m, [0, 1, 2], 'common5_depot')
        self.assertLess(z_dep, z_base - 50000)                                    # saves at least one opening cost net of the detour
        self.assertTrue(core.feasible(inst, dep, inst.n, inst.m))


class Presets(unittest.TestCase):
    def test_frozen_presets_untouched_and_new_presets_registered(self):
        self.assertEqual(NB.PRESETS['common5'], ['intra_relocate1', 'intra_2opt', 'inter_relocate1', 'inter_swap11', 'depot_reassign'])
        self.assertEqual(len(NB.PRESETS['hgamp']), 15)
        self.assertEqual(NB.PRESETS['common5_depot'][:5], NB.PRESETS['common5'])
        self.assertEqual(NB.PRESETS['hgamp_depot'][:15], NB.PRESETS['hgamp'])
        for pr in ('common5_depot', 'hgamp_depot'):
            for op in NB.PRESETS[pr]: self.assertIn(op, NB.NEIGHBORHOODS)


if __name__ == '__main__':
    unittest.main()
