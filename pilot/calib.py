#!/usr/bin/env python3
"""Calibration of the CPU budget of a pilot (run on the same kind of runner as the pilot blocks).

The cluster budget of the study is 3n CPU seconds per run; on the cluster the control arm B1 completes `cluster_iters` GRASP iterations in it.  A GitHub runner is
several times faster per CPU second, so the same CPU limit would give many more iterations than the cluster budget.  This script runs the control arm with
--max-iter <cluster_iters> (no time limit) for a few seeds in parallel and reports the mean CPU time it needs: that is the 'cluster-equivalent' budget.
usage: calib.py <family/instance> <cluster_iters> <seeds> <arm> <bin_dir> <arms_dir> <inst_root> <out.json>"""
import json, subprocess, sys, csv, os, tempfile, statistics
inst, iters, seeds, arm, bindir, armsdir, root, out = sys.argv[1:9]
iters, seeds = int(iters), int(seeds)
flags = open(os.path.join(armsdir, arm + ".flags")).read().split()
instf = os.path.join(root, inst + ".inst")
name = os.path.basename(inst)
tmp = tempfile.mkdtemp()
procs = []
for s in range(1, seeds + 1):
    pre = os.path.join(tmp, "%s_s%d" % (name, s))
    cmd = [os.path.join(bindir, "llrp_fast_v8"), "--instance", instf, "--seed", str(s)] + flags + ["--max-iter", str(iters), "--out-level", "0", "--algo", arm, "--quiet", "--out", pre]
    procs.append((s, pre, subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
cpus, its = [], []
for s, pre, p in procs:
    p.wait()
    row = next(csv.reader(open(pre + ".run.csv")))
    cpus.append(float(row[8])); its.append(int(row[21]))
res = {"instance": inst, "cluster_iters": iters, "seeds": seeds, "cpu_mean": statistics.mean(cpus), "cpu_min": min(cpus), "cpu_max": max(cpus), "iters": its}
res["limit_s"] = max(10, int(5 * round(res["cpu_mean"] / 5.0)))
json.dump(res, open(out, "w"))
print(json.dumps(res))
