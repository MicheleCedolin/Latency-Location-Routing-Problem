"""Elite route pool and set-partitioning recombination (matheuristic polish), opt-in via run_llrp.py --sp-share.

Why this fits the LLRP: the objective is the sum of the customer arrival times, so it separates over the routes. A route (depot,
sequence) has a cost that does not depend on the other routes, and a solution is a set of routes that partition the customers,
use at most K routes and open at most p depots. Every local optimum that any subset-loop method visits therefore contributes
columns, and the best combination of all collected columns is a set-partitioning problem with two side constraints:

    min  sum_r c_r x_r
    s.t. sum_{r: j in r} x_r = 1                    for every customer j
         sum_r x_r <= K
         sum_{r at depot d} x_r <= K y_d,  sum_d y_d <= p,   sum_{r at d} load_r x_r <= cap_d
         x, y binary

The incumbent's routes are always columns, so the recombination never returns a worse solution. The MILP is solved with HiGHS through
scipy.optimize.milp under a wall-clock limit; without scipy the step is skipped (and reported), the search itself is untouched.

Collection: run_local_search() adds the routes of every local optimum within `theta` of the best objective seen so far, and
core.trace_consider() adds every new incumbent. Columns are keyed by (depot, customer set) and keep the cheapest sequence.
"""
from __future__ import annotations
import time
from . import core as _core
from .core import Route, route_latency, feasible, objective, clone_solution

POOL = None            # active RoutePool or None (module level so that the hooks cost one global read when disabled)


class RoutePool:
    def __init__(self, inst, theta=0.03, max_cols=40000):
        self.inst = inst; self.theta = float(theta); self.max_cols = int(max_cols)
        self.cols = {}                     # (depot, frozenset of customers) -> [cost, seq tuple, load, source objective]
        self.best_z = float('inf'); self.added = 0; self.solutions = 0

    def add(self, sol, z):
        if sol is None or z is None: return
        if z < self.best_z: self.best_z = z
        if z > self.best_z * (1.0 + self.theta) + 1e-9: return
        inst = self.inst; self.solutions += 1
        for r in sol:
            if not r.seq: continue
            key = (r.depot, frozenset(r.seq))
            c = route_latency(inst, r)
            cur = self.cols.get(key)
            if cur is None:
                self.cols[key] = [c, tuple(r.seq), r.load, z]; self.added += 1
            else:
                if c < cur[0] - 1e-12: cur[0], cur[1] = c, tuple(r.seq)
                if z < cur[3]: cur[3] = z
        if len(self.cols) > self.max_cols: self._prune()

    def _prune(self):
        keep = int(self.max_cols * 0.8)
        items = sorted(self.cols.items(), key=lambda kv: (kv[1][3], kv[1][0]))
        self.cols = dict(items[:keep])


def enable(inst, theta=0.03, max_cols=40000):
    global POOL
    POOL = RoutePool(inst, theta, max_cols)
    _core._POOL_HOOK[0] = POOL.add
    return POOL


def disable():
    global POOL
    POOL = None
    _core._POOL_HOOK[0] = None


def recombine(inst, K, p, incumbent, incumbent_z, time_limit, pool=None, mip_gap=0.0):
    """Best partition of the customers into pool routes. Returns (solution or None, info dict). None = no strict improvement."""
    pool = pool or POOL
    info = dict(sp_cols=0, sp_status='skipped', sp_s=0.0, sp_improved=False, sp_obj=None)
    if pool is None or time_limit <= 0.05: info['sp_status'] = 'no_time' if pool is not None else 'no_pool'; return None, info
    try:
        import numpy as np
        from scipy.optimize import milp, LinearConstraint, Bounds
        from scipy.sparse import coo_matrix
    except Exception as e:                                     # scipy missing: the search result stays as it is
        info['sp_status'] = 'no_scipy'; return None, info
    t0 = time.perf_counter()
    if incumbent is not None:
        pool.add(incumbent, incumbent_z if incumbent_z is not None else objective(inst, incumbent))
        for r in incumbent:                                    # incumbent routes are always columns (also if pruned/filtered)
            if r.seq:
                key = (r.depot, frozenset(r.seq))
                if key not in pool.cols: pool.cols[key] = [route_latency(inst, r), tuple(r.seq), r.load, incumbent_z or 0.0]
    keys = list(pool.cols.keys()); R = len(keys); n, m = inst.n, inst.m
    info['sp_cols'] = R
    if R == 0: info['sp_status'] = 'empty'; return None, info
    nv = R + m
    cost = np.zeros(nv); rows = []; cols_ = []; vals = []
    for ci, key in enumerate(keys):
        d, cs = key; cost[ci] = pool.cols[key][0]
        for j in cs: rows.append(j); cols_.append(ci); vals.append(1.0)
    nr = n
    # sum x <= K
    for ci in range(R): rows.append(nr); cols_.append(ci); vals.append(1.0)
    lo = [1.0] * n + [-np.inf]; hi = [1.0] * n + [float(K)]; nr += 1
    # per depot: sum_{r at d} x_r - K y_d <= 0 ; sum_{r at d} load x <= cap_d y_d
    bydep = {}
    for ci, (d, _) in enumerate(keys): bydep.setdefault(d, []).append(ci)
    for d, lst in bydep.items():
        for ci in lst: rows.append(nr); cols_.append(ci); vals.append(1.0)
        rows.append(nr); cols_.append(R + d); vals.append(-float(K)); lo.append(-np.inf); hi.append(0.0); nr += 1
        cap = inst.depot_cap[d]
        if cap < sum(inst.demand) - 1e-9:                      # capacities only when they can bind (depot_capacity='enforce')
            for ci in lst: rows.append(nr); cols_.append(ci); vals.append(float(pool.cols[keys[ci]][2]))
            rows.append(nr); cols_.append(R + d); vals.append(-float(cap)); lo.append(-np.inf); hi.append(0.0); nr += 1
    # sum y <= p
    for d in range(m): rows.append(nr); cols_.append(R + d); vals.append(1.0)
    lo.append(-np.inf); hi.append(float(p)); nr += 1
    A = coo_matrix((vals, (rows, cols_)), shape=(nr, nv)).tocsr()
    try:
        res = milp(cost, constraints=LinearConstraint(A, np.array(lo), np.array(hi)), integrality=np.ones(nv),
                   bounds=Bounds(np.zeros(nv), np.ones(nv)),
                   options=dict(time_limit=float(max(0.1, time_limit - (time.perf_counter() - t0))), mip_rel_gap=float(mip_gap), disp=False))
    except Exception as e:
        info['sp_status'] = 'error:' + type(e).__name__; info['sp_s'] = time.perf_counter() - t0; return None, info
    info['sp_s'] = time.perf_counter() - t0
    info['sp_status'] = {0: 'optimal', 1: 'time_limit', 2: 'infeasible', 3: 'unbounded', 4: 'other'}.get(res.status, str(res.status))
    if res.x is None: return None, info
    sol = []
    for ci in range(R):
        if res.x[ci] > 0.5:
            d, cs = keys[ci]; c, seq, load, _ = pool.cols[keys[ci]]
            sol.append(Route(d, list(seq), float(sum(inst.demand[j] for j in seq))))
    if not sol or not feasible(inst, sol, K, p): info['sp_status'] += '+rejected'; return None, info
    z = objective(inst, sol); info['sp_obj'] = z
    if incumbent_z is None or z < incumbent_z - 1e-9:
        info['sp_improved'] = True; return sol, info
    return None, info
