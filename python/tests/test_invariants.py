"""Behavioural invariants that must hold for any version of the code (independent of the golden files)."""
import random, tempfile, unittest, pathlib
from common import ROOT, PROBLEM, PKG, SMOKE_INSTANCE, mod
import testlib as g

core, cons, nb, meta, heur, ls, rep = (mod(n) for n in ('core', 'construction', 'neighborhoods', 'meta_utils', 'heuristics', 'local_search', 'reporting'))
M = g.load_framework(PKG, ROOT)

# 3 customers on a 3-4-5 triangle layout, one depot at the origin.
TOY = "3 1\n0 0\n3 0\n3 4\n0 4\n10\n100\n1 1 1\n1000\n500\n0\n"


def signature(sol):
    return sorted((r.depot, tuple(r.seq)) for r in sol if r.seq)


class ToyInstance(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(self._tmp.name) / 'toy.dat'
        path.write_text(TOY)
        self.inst = core.read_dat(path)
        self.R = core.Route

    def tearDown(self):
        self._tmp.cleanup()

    def test_parser_and_distance_rule(self):
        i = self.inst
        self.assertEqual((i.n, i.m, i.Q), (3, 1, 10.0))
        self.assertAlmostEqual(i.dcc[0][1], 4.0 if PROBLEM == 'LLRP' else 400.0)   # LLRP: ceil(100*d)
        self.assertAlmostEqual(i.ddc[0][1], 5.0 if PROBLEM == 'LLRP' else 500.0)

    def test_hand_computed_objectives(self):
        one = [self.R(0, [0, 1, 2], 3)]
        rev = [self.R(0, [2, 1, 0], 3)]
        two = [self.R(0, [0], 1), self.R(0, [2, 1], 2)]
        if PROBLEM == 'LLRP':      # sum of arrival times, no return leg: 3+(3+4)+(3+4+3), ...
            cases = [(one, 20.0), (rev, 22.0), (two, 14.0)]
        else:                      # ceil(100*d) routing + 500 per vehicle + 1000 per opened depot
            cases = [(one, 1400 + 500 + 1000.0), (rev, 1400 + 500 + 1000.0), (two, 600 + 1200 + 2 * 500 + 1000.0)]
        for sol, expected in cases:
            self.assertAlmostEqual(core.objective(self.inst, sol), expected)

    def test_feasibility_rules(self):
        ok = [self.R(0, [0, 1, 2], 3)]
        self.assertTrue(core.feasible(self.inst, ok, 3, 1))
        self.assertFalse(core.feasible(self.inst, [self.R(0, [0, 1], 2)], 3, 1), 'missing customer')
        self.assertFalse(core.feasible(self.inst, [self.R(0, [0, 1, 2], 3), self.R(0, [0], 1)], 3, 1), 'duplicate customer')
        self.assertFalse(core.feasible(self.inst, [self.R(0, [0], 1), self.R(0, [1, 2], 2)], 1, 1), 'fleet limit K=1')
        self.assertFalse(core.feasible(self.inst, [self.R(0, [0, 1, 2], 99)], 3, 1), 'stale load')
        self.inst.Q = 2.0
        self.assertFalse(core.feasible(self.inst, ok, 3, 1), 'vehicle capacity exceeded')


    def test_solution_record_lists_depots_and_routes_and_adds_up(self):
        two = [self.R(0, [0], 1), self.R(0, [2, 1], 2)]
        rec = rep.solution_record(self.inst, two)
        self.assertEqual(rec['open_depots'], [0])
        self.assertEqual([r['customers'] for r in rec['routes']], [[0], [2, 1]])
        self.assertEqual(rep.routes_compact(two), 'd0:0|d0:2-1')
        total = sum(r['cost'] for r in rec['routes']) + sum(d.get('opening_cost', 0.0) for d in rec['depots'])
        self.assertAlmostEqual(total, core.objective(self.inst, two))
        self.assertEqual(rec['depots'][0]['routes'], 2)
        self.assertEqual(rec['depots'][0]['customers'], 3)


class Construction(unittest.TestCase):
    def test_constructions_are_feasible_or_none(self):
        inst, K, p = g.instance_setup(PROBLEM, M, ROOT, SMOKE_INSTANCE)
        allowed = tuple(range(p)) if PROBLEM == 'LLRP' else tuple(range(inst.m))
        built = 0
        for seed in range(25):
            rng = random.Random(seed)
            for sol in (cons.grasp_construct(inst, K, allowed, rng, 0.02),
                        cons.priority_construct(inst, K, allowed, rng.sample(range(inst.n), inst.n), rng)):
                if sol is not None:
                    built += 1
                    self.assertTrue(core.feasible(inst, sol, K, p))
        self.assertGreater(built, 20)


class Neighborhoods(unittest.TestCase):
    def test_every_move_is_feasible_improving_and_consistent(self):
        inst, K, p = g.instance_setup(PROBLEM, M, ROOT, SMOKE_INSTANCE)
        allowed = tuple(range(p)) if PROBLEM == 'LLRP' else tuple(range(inst.m))
        improving = {name: 0 for name in nb.NEIGHBORHOODS}
        for seed in range(10):
            rng = random.Random(seed)
            base = cons.grasp_construct(inst, K, allowed, rng, 0.02)
            if base is None:
                continue
            starts = [base]
            shaken = meta.shake(inst, base, K, p, allowed, rng, 3)
            if shaken is not None:
                starts.append(shaken)
            for start in starts:
                z0, before = core.objective(inst, start), signature(start)
                for name, fn in nb.NEIGHBORHOODS.items():
                    res = fn(inst, start, K, p, allowed)
                    self.assertEqual(signature(start), before, f'{name} mutated its input')
                    if res is None:
                        continue
                    z1, sol1 = res
                    improving[name] += 1
                    with self.subTest(neighborhood=name, seed=seed):
                        self.assertTrue(core.feasible(inst, sol1, K, p))
                        self.assertAlmostEqual(z1, core.objective(inst, sol1), places=9)
                        self.assertLess(z1, z0 - 1e-10)
        self.assertGreaterEqual(sum(1 for v in improving.values() if v), 8, improving)

    def test_local_search_drivers(self):
        inst, K, p = g.instance_setup(PROBLEM, M, ROOT, SMOKE_INSTANCE)
        allowed = tuple(range(p)) if PROBLEM == 'LLRP' else tuple(range(inst.m))
        rng = random.Random(3)
        start = None
        while start is None:
            start = cons.grasp_construct(inst, K, allowed, rng, 0.02)
        z0 = core.objective(inst, start)
        for method, preset in (('vnd', 'common5'), ('vnd', 'light'), ('rvnd', 'hgamp'), ('best', 'common5'), ('first', 'baseline_route')):
            with self.subTest(method=method, preset=preset):
                sol, z, moves = ls.run_local_search(method, inst, start, K, p, allowed, preset, random.Random(1))
                self.assertTrue(core.feasible(inst, sol, K, p))
                self.assertAlmostEqual(z, core.objective(inst, sol), places=9)
                self.assertLessEqual(z, z0 + 1e-9)


class Solvers(unittest.TestCase):
    def kwargs(self, inst, K, p, seed):
        return dict(inst=inst, K=K, p=p, seed=seed, restarts=g.RESTARTS, alpha=0.02, ls_method='none', ls_preset='light',
                    time_limit=None, depot_mode='sample', depot_sample=g.DEPOT_SAMPLE, budget_mode='fixed_trials', **g.SMALL)

    def test_every_solver_is_feasible_consistent_deterministic_and_traced(self):
        inst, K, p = g.instance_setup(PROBLEM, M, ROOT, SMOKE_INSTANCE)
        for name, solve in heur.SOLVERS.items():
            with self.subTest(solver=name):
                core.start_incumbent_trace(checkpoints=(1e6,), max_time=1e6)
                best, z, trials, _mv, _secs, _passes = solve(**self.kwargs(inst, K, p, 11))
                trace = core.stop_incumbent_trace(final_z=z, final_sol=best)
                self.assertIsNotNone(best)
                self.assertTrue(core.feasible(inst, best, K, p))
                self.assertAlmostEqual(z, core.objective(inst, best), places=9)
                self.assertGreater(trials, 0)
                # tracer: strictly improving events, never worse than the returned solution, snapshot is feasible
                objs = [e['objective'] for e in trace['events']]
                times = [e['time_s'] for e in trace['events']]
                self.assertEqual(objs, sorted(objs, reverse=True))
                self.assertEqual(times, sorted(times))
                self.assertLessEqual(trace['trace_best'], z + 1e-7)
                tsol = trace['trace_best_solution']
                self.assertTrue(core.feasible(inst, tsol, K, p))
                self.assertAlmostEqual(core.objective(inst, tsol), trace['trace_best'], places=9)
                # every event carries the incumbent it announces; the checkpoint solution reproduces the checkpoint objective
                for e in trace['events']:
                    self.assertTrue(core.feasible(inst, e['solution'], K, p))
                    self.assertAlmostEqual(core.objective(inst, e['solution']), e['objective'], places=9)
                (cp, cps), = trace['checkpoint_solutions'].items()
                self.assertAlmostEqual(core.objective(inst, cps), trace['checkpoints'][cp], places=9)
                # determinism within one process
                best2, z2, *_ = solve(**self.kwargs(inst, K, p, 11))
                self.assertEqual(signature(best), signature(best2))
                self.assertEqual(z, z2)


if __name__ == '__main__':
    unittest.main()
