"""Self-test of the statistics in ext10_report.py:  python3 analysis/test_report.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext10_report as R


class Wilcoxon(unittest.TestCase):
    def test_all_positive_small(self):
        n, wp, wm, pe, pn = R.wilcoxon([1, 2, 3, 4, 5])
        self.assertEqual((n, wp, wm), (5, 15.0, 0.0))
        self.assertAlmostEqual(pe, 2 / 32)                  # only the all-positive and all-negative patterns reach W = 0
        self.assertAlmostEqual(pn, 0.0431, places=3)         # z = -7.5 / sqrt(13.75)

    def test_symmetric_data_have_p_one(self):
        n, wp, wm, pe, pn = R.wilcoxon([1, -2, 3, -4])
        self.assertEqual((wp, wm), (4.0, 6.0))
        self.assertGreater(pe, 0.8)

    def test_ties_use_midranks(self):
        n, wp, wm, pe, pn = R.wilcoxon([1, 1, -1, 2])        # |d| = 1,1,1,2 -> mid-rank 2 for the three ones
        self.assertEqual((wp, wm), (8.0, 2.0))

    def test_against_scipy_if_available(self):
        try:
            from scipy.stats import wilcoxon
        except Exception:
            self.skipTest('scipy not installed')
        d = [0.5, -1.2, 2.3, 3.1, -0.7, 4.4, 5.0, 1.9, 2.8, -0.1, 3.7, 6.2]
        n, wp, wm, pe, pn = R.wilcoxon(d)
        self.assertAlmostEqual(pe, wilcoxon(d, method='exact').pvalue, places=10)
        self.assertAlmostEqual(pn, wilcoxon(d, method='approx', correction=False).pvalue, places=6)


class Anytime(unittest.TestCase):
    def test_best_after_uses_zero_based_iteration_index(self):
        ev = [(0, 10.0), (3, 8.0), (7, 5.0)]
        its = [e[0] for e in ev]
        self.assertIsNone(R.best_after(ev, its, 0))          # nothing completed
        self.assertEqual(R.best_after(ev, its, 1), 10.0)      # iteration 0 done
        self.assertEqual(R.best_after(ev, its, 3), 10.0)      # iterations 0..2 done, the event at index 3 is not yet in
        self.assertEqual(R.best_after(ev, its, 4), 8.0)
        self.assertEqual(R.best_after(ev, its, 99), 5.0)


if __name__ == '__main__':
    unittest.main()
