#!/usr/bin/env python3
"""Independent verification of every archived run.

For each run of the given result archives (``study_results/*.tar.gz``) the route set stored in ``routes.csv`` is re-evaluated by
``llrp_tools verify`` against the instance file (every customer served exactly once, at most Nv routes, at most Ng open depots
(exactly Ng unless the run used --atmost), latency recomputed from the routes) and compared with the objective stored in ``run.csv``.

usage:
    cd cpp && ./build.sh && cd ..
    python3 -I analysis/verify_archives.py study_results/*.tar.gz            # about 5 minutes for all archives

The exit status is 0 only if every run of every archive is verified.
"""
import argparse
import collections
import csv
import glob
import os
import subprocess
import sys
import tarfile
import tempfile


def split_runs(dirpath, out):
    """Write one <inst>__<alg>__<seed>.{run,routes}.csv pair per run; return {instance: [prefix, ...]} and the run count."""
    with open(os.path.join(dirpath, "run.csv"), newline="") as f:
        lines = f.read().split("\n")
    with open(os.path.join(dirpath, "routes.csv"), newline="") as f:
        rlines = f.read().split("\n")
    runs = collections.OrderedDict()
    for line in lines[1:]:
        if line.strip():
            c = next(csv.reader([line]))
            runs[(c[0], c[1], c[3])] = line          # run.csv: Instance, Algorithm, Run, Seed, ...
    routes = collections.defaultdict(list)
    for line in rlines[1:]:
        if line.strip():
            c = next(csv.reader([line]))
            routes[(c[0], c[1], c[2])].append(line)  # routes.csv: Instance, Algorithm, Seed, ...
    os.makedirs(out, exist_ok=True)
    per_inst = collections.defaultdict(list)
    for key, line in runs.items():
        pre = os.path.join(out, "%s__%s__%s" % key)
        with open(pre + ".run.csv", "w") as f:
            f.write(line + "\n")
        with open(pre + ".routes.csv", "w") as f:
            f.write("\n".join(routes.get(key, [])) + "\n")
        per_inst[key[0]].append(pre)
    return per_inst, len(runs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archives", nargs="+", help="result archives (.tar.gz)")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--tools", default=os.path.join(here, "..", "cpp", "bin", "llrp_tools"))
    ap.add_argument("--inst", default=os.path.join(here, "..", "cpp", "inst"))
    a = ap.parse_args()
    if not os.path.exists(a.tools):
        sys.exit("llrp_tools not found at %s (run cpp/build.sh first)" % a.tools)
    inst_file = {}
    for p in glob.glob(os.path.join(a.inst, "*", "*.inst")):
        inst_file[os.path.basename(p)[:-5]] = p
    total = collections.Counter()
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        for arch in a.archives:
            name = os.path.basename(arch).replace(".tar.gz", "")
            root = os.path.join(tmp, name)
            with tarfile.open(arch) as t:
                t.extractall(root, filter="data") if sys.version_info >= (3, 12) else t.extractall(root)
            n_runs = n_ok = 0
            for dirpath, _, files in sorted(os.walk(root)):
                if "run.csv" not in files or "routes.csv" not in files:
                    continue
                per_inst, n = split_runs(dirpath, os.path.join(tmp, "split", name, os.path.relpath(dirpath, root)))
                n_runs += n
                for inst, pres in per_inst.items():
                    if inst not in inst_file:
                        bad.append("%s: unknown instance %s" % (name, inst))
                        continue
                    r = subprocess.run([a.tools, "verify", inst_file[inst]] + pres, capture_output=True, text=True)
                    for ln in r.stdout.splitlines():
                        if ln.startswith("OK"):
                            n_ok += 1
                        else:
                            bad.append("%s: %s" % (name, ln[:200]))
            print("%-24s runs %5d   verified %5d   failed %d" % (name, n_runs, n_ok, n_runs - n_ok))
            total["runs"] += n_runs
            total["ok"] += n_ok
    print("TOTAL runs %d, verified %d, failed %d" % (total["runs"], total["ok"], total["runs"] - total["ok"]))
    for b in bad[:20]:
        print("  FAIL", b)
    sys.exit(0 if not bad and total["runs"] == total["ok"] and total["runs"] > 0 else 1)


if __name__ == "__main__":
    main()
