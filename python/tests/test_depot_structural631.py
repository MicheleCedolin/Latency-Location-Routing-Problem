"""Depot-set layer of the LLRP kit (depot_structural631.py): target ranking by the p-median bound, swap / swap2 / open kinds,
feasibility under the binding K and p, deadline, and the isolation of the host descent."""
import random
import time
import unittest
from common import ROOT
from llrp_framework.core import read_dat, feasible, objective, used_depots
from llrp_framework.params import REGISTERED
from llrp_framework.construction import grasp_construct
from llrp_framework.depot_structural631 import diversify, ranked_sets, pmedian_bound, rebuild
from llrp_framework.local_search import run_local_search
from llrp_framework import depot_impact, heuristics


def setup(name, seed=42, subset=None):
    prm = REGISTERED[name]
    inst = read_dat(ROOT / 'data' / prm['family'] / prm['file'])
    K, p = prm['K'], prm['p']
    rng = random.Random(seed)
    subset = subset or heuristics._pmedian_ranking(inst, p)[0]
    sol = None
    while sol is None:
        sol = grasp_construct(inst, K, subset, rng, .05)
    return inst, K, p, subset, sol


class DepotStructural(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst, cls.K, cls.p, cls.subset, cls.sol = setup('coord100-10-1b')
        assert feasible(cls.inst, cls.sol, cls.K, cls.p)

    def test_ranked_sets_use_the_whole_depot_universe_and_respect_p(self):
        rng = random.Random(3)
        active = set(used_depots(self.sol))
        for kind in ('swap', 'swap2'):
            opts = ranked_sets(self.inst, self.sol, self.subset, rng, kind, limit=10, p=self.p)
            self.assertTrue(opts, kind)
            for cfg, old, new in opts:
                self.assertLessEqual(len(cfg), self.p)
                self.assertEqual(len(cfg), len(active))
                self.assertTrue(set(cfg) - set(self.subset), 'a closed depot outside the host subset must be reachable')
        bounds = [pmedian_bound(self.inst, cfg) for cfg, _, _ in ranked_sets(self.inst, self.sol, self.subset, random.Random(0), 'swap', limit=50, p=self.p)]
        self.assertLessEqual(bounds[0], bounds[-1] + 0.1)                                   # best bound first (up to the tie-break noise)

    def test_open_kind_needs_a_free_slot(self):
        rng = random.Random(1)
        self.assertEqual(ranked_sets(self.inst, self.sol, self.subset, rng, 'open', p=len(used_depots(self.sol))), [])
        two = [d for d in self.subset][:2]
        inst, K, p, subset, sol = setup('coord100-10-1b', subset=tuple(two))
        opts = ranked_sets(inst, sol, subset, rng, 'open', limit=5, p=3)
        self.assertTrue(opts)
        for cfg, old, new in opts:
            self.assertEqual(len(cfg), len(used_depots(sol)) + 1); self.assertIsNone(old); self.assertIn(new, cfg)
        cand, _, kind = diversify(inst, sol, K, 3, subset, rng, time.perf_counter() + 5, 'open')
        self.assertIsNotNone(cand); self.assertEqual(kind, 'open')
        self.assertTrue(feasible(inst, cand, K, 3)); self.assertEqual(len(used_depots(cand)), len(used_depots(sol)) + 1)

    def test_swap_and_swap2_candidates_are_feasible_and_change_the_set(self):
        before = used_depots(self.sol)
        for kind in ('swap', 'swap2'):
            cand, attempts, actual = diversify(self.inst, self.sol, self.K, self.p, self.subset, random.Random(5), time.perf_counter() + 8, kind)
            self.assertIsNotNone(cand, kind)
            self.assertEqual(actual, kind); self.assertGreaterEqual(attempts, 1)
            self.assertTrue(feasible(self.inst, cand, self.K, self.p))
            self.assertLessEqual(len(used_depots(cand)), self.p)
            self.assertNotEqual(before, used_depots(cand))
            self.assertLessEqual(len(cand), self.K)

    def test_rebuild_is_strict_about_the_target_and_reaches_the_new_depot(self):
        rng = random.Random(9)
        cfg, old, new = ranked_sets(self.inst, self.sol, self.subset, rng, 'swap', limit=1, p=self.p)[0]
        cand = rebuild(self.inst, self.sol, self.K, self.p, self.subset, cfg, old, new, rng, time.perf_counter() + 8)
        self.assertIsNotNone(cand)
        self.assertTrue(used_depots(cand) <= set(cfg)); self.assertIn(new, used_depots(cand))

    def test_pmedian_bound_is_a_lower_bound_on_the_latency(self):
        for seed in range(6):
            inst, K, p, subset, sol = setup('coord50-5-2', seed=seed, subset=tuple(sorted(random.Random(seed).sample(range(5), 3))))
            self.assertLessEqual(pmedian_bound(inst, used_depots(sol)), objective(inst, sol) + 1e-9)
            self.assertLessEqual(pmedian_bound(inst, subset), objective(inst, sol) + 1e-9)          # the subset is a superset of the used depots

    def test_expired_deadline_returns_none(self):
        candidate, _, _ = diversify(self.inst, self.sol, self.K, self.p, self.subset, random.Random(1), time.perf_counter() - 0.1, 'swap')
        self.assertIsNone(candidate)

    def test_shared_local_search_acceptance_not_worse(self):
        # The structural layer may fail to improve, but it must never degrade the original first descent.
        inst, K, p, subset, sol = setup('coord20-5-1', seed=8)
        allowed = list(range(inst.m))
        depot_impact.configure('off', 5, seed=8, every=1)
        baseline, bz, _ = run_local_search('first', inst, sol, K, p, allowed, 'loffler9', random.Random(8))
        depot_impact.configure('structural', 5, seed=8, every=1, max_share=.5, event_seconds=1, min_interval=0)
        got, z, _ = run_local_search('first', inst, sol, K, p, allowed, 'loffler9', random.Random(8), deadline=time.perf_counter() + 3)
        self.assertTrue(feasible(inst, got, K, p))
        self.assertLessEqual(z, bz + 1e-7)
        self.assertAlmostEqual(z, objective(inst, got))
        self.assertEqual(depot_impact.stats()['depot_events'], 1)
        self.assertGreaterEqual(depot_impact.stats()['depot_elite_sets'], 1)

    def test_no_mode_no_depot_events(self):
        depot_impact.configure('off', 5, seed=1, every=1)
        self.assertEqual(depot_impact.stats()['depot_events'], 0)
        self.assertEqual(depot_impact.stats()['depot_struct_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
