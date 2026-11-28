"""Unit tests of the paper pipeline (no archives needed): reference table, at-most substitution, time to target.  usage: python3 paper/tests/test_paper.py"""
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import paperlib
import prep


class Reference(unittest.TestCase):
    def setUp(self):
        self.T = paperlib.reference()

    def test_shape(self):
        T = self.T
        self.assertEqual(len(T), 76)
        self.assertEqual(int(T["train"].sum()), 17)
        self.assertEqual(sorted(T["family"].unique()), ["barreto", "prins", "tuzun"])
        self.assertEqual(int((T["n"] >= 75).sum()), 58)               # the extended-budget instances
        self.assertEqual(int((T["n"] <= 50).sum()), 18)

    def test_values_are_consistent(self):
        T = self.T
        self.assertTrue((T[["bks", "zou_best", "zou_avg", "zou_tavg"]] > 0).all().all())
        self.assertTrue((T["zou_avg"] >= T["zou_best"] - 0.0101).all())              # rounding only (RLHEA 20-5-2b-5 prints avg 486.54 < best 486.55)
        self.assertTrue(((T["zou_best"] - T["bks"]).abs() <= 0.03).sum() >= 74)      # reference value = best published value on 74 of 76 instances

    def test_overrides_applied(self):
        T = self.T
        self.assertEqual(T.loc["20-5-1b-5", "zou_best"], 608.05)
        self.assertEqual(T.loc["Ch50-5", "zou_tavg"], 18.6)
        self.assertEqual(T.loc["50-5-1-5", "zou_tavg"], 15.71)
        ov = pd.read_csv(os.path.join(os.path.dirname(paperlib.__file__), "reference_overrides.csv"))
        for _, o in ov.iterrows():
            self.assertEqual(self.T.loc[o["instance"], o["column"]], float(o["value"]))


class Helpers(unittest.TestCase):
    def test_with_atmost_replaces_only_that_instance(self):
        base = pd.DataFrame({"Instance": ["a", "50-5-2BIS-5", "50-5-2BIS-5", "b"], "Seed": [1, 1, 2, 1], "Total Latency": [1.0, 950.0, 950.0, 2.0], "family": ["prins"] * 4})
        am = pd.DataFrame({"Instance": ["50-5-2BIS-5"] * 3, "Seed": [1, 2, 3], "Total Latency": [945.45] * 3})
        with tempfile.TemporaryDirectory() as d:
            am.to_csv(os.path.join(d, "run.csv"), index=False)
            out = prep.with_atmost(base, d, "run")
        self.assertEqual(len(out), 5)
        self.assertEqual(sorted(out.loc[out.Instance == "50-5-2BIS-5", "Total Latency"].unique()), [945.45])
        self.assertEqual(sorted(out.loc[out.Instance != "50-5-2BIS-5", "Total Latency"]), [1.0, 2.0])

    def test_with_atmost_rejects_other_instances(self):
        base = pd.DataFrame({"Instance": ["a"], "Seed": [1]})
        with tempfile.TemporaryDirectory() as d:
            pd.DataFrame({"Instance": ["a"], "Seed": [1]}).to_csv(os.path.join(d, "run.csv"), index=False)
            with self.assertRaises(AssertionError):
                prep.with_atmost(base, d, "run")

    def test_val_at(self):
        t, b = np.array([0.1, 0.5, 2.0]), np.array([10.0, 8.0, 7.0])
        self.assertTrue(np.isnan(prep.val_at(t, b, 0.05)))
        self.assertEqual(prep.val_at(t, b, 0.1), 10.0)
        self.assertEqual(prep.val_at(t, b, 1.0), 8.0)
        self.assertEqual(prep.val_at(t, b, 99.0), 7.0)

    def test_time_to_target(self):
        I = pd.DataFrame({"bks": [7.0], "zou_avg": [9.0], "zou_best": [6.0]}, index=["x"])
        tr = {("x", 1): (np.array([0.1, 0.5, 2.0]), np.array([10.0, 8.0, 7.004]))}
        r = prep.time_to_target(tr, I, ("bks", "zou_avg", "zou_best")).iloc[0]
        self.assertEqual(r["t_bks"], 2.0)                    # 7.004 <= 7.0 + 0.005
        self.assertEqual(r["t_zou_avg"], 0.5)
        self.assertTrue(np.isnan(r["t_zou_best"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
