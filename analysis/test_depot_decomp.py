"""Self-test of depot_decomp.py (standard library only).  usage: python3 analysis/test_depot_decomp.py"""
import csv
import itertools
import math
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import depot_decomp as dd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INST = """LLRP_INSTANCE 1
name T1-2
n 3
m 2
Q 10.0
Nv 2
Ng 2
bks 7
depots
0 0
10 0
customers
1 0 1
2 0 1
4 0 1
"""


class Mapping(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(dd.ref_file("20-5-1b-5", "prins"), "20-5-1b")
        self.assertEqual(dd.ref_file("50-5-2BIS-5", "prins"), "50-5-2BIS")
        self.assertEqual(dd.ref_file("200-10-3b-10", "prins"), "200-10-3b")
        self.assertEqual(dd.ref_file("P111112-10", "tuzun"), "111112")
        self.assertEqual(dd.ref_file("Gaskell32-5", "barreto"), "Gaskell_32_5b")

    def test_every_instance_of_the_repository_maps(self):
        names = set()
        root = os.path.join(REPO, "cpp", "inst")
        for fam in os.listdir(root):
            for f in os.listdir(os.path.join(root, fam)):
                stem = dd.ref_file(f[:-5], fam)
                self.assertNotIn((fam, stem), names)
                names.add((fam, stem))
        self.assertEqual(len(names), 76)


class Geometry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "T1-2.inst")
        with open(self.path, "w") as fh:
            fh.write(INST)
        self.dep, self.cus = dd.parse_inst(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_and_latency(self):
        self.assertEqual(self.dep, [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(len(self.cus), 3)
        self.assertAlmostEqual(dd.latency([(0, (0, 1, 2))], self.dep, self.cus), 1 + 2 + 4)        # arrival times 1, 2, 4
        self.assertAlmostEqual(dd.latency([(0, (0,)), (1, (2,))], self.dep, self.cus), 1 + 6)      # two routes, one customer each

    def test_reference_file_and_trust(self):
        p = os.path.join(self.tmp.name, "ref.txt")
        with open(p, "w") as fh:
            fh.write("4 1 2 3\n")                                           # depot 4 - 3 - 1 = 0, customers 1..3
        ref = dd.parse_reference(p, 3)
        self.assertEqual(ref, [(0, (0, 1, 2))])
        self.assertIsNone(dd.trust(ref, 3, self.dep, self.cus, 7.0, 1e-3))
        self.assertIn("differs", dd.trust(ref, 3, self.dep, self.cus, 8.0, 1e-3))
        self.assertIn("covers 2 of 3", dd.trust([(0, (0, 1))], 3, self.dep, self.cus, None, 1e-3))
        self.assertIn("twice", dd.trust([(0, (0, 1)), (1, (1, 2))], 3, self.dep, self.cus, None, 1e-3))
        self.assertEqual(dd.trust(None, 3, self.dep, self.cus, 7.0, 1e-3), "no published solution")
        self.assertIsNone(dd.parse_reference(os.path.join(self.tmp.name, "missing.txt"), 3))


class Completion(unittest.TestCase):
    """A published solution that lacks a few customers is completed by one route (the case of Tuzun P112222-20)."""
    dep = [(0.0, 0.0), (10.0, 0.0)]
    cus = [(1.0, 0.0, 1.0), (2.0, 0.0, 1.0), (4.0, 0.0, 1.0)]

    def test_min_latency_order_is_exact(self):
        rnd = random.Random(7)
        dep = [(rnd.uniform(0, 50), rnd.uniform(0, 50))]
        cus = [(rnd.uniform(0, 50), rnd.uniform(0, 50), 1.0) for _ in range(6)]
        lat, order = dd.min_latency_order(0, list(range(6)), dep, cus)
        brute = min(dd.latency([(0, p)], dep, cus) for p in itertools.permutations(range(6)))
        self.assertAlmostEqual(lat, brute)
        self.assertAlmostEqual(dd.latency([(0, order)], dep, cus), lat)
        self.assertEqual(sorted(order), list(range(6)))

    def test_complete_one_route(self):
        done, note = dd.complete_missing([(0, (0, 1))], 3, self.dep, self.cus, 10.0, 2, 7.0)
        self.assertEqual(done, [(0, (0, 1)), (0, (2,))])
        self.assertIn("1 missing customers", note)
        self.assertIsNone(dd.trust(done, 3, self.dep, self.cus, 7.0, 1e-3))

    def test_refusals(self):
        r = [(0, (0, 1))]
        self.assertIn("exceed Nv", dd.complete_missing(r, 3, self.dep, self.cus, 10.0, 1, 7.0)[1])                  # no room for one more route
        self.assertIn("fit one vehicle", dd.complete_missing(r, 3, self.dep, self.cus, 0.5, 2, 7.0)[1])             # capacity
        self.assertIn("does not reproduce", dd.complete_missing(r, 3, self.dep, self.cus, 10.0, 2, 7.5)[1])         # published value not matched
        self.assertIn("no published best", dd.complete_missing(r, 3, self.dep, self.cus, 10.0, 2, None)[1])
        self.assertIn("at most", dd.complete_missing([(0, (0,))], 20, self.dep, self.cus * 7, 10.0, 5, 7.0)[1])      # too many missing
        self.assertIn("twice", dd.complete_missing([(0, (0, 1)), (1, (1,))], 3, self.dep, self.cus, 10.0, 3, 7.0)[1])

    def test_ambiguous_depot_is_refused(self):
        dep = [(0.0, 0.0), (0.0, 0.0)]                                                     # two identical depots reproduce the value equally well
        done, note = dd.complete_missing([(0, (0, 1)), (1, (2,))], 4, dep, self.cus + [(8.0, 0.0, 1.0)], 10.0, 5, 3.0 + 4.0 + 8.0)
        self.assertIsNone(done)
        self.assertIn("exactly one open depot", note)

    def test_main_completes_unless_switched_off(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "inst", "prins"))
            with open(os.path.join(d, "inst", "prins", "T1-2.inst"), "w") as fh:
                fh.write(INST)
            with open(os.path.join(d, "lit.csv"), "w") as fh:
                fh.write("instance,family,n,m,Nv,algorithm,best,avg,time_s\nT1-2,prins,3,2,2,RLHEA,7.00,7.00,1.0\n")
            os.makedirs(os.path.join(d, "ref"))
            with open(os.path.join(d, "ref", "T1.txt"), "w") as fh:
                fh.write("4 1 2\n")                                                        # customer 3 is missing
            os.makedirs(os.path.join(d, "res"))
            with open(os.path.join(d, "res", "run.csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["Instance", "Seed", "Feasible", "Total Latency", "Gap to BKS (%)"])
                w.writerow(["T1-2", 1, "True", 7.0, 0.0])
            with open(os.path.join(d, "res", "routes.csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["Instance", "Seed", "Depot", "Customers"])
                w.writerow(["T1-2", 1, 0, "0 -> 1"])
                w.writerow(["T1-2", 1, 0, "2"])
            args = [os.path.join(d, "res"), "--ref-solutions", os.path.join(d, "ref"), "--inst-dir", os.path.join(d, "inst"), "--literature", os.path.join(d, "lit.csv"),
                    "--out", os.path.join(d, "out.csv")]
            self.assertEqual([r[5] for r in dd.main(args)], ["E"])
            self.assertEqual(dd.main(args + ["--no-complete"]), [])


class Classes(unittest.TestCase):
    ref = [(0, (0, 1)), (1, (2, 3))]

    def cls(self, ours):
        return dd.classify(self.ref, ours)[0]

    def test_five_classes(self):
        self.assertEqual(self.cls([(0, (0, 1)), (1, (2, 3))]), "E")
        self.assertEqual(self.cls([(0, (1, 0)), (1, (2, 3))]), "D")                       # order inside a route
        self.assertEqual(self.cls([(0, (0,)), (0, (1,)), (1, (2, 3))]), "C")              # same depots and assignment, route split
        self.assertEqual(self.cls([(0, (0, 1, 2)), (1, (3,))]), "B")                      # customer 2 moves to another depot
        self.assertEqual(self.cls([(0, (0, 1)), (2, (2, 3))]), "A")                       # other depot set

    def test_fractions(self):
        cls, nd, common = dd.classify(self.ref, [(0, (0, 1, 2)), (1, (3,))])
        self.assertEqual(cls, "B")
        self.assertAlmostEqual(nd, 0.25)                                                   # 1 of 4 customers served from another depot
        self.assertAlmostEqual(common, 0.0)


class EndToEnd(unittest.TestCase):
    def test_main(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "inst", "prins"))
            with open(os.path.join(d, "inst", "prins", "T1-2.inst"), "w") as fh:
                fh.write(INST)
            with open(os.path.join(d, "lit.csv"), "w") as fh:
                fh.write("instance,family,n,m,Nv,algorithm,best,avg,time_s\nT1-2,prins,3,2,2,RLHEA,7.00,7.00,1.0\n")
            os.makedirs(os.path.join(d, "ref"))
            with open(os.path.join(d, "ref", "T1.txt"), "w") as fh:
                fh.write("4 1 2 3\n")
            os.makedirs(os.path.join(d, "res"))
            with open(os.path.join(d, "res", "run.csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["Instance", "Seed", "Feasible", "Total Latency", "Gap to BKS (%)"])
                w.writerows([["T1-2", 1, "True", 7.0, 0.0], ["T1-2", 2, "True", 8.0, 14.3], ["T1-2", 3, "False", 99.0, 99.0]])
            with open(os.path.join(d, "res", "routes.csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["Instance", "Seed", "Depot", "Customers"])
                w.writerows([["T1-2", 1, 0, "0 -> 1 -> 2"], ["T1-2", 2, 1, "2 -> 1 -> 0"], ["T1-2", 3, 0, "0 -> 1 -> 2"]])
            out = os.path.join(d, "out.csv")
            rows = dd.main([os.path.join(d, "res"), "--ref-solutions", os.path.join(d, "ref"), "--inst-dir", os.path.join(d, "inst"),
                            "--literature", os.path.join(d, "lit.csv"), "--out", out])
            self.assertEqual([(r[3], r[5]) for r in rows], [(1, "E"), (2, "A")])           # the infeasible run is skipped
            with open(out) as fh:
                self.assertEqual(len(list(csv.DictReader(fh))), 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
