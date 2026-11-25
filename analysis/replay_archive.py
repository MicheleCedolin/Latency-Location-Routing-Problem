#!/usr/bin/env python3
"""Replay runs of a result archive with the current engine and compare the objective value.

A run that was limited by CPU time is reproduced exactly by running the same seed and flags for the number of GRASP iterations it completed
(`--max-iter <Iterations>`; the run log records it).  This script picks the cheapest runs of an archive (smallest iterations x n^2) and checks
that the engine of this repository returns the archived objective value.  It is the test that links the archives to the source code.

  python3 -I analysis/replay_archive.py study_results/b1_tuned.tar.gz --flags cpp/stages/3_pool.flags --n-runs 3 [--jobs 2]
  python3 -I analysis/replay_archive.py ARCHIVE --flags FLAGS --instance 100-10-1-10 --seed 10      # one named run

Exit code 0 if every replayed value agrees with the archive to 1e-6 (relative), 1 otherwise.
"""
import argparse, csv, glob, io, math, os, subprocess, sys, tarfile, tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_runs(archive, dest):
    with tarfile.open(archive) as tf:
        tf.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tf.extractall(dest)
    runs = []
    for f in sorted(glob.glob(os.path.join(dest, "**", "run.csv"), recursive=True)):
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                runs.append(r)
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("archive")
    ap.add_argument("--flags", required=True, help="flag file of the campaign")
    ap.add_argument("--n-runs", type=int, default=3)
    ap.add_argument("--instance")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--bin", default=os.path.join(ROOT, "cpp", "bin", "llrp_fast"))
    ap.add_argument("--manifest", default=os.path.join(ROOT, "cpp", "manifest.tsv"))
    ap.add_argument("--inst-root", default=os.path.join(ROOT, "cpp", "inst"))
    a = ap.parse_args()
    fam = {}
    with open(a.manifest) as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            fam[r["name"]] = (r["family"], int(r["n"]))
    flags = open(a.flags).read().split()
    with tempfile.TemporaryDirectory() as tmp:
        runs = read_runs(a.archive, tmp)
        if not runs:
            sys.exit("no run.csv in " + a.archive)
        if a.instance:
            sel = [r for r in runs if r["Instance"] == a.instance and (a.seed is None or int(r["Seed"]) == a.seed)]
        else:
            sel = sorted(runs, key=lambda r: int(r["Iterations"]) * fam[r["Instance"]][1] ** 2)[: a.n_runs]

        def one(r):
            f, n = fam[r["Instance"]]
            cmd = [a.bin, "--instance", os.path.join(a.inst_root, f, r["Instance"] + ".inst"), "--seed", r["Seed"]] + flags + \
                  ["--max-iter", r["Iterations"], "--quiet", "--out-level", "0"]
            out = subprocess.run(cmd, capture_output=True, text=True).stdout
            cost = None
            for line in out.splitlines():
                if line.startswith("final_cost"):
                    cost = float(line.split()[1])
            return r, cost

        bad = 0
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for r, cost in ex.map(one, sel):
                ref = float(r["Total Latency"])
                ok = cost is not None and abs(cost - ref) <= 1e-6 * max(1.0, abs(ref))
                bad += not ok
                print("%-4s %-14s seed %-3s iterations %-6s archive %.8f replay %s" % ("OK" if ok else "DIFF", r["Instance"], r["Seed"], r["Iterations"], ref,
                                                                                    "%.8f" % cost if cost is not None else "none"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
