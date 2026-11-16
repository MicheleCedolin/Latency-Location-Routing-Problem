"""tools/ls_ablation.py: drivers vs. the framework, local optimality, configuration generators, resume and summaries on a tiny synthetic report."""
import csv, importlib, json, pathlib, random, subprocess, sys, tempfile, unittest
from common import ROOT, mod

sys.path.insert(0, str(ROOT / 'tools'))
ab = importlib.import_module('ls_ablation')
from test_post_tools import _make_report, INSTANCES, METHODS  # noqa: E402
from llrp_framework import core, local_search as LS, neighborhoods as NB  # noqa: E402

TOOL = str(ROOT / 'tools' / 'ls_ablation.py')


def _read(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def _run(*args, timeout=600):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, timeout=timeout)


def _fake_profile():
    return {op: dict(mean_candidates=float(100 + 7 * i), mean_time_s=0.001 * i, mean_gain=float((i * 37) % 11), solutions=3.0, share_improvable=0.5)
            for i, op in enumerate(ab.CANON)}


class Configurations(unittest.TestCase):
    def test_classes_partition_the_15_operators(self):
        flat = [o for ops in ab.CLASSES.values() for o in ops]
        self.assertEqual(sorted(flat), sorted(NB.PRESETS['hgamp']))   # the 15 operators of Ext-15 (the coordinated depot operators of clean.6.0 are outside the ablation design); self.assertEqual(len(flat), len(set(flat)), 'an operator belongs to two classes')
        for c, lad in ab.LADDER.items():
            self.assertEqual(sorted(lad), sorted(ab.CLASSES[c]))

    def test_stage_sizes(self):
        self.assertEqual(len(ab.stage0()), 5)
        self.assertEqual(len(ab.stage1()), 13)
        self.assertEqual(len(ab.stage2('ABCDE')), 1 + 3 + 2 + 3 + 1)
        self.assertEqual(len(ab.stage3(ab.parse_set('classes:ABCDE'), _fake_profile())), 10)
        self.assertEqual(len(ab.stage4(ab.CANON)), 7)                              # 5 drivers + first-capable subset under vnd and under first
        self.assertEqual(len(ab.stage4(['intra_relocate1', 'inter_relocate1', 'inter_swap11'])), 6)   # all first-capable: one "first" config
        with self.assertRaises(ValueError): ab.stage2('')

    def test_stage1_definitions(self):
        s1 = {c.name: c for c in ab.stage1()}
        self.assertEqual(set(s1['S1_LOCO_E'].ops), set(ab.CANON) - {'depot_reassign'})
        self.assertEqual(len(s1['S1_LOCO_A'].ops), 11); self.assertEqual(len(s1['S1_ADD_C'].ops), 6)
        self.assertEqual(set(s1['S1_ADD_F'].ops), {'intra_relocate1', 'inter_relocate1', 'route_split'})
        self.assertTrue(all(c.ref in ('S0_full15_vnd', 'S1_base2') for c in s1.values() if c.name != 'S1_base2'))
        for c in s1.values():                                                       # all subsets keep the canonical relative order
            self.assertEqual(c.ops, ab.canon(c.ops))

    def test_stage3_orders_are_permutations_and_deterministic(self):
        setops = ab.parse_set('classes:ABCDE')
        a, b = ab.stage3(setops, _fake_profile()), ab.stage3(setops, _fake_profile())
        for c in a:
            self.assertEqual(sorted(c.ops), sorted(setops), c.name)
        self.assertEqual([c.ops for c in a], [c.ops for c in b])
        rnd = [tuple(c.ops) for c in a if c.name.startswith('S3_random')]
        self.assertEqual(len(set(rnd)), 3)
        self.assertEqual(a[3].ops[0][:5], 'intra'); self.assertEqual(ab.OP_CLASS[a[4].ops[0]], 'B'); self.assertEqual(a[5].ops[0], 'depot_reassign')
        cheap = {c.name: c for c in a}['S3_cheap_first'].ops
        self.assertEqual(cheap, sorted(setops, key=lambda o: (_fake_profile()[o]['mean_candidates'], ab.CANON.index(o))))

    def test_stage2_ladders_nested(self):
        s2 = {c.name: c for c in ab.stage2('ABCDE')}
        ref = s2['S2_ref_ABCDE']
        for k in (1, 2, 3):
            self.assertTrue(set(s2[f'S2_C{k}of4'].ops) < set(ref.ops))
        self.assertLess(set(s2['S2_C1of4'].ops), set(s2['S2_C2of4'].ops))
        self.assertEqual([o for o in s2['S2_C1of4'].ops if ab.OP_CLASS[o] == 'C'], ['inter_swap11'])

    def test_set_parser_and_config_file(self):
        self.assertEqual(ab.parse_set('classes:A,B'), ab.canon(ab.CLASSES['A'] + ab.CLASSES['B']))
        self.assertEqual(ab.parse_set('ops:intra_2opt+inter_swap11'), ['inter_swap11', 'intra_2opt'])      # canonical order, not the order written
        self.assertEqual(set(ab.parse_set('S0_common5_vnd')), set(NB.PRESETS['common5']))                # a configuration name gives its operators (stages 3/4 put them in canonical order)
        self.assertEqual(ab.parse_set('S2_ref_ABCDE'), ab.parse_set('classes:ABCDE'))
        with self.assertRaises(ValueError): ab.parse_set('nonsense')
        with self.assertRaises(ValueError): ab.parse_set('ops:not_an_operator')
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / 'c.txt'
            f.write_text('# comment\nmy_a | vnd | intra_2opt, inter_swap11 | S0_full15_vnd\nmy_b | rvnd | inter_relocate1+intra_relocate1\n')
            cfg = ab.read_config_file(f)
            self.assertEqual([c.name for c in cfg], ['my_a', 'my_b']); self.assertEqual(cfg[0].ref, 'S0_full15_vnd'); self.assertEqual(cfg[1].driver, 'rvnd')

class Drivers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rep = pathlib.Path(cls.tmp.name) / 'report.csv'
        _make_report(cls.rep)
        cls.rows = ab.load_rows(cls.rep)[::3][:6]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _case(self, row, scatter=False):
        """scatter=True: same customers, but one route per customer (a poor start with many moves to make)."""
        inst = ab._instance(row['instance'])
        sol = core.normalize(inst, ab.parse_routes(row['solution_routes']))
        if scatter:
            sol = core.normalize(inst, [core.Route(r.depot, [c], 0.0) for r in sol for c in r.seq])
        return inst, sol, inst.n, inst.m, tuple(range(inst.m))

    def test_first_capable_set_matches_the_framework(self):
        inst, sol, K, p, al = self._case(self.rows[0], scatter=True)
        for op in ab.CANON:
            if op in ab.FIRST_OK:
                LS.first_descent(inst, sol, K, p, al, op)
            else:
                with self.assertRaises(ValueError, msg=op):
                    LS.first_descent(inst, sol, K, p, al, op)

    def test_reproduce_framework_drivers(self):
        for row in self.rows[:2]:
            inst, sol, K, p, al = self._case(row, scatter=True)
            for driver, preset in (('vnd', 'hgamp'), ('vnd', 'common5'), ('rvnd', 'hgamp'), ('best', 'common5'), ('first', 'baseline_route')):
                ref_s, ref_z, ref_m = LS.run_local_search(driver, inst, sol, K, p, al, preset, random.Random(row['seed']), None)
                s, z, m, scans, ps, timed = ab.apply_ls(driver, inst, sol, NB.PRESETS[preset], random.Random(row['seed']), None, K, p, al)
                self.assertAlmostEqual(z, ref_z, places=6, msg=f'{driver}/{preset}')
                self.assertEqual(m, ref_m, f'{driver}/{preset}'); self.assertFalse(timed)
                self.assertAlmostEqual(core.objective(inst, core.normalize(inst, s)), z, places=6)

    def test_every_driver_ends_in_a_local_optimum_and_never_worsens(self):
        for row in self.rows[:2]:
            inst, sol, K, p, al = self._case(row, scatter=True)
            z0 = core.objective(inst, sol)
            for driver in ('vnd', 'cyclic', 'pipe', 'rvnd', 'best'):
                s, z, m, scans, ps, timed = ab.apply_ls(driver, inst, sol, ab.CANON, random.Random(1), None, K, p, al)
                s = core.normalize(inst, s)
                self.assertTrue(core.feasible(inst, s, K, p)); self.assertLessEqual(z, z0 + 1e-9); self.assertAlmostEqual(core.objective(inst, s), z, places=6)
                self.assertEqual(sum(v[1] for v in ps.values()), m, driver)                       # per-operator move counts add up
                self.assertAlmostEqual(sum(v[2] for v in ps.values()), z0 - z, places=5, msg=driver)  # per-operator gains add up to the total gain
                for op in ab.CANON:
                    res = NB.NEIGHBORHOODS[op](inst, s, K, p, al)
                    self.assertTrue(res is None or res[0] >= z - 1e-7, f'{driver} stopped although {op} still improves')

    def test_cyclic_and_pipe_differ_from_basic_in_scan_pattern(self):
        inst, sol, K, p, al = self._case(self.rows[0], scatter=True)
        res = {d: ab.apply_ls(d, inst, sol, ab.CANON, random.Random(1), None, K, p, al) for d in ('vnd', 'cyclic', 'pipe')}
        self.assertGreater(len({r[3] for r in res.values()}), 1, 'the three change rules scanned identically, they should not')

    def test_candidate_counter_is_deterministic(self):
        row = self.rows[1]
        inst, sol, K, p, al = self._case(row)
        out = []
        for _ in range(2):
            c0 = ab._CNT[0]
            ab.apply_ls('vnd', inst, sol, NB.PRESETS['common5'], random.Random(1), None, K, p, al)
            out.append(ab._CNT[0] - c0)
        self.assertEqual(out[0], out[1]); self.assertGreater(out[0], 0)

    def test_deadline_in_the_past_returns_start_solution(self):
        row = self.rows[0]
        inst, sol, K, p, al = self._case(row)
        for driver in ('vnd', 'cyclic', 'pipe', 'rvnd', 'best', 'first'):
            s, z, m, scans, ps, timed = ab.apply_ls(driver, inst, sol, ab.CANON if driver != 'first' else sorted(ab.FIRST_OK), random.Random(1), 0.0001, K, p, al)
            self.assertLessEqual(z, core.objective(inst, sol) + 1e-9)


class EndToEnd(unittest.TestCase):
    def test_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp); rep = tmp / 'report.csv'; rows = _make_report(rep); out = tmp / 'abl'
            r = _run('profile', '--report', str(rep), '--out', str(out), '--sample', '6', '--workers', '2'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            prof = _read(out / 'profile.csv'); self.assertEqual([x['op'] for x in prof], ab.CANON)
            r = _run('list', '--out', str(out), '--stage', '3', '--set', 'classes:ABCDE'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn('10 configurations', r.stdout)

            r = _run('run', '--report', str(rep), '--out', str(out), '--stage', '0,1', '--workers', '2', '--seeds', '1-2'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(len(list((out / 'configs').glob('*.done'))), 18)
            res = {p.stem: _read(p) for p in (out / 'configs').glob('*.csv')}
            n_expected = len(INSTANCES) * len(METHODS) * 2
            self.assertTrue(all(len(v) == n_expected for v in res.values()))
            for name, v in res.items():
                for x in v:
                    self.assertEqual(x['status'], 'ok'); self.assertLessEqual(float(x['z1']), float(x['z0']) + 1e-9); self.assertGreater(int(float(x['candidates'])), 0)

            # the all-15 VND must agree with the polish tool of the post-analysis package (same driver, same preset)
            pol = subprocess.run([sys.executable, str(ROOT / 'tools' / 'polish_report.py'), '--report', str(rep), '--ls', 'vnd', '--preset', 'hgamp', '--workers', '2',
                                  '--seeds', '1-2', '--out', str(tmp / 'pol')], capture_output=True, text=True, timeout=600)
            self.assertEqual(pol.returncode, 0, pol.stdout + pol.stderr)
            polz = {(x['instance'], x['heuristic'], x['seed']): float(x['objective_polished']) for x in _read(tmp / 'pol' / 'polished_report.csv') if x['polish_status'] == 'ok'}
            for x in res['S0_full15_vnd']:
                self.assertAlmostEqual(float(x['z1']), polz[(x['instance'], x['heuristic'], x['seed'])], places=6)

            # resume: nothing is recomputed
            stamp = {p.name: p.stat().st_mtime_ns for p in (out / 'configs').glob('*')}
            r = _run('run', '--report', str(rep), '--out', str(out), '--stage', '0,1', '--workers', '2', '--seeds', '1-2'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.count('skipped'), 18)
            self.assertEqual(stamp, {p.name: p.stat().st_mtime_ns for p in (out / 'configs').glob('*')})
            # a changed filter invalidates the finished configurations
            r = _run('run', '--report', str(rep), '--out', str(out), '--stage', '0', '--workers', '2', '--seeds', '1'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.count('skipped'), 0)
            r = _run('run', '--report', str(rep), '--out', str(out), '--stage', '0,1', '--workers', '2', '--seeds', '1-2'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            # stages 3 and 4 on the retained set
            for stage in ('3', '4'):
                r = _run('run', '--report', str(rep), '--out', str(out), '--stage', stage, '--set', 'classes:ABCDE', '--workers', '2', '--seeds', '1-2')
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = _run('run', '--report', str(rep), '--out', str(out), '--stage', '2', '--keep', 'ABCDE', '--workers', '2', '--seeds', '1-2'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((out / 'configs' / 'S2_C1of4.done').exists()); self.assertTrue((out / 'configs' / 'S4_cyclic.done').exists()); self.assertTrue((out / 'configs' / 'S3_random3.done').exists())

            r = _run('summarize', '--out', str(out), '--boot', '200'); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for name in ('ablation_summary.csv', 'ablation_ops.csv', 'ablation_contrasts.csv', 'ablation_report.md'):
                self.assertTrue((out / name).exists(), name)
            con = _read(out / 'ablation_contrasts.csv')
            allc = [c for c in con if c['stratum'] == 'all']
            cfgs = json.loads((out / 'configs.json').read_text())
            self.assertEqual(len(allc), sum(1 for c in cfgs.values() if c['ref']))
            for c in allc:
                self.assertLessEqual(float(c['ci_low']), float(c['diff_gap_pp']) + 1e-9); self.assertGreaterEqual(float(c['ci_high']), float(c['diff_gap_pp']) - 1e-9)
                self.assertIn(c['decision'], ('equivalent', 'better', 'worse', 'inconclusive'))
            ops = _read(out / 'ablation_ops.csv')
            for cname in ('S0_full15_vnd', 'S0_common5_vnd'):
                self.assertAlmostEqual(sum(float(o['gain_share']) for o in ops if o['config'] == cname), 1.0, places=3)
            self.assertEqual({o['op'] for o in ops if o['config'] == 'S0_common5_vnd'}, set(NB.PRESETS['common5']))

    def test_mismatch_and_bad_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp); rep = tmp / 'report.csv'; rows = _make_report(rep)
            rows[0]['objective'] = float(rows[0]['objective']) + 5.0
            with open(rep, 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
            r = _run('run', '--report', str(rep), '--out', str(tmp / 'o'), '--stage', '0', '--workers', '1', '--seeds', '1')
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('objective_mismatch', r.stdout + (tmp / 'o' / 'configs' / 'S0_full15_vnd.csv').read_text())
            self.assertFalse((tmp / 'o' / 'configs' / 'S0_full15_vnd.done').exists())            # not marked as finished
            self.assertNotEqual(_run('list', '--out', str(tmp / 'o'), '--stage', '2').returncode, 0)   # stage 2 without --keep
            self.assertNotEqual(_run('list', '--out', str(tmp / 'o'), '--stage', '3').returncode, 0)   # stage 3 without a set
            self.assertNotEqual(_run('list', '--out', str(tmp / 'o'), '--stage', '7').returncode, 0)


if __name__ == '__main__':
    unittest.main()
