"""End-to-end: the runner CLI writes the full audit trail (summary, trajectory, solution, config)."""
import csv, importlib, json, subprocess, sys, tempfile, unittest, pathlib
from common import ROOT, PROBLEM, RUNNER, SMOKE_INSTANCE


def run(out_dir, *args):
    cmd = [sys.executable, str(ROOT / RUNNER), '--kit-root', str(ROOT), '--instances', SMOKE_INSTANCE, '--seeds', '1',
           '--out-dir', str(out_dir), *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    return res


def audit(folder, *extra):
    # Flat output folders (no launcher layout, no jobs.txt): check the stored solutions only.
    args = extra or ('--no-manifest',)
    return subprocess.run([sys.executable, str(ROOT / 'verify_run.py'), str(folder), '--kit-root', str(ROOT), *args], capture_output=True, text=True)


def rows(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


class RunnerSmoke(unittest.TestCase):
    def test_fixed_trials_run_writes_all_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, '--heuristic', 'grasp', '--local-search', 'first', '--neighborhoods', 'baseline_route',
                '--budget-mode', 'fixed_trials', '--restarts-per-depot-subset', '1', '--depot-mode', 'sample', '--depot-sample', '1')
            out = pathlib.Path(tmp)
            for name in ('summary.csv', 'aggregate.csv', 'trajectory.csv', 'config.json'):
                self.assertTrue((out / name).stat().st_size > 0, name)
            self.assertEqual(len(list(out.glob('*.sol.txt'))), 1)
            self.assertEqual(len(list(out.glob('*.solution.json'))), 1)
            row = rows(out / 'summary.csv')[0]
            self.assertEqual(row['problem'], PROBLEM)
            self.assertEqual(row['feasible'], 'True')
            cfg = json.loads((out / 'config.json').read_text())
            self.assertEqual(cfg['args']['heuristic'], 'grasp')
            self.assertIn('python', cfg)
            self.assertIn('code_version', cfg)

    def test_fixed_time_run_has_checkpoints_and_consistent_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, '--heuristic', 'sa', '--local-search', 'none', '--neighborhoods', 'none',
                '--budget-mode', 'fixed_time', '--time-limit', '1', '--checkpoints', '0.5:1')
            row = rows(pathlib.Path(tmp) / 'summary.csv')[0]
            self.assertEqual(row['feasible'], 'True')
            self.assertEqual(row['trace_final_consistent'], 'True')
            self.assertLess(float(row['budget_overrun_s']), 0.5)
            for column in ('objective_0p5s', 'objective_1s', 'gap_0p5s_pct', 'gap_1s_pct', 'objective_fixed_budget', 'tt_bks_s'):
                self.assertIn(column, row)
            for column in ('reference_hit', 'beats_reference', 'reference_tol', 'time_to_best_s', 'open_depot_ids', 'solution_routes'):
                self.assertIn(column, row)
            self.assertLessEqual(float(row['time_to_best_s']), 1.0)
            doc = json.loads(next(pathlib.Path(tmp).glob('*.solution.json')).read_text())
            self.assertEqual(doc['index_base'], 0)
            self.assertEqual(';'.join(map(str, doc['open_depots'])), row['open_depot_ids'])
            self.assertEqual(sorted(doc['checkpoints']), ['0p5', '1'])
            res = audit(tmp)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            traj = rows(pathlib.Path(tmp) / 'trajectory.csv')
            self.assertGreater(len(traj), 0)
            times = [float(r['time_s']) for r in traj]
            self.assertEqual(times, sorted(times))
            # the reported solution is the last improvement: its time is time_to_best_s, its value is the objective
            self.assertAlmostEqual(float(row['time_to_best_s']), times[-1], places=9)
            self.assertAlmostEqual(doc['time_to_best_s'], times[-1], places=9)
            self.assertAlmostEqual(float(traj[-1]['objective']), float(row['objective']), places=6)


    def test_audit_detects_a_corrupted_solution_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, '--heuristic', 'sa', '--local-search', 'none', '--neighborhoods', 'none',
                '--budget-mode', 'fixed_time', '--time-limit', '1', '--checkpoints', '1')
            path = next(pathlib.Path(tmp).glob('*.solution.json'))
            doc = json.loads(path.read_text())
            seq = doc['routes'][0]['customers']
            seq[0], seq[-1] = seq[-1], seq[0]                   # same customers, different order: objective changes
            if len(seq) < 2 or seq == sorted(seq, reverse=True) == sorted(seq):
                self.skipTest('route too short to perturb')
            path.write_text(json.dumps(doc))
            self.assertEqual(audit(tmp).returncode, 1)

    def test_reference_rule_is_one_sided(self):
        status = importlib.import_module(RUNNER[:-3]).reference_status
        self.assertEqual(status(100.0, 100.0, 0.015), dict(gap_pct=0.0, hit=True, beats=False))
        self.assertTrue(status(100.015, 100.0, 0.015)['hit'])
        self.assertFalse(status(100.02, 100.0, 0.015)['hit'])
        better = status(99.0, 100.0, 0.015)
        self.assertTrue(better['hit'] and better['beats'])           # better than the literature value is a hit, reported separately
        self.assertEqual(status(None, 100.0, 0.015), dict(gap_pct=None, hit=False, beats=False))
        self.assertEqual(status(float('inf'), 100.0, 0.015), dict(gap_pct=None, hit=False, beats=False))


if __name__ == '__main__':
    unittest.main()
