"""Preset `loffler9` (clean.6.2): Loffler-aligned operator set and its first-improvement descent.

* the preset lists the operators of Table 1 of Loffler, Bartolini, Schneider (2023) that exist in the framework, in that table's relative order;
* every operator of the preset has a first-improvement implementation (delta and reference are compared operator by operator in
  test_delta_equivalence.py; the whole descent is compared in Drivers.test_drivers_follow_the_same_trajectory);
* the first-improvement descent ends in a local optimum of all nine neighbourhoods (no operator finds an improving move), never worsens a
  solution, keeps it feasible, and is deterministic;
* the Phase A presets and drivers are unchanged by the addition (frozen lists).
"""
import random, unittest
from common import ROOT, PKG  # noqa: F401
from llrp_framework import core, neighborhoods as NB, local_search as LS, construction
from llrp_framework.core import clone_solution
from llrp_framework.params import REGISTERED

LOFFLER9 = ['intra_relocate1', 'inter_relocate1', 'intra_swap11', 'inter_swap11', 'intra_relocate2', 'inter_relocate2',
            'inter_swap22', 'route_split', 'two_opt_star']


class Loffler9(unittest.TestCase):
    def test_preset_content_and_order(self):
        self.assertEqual(NB.PRESETS['loffler9'], LOFFLER9)
        for op in LOFFLER9:
            self.assertIn(op, NB.NEIGHBORHOODS); self.assertIn(op, LS._FIRST_OPS)
        # relative order of Loffler's Table 1: Relocate-1, Exchange-1, Relocate-2, Exchange-2, Split-b/f, 2-Opt*
        i = {o: k for k, o in enumerate(LOFFLER9)}
        self.assertLess(i['inter_relocate1'], i['intra_swap11']); self.assertLess(i['inter_swap11'], i['intra_relocate2'])
        self.assertLess(i['inter_relocate2'], i['inter_swap22']); self.assertLess(i['inter_swap22'], i['route_split'])
        self.assertLess(i['route_split'], i['two_opt_star'])
        # no intra-route 2-opt and no depot move: as in that table
        self.assertNotIn('intra_2opt', LOFFLER9); self.assertNotIn('depot_reassign', LOFFLER9)

    def test_earlier_presets_unchanged(self):
        self.assertEqual(NB.PRESETS['baseline_route'], ['intra_relocate1', 'inter_relocate1', 'intra_swap11', 'inter_swap11', 'intra_2opt'])
        self.assertEqual(NB.PRESETS['common5'], ['intra_relocate1', 'intra_2opt', 'inter_relocate1', 'inter_swap11', 'depot_reassign'])
        self.assertEqual(len(NB.PRESETS['hgamp']), 15)
        self.assertEqual(LS._FIRST_OPS[:6], ('intra_relocate1', 'inter_relocate1', 'intra_swap11', 'inter_swap11', 'intra_2opt', 'depot_reassign'))

    def test_first_descent_ends_in_a_local_optimum(self):
        construction.set_rcl_policy('cardinality', 7)
        rng = random.Random(11); improved = 0
        for nm in ('coord20-5-1', 'coord50-5-1'):
            prm = REGISTERED[nm]; inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
            allowed = list(range(inst.m))
            for k in range(3):
                start = None
                while start is None:
                    start = construction.grasp_construct(inst, inst.n, allowed, rng, rng.choice([0.3, 0.8]))
                start = core.normalize(inst, start); z0 = core.objective(inst, start)
                cur, z, moves = LS.first_descent(inst, clone_solution(start), inst.n, inst.m, allowed, 'loffler9')
                self.assertTrue(core.feasible(inst, cur, inst.n, inst.m))
                self.assertLessEqual(z, z0); self.assertAlmostEqual(z, core.objective(inst, cur), places=6)
                improved += z < z0 - 1e-9
                for op in LOFFLER9:
                    self.assertIsNone(NB.NEIGHBORHOODS[op](inst, cur, inst.n, inst.m, allowed), f'{nm} {k}: {op} still improves')
                cur2, z2, moves2 = LS.first_descent(inst, clone_solution(start), inst.n, inst.m, allowed, 'loffler9')   # deterministic
                self.assertEqual((z, moves), (z2, moves2))
        self.assertGreater(improved, 3)


if __name__ == '__main__':
    unittest.main()
