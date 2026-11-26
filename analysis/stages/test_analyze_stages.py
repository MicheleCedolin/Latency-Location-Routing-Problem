"""Self-test of analyze_stages.py on synthetic archives (needs scipy).  usage: python3 -I analysis/stages/test_analyze_stages.py"""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_stages as st

NAMES = ["I%02d" % i for i in range(12)]
SIZE = {nm: (100, 100, 150, 200)[i % 4] for i, nm in enumerate(NAMES)}
BKS = 1000.0


def write_arm(root, arm, shift, verify=True):
    d = os.path.join(root, "prins", arm)
    os.makedirs(d)
    with open(os.path.join(d, "run.csv"), "w", newline="") as fh, open(os.path.join(d, "trace.csv"), "w", newline="") as tr, open(os.path.join(d, "verify.txt"), "w") as vf:
        w, t = csv.writer(fh), csv.writer(tr)
        w.writerow(["Instance", "Algorithm", "Run", "Seed", "Feasible", "Total Latency", "Reference BKS", "Gap to BKS (%)", "CPU Time", "Iterations", "Stop Reason"])
        t.writerow(["Instance", "Algorithm", "Seed", "Iteration", "CPU Seconds", "Best Latency"])
        for i, nm in enumerate(NAMES):
            for sd in range(1, 31):
                cost = BKS * (1 + (shift + 0.0001 * ((i * 7 + sd) % 5)) / 100.0)
                lim = max(5.0, 3.0 * SIZE[nm])
                w.writerow([nm, arm, sd, sd, "True", "%.8f" % cost, "%.2f" % BKS, "", "%.3f" % lim, 100, "time"])
                t.writerow([nm, arm, sd, 0, "0.5", "%.8f" % (cost * 1.01)])
                t.writerow([nm, arm, sd, 1, "%.3f" % lim, "%.8f" % cost])
                vf.write("OK %s_s%d_%s\n" % (nm, sd, arm))


class Helpers(unittest.TestCase):
    def test_best_at(self):
        tr = [(0.5, 10.0), (2.0, 9.0), (5.0, 8.0)]
        self.assertIsNone(st.best_at(tr, 0.1))
        self.assertEqual(st.best_at(tr, 2.0), 9.0)
        self.assertEqual(st.best_at(tr, 100.0), 8.0)

    def test_bootstrap_is_deterministic_and_brackets_the_mean(self):
        d = [-0.5, -0.4, -0.3, -0.2, -0.1, 0.0, -0.45, -0.35]
        lo, hi = st.boot_ci(d, b=500)
        self.assertEqual((lo, hi), st.boot_ci(d, b=500))
        self.assertLess(lo, sum(d) / len(d))
        self.assertGreater(hi, sum(d) / len(d))

    def test_wilcoxon_direction(self):
        self.assertLess(st.wx([-0.3 - 0.01 * i for i in range(20)], "less"), 1e-3)
        self.assertGreater(st.wx([0.3 + 0.01 * i for i in range(20)], "less"), 0.99)
        self.assertNotEqual(st.fp(float("nan")), "x")


class EndToEnd(unittest.TestCase):
    def test_criteria(self):
        with tempfile.TemporaryDirectory() as d:
            for arm, shift in (("ext10", 1.0), ("V1", 0.5), ("B1", 0.2)):
                write_arm(os.path.join(d, arm), arm, shift)
            with open(os.path.join(d, "manifest.tsv"), "w") as fh:
                fh.write("family\tname\tn\tm\tQ\tNv\tNg\tbks\ttotal_demand\tmin_vehicles\ttightness\tsize\tflag\n")
                for nm in NAMES:
                    fh.write("prins\t%s\t%d\t5\t100\t5\t2\t%.2f\t1\t1\t0.5\tL\t-\n" % (nm, SIZE[nm], BKS))
            with open(os.path.join(d, "lit.csv"), "w") as fh:
                fh.write("instance,family,n,m,Nv,algorithm,best,avg,time_s\n")
                for nm in NAMES:
                    fh.write("%s,prins,%d,5,5,RLHEA,%.2f,%.2f,50.0\n" % (nm, SIZE[nm], BKS * 1.0002, BKS * 1.003))
            with open(os.path.join(d, "inst.txt"), "w") as fh:
                fh.write("# comment\n" + "\n".join(NAMES) + "\n")
            out = os.path.join(d, "out")
            res = st.main(["--base", os.path.join(d, "ext10"), "--depot", os.path.join(d, "V1"), "--pool", os.path.join(d, "B1"), "--manifest", os.path.join(d, "manifest.tsv"),
                           "--literature", os.path.join(d, "lit.csv"), "--instances", os.path.join(d, "inst.txt"), "--out", out])
            self.assertTrue(res["g0"] and res["g1"] and res["z"] and res["g1b"] and res["g0b"] and res["zb"])
            self.assertFalse(res["g2"])                     # V1 mean latency is 0.5 % above the BKS, Zou f_avg is 0.3 % above
            with open(os.path.join(out, "stages_instances.csv")) as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 12)
            self.assertAlmostEqual(float(rows[0]["gap_ext10"]) - float(rows[0]["gap_V1"]), 0.5, places=2)
            self.assertTrue(all(r["hit_B1"] == "0" for r in rows))
            with open(os.path.join(out, "stages_summary.md")) as fh:
                text = fh.read()
            self.assertIn("V1 generalises to n > 75", text)
            self.assertIn("independently verified | CPU / limit mean", text.replace("  ", " "))

    def test_incomplete_archive_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for arm, shift in (("ext10", 1.0), ("V1", 0.5), ("B1", 0.2)):
                write_arm(os.path.join(d, arm), arm, shift)
            run = os.path.join(d, "B1", "prins", "B1", "run.csv")
            with open(run) as fh:
                lines = fh.readlines()
            with open(run, "w") as fh:
                fh.writelines(lines[:-1])                    # one run missing
            with open(os.path.join(d, "manifest.tsv"), "w") as fh:
                fh.write("family\tname\tn\tm\tQ\tNv\tNg\tbks\ttotal_demand\tmin_vehicles\ttightness\tsize\tflag\n")
                for nm in NAMES:
                    fh.write("prins\t%s\t%d\t5\t100\t5\t2\t%.2f\t1\t1\t0.5\tL\t-\n" % (nm, SIZE[nm], BKS))
            with open(os.path.join(d, "lit.csv"), "w") as fh:
                fh.write("instance,family,n,m,Nv,algorithm,best,avg,time_s\n")
            with open(os.path.join(d, "inst.txt"), "w") as fh:
                fh.write("\n".join(NAMES) + "\n")
            with self.assertRaises(SystemExit) as cm:
                st.main(["--base", os.path.join(d, "ext10"), "--depot", os.path.join(d, "V1"), "--pool", os.path.join(d, "B1"), "--manifest", os.path.join(d, "manifest.tsv"),
                         "--literature", os.path.join(d, "lit.csv"), "--instances", os.path.join(d, "inst.txt"), "--out", os.path.join(d, "o")])
            self.assertIn("incomplete", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
