"""Pilot-integrity guards (clean.3): budget semantics, index validation, audit completeness, pooling safety, run identity."""
import csv, hashlib, json, pathlib, subprocess, sys, tempfile, unittest
from common import ROOT, PROBLEM, PKG, RUNNER, SMOKE_INSTANCE, mod

core, runinfo, params = mod('core'), mod('runinfo'), mod('params')
TOY = "3 1\n0 0\n3 0\n3 4\n0 4\n10\n100\n1 1 1\n1000\n500\n0\n"        # 3 customers, 1 depot, Q = 10, demand 1 each


def run(out_dir, *args, instance=SMOKE_INSTANCE, seed='1', check=True):
    cmd = [sys.executable, str(ROOT / RUNNER), '--kit-root', str(ROOT), '--instances', instance, '--seeds', seed,
           '--out-dir', str(out_dir), *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if check:
        assert res.returncode == 0, res.stderr
    return res


def rows(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def verify(folder, *extra):
    return subprocess.run([sys.executable, str(ROOT / 'verify_run.py'), str(folder), '--kit-root', str(ROOT), *extra],
                          capture_output=True, text=True)


class BudgetSemantics(unittest.TestCase):
    def test_late_solution_is_never_the_result(self):
        # trace has no in-budget incumbent, the solver nevertheless returned a feasible solution after the deadline
        raw = [core.Route(0, [0, 1, 2], 3.0)]
        status, sol, z, missing = runinfo.budget_outcome(None, None, raw, 114847.0, 'fixed_time')
        self.assertEqual((status, sol, z, missing), ('no_incumbent_within_budget', None, None, True))
        self.assertEqual(runinfo.budget_outcome(None, None, None, float('inf'), 'fixed_time')[0], 'no_solution')
        ok = runinfo.budget_outcome(12.5, raw, raw, 11.0, 'fixed_time')       # traced incumbent wins over a better late raw value
        self.assertEqual((ok[0], ok[2]), ('ok', 12.5))
        ft = runinfo.budget_outcome(None, None, raw, 7.0, 'fixed_trials')     # no deadline in fixed_trials: untraced raw accepted, flagged
        self.assertEqual((ft[0], ft[2], ft[3]), ('ok', 7.0, True))

    def test_runner_reports_no_incumbent_instead_of_a_late_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, '--heuristic', 'grasp', '--local-search', 'none', '--neighborhoods', 'none', '--budget-mode', 'fixed_time',
                '--time-limit', '0.0001', '--checkpoints', '1')
            row = rows(pathlib.Path(tmp) / 'summary.csv')[0]
            self.assertIn(row['status'], ('no_incumbent_within_budget', 'no_solution'))
            for column in ('objective', 'objective_fixed_budget', 'gap_pct', 'time_to_best_s'):
                self.assertEqual(row[column], '', column)
            self.assertEqual((row['feasible'], row['reference_hit'], row['beats_reference']), ('False', 'False', 'False'))
            self.assertEqual(list(pathlib.Path(tmp).glob('*.solution.json')), [])
            self.assertTrue((pathlib.Path(tmp) / 'trajectory.csv').exists())      # header only: a missing file means a crash

    def test_fixed_trials_has_no_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, '--heuristic', 'grasp', '--local-search', 'first', '--neighborhoods', 'baseline_route', '--budget-mode',
                'fixed_trials', '--time-limit', '0.0001', '--restarts-per-depot-subset', '1', '--depot-mode', 'sample', '--depot-sample', '1')
            row = rows(pathlib.Path(tmp) / 'summary.csv')[0]
            self.assertEqual((row['status'], row['feasible'], row['time_limit_s']), ('ok', 'True', ''))
            self.assertNotEqual(row['objective'], '')
            self.assertEqual(verify(tmp, '--no-manifest').returncode, 0)


class IndexValidation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        path = pathlib.Path(self._tmp.name) / 'toy.dat'
        path.write_text(TOY)
        self.inst = core.read_dat(path)

    def tearDown(self):
        self._tmp.cleanup()

    def feasible(self, depot, seq):
        return core.feasible(self.inst, [core.Route(depot, list(seq), float(len(seq)))], 3, 1)

    def test_valid_solution_passes(self):
        self.assertTrue(self.feasible(0, [0, 1, 2]))

    def test_out_of_range_depot_is_rejected(self):
        self.assertFalse(self.feasible(-1, [0, 1, 2]))     # would silently read the last depot through Python's wrap-around
        self.assertFalse(self.feasible(1, [0, 1, 2]))      # only depot 0 exists

    def test_out_of_range_customer_is_rejected(self):
        self.assertFalse(self.feasible(0, [0, 1, -1]))
        self.assertFalse(self.feasible(0, [0, 1, 3]))


class AuditCompleteness(unittest.TestCase):
    """Launcher layout <run>/<instance>/<method>_<ls>_<nbh>/seed_<k>/ with a jobs.txt manifest."""

    def make_job(self, out, seed):
        d = out / SMOKE_INSTANCE / 'sa_none_none' / f'seed_{seed}'
        run(d, '--heuristic', 'sa', '--local-search', 'none', '--neighborhoods', 'none', '--budget-mode', 'fixed_time',
            '--time-limit', '0.5', '--checkpoints', '0.5', seed=str(seed))
        (d / 'exit_code.txt').write_text('0\n')
        return d

    def test_missing_extra_and_stray_rows_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            (out / 'jobs.txt').write_text(f'{SMOKE_INSTANCE} sa none none 1\n{SMOKE_INSTANCE} sa none none 2\n')
            d1 = self.make_job(out, 1)
            res = verify(out)
            self.assertEqual(res.returncode, 1, res.stdout)                    # seed 2 is expected but absent
            self.assertIn('MISSING', res.stdout)
            self.make_job(out, 2)
            res = verify(out)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn('expected 2 | ok 2', res.stdout)
            # a stray summary row for seed 999 without a solution file must not pass
            with (d1 / 'summary.csv').open() as f:
                header, first = f.read().splitlines()[:2]
            fields = header.split(',')
            (d1 / 'summary.csv').write_text(header + '\n' + first + '\n' + first.replace(',1,sa,', ',999,sa,', 1) + '\n')
            res = verify(out)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn('INCONSISTENT', res.stdout)
            (d1 / 'summary.csv').write_text(header + '\n' + first + '\n')
            # a result folder that is not in the manifest
            extra = out / SMOKE_INSTANCE / 'sa_none_none' / 'seed_7'
            extra.mkdir(parents=True)
            (extra / 'summary.csv').write_text(header + '\n' + first + '\n')
            res = verify(out)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn('UNEXPECTED', res.stdout)
            self.assertEqual(verify(out, '--allow-extra').returncode, 0)

    def test_failed_job_and_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            self.assertEqual(verify(out).returncode, 2)                        # no manifest: completeness unknowable
            (out / 'jobs.txt').write_text(f'{SMOKE_INSTANCE} sa none none 1\n')
            d = self.make_job(out, 1)
            (d / 'exit_code.txt').write_text('1\n')
            res = verify(out)
            self.assertEqual(res.returncode, 1)
            self.assertIn('FAILED', res.stdout)


class PoolingSafety(unittest.TestCase):
    HEADER = ['problem', 'instance', 'seed', 'heuristic', 'local_search', 'neighborhoods', 'config_id', 'status', 'budget_mode',
              'time_limit_s', 'reference_best', 'reference_tol', 'objective', 'gap_pct_x', 'objective_1s', 'gap_1s_pct',
              'tt_bks_s', 'tt_bks_censored', 'time_to_best_s']

    def write(self, folder, items):
        folder.mkdir(parents=True)
        with (folder / 'summary.csv').open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=self.HEADER)
            w.writeheader()
            for it in items:
                base = dict(problem=PROBLEM, instance='i1', seed=1, heuristic='grasp', local_search='none', neighborhoods='none',
                            config_id='aaaa', status='ok', budget_mode='fixed_time', time_limit_s=1, reference_best=100, reference_tol=0.1,
                            objective=105, gap_pct_x='', objective_1s=105, gap_1s_pct=5, tt_bks_s='', tt_bks_censored=True, time_to_best_s=0.5)
                base.update(it)
                w.writerow(base)

    def collect(self, root, *extra):
        return subprocess.run([sys.executable, str(ROOT / 'collect.py'), str(root), *extra], capture_output=True, text=True)

    def test_configurations_are_kept_apart_and_duplicates_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.write(root / 'a', [dict(seed=1), dict(seed=2)])
            self.write(root / 'b', [dict(seed=1, local_search='vnd', neighborhoods='common5', config_id='bbbb', objective_1s=101)])
            res = self.collect(root)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            anyt = rows(root / 'anytime_method_summary.csv')
            self.assertEqual(sorted((r['local_search'], r['runs']) for r in anyt), [('none', '2'), ('vnd', '1')])
            self.assertEqual(len(rows(root / 'config_registry.csv')), 2)
            self.write(root / 'c', [dict(seed=1)])                              # same instance, seed and configuration as in a/
            res = self.collect(root)
            self.assertEqual(res.returncode, 3, res.stdout)
            self.assertEqual(self.collect(root, '--allow-duplicates').returncode, 0)


class DatasetsAndReferences(unittest.TestCase):
    """Data files, registry and the reference table belong together."""

    def test_data_files_match_their_checksums(self):
        for fam, count in (('P', 30), ('B', 10), ('T', 36)):
            lines = (ROOT / 'data' / fam / 'SHA256SUMS').read_text().splitlines()
            self.assertEqual(len(lines), count)
            for line in lines:
                digest, name = line.split()
                with self.subTest(file=f'{fam}/{name}'):
                    self.assertEqual(hashlib.sha256((ROOT / 'data' / fam / name).read_bytes()).hexdigest(), digest)

    def test_registry_groups_and_reference_agree(self):
        refs = {r['instance']: r for r in rows_of(ROOT / 'reference' / 'LLRP_reference.csv')}
        self.assertEqual({k: len(v) for k, v in params.GROUPS.items()},
                         {'P20': 4, 'P50': 8, 'P100': 12, 'P200': 6, 'B': 10, 'T': 36, 'T100': 12, 'T150': 12, 'T200': 12, 'ALL': 76})
        self.assertEqual(set(refs), set(params.REGISTERED))
        for name, prm in params.REGISTERED.items():
            with self.subTest(instance=name):
                r = refs[name]
                self.assertEqual((r['group'], int(r['K']), int(r['p']), float(r['bks'])), (prm['family'], prm['K'], prm['p'], prm['bks']))
                inst = core.read_dat(ROOT / 'data' / prm['family'] / prm['file'])
                self.assertEqual((inst.n, inst.m), (prm['n'], prm['m']))
                self.assertEqual(inst.distance_rule, 'real_euclidean')
                self.assertEqual(inst.open_cost, [0.0] * inst.m); self.assertEqual(inst.vehicle_cost, 0.0)
                self.assertGreaterEqual(prm['K'] * inst.Q, sum(inst.demand))                 # the fleet can carry the demand
                self.assertTrue(1 <= prm['p'] <= inst.m)
                self.assertGreaterEqual(min(inst.depot_cap), sum(inst.demand))               # default: depots uncapacitated
        sizes = {g: {params.REGISTERED[i]['n'] for i in params.GROUPS[g]} for g in ('T100', 'T150', 'T200', 'P20', 'P50', 'P100', 'P200')}
        self.assertEqual(sizes, {'T100': {100}, 'T150': {150}, 'T200': {200}, 'P20': {20}, 'P50': {50}, 'P100': {100}, 'P200': {200}})

    def test_depot_capacity_option(self):
        inst0 = core.read_dat(ROOT / 'data' / 'P' / 'coord20-5-1.dat')
        inst1 = core.read_dat(ROOT / 'data' / 'P' / 'coord20-5-1.dat', depot_capacity='enforce')
        self.assertEqual(inst1.depot_cap, inst0.depot_cap_file)
        self.assertLess(max(inst1.depot_cap), sum(inst1.demand))
        self.assertEqual(inst0.depot_cap, [float(sum(inst0.demand))] * inst0.m)

    def test_runner_scores_a_barreto_and_a_tuzun_burke_instance(self):
        with tempfile.TemporaryDirectory() as td:
            for inst in ('coordGaspelle', 'coordP111112'):
                out = pathlib.Path(td) / inst
                run(out, '--heuristic', 'grasp', '--local-search', 'first', '--neighborhoods', 'baseline_route', '--time-limit', '3',
                    '--checkpoints', '1:3', instance=inst)
                r = rows(out / 'summary.csv')[0]
                self.assertEqual(r['status'], 'ok')
                self.assertEqual(r['feasible'], 'True'); self.assertEqual(r['K_binding'], 'True')
                self.assertGreater(float(r['reference_best']), 0)
                self.assertGreaterEqual(float(r['objective']), float(r['reference_best']) - 0.5)


def rows_of(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


class RunIdentity(unittest.TestCase):
    def fingerprint(self, *args, seed='1'):
        res = run('unused', '--heuristic', 'sa', '--local-search', 'none', '--neighborhoods', 'none', '--budget-mode', 'fixed_time',
                  '--time-limit', '1', '--checkpoints', '0.5:1', *args, '--print-fingerprint', seed=seed)
        return res.stdout.strip()

    def test_fingerprint_follows_what_a_run_computes(self):
        base = self.fingerprint()
        self.assertEqual(base, self.fingerprint())                              # deterministic
        self.assertNotEqual(base, self.fingerprint('--sa-iters', '10'))         # hyper-parameter
        self.assertNotEqual(base, self.fingerprint('--time-limit', '2'))        # budget
        self.assertNotEqual(base, self.fingerprint(seed='2'))                   # job
        self.assertFalse(pathlib.Path('unused').exists())                       # printing creates nothing

    def test_config_json_carries_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, '--heuristic', 'sa', '--local-search', 'none', '--neighborhoods', 'none', '--budget-mode', 'fixed_time',
                '--time-limit', '1', '--checkpoints', '0.5:1')
            cfg = json.loads((pathlib.Path(tmp) / 'config.json').read_text())
            for key in ('config_id', 'fingerprint', 'source_sha256', 'instance_sha256', 'reference_sha256', 'python_family', 'formulation'):
                self.assertIn(key, cfg)
            self.assertEqual(rows(pathlib.Path(tmp) / 'summary.csv')[0]['fingerprint'], cfg['fingerprint'])


if __name__ == '__main__':
    unittest.main()
