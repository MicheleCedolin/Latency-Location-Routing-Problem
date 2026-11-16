"""Helpers shared by the LLRP tests: tiny frozen solver parameters, the framework loader and the instance setup (K and p from the registry)."""
from __future__ import annotations
import hashlib, importlib, json, pathlib, sys

SMALL = dict(
    ils_iters=3, perturb_strength=2, vns_kmax=3, vns_iters=3,
    sa_iters=150, tabu_iters=40, tabu_candidates=10,
    ga_pop=10, ga_generations=4, alns_iters=25, lns_iters=25, msls_starts=3,
    brkga_pop=10, brkga_generations=3, aco_ants=6, aco_iterations=3,
    rtr_iters=150, ta_iters=150, ig_iters=25,
    grasppr_starts=4, grasppr_steps=5, scatter_pool=6, scatter_refset=3, scatter_iters=2, scatter_steps=5,
    pso_particles=6, pso_iters=3, de_pop=6, de_iters=3, rkrs_trials=40,
)
RESTARTS = 2
DEPOT_SAMPLE = 2


def load_framework(pkg, code_dir):
    """Import ``pkg`` from ``code_dir`` (directory that contains the package folder). Modules already imported are reused (they are
    never purged: a purge makes the later tests of the same process see a second copy of the module-level state, e.g. depot_impact.S)."""
    code_dir = str(pathlib.Path(code_dir).resolve())
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    return {m: importlib.import_module(f'{pkg}.{m}') for m in ('core', 'params', 'heuristics', 'construction')}


def route_hash(sol):
    if not sol:
        return None
    sig = sorted((r.depot, tuple(r.seq)) for r in sol if r.seq)
    return hashlib.sha1(json.dumps(sig).encode()).hexdigest()[:12]


def instance_setup(problem, mods, root, name):
    """(instance, K, p) of a registered instance: K = fleet bound, p = open-depot bound of reference/LLRP_reference.csv."""
    root = pathlib.Path(root)
    prm = mods['params'].REGISTERED[name]
    inst = mods['core'].read_dat(root / 'data' / prm['family'] / prm['file'])
    return inst, prm['K'], prm['p']
