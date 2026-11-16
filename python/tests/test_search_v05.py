"""v0.5 search components: start mix, depot race, route pool + set-partitioning polish.

* START_MIX = 0 must leave every result of the previous versions bit-identical (rng.random() is drawn only when START_MIX > 0).
* DepotRace is a pure scheduler: every arm is pulled before an arm is pulled a second time at the latest after the window has
  rotated through the ranking, the window keeps the best arms, and the p-median order is the prior.
* The set-partitioning recombination never returns a worse solution than the incumbent and its result is a feasible LLRP solution.
"""
import pathlib, random, subprocess, sys, tempfile, unittest, csv
from common import ROOT, RUNNER, SMOKE_INSTANCE
from llrp_framework import core, heuristics as H, route_pool, depot_impact, construction
from llrp_framework.core import read_dat, objective, feasible
from llrp_framework.params import REGISTERED, reference_kp


def setUpModule():
    # Other test modules of the suite switch process-wide options (depot-impact layer, RCL policy) on and may not switch them off;
    # a time-triggered layer left on would make two identical runs differ. These tests need the plain defaults.
    depot_impact.configure('off')
    construction.set_rcl_policy('cardinality', 7)
    route_pool.disable()


def load(name):
    prm = REGISTERED[name]
    return read_dat(ROOT / 'data' / prm['family'] / prm['file']), reference_kp(name)


def ils(inst, K, p, seed, **kw):
    return H.solve_ils(inst, K, p, seed, 1, 0.3, 'first', 'loffler9', depot_mode=kw.pop('depot_mode', 'pmedian'),
                       budget_mode='fixed_trials', ils_iters=3, **kw)


class StartMix(unittest.TestCase):
    def tearDown(self):
        H.configure_search(0.0, 2.0, 8)

    def test_zero_mix_is_bit_identical(self):
        inst, (K, p) = load(SMOKE_INSTANCE)
        H.configure_search(0.0)
        a = ils(inst, K, p, 3)
        H.configure_search(0.0, race_gamma=3.0, race_explore=2)       # race parameters must not matter outside race mode
        b = ils(inst, K, p, 3)
        self.assertEqual(repr(a[1]), repr(b[1]))
        self.assertEqual(a[2], b[2])

    def test_mixed_starts_are_feasible(self):
        inst, (K, p) = load(SMOKE_INSTANCE)
        for q in (0.5, 1.0):
            H.configure_search(q)
            sol, z, *_ = ils(inst, K, p, 4)
            self.assertTrue(feasible(inst, sol, K, p))
            self.assertAlmostEqual(z, objective(inst, sol), places=6)

    def test_invalid_parameters(self):
        for bad in (dict(start_mix=-0.1), dict(start_mix=1.5), dict(race_gamma=-1.0), dict(race_explore=-1)):
            with self.assertRaises(ValueError):
                H.configure_search(**bad)


class Race(unittest.TestCase):
    def setUp(self):
        self.inst, _ = load('coord50-5-2bBIS')

    def pull_all(self, race, passes, value):
        for _ in range(passes):
            for S in race.round():
                core.arm_reset(); core._ARM_BEST[0] = value(race.rank[S])

    def test_arms_follow_pmedian_order(self):
        race = H.DepotRace(self.inst, 3, 50, 2.0, 8, 6)
        self.assertEqual(race.arms, list(H._pmedian_ranking(self.inst, 3)[:50]))
        self.assertAlmostEqual(race.prior[race.arms[3]], 1.0 / 16.0)

    def test_pulls_follow_the_rank_prior_and_every_arm_is_reached(self):
        race = H.DepotRace(self.inst, 3, 50, 2.0, 8, 6)
        self.pull_all(race, 20, lambda r: 1000.0)                        # no evidence: the prior alone decides
        pulls = [race.pulls[S] for S in race.arms]
        self.assertEqual(sum(pulls), 120)
        self.assertEqual(pulls[0], max(pulls))                           # the rank-1 set gets the largest share
        self.assertGreaterEqual(pulls[0], 2 * pulls[1])
        self.assertTrue(all(v >= 1 for v in pulls))                      # 10 arms: the exploration pulls reach the tail

    def test_one_bad_block_does_not_remove_the_top_arm(self):
        race = H.DepotRace(self.inst, 3, 50, 2.0, 8, 6)
        self.pull_all(race, 6, lambda r: 1300.0 if r == 0 else 1000.0)    # rank-1 arm looks 30 % worse in every pull
        self.assertGreaterEqual(race.pulls[race.arms[0]], 5)             # evidence reduces the weight but does not eliminate the arm

    def test_race_mode_runs_and_is_reproducible(self):
        inst, (K, p) = load(SMOKE_INSTANCE)
        a = ils(inst, K, p, 5, depot_mode='race')
        b = ils(inst, K, p, 5, depot_mode='race')
        self.assertEqual(repr(a[1]), repr(b[1]))
        self.assertTrue(feasible(inst, a[0], K, p))

    def test_sequence_protocol_for_methods_that_index_the_subsets(self):
        rng = random.Random(2)
        r = H._depot_subsets(self.inst, 3, rng, 'race', 50)
        self.assertEqual(len(r), 6)
        self.assertIn(rng.choice(r), [r[i] for i in range(len(r))])


class RoutePool(unittest.TestCase):
    def tearDown(self):
        route_pool.disable()

    def test_recombination_never_worse_and_feasible(self):
        try:
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest('scipy not installed')
        inst, (K, p) = load(SMOKE_INSTANCE)
        pool = route_pool.enable(inst, theta=0.10)
        sol, z, *_ = ils(inst, K, p, 6)
        self.assertGreater(len(pool.cols), 0)
        new, info = route_pool.recombine(inst, K, p, sol, z, 20.0, pool=pool)
        self.assertIn(info['sp_status'], ('optimal', 'time_limit'))
        if new is not None:
            self.assertTrue(feasible(inst, new, K, p))
            self.assertLess(objective(inst, new), z - 1e-9)
        else:
            self.assertFalse(info['sp_improved'])

    def test_missing_scipy_is_reported_not_fatal(self):
        inst, (K, p) = load(SMOKE_INSTANCE)
        pool = route_pool.enable(inst)
        sol, z, *_ = ils(inst, K, p, 7)
        import builtins
        real = builtins.__import__

        def no_scipy(name, *a, **k):
            if name.startswith('scipy'):
                raise ImportError(name)
            return real(name, *a, **k)
        builtins.__import__ = no_scipy
        try:
            new, info = route_pool.recombine(inst, K, p, sol, z, 5.0, pool=pool)
        finally:
            builtins.__import__ = real
        self.assertIsNone(new)
        self.assertEqual(info['sp_status'], 'no_scipy')


class RunnerFlags(unittest.TestCase):
    def test_race_and_sp_share_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [sys.executable, str(ROOT / RUNNER), '--kit-root', str(ROOT), '--instances', SMOKE_INSTANCE, '--seeds', '1',
                   '--out-dir', tmp, '--heuristic', 'ils', '--local-search', 'first', '--neighborhoods', 'loffler9',
                   '--budget-mode', 'fixed_time', '--time-limit', '6', '--depot-mode', 'race', '--start-mix', '0.5', '--sp-share', '0.2']
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            self.assertEqual(res.returncode, 0, res.stderr)
            with open(pathlib.Path(tmp) / 'summary.csv', newline='') as f:
                row = next(csv.DictReader(f))
            self.assertIn(row['sp_status'], ('optimal', 'time_limit', 'no_scipy'))
            self.assertEqual(row['feasible'], 'True')
            self.assertLessEqual(float(row['budget_overrun_s']), 0.5)
            v = subprocess.run([sys.executable, str(ROOT / 'verify_run.py'), tmp, '--kit-root', str(ROOT), '--no-manifest'], capture_output=True, text=True)
            self.assertEqual(v.returncode, 0, v.stdout + v.stderr)


if __name__ == '__main__':
    unittest.main()
