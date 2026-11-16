#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_large_ablation.py
=====================

Large-instance extension of the component (ablation) analysis for the
GRASP-VND metaheuristic for the Latency Location-Routing Problem (LLRP).

Purpose
-------
  Run Base+SO and Base+SO+DS on Prins and Tuzun instances with n >= 100
  (about 12 stratified instances, or all 66 Prins and Tuzun instances).

Configurations (the algorithm modules are used UNMODIFIED, see code/)
  SO     Base + strategic oscillation        code/VND0SO.py
  SO_DS  Base + strategic oscillation + DS   code/VND0SOdepot.py

Protocol (identical to the main experiments)
  * 30 independent runs per (instance, configuration): seeds 0..29,
    run_id = seed + 1, random.seed(seed) and numpy.random.seed(seed)
  * I_max = 50 GRASP iterations, RCL size 5 (alpha_max)
  * single-threaded runs; one run = one job (multiprocessing pool)
  * the same seed is used by both configurations (paired design)

Sub-commands
  select     build the stratified 12-instance list  -> selected_instances.csv
             (select --all: all 66 Prins+Tuzun instances in 5 stages -> selected_all.csv)
  plan       print the job plan / progress (no computation)
  calibrate  time a few iterations per (instance, config) and extrapolate
  run        execute the experiment (resumable, refuses without --yes)
  aggregate  merge raw per-run JSON files into CSV tables
  analyze    paired comparison SO vs SO_DS (Wilcoxon + Holm + effect sizes)

Typical session
  python run_large_ablation.py select
  python run_large_ablation.py calibrate --workers 8 --iters 10
  python run_large_ablation.py run --workers 30                # dry plan
  python run_large_ablation.py run --workers 30 --yes          # real run
  python run_large_ablation.py aggregate
  python run_large_ablation.py analyze

Compatible with Python >= 3.6 (no dataclasses / walrus / PEP 585 generics).
"""
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_v] = "1"

import argparse
import contextlib
import glob
import hashlib
import importlib
import io
import json
import math
import multiprocessing as mp
import platform
import random
import socket
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

CONFIGS = {
    "SO": {"module": "VND0SO", "label": "Base+SO",
           "algorithm": "GRASP-VND0-SO"},
    "SO_DS": {"module": "VND0SOdepot", "label": "Base+SO+DS",
              "algorithm": "GRASP-VND0-SO-DS"},
}
FAMILIES = {"Prins": "Prins_Instances.xlsx", "Tuzun": "Tuzun_Instances.xlsx"}

DEFAULT_ITERS = 50
DEFAULT_RCL = 5
DEFAULT_SEEDS = "0-29"
SELECT_SEED = 2026          # seed of the stratified instance draw
N_MIN = 100                 # large instances: n >= 100


# =============================================================================
# helpers
# =============================================================================

def parse_seeds(text):
    out = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(set(out))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    if isinstance(o, set):
        return sorted(o)
    raise TypeError("not serialisable: %r" % (type(o),))


def atomic_write_json(path, obj):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as fh:
        json.dump(obj, fh, default=_json_default)
    os.replace(tmp, path)


def valid_json(path):
    try:
        with open(path) as fh:
            d = json.load(fh)
        return isinstance(d, dict) and "run" in d
    except Exception:
        return False


def job_status(job):
    """'done' | 'missing' | 'mismatch' (result exists but other settings)."""
    p = job_path(job["raw_dir"], job["cfg"], job["instance"], job["seed"])
    if not os.path.exists(p):
        return "missing"
    try:
        with open(p) as fh:
            d = json.load(fh)["run"]
    except Exception:
        return "missing"          # corrupt / partial file -> recompute
    if d.get("Iterations") != job["iters"] or d.get("RCL") != job["rcl"]:
        return "mismatch"
    return "done"


def cpu_model():
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "unknown"


def environment_info(code_dir, data_dir):
    info = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": socket.gethostname(),
        "cpu": cpu_model(),
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(),
        "python": sys.version.replace("\n", " "),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    try:
        import numba
        info["numba"] = numba.__version__
    except Exception as exc:                                   # pragma: no cover
        info["numba"] = "NOT AVAILABLE (%s)" % exc
    files = {}
    for cfg in CONFIGS.values():
        p = os.path.join(code_dir, cfg["module"] + ".py")
        if os.path.exists(p):
            files[os.path.relpath(p, HERE)] = sha256(p)
    for fn in FAMILIES.values():
        p = os.path.join(data_dir, fn)
        if os.path.exists(p):
            files[os.path.relpath(p, HERE)] = sha256(p)
    info["sha256"] = files
    return info


# =============================================================================
# instance catalogue and stratified selection
# =============================================================================

def _import_module(cfg, code_dir):
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    return importlib.import_module(CONFIGS[cfg]["module"])


def assign_stage(row):
    """Execution stage: 0 small Prins, 1 n=100, 2 n=150, 3 Prins n=200,
    4 Tuzun n=200 (cheap/early results first, most expensive last)."""
    n = int(row["n"])
    if n < 100:
        return 0
    if n == 100:
        return 1
    if n < 200:
        return 2
    return 3 if row["Family"] == "Prins" else 4


def build_catalogue(code_dir, data_dir, n_min=N_MIN):
    """All instances with n >= n_min found in the two workbooks."""
    mod = _import_module("SO", code_dir)
    rows = []
    for fam, fn in FAMILIES.items():
        path = os.path.join(data_dir, fn)
        xl = pd.ExcelFile(path)
        names = [s[:-len("-Customer")] for s in xl.sheet_names
                 if s.endswith("-Customer")]
        for name in names:
            if (name + "-Depot") not in xl.sheet_names:
                continue
            cust = xl.parse(name + "-Customer").dropna(how="all")
            dep = xl.parse(name + "-Depot").dropna(how="all")
            try:
                p = mod.get_llrp_parameters(name)
            except Exception:
                continue
            rows.append({
                "Family": fam, "Instance": name, "n": len(cust),
                "m": len(dep), "Q": p["vehicle_cap"], "Nv": p["num_vehicles"],
                "Ng": p["num_open_depots"], "BKS": p["bks"],
            })
    cat = pd.DataFrame(rows)
    cat = cat[cat["n"] >= n_min].reset_index(drop=True)
    cat["Stage"] = cat.apply(assign_stage, axis=1)
    return cat


def stratified_selection(cat, seed=SELECT_SEED):
    """
    One instance per stratum, drawn with a fixed legacy-RandomState seed.
      Prins : strata (n, m, Q)  -> 3 size/depot classes x 2 capacity classes = 6
      Tuzun : strata (n, m)     -> 3 sizes x 2 depot counts                 = 6
    """
    rs = np.random.RandomState(seed)
    chosen = []
    for fam in ["Prins", "Tuzun"]:
        sub = cat[cat["Family"] == fam]
        keys = ["n", "m", "Q"] if fam == "Prins" else ["n", "m"]
        for key, grp in sorted(sub.groupby(keys), key=lambda kv: kv[0]):
            names = sorted(grp["Instance"].tolist())
            pick = names[rs.randint(len(names))]
            row = grp[grp["Instance"] == pick].iloc[0].to_dict()
            row["Stratum"] = "%s|%s" % (fam, "|".join(
                "%s=%s" % (k, v) for k, v in zip(keys, np.atleast_1d(key))))
            row["StratumSize"] = len(names)
            chosen.append(row)
    return pd.DataFrame(chosen)


def load_selection(args):
    code_dir = os.path.abspath(args.code_dir)
    data_dir = os.path.abspath(args.data_dir)
    if args.instances:
        cat = build_catalogue(code_dir, data_dir)
        wanted = [s.strip() for s in args.instances.split(",") if s.strip()]
        missing = [w for w in wanted if w not in set(cat["Instance"])]
        if missing:
            # allow n < 100 for smoke tests: look them up directly
            sel = _lookup_any(wanted, code_dir, data_dir)
        else:
            sel = cat.set_index("Instance").loc[wanted].reset_index()
        sel["Stage"] = 1
        return sel
    path = os.path.abspath(args.selection)
    if not os.path.exists(path):
        sys.exit("selection file %s not found - run `select` first or pass "
                 "--instances A,B,..." % path)
    sel = pd.read_csv(path)
    if "Stage" not in sel.columns:
        sel["Stage"] = 1
    return sel


def _lookup_any(names, code_dir, data_dir):
    mod = _import_module("SO", code_dir)
    rows = []
    for name in names:
        found = False
        for fam, fn in FAMILIES.items():
            xl = pd.ExcelFile(os.path.join(data_dir, fn))
            if name + "-Customer" in xl.sheet_names:
                cust = xl.parse(name + "-Customer").dropna(how="all")
                dep = xl.parse(name + "-Depot").dropna(how="all")
                p = mod.get_llrp_parameters(name)
                rows.append({"Family": fam, "Instance": name, "n": len(cust),
                             "m": len(dep), "Q": p["vehicle_cap"],
                             "Nv": p["num_vehicles"],
                             "Ng": p["num_open_depots"], "BKS": p["bks"]})
                found = True
                break
        if not found:
            sys.exit("instance %s not found in the workbooks" % name)
    return pd.DataFrame(rows)


# =============================================================================
# independent solution verification (does not use the algorithm's own code)
# =============================================================================

def verify_solution(sol, inst):
    d = np.asarray(inst.depot_coords, dtype=float)
    c = np.asarray(inst.cust_coords, dtype=float)
    dem = np.asarray(inst.demands, dtype=float)
    routes = [r for r in sol.routes if r["path"]]
    seen, loads, open_d, total = [], [], set(), 0.0
    for r in routes:
        dep = int(r["depot"])
        open_d.add(dep)
        prev, t, load = d[dep], 0.0, 0.0
        for cu in r["path"]:
            cu = int(cu)
            cur = c[cu]
            t += float(math.hypot(cur[0] - prev[0], cur[1] - prev[1]))
            total += t
            load += float(dem[cu])
            seen.append(cu)
            prev = cur
        loads.append(load)
    problems = []
    if sorted(seen) != list(range(inst.num_customers)):
        problems.append("coverage")
    if loads and max(loads) > inst.vehicle_cap + 1e-4:
        problems.append("capacity")
    if inst.num_vehicles is not None and len(routes) > inst.num_vehicles:
        problems.append("Nv")
    if inst.num_open_depots is not None and len(open_d) != inst.num_open_depots:
        problems.append("Ng")
    return {
        "feasible_indep": len(problems) == 0,
        "problems": ",".join(problems),
        "latency_indep": total,
        "n_routes": len(routes),
        "open_depots": sorted(open_d),
        "max_load": max(loads) if loads else 0.0,
        "latency_consistent": abs(total - float(sol.cost)) <=
        1e-6 * max(1.0, total),
    }


# =============================================================================
# one job = one (config, instance, seed) run
# =============================================================================

_STATE = {}


def _get_module(cfg, code_dir):
    key = ("mod", cfg)
    if key not in _STATE:
        _STATE[key] = _import_module(cfg, code_dir)
    return _STATE[key]


def _get_instance(cfg, name, data_dir, family, code_dir):
    key = ("inst", cfg, name)
    if key not in _STATE:
        mod = _get_module(cfg, code_dir)
        path = os.path.join(data_dir, FAMILIES[family])
        with contextlib.redirect_stdout(io.StringIO()):
            _STATE[key] = mod.Instance.from_excel(
                path, cust_sheet=name + "-Customer", dep_sheet=name + "-Depot")
    return _STATE[key]


def job_path(raw_dir, cfg, name, seed):
    return os.path.join(raw_dir, cfg, name, "seed_%02d.json" % seed)


def run_job(job):
    """Executed inside a worker process. Never raises."""
    cfg, name, seed = job["cfg"], job["instance"], job["seed"]
    out = job_path(job["raw_dir"], cfg, name, seed)
    if not job.get("force"):
        st = job_status(job)
        if st == "done":
            return {"cfg": cfg, "instance": name, "seed": seed,
                    "skipped": True}
        if st == "mismatch":
            return {"cfg": cfg, "instance": name, "seed": seed,
                    "error": "existing result has different Iterations/RCL; "
                             "use another --out directory"}
    try:
        mod = _get_module(cfg, job["code_dir"])
        inst = _get_instance(cfg, name, job["data_dir"], job["family"],
                             job["code_dir"])
        random.seed(seed)
        np.random.seed(seed)
        buf = io.StringIO()
        w0, c0 = time.perf_counter(), time.process_time()
        with contextlib.redirect_stdout(buf):
            sol, logs = mod.run_grasp_vnd_logged(
                inst, max_iter=job["iters"], alpha_max=job["rcl"],
                run_id=seed + 1, seed=seed, instance_name=name)
        wall = time.perf_counter() - w0
        cpu = time.process_time() - c0
        ver = verify_solution(sol, inst)
        module_feasible = bool(sol.check_validity())

        first_feas, best_it = None, None
        for lg in logs:
            lg["Algorithm"] = CONFIGS[cfg]["algorithm"]
            lg["Config"] = CONFIGS[cfg]["label"]
            if first_feas is None and lg.get("Feasible"):
                first_feas = lg["Iteration"]
            if lg.get("Improved Best"):
                best_it = lg["Iteration"]

        bks = inst.bks
        gap = (100.0 * (float(sol.cost) - bks) / bks) if bks else None
        run = {
            "Instance": name, "Family": job["family"], "Config": cfg,
            "Config Label": CONFIGS[cfg]["label"],
            "Algorithm": CONFIGS[cfg]["algorithm"],
            "Run": seed + 1, "Seed": seed, "Iterations": job["iters"],
            "RCL": job["rcl"],
            "n": inst.num_customers, "m": inst.num_depots,
            "Q": inst.vehicle_cap, "Nv": inst.num_vehicles,
            "Ng": inst.num_open_depots,
            "Feasible": module_feasible,
            "Feasible (independent)": ver["feasible_indep"],
            "Violations": ver["problems"],
            "Total Latency": float(sol.cost),
            "Latency (independent)": ver["latency_indep"],
            "Latency Consistent": ver["latency_consistent"],
            "BKS/Reference": bks, "Gap (%)": gap,
            "Wall Time (s)": wall, "CPU Time (s)": cpu,
            "Open Depots": str(ver["open_depots"]),
            "Number of Routes": ver["n_routes"], "Max Load": ver["max_load"],
            "First Feasible Iteration": first_feas,
            "Last Improving Iteration": best_it,
            "Host": socket.gethostname(),
        }
        arrivals = []
        routes = []
        for idx, r in enumerate(sol.routes):
            if not r["path"]:
                continue
            arr = mod.get_arrival_times(r["depot"], r["path"], inst)
            routes.append({
                "Route ID": idx + 1, "Depot": int(r["depot"]),
                "Customers": " -> ".join(map(str, r["path"])),
                "Number of Customers": len(r["path"]),
                "Load": float(r["load"]), "Route Latency": float(sum(arr)),
            })
        atomic_write_json(out, {"run": run, "iterations": logs,
                                "routes": routes})
        return {"cfg": cfg, "instance": name, "seed": seed, "skipped": False,
                "latency": run["Total Latency"],
                "feasible": ver["feasible_indep"], "wall": wall, "cpu": cpu}
    except Exception as exc:
        import traceback
        return {"cfg": cfg, "instance": name, "seed": seed, "error": repr(exc),
                "trace": traceback.format_exc()}


# =============================================================================
# job planning
# =============================================================================

def _job(row, cfg, s, iters, rcl, raw_dir, code_dir, data_dir, force):
    return {"cfg": cfg, "instance": row["Instance"], "family": row["Family"],
            "seed": int(s), "iters": iters, "rcl": rcl, "raw_dir": raw_dir,
            "code_dir": code_dir, "data_dir": data_dir, "force": force,
            "stage": int(row["Stage"]) if "Stage" in row else 1}


def make_jobs(sel, configs, seeds, iters, rcl, raw_dir, code_dir, data_dir,
              waves, force=False, order="waves"):
    """
    order="instance": stage by stage (column Stage of the selection), inside a
        stage instance by instance (file order), inside an instance seed by
        seed with both configurations of a seed adjacent. One continuous
        queue, so workers never idle between instances; every finished
        instance is complete (30 paired runs) and usable immediately.
    order="waves": longest-processing-time-first inside each wave of seeds,
        so that an interrupted run still contains complete blocks of seeds.
    """
    seeds = list(seeds)
    if order == "instance":
        sel2 = sel.copy()
        if "Stage" not in sel2.columns:
            sel2["Stage"] = 1
        sel2["_ord"] = range(len(sel2))
        sel2 = sel2.sort_values(["Stage", "_ord"], kind="mergesort")
        jobs = []
        for _, row in sel2.iterrows():
            for s in seeds:
                for cfg in configs:
                    jobs.append(_job(row, cfg, s, iters, rcl, raw_dir,
                                     code_dir, data_dir, force))
        return jobs
    waves = max(1, min(waves, len(seeds)))
    size = int(math.ceil(len(seeds) / float(waves)))
    jobs = []
    for w in range(waves):
        block = seeds[w * size:(w + 1) * size]
        part = []
        for _, row in sel.iterrows():
            for cfg in configs:
                for s in block:
                    weight = float(row["n"]) ** 2 * (1.3 if cfg == "SO_DS"
                                                      else 1.0)
                    part.append((weight, _job(row, cfg, s, iters, rcl, raw_dir,
                                              code_dir, data_dir, force)))
        part.sort(key=lambda t: (-t[0], t[1]["seed"], t[1]["cfg"]))
        jobs.extend(j for _, j in part)
    return jobs


def pending(jobs):
    bad = [j for j in jobs if job_status(j) == "mismatch"]
    if bad:
        sys.exit("%d existing result files in %s were produced with other "
                 "Iterations/RCL settings (e.g. %s seed %d). Use a different "
                 "--out directory." % (len(bad), bad[0]["raw_dir"],
                                       bad[0]["instance"], bad[0]["seed"]))
    return [j for j in jobs if job_status(j) != "done"]


def execute(jobs, workers, log_path=None, time_limit_min=0.0, grace_min=10.0):
    """
    Windowed dispatch (at most `workers` jobs in flight).
    time_limit_min > 0: after that many minutes no new job is started; running
    jobs may finish for another `grace_min` minutes, then they are terminated
    (their partial work is lost, finished runs are kept and resumable).
    """
    total = len(jobs)
    errors = []
    if total == 0:
        print("nothing to do")
        return errors
    t0 = time.time()
    soft = t0 + 60.0 * time_limit_min if time_limit_min else None
    hard = soft + 60.0 * grace_min if soft else None
    queue = list(jobs)
    inflight = []
    state = {"done": 0, "core": 0.0}
    note = {"soft": False}

    def report(res):
        state["done"] += 1
        if res.get("error"):
            errors.append(res)
            msg = "[%d/%d] ERROR %s %s seed=%d : %s" % (
                state["done"], total, res["cfg"], res["instance"],
                res["seed"], res["error"])
        elif res.get("skipped"):
            msg = "[%d/%d] skip  %s %s seed=%d" % (
                state["done"], total, res["cfg"], res["instance"],
                res["seed"])
        else:
            state["core"] += res["wall"]
            el = time.time() - t0
            eta = el / state["done"] * (total - state["done"])
            msg = ("[%d/%d] %-5s %-14s seed=%02d lat=%.2f feas=%s "
                   "wall=%.0fs  elapsed=%.2fh eta~%.2fh") % (
                state["done"], total, res["cfg"], res["instance"],
                res["seed"], res["latency"], res["feasible"], res["wall"],
                el / 3600.0, eta / 3600.0)
        print(msg)
        sys.stdout.flush()
        if log_path:
            with open(log_path, "a") as fh:
                fh.write(msg + "\n")

    pool = mp.Pool(processes=max(1, workers))
    terminated = 0
    try:
        while queue or inflight:
            now = time.time()
            if soft and now >= soft and queue:
                if not note["soft"]:
                    print("TIME LIMIT (%.1f min) reached: no new jobs; %d "
                          "running job(s) get %.1f more min" % (
                              time_limit_min, len(inflight), grace_min))
                    note["soft"] = True
                queue = []
            if hard and now >= hard and inflight:
                terminated = len(inflight)
                print("grace period over: terminating %d running job(s)"
                      % terminated)
                break
            while queue and len(inflight) < workers:
                j = queue.pop(0)
                inflight.append((j, pool.apply_async(run_job, (j,))))
            still = []
            for j, ar in inflight:
                if ar.ready():
                    try:
                        report(ar.get())
                    except Exception as exc:      # worker crashed
                        report({"cfg": j["cfg"], "instance": j["instance"],
                                "seed": j["seed"], "error": repr(exc)})
                else:
                    still.append((j, ar))
            inflight = still
            time.sleep(0.5)
        if terminated:
            pool.terminate()
        else:
            pool.close()
    except KeyboardInterrupt:
        print("interrupted - finished runs are kept; re-run the same command "
              "to resume")
        pool.terminate()
    finally:
        pool.join()
    print("finished: %d/%d jobs completed, %d errors, %d not started, "
          "%d terminated, %.2f core-hours of algorithm time, %.2f h wall" % (
              state["done"], total, len(errors), len(queue), terminated,
              state["core"] / 3600.0, (time.time() - t0) / 3600.0))
    for e in errors[:5]:
        print(e.get("trace") or e.get("error"))
    return errors


# =============================================================================
# sub-commands
# =============================================================================

def common_paths(args):
    return (os.path.abspath(args.code_dir), os.path.abspath(args.data_dir),
            os.path.abspath(args.out))


def cmd_select(args):
    code_dir, data_dir, out = common_paths(args)
    if args.all:
        cat = build_catalogue(code_dir, data_dir, n_min=0)
        fam_rank = {"Tuzun": 0, "Prins": 1}
        cat["_f"] = cat["Family"].map(fam_rank)
        cat = cat.sort_values(["Stage", "_f", "Instance"]).drop(columns="_f")
        path = os.path.abspath(args.all_selection)
        cat.to_csv(path, index=False)
        pd.set_option("display.width", 200)
        print("ALL Prins + Tuzun instances: %d" % len(cat))
        print(cat.groupby(["Stage", "Family", "n"]).size().to_string())
        print("written:", path)
        return
    cat = build_catalogue(code_dir, data_dir)
    sel = stratified_selection(cat, args.select_seed)
    path = os.path.abspath(args.selection)
    sel.to_csv(path, index=False)
    cat.to_csv(os.path.join(os.path.dirname(path), "candidates_n100plus.csv"),
               index=False)
    pd.set_option("display.width", 200)
    print("candidate pool (n >= %d): %d instances (%s)" % (
        N_MIN, len(cat), cat.groupby("Family").size().to_dict()))
    print("selection seed:", args.select_seed)
    print(sel[["Family", "Instance", "n", "m", "Q", "Nv", "Ng", "BKS",
               "StratumSize"]].to_string(index=False))
    print("written:", path)


def _estimates(sel, configs, iters, out, calib_path):
    """
    Seconds per full run for every (instance, config).
    Source priority: measured production runs > calibration > power-law model
    fitted to everything measured (fallback exponent 3.1).
    """
    obs = {}
    for p in glob.glob(os.path.join(out, "raw", "*", "*", "seed_*.json")):
        try:
            with open(p) as fh:
                r = json.load(fh)["run"]
        except Exception:
            continue
        key = (r["Instance"], r["Config"])
        obs.setdefault(key, []).append(r["Wall Time (s)"] / float(
            r["Iterations"]) * iters)
    measured = dict((k, float(np.mean(v))) for k, v in obs.items())
    calib = {}
    if calib_path and os.path.exists(calib_path):
        c = pd.read_csv(calib_path)
        for _, r in c.iterrows():
            calib[(r["Instance"], r["Config"])] = float(
                r["Sec per Iteration"]) * iters
    npts = {}
    for _, r in sel.iterrows():
        npts[r["Instance"]] = float(r["n"])
    pts = []
    for src in (calib, measured):
        for (inst, cfg), sec in src.items():
            if inst in npts:
                pts.append((npts[inst], sec))
    b, a = 3.1, None
    if len(pts) >= 2 and len(set(x for x, _ in pts)) >= 2:
        xs = np.log([x for x, _ in pts])
        ys = np.log([y for _, y in pts])
        b, a = np.polyfit(xs, ys, 1)
    elif pts:
        a = np.log(np.median([y for _, y in pts])) - b * np.log(
            np.median([x for x, _ in pts]))
    est = {}
    for _, r in sel.iterrows():
        for cfg in configs:
            key = (r["Instance"], cfg)
            if key in measured:
                est[key] = (measured[key], "measured")
            elif key in calib:
                est[key] = (calib[key], "calibration")
            elif a is not None:
                est[key] = (float(np.exp(a + b * np.log(float(r["n"])))),
                            "model")
            else:
                est[key] = (None, "none")
    return est


def cmd_plan(args):
    code_dir, data_dir, out = common_paths(args)
    sel = load_selection(args)
    seeds = parse_seeds(args.seeds)
    configs = args.configs.split(",")
    raw_dir = os.path.join(out, "raw")
    jobs = make_jobs(sel, configs, seeds, args.iters, args.rcl, raw_dir,
                     code_dir, data_dir, args.waves, order=args.order)
    todo = pending(jobs)
    print("instances : %d" % len(sel))
    print("configs   : %s" % configs)
    print("seeds     : %d (%s)" % (len(seeds), args.seeds))
    print("iterations: %d, RCL %d, job order: %s" % (
        args.iters, args.rcl, args.order))
    if args.time_limit_min:
        print("time limit: %.1f min (+%.1f min grace)" % (
            args.time_limit_min, args.grace_min))
    print("jobs      : %d total, %d done, %d pending" % (
        len(jobs), len(jobs) - len(todo), len(todo)))
    calib = args.calibration or os.path.join(out, "calibration.csv")
    est = _estimates(sel, configs, args.iters, out, calib)
    todo_keys = set((j["instance"], j["cfg"], j["seed"]) for j in todo)
    rows = []
    for stage, grp in sel.groupby("Stage"):
        jt = jd = 0
        rem = 0.0
        unknown = 0
        srcs = set()
        for _, r in grp.iterrows():
            for cfg in configs:
                sec, src = est[(r["Instance"], cfg)]
                srcs.add(src)
                for sd in seeds:
                    jt += 1
                    if (r["Instance"], cfg, sd) in todo_keys:
                        if sec is None:
                            unknown += 1
                        else:
                            rem += sec
                    else:
                        jd += 1
        nan = float("nan")
        no_est = (srcs == set(["none"]))
        rows.append({"Stage": int(stage), "Instances": len(grp),
                     "Jobs": jt, "Done": jd, "Pending": jt - jd,
                     "Remaining core-h": nan if no_est else rem / 3600.0,
                     "Wall h (%d workers)" % args.workers:
                     nan if no_est else rem / 3600.0 / max(1, args.workers),
                     "Estimate source": "+".join(sorted(srcs))})
    tab = pd.DataFrame(rows)
    if len(tab):
        pd.set_option("display.width", 220)
        print(tab.round(1).to_string(index=False))
        if tab["Remaining core-h"].notna().any():
            tot = tab["Remaining core-h"].sum()
            print("TOTAL remaining: %.0f core-hours, about %.1f h wall on %d "
                  "workers (%.1f days)" % (tot, tot / max(1, args.workers),
                                           args.workers,
                                           tot / max(1, args.workers) / 24.0))
        else:
            print("time estimate: n/a (pass --calibration "
                  "results_hpc_test/calibration.csv or finish some runs)")
    return jobs, todo


def cmd_run(args):
    code_dir, data_dir, out = common_paths(args)
    jobs, todo = cmd_plan(args)
    if not args.yes:
        print("\nDRY PLAN ONLY. Add --yes to start the computation.")
        return
    os.makedirs(out, exist_ok=True)
    env = environment_info(code_dir, data_dir)
    env["args"] = vars(args)
    atomic_write_json(os.path.join(out, "environment_%s.json" %
                                   time.strftime("%Y%m%d_%H%M%S")), env)
    if args.limit:
        todo = todo[:args.limit]
    execute(todo, args.workers, os.path.join(out, "progress.log"),
            args.time_limit_min, args.grace_min)
    left = len(pending(jobs))
    print("pending after this invocation: %d" % left)
    if left and not args.limit:
        sys.exit(1)            # lets run_full.sh restart after a crash


def cmd_calibrate(args):
    code_dir, data_dir, out = common_paths(args)
    sel = load_selection(args)
    configs = args.configs.split(",")
    calib_raw = os.path.join(out, "calib_raw")
    jobs = make_jobs(sel, configs, [args.seed], args.iters, args.rcl,
                     calib_raw, code_dir, data_dir, 1, force=True,
                     order="waves")
    print("calibration: %d jobs x %d iterations (seed %d) on %d workers" % (
        len(jobs), args.iters, args.seed, args.workers))
    print("NOTE: use <= number of PHYSICAL cores as --workers, otherwise "
          "hyper-threading inflates the timings.")
    os.makedirs(out, exist_ok=True)
    execute(jobs, args.workers, None, args.time_limit_min, args.grace_min)
    rows = []
    for j in jobs:
        p = job_path(calib_raw, j["cfg"], j["instance"], j["seed"])
        if not os.path.exists(p):
            continue
        with open(p) as fh:
            d = json.load(fh)["run"]
        rows.append({"Instance": d["Instance"], "Config": d["Config"],
                     "n": d["n"], "m": d["m"], "Iterations": d["Iterations"],
                     "Wall (s)": d["Wall Time (s)"],
                     "Sec per Iteration": d["Wall Time (s)"] /
                     float(d["Iterations"]),
                     "Feasible": d["Feasible (independent)"]})
    cal = pd.DataFrame(rows)
    if len(cal) < len(jobs):
        print("WARNING: only %d of %d calibration jobs finished (time limit?) "
              "- the extrapolation below is INCOMPLETE and underestimates "
              "the total." % (len(cal), len(jobs)))
    if cal.empty:
        print("No calibration job finished within the time limit - increase "
              "LIMIT_MIN / --time-limit-min.")
        return
    cal.to_csv(os.path.join(out, "calibration.csv"), index=False)
    pd.set_option("display.width", 200)
    print(cal.to_string(index=False))
    n_seeds = len(parse_seeds(args.seeds))
    full_iters = args.full_iters
    tot = float((cal["Sec per Iteration"] * full_iters * n_seeds).sum()) / 3600
    print("\nExtrapolated algorithm time for %d seeds x %d iterations: "
          "%.0f core-hours" % (n_seeds, full_iters, tot))
    for w in (16, 30, 32, 48, 60):
        print("   on %2d workers: ~%.1f h wall (no hyper-threading penalty "
              "assumed)" % (w, tot / w))
    print("CAVEAT: first iterations are diversification iterations; "
          "intensification iterations (3 of every 8) may be cheaper/dearer. "
          "Treat as +-30%.")
    print("per-config core-hours:")
    cal["CoreH"] = cal["Sec per Iteration"] * full_iters * n_seeds / 3600.0
    print(cal.groupby("Config")["CoreH"].sum().round(1).to_string())


def _collect(out):
    raw = os.path.join(out, "raw")
    runs, its, routes = [], [], []
    for p in sorted(glob.glob(os.path.join(raw, "*", "*", "seed_*.json"))):
        try:
            with open(p) as fh:
                d = json.load(fh)
        except Exception:
            print("unreadable (ignored): %s" % p)
            continue
        runs.append(d["run"])
        for lg in d["iterations"]:
            its.append(lg)
        for r in d["routes"]:
            r2 = dict(r)
            r2.update({"Instance": d["run"]["Instance"],
                       "Config": d["run"]["Config"],
                       "Seed": d["run"]["Seed"]})
            routes.append(r2)
    return pd.DataFrame(runs), pd.DataFrame(its), pd.DataFrame(routes)


def cmd_aggregate(args):
    _, _, out = common_paths(args)
    runs, its, routes = _collect(out)
    if runs.empty:
        sys.exit("no results found under %s" % os.path.join(out, "raw"))
    agg = os.path.join(out, "aggregated")
    os.makedirs(agg, exist_ok=True)
    runs.to_csv(os.path.join(agg, "run_level.csv"), index=False)
    its.to_csv(os.path.join(agg, "iteration_level.csv"), index=False)
    routes.to_csv(os.path.join(agg, "best_routes.csv"), index=False)

    def _s(g):
        feas = g[g["Feasible (independent)"]]
        lat = feas["Total Latency"]
        return pd.Series({
            "Runs": len(g), "Feasible Runs": int(len(feas)),
            "Best": lat.min() if len(lat) else np.nan,
            "Mean": lat.mean() if len(lat) else np.nan,
            "Median": lat.median() if len(lat) else np.nan,
            "Worst": lat.max() if len(lat) else np.nan,
            "Std": lat.std(ddof=1) if len(lat) > 1 else np.nan,
            "Mean Wall (s)": g["Wall Time (s)"].mean(),
            "Mean CPU (s)": g["CPU Time (s)"].mean(),
            "Sum CPU (h)": g["CPU Time (s)"].sum() / 3600.0,
            "BKS/Reference": g["BKS/Reference"].iloc[0],
            "Inconsistent Latency": int((~g["Latency Consistent"]).sum()),
        })
    summ = runs.groupby(["Family", "Instance", "n", "m", "Config"]).apply(_s)
    summ = summ.reset_index()
    for _c in ("Runs", "Feasible Runs", "Inconsistent Latency"):
        summ[_c] = summ[_c].astype(int)
    summ["Best Gap to BKS (%)"] = 100 * (summ["Best"] - summ["BKS/Reference"]) \
        / summ["BKS/Reference"]
    summ["Mean Gap to BKS (%)"] = 100 * (summ["Mean"] - summ["BKS/Reference"]) \
        / summ["BKS/Reference"]
    summ.to_csv(os.path.join(agg, "summary_by_instance_config.csv"),
                index=False)
    if args.xlsx:
        for (inst, cfg), g in runs.groupby(["Instance", "Config"]):
            fn = os.path.join(agg, "Analysis_%s_%s.xlsx" % (inst, cfg))
            s = summ[(summ["Instance"] == inst) & (summ["Config"] == cfg)]
            with pd.ExcelWriter(fn, engine="openpyxl") as w:
                s.to_excel(w, sheet_name="Summary", index=False)
                g.to_excel(w, sheet_name="Run_Level_Details", index=False)
                its[(its["Instance"] == inst) &
                    (its["Config"] == CONFIGS[cfg]["label"])].to_excel(
                    w, sheet_name="Iteration_Level_Details", index=False)
                routes[(routes["Instance"] == inst) &
                       (routes["Config"] == cfg)].to_excel(
                    w, sheet_name="Best_Routes", index=False)
    pd.set_option("display.width", 220)
    print(summ[["Instance", "Config", "Runs", "Feasible Runs", "Best", "Mean",
                "Std", "Mean Wall (s)", "Sum CPU (h)"]].to_string(index=False))
    print("\nrun-level rows: %d | iteration-level rows: %d | total CPU %.1f h" %
          (len(runs), len(its), runs["CPU Time (s)"].sum() / 3600.0))
    bad = runs[~runs["Latency Consistent"] | ~runs["Feasible (independent)"]]
    print("independent-check failures (infeasible or inconsistent): %d" %
          len(bad))
    print("written to", agg)


def _holm(p):
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    run = 0.0
    for rank, idx in enumerate(order):
        run = max(run, (m - rank) * p[idx])
        adj[idx] = min(1.0, run)
    return adj


def cmd_analyze(args):
    from scipy import stats
    _, _, out = common_paths(args)
    agg = os.path.join(out, "aggregated", "run_level.csv")
    if not os.path.exists(agg):
        sys.exit("run `aggregate` first")
    runs = pd.read_csv(agg)
    a = runs[runs["Config"] == "SO"].set_index(["Instance", "Seed"])
    b = runs[runs["Config"] == "SO_DS"].set_index(["Instance", "Seed"])
    idx = a.index.intersection(b.index)
    a, b = a.loc[idx], b.loc[idx]
    rows = []
    for inst in sorted(set(i for i, _ in idx)):
        ia = a.xs(inst, level=0)
        ib = b.xs(inst, level=0)
        feas = ia["Feasible (independent)"] & ib["Feasible (independent)"]
        x, y = ia.loc[feas, "Total Latency"], ib.loc[feas, "Total Latency"]
        d = x - y                       # >0  => DS better (lower latency)
        if len(d) >= 6 and (d != 0).any():
            try:
                p = stats.wilcoxon(d, zero_method="wilcox",
                                   alternative="two-sided").pvalue
            except Exception:
                p = np.nan
        else:
            p = np.nan
        meta = ia.iloc[0]
        rows.append({
            "Instance": inst, "Family": meta["Family"], "n": int(meta["n"]),
            "m": int(meta["m"]), "Pairs": int(len(d)),
            "Feasible SO": int(ia["Feasible (independent)"].sum()),
            "Feasible SO+DS": int(ib["Feasible (independent)"].sum()),
            "Mean SO": x.mean(), "Mean SO+DS": y.mean(),
            "Mean Improvement (%)": 100 * (x.mean() - y.mean()) / x.mean()
            if len(x) else np.nan,
            "DS better (runs)": int((d > 0).sum()),
            "DS worse (runs)": int((d < 0).sum()),
            "Identical (runs)": int((d == 0).sum()),
            "p (paired Wilcoxon, runs)": p,
            "Mean CPU SO (s)": ia["CPU Time (s)"].mean(),
            "Mean CPU SO+DS (s)": ib["CPU Time (s)"].mean(),
        })
    res = pd.DataFrame(rows)
    res["Complete"] = res["Pairs"] >= args.min_pairs
    if (~res["Complete"]).any():
        print("%d instance(s) have < %d feasible pairs yet and are excluded "
              "from Holm and the instance-level test: %s" % (
                  int((~res["Complete"]).sum()), args.min_pairs,
                  ", ".join(res.loc[~res["Complete"], "Instance"])))
    ok = res["p (paired Wilcoxon, runs)"].notna() & res["Complete"]
    res["p Holm"] = np.nan
    if ok.any():
        res.loc[ok, "p Holm"] = _holm(res.loc[ok, "p (paired Wilcoxon, runs)"])
    res.to_csv(os.path.join(out, "aggregated", "analysis_SO_vs_SO_DS.csv"),
               index=False)
    pd.set_option("display.width", 250)
    print(res.round(4).to_string(index=False))
    tot_pairs = int(res["Pairs"].sum())
    if tot_pairs:
        print("\nruns where DS changed nothing (identical latency): %d of %d "
              "pairs (%.1f %%)" % (int(res["Identical (runs)"].sum()), tot_pairs,
                                    100.0 * res["Identical (runs)"].sum() /
                                    tot_pairs))

    # instance-level test (protocol of the paper): paired over instances
    rc = res[res["Complete"]]
    mean_a, mean_b = rc["Mean SO"].values, rc["Mean SO+DS"].values
    dd = mean_a - mean_b
    if len(dd) >= 6 and (dd != 0).any():
        w = stats.wilcoxon(dd, zero_method="wilcox", alternative="two-sided")
        ranks = stats.rankdata(np.abs(dd[dd != 0]))
        r_plus = ranks[dd[dd != 0] > 0].sum()
        r_minus = ranks[dd[dd != 0] < 0].sum()
        rbc = (r_plus - r_minus) / (r_plus + r_minus)
        rs = np.random.RandomState(2026)
        imp = rc["Mean Improvement (%)"].values
        boots = [imp[rs.randint(0, len(imp), len(imp))].mean()
                 for _ in range(10000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        print("\ninstance-level Wilcoxon (SO vs SO+DS, %d instances): "
              "p=%.4g, rank-biserial=%.3f (positive => DS lower latency)" %
              (len(dd), w.pvalue, rbc))
        print("mean improvement of DS over SO: %.3f %%  (95%% bootstrap CI "
              "[%.3f, %.3f])" % (imp.mean(), lo, hi))
    else:
        print("\ninstance-level test skipped (needs >= 6 instances with "
              "differences)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("command", choices=["select", "plan", "calibrate", "run",
                                        "aggregate", "analyze"])
    ap.add_argument("--code-dir", default=os.path.join(HERE, "code"))
    ap.add_argument("--data-dir", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "results_large"))
    ap.add_argument("--selection",
                    default=os.path.join(HERE, "selected_instances.csv"))
    ap.add_argument("--all", action="store_true",
                    help="select: all Prins+Tuzun instances in 5 stages")
    ap.add_argument("--all-selection",
                    default=os.path.join(HERE, "selected_all.csv"))
    ap.add_argument("--order", choices=["instance", "waves"],
                    default="instance",
                    help="job order: stage->instance->seed (default) or "
                         "seed waves with LPT")
    ap.add_argument("--calibration", default="",
                    help="calibration.csv used for time estimates")
    ap.add_argument("--min-pairs", type=int, default=30,
                    help="analyze: minimum feasible pairs for an instance to "
                         "enter Holm / the instance-level test")
    ap.add_argument("--instances", default="",
                    help="comma list overriding the selection file")
    ap.add_argument("--configs", default="SO,SO_DS")
    ap.add_argument("--seeds", default=DEFAULT_SEEDS)
    ap.add_argument("--iters", type=int, default=DEFAULT_ITERS)
    ap.add_argument("--rcl", type=int, default=DEFAULT_RCL)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)
                                                       // 2))
    ap.add_argument("--waves", type=int, default=3,
                    help="seed blocks scheduled one after the other")
    ap.add_argument("--yes", action="store_true",
                    help="really start the computation (`run`)")
    ap.add_argument("--time-limit-min", type=float, default=0.0,
                    help="stop starting new jobs after this many minutes "
                         "(0 = no limit)")
    ap.add_argument("--grace-min", type=float, default=10.0,
                    help="minutes running jobs may continue after the time "
                         "limit before they are terminated")
    ap.add_argument("--limit", type=int, default=0,
                    help="run at most this many pending jobs (testing)")
    ap.add_argument("--select-seed", type=int, default=SELECT_SEED)
    ap.add_argument("--seed", type=int, default=0, help="calibrate: seed")
    ap.add_argument("--full-iters", type=int, default=DEFAULT_ITERS,
                    help="calibrate: iterations of the real run")
    ap.add_argument("--xlsx", action="store_true",
                    help="aggregate: also write per-instance Excel workbooks")
    args = ap.parse_args()
    if args.command == "calibrate" and args.iters == DEFAULT_ITERS:
        args.iters = 10
    {"select": cmd_select, "plan": cmd_plan, "calibrate": cmd_calibrate,
     "run": cmd_run, "aggregate": cmd_aggregate,
     "analyze": cmd_analyze}[args.command](args)


if __name__ == "__main__":
    main()
