"""clean.6.4.0 adaptive depot impact: feasibility, restriction to the elite set, non-degradation, schedule gates,
fixed_trials equivalence with structural, and isolation of the older modes."""
import random
import time
import unittest
from common import ROOT
from llrp_framework.core import read_dat, feasible, objective, used_depots
from llrp_framework.construction import grasp_construct
from llrp_framework.local_search import run_local_search, first_descent
from llrp_framework import depot_impact
from llrp_framework.depot_adaptive64 import ruin_recreate, intensify, adaptive_maybe


def polish(i, c, k, pp, a, d):
    return first_descent(i, c, k, pp, a, 'loffler9', d)


class Adaptive64(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst = read_dat(ROOT / 'data/P/coord100-10-1b.dat')
        cls.allowed = list(range(cls.inst.m))
        sol = grasp_construct(cls.inst, cls.inst.n, cls.allowed, random.Random(42), .05)
        assert sol and feasible(cls.inst, sol)
        cls.sol, cls.z, _ = first_descent(cls.inst, sol, cls.inst.n, cls.inst.m, cls.allowed, 'loffler9',
                                          time.perf_counter() + 20)

    def test_configure_validation(self):
        depot_impact.configure('adaptive', 10, seed=1)
        for bad in (dict(first_frac=1.0), dict(period_frac=0), dict(exploit_slice=0), dict(cap_exp=-1)):
            with self.assertRaises(ValueError):
                depot_impact.configure('adaptive', 10, seed=1, **bad)
        with self.assertRaises(ValueError):
            depot_impact.configure('nope', 10)

    def test_ruin_recreate_stays_inside_target(self):
        target = tuple(sorted(used_depots(self.sol)))
        rng = random.Random(3)
        made = 0
        for frac in (0.05, 0.10, 0.18, 0.30):
            cand = ruin_recreate(self.inst, self.inst.n, self.sol, target, rng, frac, time.perf_counter() + 5)
            if cand is None:
                continue
            made += 1
            self.assertTrue(feasible(self.inst, cand, self.inst.n, self.inst.m))
            self.assertTrue(set(used_depots(cand)).issubset(target))
        self.assertGreaterEqual(made, 2)

    def test_intensify_never_degrades_and_respects_deadline(self):
        t0 = time.perf_counter()
        best, bz, _, iters, improved = intensify(self.inst, self.sol, self.z, self.inst.n, self.inst.m,
                                                 random.Random(7), t0 + 3.0, polish)
        self.assertLess(time.perf_counter() - t0, 3.0 + 1.5)
        self.assertLessEqual(bz, self.z + 1e-7)
        self.assertTrue(feasible(self.inst, best, self.inst.n, self.inst.m))
        self.assertAlmostEqual(bz, objective(self.inst, best), places=6)
        self.assertTrue(set(used_depots(best)).issubset(set(used_depots(self.sol))))
        self.assertGreaterEqual(iters, 1)

    def test_schedule_gates(self):
        inst = read_dat(ROOT / 'data/P/coord20-5-1.dat')
        allowed = list(range(inst.m))
        sol = grasp_construct(inst, inst.n, allowed, random.Random(8), .05)
        sol, z, _ = first_descent(inst, sol, inst.n, inst.m, allowed, 'loffler9', time.perf_counter() + 5)
        depot_impact.configure('adaptive', 20, seed=8, max_share=.5, event_seconds=1, min_interval=0,
                               first_frac=.5, period_frac=.25, exploit_start=.7, exploit_slice=.05)
        S = depot_impact.S
        rng = random.Random(8)
        dl = time.perf_counter() + 60
        # 1) before first_frac * budget: nothing happens, but the hook still registers the elite
        out = depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, rng, dl, polish)
        self.assertEqual(S['events'], 0)
        self.assertEqual(out[1], z)
        # 2) after it: one exploration event
        S['start'] -= 11
        depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, rng, dl, polish)
        self.assertEqual((S['events'], S['adapt_explore'], S['adapt_exploit']), (1, 1, 0))
        # 3) period gate: an immediate second call is refused
        depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, rng, dl, polish)
        self.assertEqual(S['events'], 1)
        # 4) exploit phase (elapsed >= 0.7 * 20 s): next allowed event is an exploitation event
        S['start'] -= 5
        S['last_event'] -= 100
        got, gz, _ = depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, rng, dl, polish)
        self.assertEqual((S['adapt_exploit'], S['adapt_since_explore']), (1, 1))
        self.assertLessEqual(gz, z + 1e-7)
        self.assertTrue(feasible(inst, got, inst.n, inst.m))
        self.assertAlmostEqual(gz, objective(inst, got), places=6)
        st = depot_impact.stats()
        self.assertIn('depot_adapt_exploit', st)
        self.assertGreaterEqual(st['depot_adapt_first_event_s'], 10.9)

    def test_exploit_disabled_by_start_at_one(self):
        inst = read_dat(ROOT / 'data/P/coord20-5-1.dat')
        allowed = list(range(inst.m))
        sol = grasp_construct(inst, inst.n, allowed, random.Random(8), .05)
        sol, z, _ = first_descent(inst, sol, inst.n, inst.m, allowed, 'loffler9', time.perf_counter() + 5)
        depot_impact.configure('adaptive', 20, seed=8, max_share=.5, event_seconds=1, min_interval=0,
                               first_frac=.0, period_frac=.01, exploit_start=1.0)
        S = depot_impact.S
        S['start'] -= 19
        depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, random.Random(1), time.perf_counter() + 30, polish)
        self.assertEqual(S['adapt_exploit'], 0)

    def test_stall_returns_to_exploration(self):
        inst = read_dat(ROOT / 'data/P/coord20-5-1.dat')
        allowed = list(range(inst.m))
        sol = grasp_construct(inst, inst.n, allowed, random.Random(8), .05)
        sol, z, _ = first_descent(inst, sol, inst.n, inst.m, allowed, 'loffler9', time.perf_counter() + 5)
        depot_impact.configure('adaptive', 20, seed=8, max_share=.5, event_seconds=1, min_interval=0,
                               first_frac=.0, period_frac=.01, exploit_start=.1)
        S = depot_impact.S
        S['start'] -= 19
        S['adapt_stall'] = 2                       # exploitation has stalled: the next event must explore
        depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, random.Random(1), time.perf_counter() + 30, polish)
        self.assertEqual((S['adapt_exploit'], S['adapt_explore']), (0, 1))
        S['adapt_stall'] = 0                       # a fresh start exploits again
        S['last_event'] -= 100
        depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, random.Random(1), time.perf_counter() + 30, polish)
        self.assertEqual(S['adapt_exploit'], 1)

    def test_events_do_not_touch_host_rng(self):
        inst = read_dat(ROOT / 'data/P/coord20-5-1.dat')
        allowed = list(range(inst.m))
        sol = grasp_construct(inst, inst.n, allowed, random.Random(8), .05)
        sol, z, _ = first_descent(inst, sol, inst.n, inst.m, allowed, 'loffler9', time.perf_counter() + 5)
        depot_impact.configure('adaptive', 20, seed=8, max_share=.5, event_seconds=1, min_interval=0,
                               first_frac=.0, period_frac=.01, exploit_start=.1)
        S = depot_impact.S
        S['start'] -= 19
        host = random.Random(1)
        before = host.getstate()
        for _ in range(3):                                   # exploration and exploitation events
            S['last_event'] -= 100
            depot_impact.maybe(inst, sol, z, inst.n, inst.m, allowed, host, time.perf_counter() + 30, polish)
        self.assertGreaterEqual(S['events'], 2)
        self.assertEqual(host.getstate(), before)

    def test_fixed_trials_equals_structural(self):
        inst = read_dat(ROOT / 'data/P/coord20-5-1.dat')
        allowed = list(range(inst.m))
        sol = grasp_construct(inst, inst.n, allowed, random.Random(8), .05)
        res = {}
        for mode in ('structural', 'adaptive'):
            depot_impact.configure(mode, None, seed=8, every=1, max_share=.5, event_seconds=1, min_interval=0)
            # same path as local_search.run_local_search('first', ..., 'loffler9'), called on the module this test configured
            s0, z0, mv0 = first_descent(inst, sol, inst.n, inst.m, allowed, 'loffler9', time.perf_counter() + 3)
            got, z, mv = depot_impact.maybe(inst, s0, z0, inst.n, inst.m, allowed, random.Random(8),
                                            time.perf_counter() + 3, polish)
            res[mode] = (round(z, 9), [(r.depot, tuple(r.seq)) for r in got], mv0 + mv, depot_impact.stats()['depot_events'])
        self.assertEqual(res['structural'], res['adaptive'])
        self.assertEqual(res['adaptive'][3], 1)

    def test_older_modes_have_no_adaptive_columns(self):
        for mode in ('off', 'balanced', 'structural'):
            depot_impact.configure(mode, 5, seed=1)
            self.assertNotIn('depot_adapt_explore', depot_impact.stats())
        depot_impact.configure('adaptive', 5, seed=1)
        self.assertIn('depot_adapt_explore', depot_impact.stats())


if __name__ == '__main__':
    unittest.main()
