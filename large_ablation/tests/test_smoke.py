#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test of the large-instance ablation runner (about 1 minute).

Checks, on the small instance 50-5-1-5 (2 seeds, 3 iterations, both configs):
  1. all jobs finish without error and pass the independent verification;
  2. results are bit-identical for 1 and 2 workers (seed determinism);
  3. a second invocation finds everything finished (resume);
  4. `aggregate` produces the run-level table.
"""
import json
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(os.path.dirname(HERE), "run_large_ablation.py")
COMMON = ["--instances", "50-5-1-5", "--seeds", "0-1", "--iters", "3"]


def sh(args):
    p = subprocess.Popen([sys.executable, RUNNER] + args,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True)
    out = p.communicate()[0]
    if p.returncode != 0:
        print(out)
        raise SystemExit("runner failed: %s" % " ".join(args))
    return out


def results(out_dir):
    res = {}
    for p in glob.glob(os.path.join(out_dir, "raw", "*", "*", "seed_*.json")):
        with open(p) as fh:
            d = json.load(fh)["run"]
        res[(d["Config"], d["Instance"], d["Seed"])] = d
    return res


def main():
    tmp = tempfile.mkdtemp(prefix="llrp_smoke_")
    try:
        a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
        out = sh(["run", "--out", a, "--workers", "1", "--yes"] + COMMON)
        assert "0 errors" in out, out
        sh(["run", "--out", b, "--workers", "2", "--yes"] + COMMON)
        ra, rb = results(a), results(b)
        assert len(ra) == 4 and set(ra) == set(rb), (len(ra), len(rb))
        for k in ra:
            assert ra[k]["Feasible (independent)"], k
            assert ra[k]["Latency Consistent"], k
            assert abs(ra[k]["Total Latency"] - rb[k]["Total Latency"]) < 1e-9, k
        print("determinism (1 vs 2 workers): OK")
        again = sh(["run", "--out", a, "--workers", "1", "--yes"] + COMMON)
        assert "0 pending" in again, again
        print("resume: OK")
        sh(["aggregate", "--out", a])
        assert os.path.exists(os.path.join(a, "aggregated", "run_level.csv"))
        print("aggregate: OK")
        print("ALL SMOKE TESTS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
