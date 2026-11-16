"""LLRP-specific guards: the latency objective, the insertion deltas, the fleet look-ahead on the tight K of all 76 benchmark instances,
the packing fallback, the stand-alone checker and the reference table."""
import csv, math, os, pathlib, random, sys, unittest
from common import ROOT
sys.path.insert(0, str(ROOT / 'tools'))
import indep_check as ic
from llrp_framework import core, construction as C, heuristics as H
from llrp_framework.core import Route, Instance
from llrp_framework.params import REGISTERED

TOY = "3 1\n0 0\n3 0\n3 4\n0 4\n10\n100\n1 1 1\n1000\n500\n0\n"        # depot (0,0); customers (3,0), (3,4), (0,4); Q = 10, unit demands


def toy():
    import tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.dat', delete=False) as f:
        f.write(TOY)
    try:
        return core.read_dat(pathlib.Path(f.name))
    finally:
        os.unlink(f.name)


class Latency(unittest.TestCase):
    def test_hand_computed_latency_has_no_return_arc_and_depends_on_direction(self):
        inst = toy()
        # (3,0) at t=3, (3,4) at t=7, (0,4) at t=10  ->  20
        self.assertAlmostEqual(core.route_latency(inst, Route(0, [0, 1, 2], 0.0)), 3 + 7 + 10)
        # reverse: (0,4) at t=4, (3,4) at t=7, (3,0) at t=11  ->  22
        self.assertAlmostEqual(core.route_latency(inst, Route(0, [2, 1, 0], 0.0)), 4 + 7 + 11)
        # two routes: [0] -> 3, [2,1] -> 4 + 7
        sol = core.normalize(inst, [Route(0, [0], 0.0), Route(0, [2, 1], 0.0)])
        self.assertAlmostEqual(core.objective(inst, sol), 3 + 4 + 7)
        self.assertEqual(core.objective_components(inst, sol)[:2], (0.0, 0.0))
        self.assertEqual(core.arrival_times(inst, 0, [2, 1, 0]), [4.0, 7.0, 11.0])

    def test_profile_uses_real_distances_and_no_opening_or_vehicle_cost(self):
        inst = core.read_dat(ROOT / 'data/P/coord20-5-1.dat')
        self.assertEqual(inst.distance_rule, 'real_euclidean')
        self.assertEqual((inst.open_cost, inst.vehicle_cost), ([0.0] * 5, 0.0))
        self.assertTrue(any(v > 0 for v in inst.open_cost_file))
        self.assertAlmostEqual(inst.ddc[0][0], math.hypot(inst.dep[0][0] - inst.cust[0][0], inst.dep[0][1] - inst.cust[0][1]))

    def test_framework_objective_equals_the_standalone_evaluator(self):
        rng = random.Random(4)
        for name in ('coord20-5-1', 'coord50-5-2', 'coordChrist50', 'coordP111112'):
            prm = REGISTERED[name]; path = ROOT / 'data' / prm['family'] / prm['file']
            inst = core.read_dat(path); d = ic.parse_dat(path)
            for _ in range(5):
                order = list(range(inst.n)); rng.shuffle(order)
                routes, cur, load = [], [], 0.0
                for c in order:
                    if cur and (load + inst.demand[c] > inst.Q or rng.random() < 0.2):
                        routes.append((rng.randrange(inst.m), cur)); cur, load = [], 0.0
                    cur.append(c); load += inst.demand[c]
                routes.append((rng.randrange(inst.m), cur))
                sol = core.normalize(inst, [Route(dp, list(s), 0.0) for dp, s in routes])
                self.assertAlmostEqual(core.objective(inst, sol), ic.latency(d, routes), places=7)


class InsertionDeltas(unittest.TestCase):
    def test_deltas_match_recomputation(self):
        inst = core.read_dat(ROOT / 'data/P/coord50-5-2.dat'); rng = random.Random(1)
        for _ in range(200):
            L = rng.randint(1, 9); seq = rng.sample(range(inst.n), L + 1); c = seq.pop(); dp = rng.randrange(inst.m)
            r = Route(dp, seq, 0.0); base = core.route_latency(inst, r)
            dl = C._route_deltas(inst, r, c)
            self.assertEqual(len(dl), L + 1)
            for pos in range(L + 1):
                ref = core.route_latency(inst, Route(dp, seq[:pos] + [c] + seq[pos:], 0.0)) - base
                self.assertAlmostEqual(dl[pos], ref, delta=1e-9 * max(1.0, abs(ref)))
            self.assertAlmostEqual(C._new_route_cost(inst, set(), c, dp), core.route_latency(inst, Route(dp, [c], 0.0)))


class FleetLookAhead(unittest.TestCase):
    def test_pack_ok_is_a_certificate_and_aggregate_bound(self):
        self.assertTrue(C._pack_ok(sorted([-5, -4, -3]), [8, 4], 8))
        self.assertFalse(C._pack_ok(sorted([-5, -5, -5]), [8, 6], 8))          # 15 > 14: aggregate
        self.assertFalse(C._pack_ok(sorted([-6, -6, -6]), [8, 8, 4], 8))       # aggregate fits (20 >= 18) but 6+6 does not pack into 8,8,4

    def test_packing_fallback_beats_bfd_where_bfd_needs_k_plus_one(self):
        inst = core.read_dat(ROOT / 'data/P/coord100-5-1.dat'); K = REGISTERED['coord100-5-1']['K']
        self.assertFalse(C._root_pack_ok(inst, K))                                 # best-fit decreasing needs 25 vehicles
        bins = C._pack_bins(inst, K, random.Random(1))
        self.assertIsNotNone(bins); self.assertLessEqual(len(bins), K)
        self.assertEqual(sorted(c for b in bins for c in b), list(range(inst.n)))
        self.assertTrue(all(sum(inst.demand[c] for c in b) <= inst.Q + 1e-9 for b in bins))

    def test_constructors_are_feasible_on_all_76_instances_with_binding_k_and_p(self):
        rng = random.Random(11); fails = []
        for name, prm in REGISTERED.items():
            inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file']); K, p = prm['K'], prm['p']
            depots = H._depot_subsets(inst, p, rng, 'pmedian', 3)[0]
            for build in (lambda: C.grasp_construct(inst, K, depots, rng, .02),
                          lambda: C.priority_construct(inst, K, depots, rng.sample(range(inst.n), inst.n), rng)):
                sol = None
                for _ in range(3):                                                  # a construction may legitimately dead-end; 3 tries
                    sol = build()
                    if sol is not None: break
                if sol is None or not core.feasible(inst, core.normalize(inst, sol), K, p): fails.append(name)
        self.assertEqual(fails, [])


    def test_repairs_do_not_dead_end_on_the_tight_fleet_of_100_5_1(self):
        """Greedy / regret-2 repairs lost ~11 % of the moves on 100-5-1 (K = 24, BFD needs 25) before the BFD-certified look-ahead."""
        name = 'coord100-5-1'; prm = REGISTERED[name]; K, p = prm['K'], prm['p']
        inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file']); rng = random.Random(5)
        depots = H._depot_subsets(inst, p, rng, 'pmedian', 1)[0]
        sol = None
        while sol is None: sol = C.grasp_construct(inst, K, depots, rng, .02)
        self.assertEqual(len(sol), K)                                               # every vehicle is in use: only insertions are possible
        n_ok = n = 0
        for destroy in (H._destroy_random, H._destroy_related, H._destroy_worst):
            for repair in (H._repair_greedy, H._repair_regret2):
                for _ in range(15):
                    removed = destroy(inst, sol, 20, rng); partial = H._partial_remove(inst, sol, removed)
                    out = repair(inst, partial, removed, K, depots, rng); n += 1
                    if out is not None:
                        self.assertTrue(core.feasible(inst, core.normalize(inst, out), K, p)); n_ok += 1
        self.assertEqual(n_ok, n)


class RuinSize(unittest.TestCase):
    def test_destroy_size_modes(self):
        inst = core.read_dat(ROOT / 'data/P/coord20-5-2.dat')
        r1 = random.Random(1); r2 = random.Random(1)
        self.assertEqual(H._destroy_size(inst, r1, 0.2, 'fixed'), 4)
        self.assertEqual(r1.getstate(), r2.getstate())                      # fixed mode draws no random number (old runs reproduce)
        qs = {H._destroy_size(inst, r1, 0.2, 'range') for _ in range(400)}
        self.assertEqual((min(qs), max(qs)), (4, 8))                       # n = 20: [max(4, ceil(0.1 n)), ceil(0.4 n)]
        big = core.read_dat(ROOT / 'data/P/coord100-5-1.dat')
        qs = {H._destroy_size(big, r1, 0.2, 'range') for _ in range(2000)}
        self.assertEqual((min(qs), max(qs)), (10, 40))
        self.assertEqual(H._destroy_size(inst, r1, 0.2, 'floor'), 7)                       # n = 20: 0.2 n = 4 is raised to 7
        self.assertEqual(H._destroy_size(big, r1, 0.2, 'floor'), 20)                       # n >= 35: identical to fixed
        self.assertEqual(H._destroy_size(big, r1, 0.2, 'fixed'), 20)


class Depots(unittest.TestCase):
    def test_pmedian_ranking_is_sorted_and_complete(self):
        inst = core.read_dat(ROOT / 'data/P/coord50-5-2.dat')
        rk = H._pmedian_ranking(inst, 3)
        self.assertEqual(len(rk), 10); self.assertEqual(len(set(rk)), 10)
        vals = [sum(min(inst.ddc[d][c] for d in S) for c in range(inst.n)) for S in rk]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual(set(H._depot_subsets(inst, 3, random.Random(0), 'pmedian', 4)), set(rk[:4]))
        self.assertEqual(len(H._depot_subsets(inst, 3, random.Random(0), 'enumerate')), 10)

    def test_depot_capacity_enforce_is_respected_by_the_constructor(self):
        inst = core.read_dat(ROOT / 'data/P/coord20-5-1.dat', depot_capacity='enforce'); prm = REGISTERED['coord20-5-1']
        rng = random.Random(2); done = 0
        for _ in range(10):
            s = C.grasp_construct(inst, prm['K'], (0, 1, 2), rng, .02)
            if s is not None:
                done += 1; self.assertTrue(core.feasible(inst, core.normalize(inst, s), prm['K'], prm['p']))
        self.assertGreater(done, 0)


class ReferenceTable(unittest.TestCase):
    def test_reference_csv_rows(self):
        with open(ROOT / 'reference' / 'LLRP_reference.csv') as fh: rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 76)
        self.assertEqual({g: sum(r['group'] == g for r in rows) for g in 'TPB'}, {'T': 36, 'P': 30, 'B': 10})
        for r in rows:
            self.assertGreaterEqual(int(r['K']), int(r['min_vehicles'])); self.assertGreater(float(r['bks']), 0)

    @unittest.skipUnless(os.environ.get('LLRP_PUBLISHED_DIR'), 'set LLRP_PUBLISHED_DIR to the solutions/ folder of github.com/YujiZou/LLRP')
    def test_published_solutions_reproduce_the_table(self):
        d = pathlib.Path(os.environ['LLRP_PUBLISHED_DIR'])
        known_bad = {'112222', 'Or-117-14', '131122', '122122'}      # incomplete / empty / worse than the table in the published repository
        with open(ROOT / 'reference' / 'LLRP_reference.csv') as fh: ref_rows = list(csv.DictReader(fh))
        for r in ref_rows:
            if r['name'] in known_bad: continue
            dd = ic.parse_dat(ROOT / 'data' / r['group'] / r['file'])
            routes = ic.parse_published(d / r['published_file'], dd['n'], dd['m'])
            probs = [x for x in ic.check(dd, routes, int(r['K']), int(r['p']))[0] if 'capacity' not in x or not x.startswith('depot')]
            self.assertEqual(probs, [], r['name'])                  # only the (ignored) depot capacities may be exceeded
            self.assertAlmostEqual(ic.latency(dd, routes), float(r['bks']), delta=0.011 + 1e-6 * float(r['bks']))


if __name__ == '__main__':
    unittest.main()
