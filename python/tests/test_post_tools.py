"""tools/polish_report.py and tools/rank_stats.py: statistics against known values, and an end-to-end run on a tiny synthetic report."""
import csv, importlib, json, math, pathlib, subprocess, sys, tempfile, unittest
from common import ROOT, mod

sys.path.insert(0, str(ROOT / 'tools'))
rs = importlib.import_module('rank_stats')
pr = importlib.import_module('polish_report')
import testlib as g  # noqa: E402

INSTANCES = ('coord20-5-1', 'coord20-5-2')
METHODS = ('grasp', 'sa', 'tabu')


class Statistics(unittest.TestCase):
    def test_distribution_functions(self):
        self.assertAlmostEqual(rs.chi2_sf(3.841458820694124, 1), 0.05, places=9)
        self.assertAlmostEqual(rs.chi2_sf(9.487729036781154, 4), 0.05, places=9)
        self.assertAlmostEqual(rs.f_sf(4.964602743730711, 1, 10), 0.05, places=9)
        self.assertAlmostEqual(rs.norm_sf(1.959963984540054), 0.025, places=9)

    def test_ranks_holm_tau(self):
        r, ties = rs.avg_ranks([3.0, 1.0, 3.0, 2.0])
        self.assertEqual(r, [3.5, 1.0, 3.5, 2.0]); self.assertEqual(ties, [2])
        self.assertEqual([round(x, 4) for x in rs.holm([0.01, 0.04, 0.03, 0.005, 0.2])], [0.04, 0.09, 0.09, 0.025, 0.2])
        self.assertAlmostEqual(rs.kendall_tau_b([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)
        self.assertAlmostEqual(rs.kendall_tau_b([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_friedman_known_example(self):
        # three treatments in perfect agreement over 6 blocks: maximal statistic, tiny p
        M = [[1.0, 2.0, 3.0]] * 6
        mean_r, chi, p, F, pF = rs.friedman(M)
        self.assertEqual(mean_r, [1.0, 2.0, 3.0]); self.assertAlmostEqual(chi, 12.0); self.assertLess(p, 0.005)

    def test_mannwhitney_extremes(self):
        self.assertLess(rs.mannwhitney_p(list(range(30)), list(range(100, 130))), 1e-6)
        self.assertEqual(rs.mannwhitney_p([1.0] * 10, [1.0] * 10), 1.0)


def _make_report(path):
    mods = {n: mod(n) for n in ('core', 'construction', 'heuristics')}
    mods['construction'].set_rcl_policy('cardinality', 7)
    prm = mod('params').REGISTERED
    refs = {k: dict(reference_best=v['bks']) for k, v in prm.items()}
    cols = ['problem', 'instance', 'seed', 'heuristic', 'local_search', 'status', 'objective', 'gap_pct', 'reference_best',
            'reference_hit', 'reference_tol', 'solution_routes']
    rows = []
    for name in INSTANCES:
        inst = mods['core'].read_dat(ROOT / 'data' / prm[name]['family'] / prm[name]['file'])
        ref = float(refs[name]['reference_best'])
        for m in METHODS:
            for seed in (1, 2, 3):
                best, z, *_ = mods['heuristics'].SOLVERS[m](inst=inst, K=prm[name]['K'], p=prm[name]['p'], seed=seed, restarts=g.RESTARTS, alpha=0.02,
                                                              ls_method='none', ls_preset='light', time_limit=None, depot_mode='sample',
                                                              depot_sample=g.DEPOT_SAMPLE, budget_mode='fixed_trials', **g.SMALL)
                rows.append(dict(problem='LLRP', instance=name, seed=seed, heuristic=m, local_search='none', status='ok', objective=z,
                                 gap_pct=(z - ref) / ref * 100, reference_best=ref, reference_hit=bool(z <= ref + 0.01), reference_tol=0.01,
                                 solution_routes=pr.fmt_routes(best)))
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    return rows


def _read(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


class EndToEnd(unittest.TestCase):
    def test_polish_and_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp); rep = tmp / 'report.csv'; _make_report(rep)
            def polish(out, *extra):
                return subprocess.run([sys.executable, str(ROOT / 'tools' / 'polish_report.py'), '--report', str(rep), '--workers', '2',
                                       '--out', str(out), *extra], capture_output=True, text=True, timeout=300)
            a = polish(tmp / 'p2'); self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
            b = polish(tmp / 'p1', '--workers', '1'); self.assertEqual(b.returncode, 0, b.stderr)   # later --workers wins: 1 worker
            ra, rb = _read(tmp / 'p2' / 'polished_report.csv'), _read(tmp / 'p1' / 'polished_report.csv')
            self.assertEqual(len(ra), len(INSTANCES) * len(METHODS) * 3)
            for x, y in zip(ra, rb):
                self.assertEqual(x['polish_status'], 'ok')
                self.assertEqual(x['objective_polished'], y['objective_polished'])             # deterministic, independent of workers
                self.assertLessEqual(float(x['objective_polished']), float(x['objective']) + 1e-9)
                self.assertEqual(x['polish_ls'], 'vnd'); self.assertEqual(x['polish_preset'], 'common5')
            self.assertTrue((tmp / 'p2' / 'polish_by_heuristic.csv').exists())
            # --seeds filter polishes a subset and marks the rest as skipped
            c = polish(tmp / 'ps', '--seeds', '1'); self.assertEqual(c.returncode, 0, c.stderr)
            st = [r['polish_status'] for r in _read(tmp / 'ps' / 'polished_report.csv')]
            self.assertEqual(st.count('ok'), len(INSTANCES) * len(METHODS)); self.assertEqual(st.count('skipped'), len(st) - st.count('ok'))
            # statistics on the polished report
            r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'rank_stats.py'), '--report', str(tmp / 'p2' / 'polished_report.csv'),
                                '--out', str(tmp / 'rank')], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for name in ('rank_summary_before.csv', 'rank_summary_after.csv', 'friedman_before.txt', 'friedman_after.txt', 'pairwise_wins_after.csv',
                         'rank_before_after.csv', 'rank_report.md'):
                self.assertTrue((tmp / 'rank' / name).exists(), name)
            summ = _read(tmp / 'rank' / 'rank_summary_after.csv'); self.assertEqual({s['method'] for s in summ}, set(METHODS))
            pos = [int(s['position']) for s in summ]                  # equal mean ranks share a position
            self.assertEqual(pos, sorted(pos)); self.assertEqual(pos[0], 1); self.assertTrue(all(1 <= x <= 3 for x in pos))

    def test_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp); rep = tmp / 'report.csv'; rows = _make_report(rep)
            rows[0]['objective'] = float(rows[0]['objective']) + 5.0     # stored routes no longer reproduce the reported objective
            with open(rep, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
            res = subprocess.run([sys.executable, str(ROOT / 'tools' / 'polish_report.py'), '--report', str(rep), '--workers', '1', '--out', str(tmp / 'o')],
                                 capture_output=True, text=True, timeout=300)
            self.assertEqual(res.returncode, 1)
            self.assertEqual(_read(tmp / 'o' / 'polished_report.csv')[0]['polish_status'], 'objective_mismatch')

    def test_duplicate_rows_stop_rank_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp); rep = tmp / 'report.csv'; rows = _make_report(rep)
            with open(rep, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows + rows[:1])
            res = subprocess.run([sys.executable, str(ROOT / 'tools' / 'rank_stats.py'), '--report', str(rep), '--out', str(tmp / 'o')], capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0); self.assertIn('duplicate', res.stdout + res.stderr)


if __name__ == '__main__':
    unittest.main()
