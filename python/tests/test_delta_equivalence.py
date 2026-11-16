"""Delta evaluation (neighborhoods.Scan, local_search first-improvement) must be a pure speed-up.

For every operator, on random feasible solutions of random tiny instances and of the P20/P50 benchmark instances (also under tight
vehicle / depot capacities and binding K, p), the fast operator and the full-recomputation reference (reference_ops.py) must return
the same move: identical objective (bit for bit), identical normalised solution, identical effort counters (objective_evals,
route_evals, candidates), and must leave the input untouched. Whole local-search drivers must follow the same trajectory including
the anytime trace.
"""
import dataclasses, random, time, unittest
from common import ROOT, PKG  # noqa: F401  (puts the kit on sys.path)
from llrp_framework import core, neighborhoods as NB, reference_ops as REF, local_search as LS, construction
from llrp_framework.core import clone_solution, Route
from llrp_framework.meta_utils import random_feasible_neighbor
from llrp_framework.params import REGISTERED

FIRST = ['intra_relocate1', 'inter_relocate1', 'intra_swap11', 'inter_swap11', 'intra_2opt', 'depot_reassign',
         'intra_relocate2', 'inter_relocate2', 'inter_swap22', 'two_opt_star', 'route_split']


def sig(sol):
    return tuple((r.depot, tuple(r.seq), repr(r.load)) for r in sol)


def sig_scan(res):
    return None if res is None else (repr(res[0]), sig(res[1]))


def sig_first(res):
    return None if res is None else (repr(res[1]), sig(res[0]))


def random_instance(rng, n, m, rule):
    cust = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]
    dep = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(m)]
    demand = [float(rng.randint(1, 9)) for _ in range(n)]
    Q = float(rng.randint(12, 30))
    dcc = [[core._metric(a, b, rule) for b in cust] for a in cust]
    ddc = [[core._metric(a, b, rule) for b in cust] for a in dep]
    lo = int(min(Q, sum(demand)))
    cap = [float(rng.randint(lo, int(sum(demand)) + 5)) for _ in range(m)]
    return core.Instance(n, m, cust, dep, demand, Q, dcc, ddc, cap, [float(rng.randint(0, 300)) for _ in range(m)],
                         float(rng.randint(0, 50)), 'P', rule)


def random_solution(inst, rng):
    for _ in range(300):
        order = list(range(inst.n)); rng.shuffle(order)
        routes, cur, load = [], [], 0.0
        for c in order:
            if cur and (load + inst.demand[c] > inst.Q or rng.random() < 0.35):
                routes.append(cur); cur, load = [], 0.0
            cur.append(c); load += inst.demand[c]
        routes.append(cur)
        sol = core.normalize(inst, [Route(rng.randrange(inst.m), s, 0.0) for s in routes])
        if core.feasible(inst, sol):
            return sol
    return None


def compare_all(tc, inst, sol, K, p, label):
    """Every scan operator and every first-improvement move: fast == reference. Returns number of non-None scan results."""
    allowed = list(range(inst.m)); found = 0
    for op in REF.REFERENCE_NEIGHBORHOODS:
        a, b = clone_solution(sol), clone_solution(sol)
        core.reset_objective_evals(); ra = NB.NEIGHBORHOODS[op](inst, a, K, p, allowed); ca = tuple(core._CTR)
        core.reset_objective_evals(); rb = REF.REFERENCE_NEIGHBORHOODS[op](inst, b, K, p, allowed); cb = tuple(core._CTR)
        tc.assertEqual(sig_scan(ra), sig_scan(rb), f'{label} {op}: result')
        tc.assertEqual(ca, cb, f'{label} {op}: counters')
        tc.assertEqual(sig(a), sig(sol), f'{label} {op}: input modified'); found += ra is not None
    z0 = core.objective(inst, sol)
    for op in FIRST:
        for zz in (z0, z0 + 100.0):
            a, b = clone_solution(sol), clone_solution(sol)
            core.reset_objective_evals(); ra = LS._first_improving_move(op, inst, a, K, p, allowed, zz); ca = tuple(core._CTR)
            core.reset_objective_evals(); rb = REF.first_improving_move(op, inst, b, K, p, allowed, zz); cb = tuple(core._CTR)
            tc.assertEqual(sig_first(ra), sig_first(rb), f'{label} first {op}: result')
            tc.assertEqual(ca, cb, f'{label} first {op}: counters')
    return found


class Operators(unittest.TestCase):
    def test_random_tiny_instances(self):
        rng = random.Random(2026); cases = found = 0
        for t in range(150):
            inst = random_instance(rng, rng.randint(4, 12), rng.randint(2, 4), 'real_euclidean' if t % 2 else 'ceil100_euclidean')
            self.assertTrue(core.fast_eval_ok(inst))
            for _ in range(2):
                sol = random_solution(inst, rng)
                if sol is None: continue
                K = min(inst.n, len(sol) + rng.choice([0, 0, 1, 3])); p = min(inst.m, len({r.depot for r in sol}) + rng.choice([0, 0, 1, 3]))
                found += compare_all(self, inst, sol, K, p, f'tiny{t}'); cases += 1
        self.assertGreater(cases, 250); self.assertGreater(found, 500)      # the sample really contains improving moves

    def test_benchmark_instances_plain_and_tight(self):
        construction.set_rcl_policy('cardinality', 7)
        rng = random.Random(77); found = 0
        for nm, nstart in (('coord20-5-1', 6), ('coord50-5-1', 3), ('coord50-5-2BIS', 2)):
            prm = REGISTERED[nm]; inst0 = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
            allowed = list(range(inst0.m))
            for v in range(nstart):
                s = None
                while s is None:
                    s = construction.grasp_construct(inst0, inst0.n, allowed, rng, rng.choice([0.0, 0.3, 0.8]))
                cur = core.normalize(inst0, s)
                for _ in range(rng.choice([0, 3, 10])):
                    q = random_feasible_neighbor(inst0, cur, inst0.n, inst0.m, allowed, rng)
                    if q is not None: cur = q
                loads = [0.0] * inst0.m
                for r in cur: loads[r.depot] += core.recompute_load(inst0, r)
                qmax = max(core.recompute_load(inst0, r) for r in cur)
                for mode in ('plain', 'tight'):
                    inst, K, p = inst0, inst0.n, inst0.m
                    if mode == 'tight':
                        inst = dataclasses.replace(inst0, Q=qmax + rng.choice([0, 1, 5]), depot_cap=[l + rng.choice([0, 3, 12]) for l in loads])
                        K = len(cur) + rng.choice([0, 1]); p = len({r.depot for r in cur}) + rng.choice([0, 1])
                    self.assertTrue(core.feasible(inst, cur, K, p))
                    found += compare_all(self, inst, cur, K, p, f'{nm}/{v}/{mode}')
        self.assertGreater(found, 40)

    def test_vanishing_routes_and_depot_closing_are_exercised(self):
        """A hand-made case: singleton routes, one depot with a single route, a closed depot -> all the opening-cost branches."""
        rule = 'ceil100_euclidean'
        cust = [(10, 10), (12, 11), (50, 50), (52, 51), (90, 10), (88, 12)]
        dep = [(11, 10), (51, 50), (89, 11), (50, 90)]
        n, m = len(cust), len(dep)
        demand = [3.0, 4.0, 5.0, 2.0, 6.0, 1.0]
        dcc = [[core._metric(a, b, rule) for b in cust] for a in cust]; ddc = [[core._metric(a, b, rule) for b in cust] for a in dep]
        inst = core.Instance(n, m, cust, dep, demand, 12.0, dcc, ddc, [30.0, 30.0, 30.0, 30.0], [100.0, 200.0, 150.0, 5.0], 20.0, 'P', rule)
        sol = core.normalize(inst, [Route(0, [0], 0.0), Route(0, [1], 0.0), Route(1, [2], 0.0), Route(1, [3, 5], 0.0), Route(2, [4], 0.0)])
        self.assertTrue(core.feasible(inst, sol))
        found = compare_all(self, inst, sol, n, m, 'hand')
        self.assertGreater(found, 3)      # latency: fewer improving moves on this hand-made case than with closed tours
        # depot 3 is closed, depots 0 and 2 would close if their last routes move; a tight p forbids opening a new depot
        compare_all(self, inst, sol, n, 3, 'hand-p3')
        compare_all(self, inst, sol, len(sol), m, 'hand-K')


class Drivers(unittest.TestCase):
    def _run(self, driver, inst, start, K, p, preset, reference):
        allowed = list(range(inst.m)); NB._FORCE_REFERENCE = reference
        try:
            core.reset_objective_evals(); core.start_incumbent_trace(checkpoints=(1.0,), max_time=float('inf'))
            if driver == 'vnd': out = LS.vnd(inst, clone_solution(start), K, p, allowed, preset)
            elif driver == 'rvnd': out = LS.rvnd(inst, clone_solution(start), K, p, allowed, preset, random.Random(3))
            elif driver == 'best': out = LS.best_descent(inst, clone_solution(start), K, p, allowed, preset)
            else: out = LS.first_descent(inst, clone_solution(start), K, p, allowed, preset)
            tr = core.stop_incumbent_trace(out[1])
        finally:
            NB._FORCE_REFERENCE = False
        events = [(repr(e['objective']), sig(e['solution'])) for e in tr['events']]
        return (repr(out[1]), sig(out[0]), out[2], tuple(core._CTR), events)

    def test_drivers_follow_the_same_trajectory(self):
        construction.set_rcl_policy('cardinality', 7)
        rng = random.Random(5)
        for nm in ('coord20-5-1', 'coord50-5-1'):
            prm = REGISTERED[nm]; inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
            start = None
            while start is None:
                start = construction.grasp_construct(inst, inst.n, list(range(inst.m)), rng, 0.5)
            start = core.normalize(inst, start)
            for driver, preset in (('first', 'baseline_route'), ('vnd', 'common5'), ('rvnd', 'common5'), ('best', 'common5'), ('vnd', 'hgamp'), ('first', 'loffler9')):
                if nm == 'coord50-5-1' and preset == 'hgamp': preset = 'light'
                a = self._run(driver, inst, start, inst.n, inst.m, preset, False)
                b = self._run(driver, inst, start, inst.n, inst.m, preset, True)
                self.assertEqual(a, b, f'{nm} {driver}/{preset}')
                self.assertGreater(len(a[4]), 1, 'the descent should have improved the start')


class Fallbacks(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(1)
        self.inst = random_instance(self.rng, 8, 3, 'ceil100_euclidean')
        self.sol = random_solution(self.inst, self.rng)

    def test_scan_is_used_for_feasible_integer_instances(self):
        self.assertIsNotNone(NB.make_scan(self.inst, self.sol, self.inst.n, self.inst.m))

    def test_non_integer_demands_use_the_reference(self):
        inst = dataclasses.replace(self.inst, demand=[d + 0.5 for d in self.inst.demand], _fast=None)
        self.assertFalse(core.fast_eval_ok(inst))
        self.assertIsNone(NB.make_scan(inst, self.sol, inst.n, inst.m))

    def test_infeasible_or_unnormalised_base_uses_the_reference(self):
        bad = clone_solution(self.sol); bad[0].load += 5.0
        self.assertIsNone(NB.make_scan(self.inst, bad, self.inst.n, self.inst.m))
        empty = clone_solution(self.sol) + [Route(0, [], 0.0)]
        self.assertIsNone(NB.make_scan(self.inst, empty, self.inst.n, self.inst.m))

    def test_deadline_in_the_past_raises_after_counting_one_candidate(self):
        allowed = list(range(self.inst.m)); NB.set_scan_deadline(time.perf_counter() - 1.0)
        try:
            for fn in (NB.NEIGHBORHOODS['intra_swap11'], REF.REFERENCE_NEIGHBORHOODS['intra_swap11']):
                core.reset_objective_evals()
                with self.assertRaises(NB.ScanTimeout):
                    fn(self.inst, clone_solution(self.sol), self.inst.n, self.inst.m, allowed)
                self.assertEqual(core.get_candidate_count(), 1)
        finally:
            NB.set_scan_deadline(None)


if __name__ == '__main__':
    unittest.main()
