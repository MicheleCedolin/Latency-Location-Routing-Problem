from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json, math
import time
from typing import List, Tuple

# Effort counters (diagnostic only; they never influence the search). One list so that the fast evaluation layer
# (neighborhoods.Scan) can bump them cheaply:
#   [0] objective_evals  complete-solution evaluations (a candidate that passed the feasibility test counts once)
#   [1] route_evals      route-level evaluations, counted LOGICALLY: a candidate costs one per non-empty route of the
#                        candidate, exactly as if the whole solution had been evaluated (delta evaluation does not change it)
#   [2] construct_calls, [3] construct_failures: construction attempts / dead ends
#   [4] candidates       candidate moves handed to the acceptance step of a neighbourhood scan (feasible or not);
#                        the implementation-independent cost measure of tools/ls_ablation.py
_CTR = [0, 0, 0, 0, 0]


class ScanTimeout(Exception):
    """Raised from inside a neighborhood scan once the run deadline has passed."""


# Deadline (time.perf_counter() value) of the scans of the current local search, or None (set via neighborhoods.set_scan_deadline).
# Kept here, in a one-element list, so that the fast and the reference operators always see the same state.
_SCAN_DL = [None]

# Lightweight anytime-performance tracing. Search logic is unchanged: the
# tracer is updated only when a solver/local-search routine explicitly exposes
# a feasible candidate through trace_consider().
_TRACE_STATE = None
_TRACE_EPS = 1e-10


def start_incumbent_trace(checkpoints=(30.0,60.0,90.0,120.0), max_time=None):
    """Start one in-process incumbent trace.

    Checkpoints are wall-clock seconds measured from this call. The tracer does
    not alter random state, objective values, acceptance logic, or stopping logic.
    max_time=None caps the trace at the last checkpoint; max_time=float('inf') never discards
    an event (fixed-trial runs have no wall-clock budget).
    """
    global _TRACE_STATE
    cps=sorted({float(x) for x in checkpoints if float(x)>0})
    mt=float(max_time) if max_time is not None else (max(cps) if cps else None)
    _TRACE_STATE={
        'start': time.perf_counter(),
        'checkpoints': cps,
        'max_time': mt,
        'best': float('inf'),
        'best_sol': None,
        'events': [],
    }


# Arm scoreboard of the depot-subset race (heuristics.DepotRace): the smallest objective exposed through trace_consider since
# the last arm_reset(). One comparison per call; it never changes a search decision on its own.
_ARM_BEST = [float('inf')]
_POOL_HOOK = [None]       # route_pool.RoutePool.add while --sp-share is active


def arm_reset():
    _ARM_BEST[0]=float('inf')


def arm_best():
    return _ARM_BEST[0]


def trace_consider(z, sol=None):
    """Expose a feasible complete candidate to the anytime tracer.

    The common case (not a new incumbent) returns before reading the clock, so
    instrumentation overhead is negligible relative to candidate evaluation.
    """
    if z is not None and z < _ARM_BEST[0]:
        _ARM_BEST[0]=float(z)
    st=_TRACE_STATE
    if st is None or z is None:
        return
    z=float(z)
    if not math.isfinite(z) or z >= st['best']-_TRACE_EPS:
        return
    elapsed=time.perf_counter()-st['start']
    mt=st['max_time']
    if mt is not None and elapsed > mt + 1e-12:
        return
    st['best']=z
    if sol is not None:
        bs=clone_solution(sol); mp=st.get('dmap')
        if mp is not None:                         # depot layer: the solver works on a sub-instance, report original depot indices
            for r in bs: r.depot=mp[r.depot]
        st['best_sol']=bs
        h=_POOL_HOOK[0]
        if h is not None: h(bs,z)
    st['events'].append({'time_s': elapsed, 'objective': z, 'solution': st['best_sol'] if sol is not None else None})


def set_trace_depot_map(mp):
    """While a depot layer (depot_layer.py) runs a solver on a sub-instance whose depot i is depot mp[i] of the original instance, the
    tracer stores the incumbent solutions with the original depot indices. None switches the mapping off. No effect without a tracer."""
    st=_TRACE_STATE
    if st is not None: st['dmap']=None if mp is None else tuple(mp)


def trace_wants(z):
    """True when trace_consider(z, ...) would record z as a new incumbent (lets a caller build the solution lazily)."""
    st=_TRACE_STATE
    return st is not None and z < st['best']-_TRACE_EPS and math.isfinite(z)


def stop_incumbent_trace(final_z=None, final_sol=None):
    """Stop tracing and reconstruct incumbent values at requested checkpoints."""
    global _TRACE_STATE
    st=_TRACE_STATE
    if st is None:
        return {'events': [], 'checkpoints': {}, 'checkpoint_solutions': {}, 'trace_best': None,
                'trace_best_solution': None, 'raw_final_consistent': False,
                'elapsed_s': 0.0}
    elapsed=time.perf_counter()-st['start']
    events=list(st['events'])
    snaps={}; snap_sols={}
    for cp in st['checkpoints']:
        if st['max_time'] is not None and cp > st['max_time']+1e-12:
            continue
        val=None; vsol=None
        for e in events:
            if e['time_s'] <= cp+1e-12:
                val=e['objective']; vsol=e.get('solution')
            else:
                break
        snaps[cp]=val
        snap_sols[cp]=clone_solution(vsol) if vsol is not None else None
    tb=st['best'] if math.isfinite(st['best']) else None
    fz=float(final_z) if final_z is not None and math.isfinite(float(final_z)) else None
    raw_consistent=(tb is None and fz is None) or (tb is not None and fz is not None and abs(tb-fz)<=1e-7*max(1.0,abs(fz)))
    out={
        'events': events,
        'checkpoints': snaps,
        'checkpoint_solutions': snap_sols,
        'trace_best': tb,
        'trace_best_solution': clone_solution(st['best_sol']) if st.get('best_sol') is not None else None,
        'raw_final_consistent': bool(raw_consistent),
        'elapsed_s': elapsed,
    }
    _TRACE_STATE=None
    return out

def reset_objective_evals():
    _CTR[:] = [0, 0, 0, 0, 0]

def get_objective_evals():
    return _CTR[0]

def get_effort_counters():
    return dict(objective_evals=_CTR[0], route_evals=_CTR[1],
                construct_calls=_CTR[2], construct_failures=_CTR[3])

def get_candidate_count():
    return _CTR[4]

def count_construction(ok):
    _CTR[2] += 1
    if not ok:
        _CTR[3] += 1

@dataclass
class Instance:
    n: int
    m: int
    cust: List[Tuple[float,float]]
    dep: List[Tuple[float,float]]
    demand: List[float]
    Q: float
    dcc: List[List[float]]
    ddc: List[List[float]]
    depot_cap: List[float]
    open_cost: List[float]
    vehicle_cost: float
    family: str
    distance_rule: str
    # Objective profile. 'llrp': minimise the sum of customer arrival times (latency), no return to the depot, no opening or
    # vehicle cost in the objective. open_cost_file keeps the (CLRP-style) opening costs stored in the .dat file for reference only.
    profile: str = 'llrp'
    open_cost_file: List[float] = field(default_factory=list, repr=False, compare=False)
    depot_cap_file: List[float] = field(default_factory=list, repr=False, compare=False)
    depot_capacity: str = 'ignore'
    # Memo tables (speed only; they never change a value): route distance by (depot, customers), route load by customers,
    # and the prefix tables of construction.py by (depot, customers). Bounded by _MEMO_MAX entries each.
    _dc: dict = field(default_factory=dict, repr=False, compare=False)
    _lc: dict = field(default_factory=dict, repr=False, compare=False)
    _pc: dict = field(default_factory=dict, repr=False, compare=False)
    _fast: object = field(default=None, repr=False, compare=False)

_MEMO_MAX = 300000

@dataclass
class Route:
    depot: int
    seq: List[int]
    load: float

Solution = List[Route]

def _ed(a,b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def _metric(a,b,rule):
    d=_ed(a,b)
    if rule=='ceil100_euclidean':
        return float(math.ceil(100.0*d-1e-12))
    if rule=='real_euclidean':
        return float(d)
    raise ValueError(rule)

def _family_from_path(path: Path) -> str:
    p=path.resolve()
    if p.parent.name in {'B','P','T','S'}:
        return p.parent.name
    return 'UNKNOWN'

def read_instance(path: Path, profile: str = 'llrp', depot_capacity: str = 'ignore') -> Instance:
    """Read a .dat (or .json) instance.

    profile='llrp' (the only one): real-valued Euclidean distances for every family (the P files too: their flag selects the
    ceil(100 d) rounding of the CLRP literature, which the LLRP literature does not use), zero opening and vehicle cost in the
    objective. The opening costs of the file are kept in Instance.open_cost_file.
    depot_capacity='ignore' (default): depots are uncapacitated (capacity = total demand, never binding). This is the convention of
    the LLRP literature: the published solutions of Zou et al. (2024) exceed the depot capacities of the P files and of Min-134-8
    (tools/indep_check.py, reference/published_check.csv) and only respect Q, K and p. depot_capacity='enforce' uses the capacities
    of the file (a capacitated variant that is not the benchmark problem).
    """
    if depot_capacity not in ('ignore','enforce'): raise ValueError(depot_capacity)
    if profile!='llrp': raise ValueError('only the llrp profile is implemented: '+str(profile))
    path=Path(path); family=_family_from_path(path)
    if path.suffix.lower()=='.json':
        d=json.loads(path.read_text())
        customers=d['customers']; depots=d['depots']
        cust=[(float(x['x']),float(x['y'])) for x in customers]
        dep=[(float(x['x']),float(x['y'])) for x in depots]
        demand=[float(x['demand']) for x in customers]
        Q=float(d['vehicle_capacity'])
        depot_cap=[float(x['capacity']) for x in depots]
        open_cost=[float(x['costs']) for x in depots]
        vehicle_cost=float(d['vehicle_costs'])
        # HGAMP reproduction profile for Schneider-Löffler instances.
        rule='real_euclidean'
    else:
        lines=[line.split() for line in path.read_text().splitlines() if line.strip()]
        # coordOr117.dat contains two extra zero fields on each depot coordinate row.
        if path.name=='coordOr117.dat':
            lines[2:16]=[row[:2] for row in lines[2:16]]
        t=iter(v for row in lines for v in row)
        n=int(next(t)); m=int(next(t))
        dep=[(float(next(t)),float(next(t))) for _ in range(m)]
        cust=[(float(next(t)),float(next(t))) for _ in range(n)]
        Q=float(next(t))
        depot_cap=[float(next(t)) for _ in range(m)]
        demand=[float(next(t)) for _ in range(n)]
        open_cost=[float(next(t)) for _ in range(m)]
        vehicle_cost=float(next(t)); flag=int(next(t))
        extra=list(t)
        if extra:
            raise ValueError(f'Unexpected extra tokens in {path}: {extra[:8]}')
        rule='real_euclidean'                 # LLRP: real distances for P, B and T alike (the flag is read and ignored)
    n=len(cust); m=len(dep)
    dcc=[[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n): dcc[i][j]=_metric(cust[i],cust[j],rule)
    ddc=[[0.0]*n for _ in range(m)]
    for dd in range(m):
        for i in range(n): ddc[dd][i]=_metric(dep[dd],cust[i],rule)
    cap_file=list(depot_cap)
    if depot_capacity=='ignore': depot_cap=[float(sum(demand))]*m
    return Instance(n,m,cust,dep,demand,Q,dcc,ddc,depot_cap,[0.0]*m,0.0,family,rule,profile,list(open_cost),cap_file,depot_capacity)

def read_dat(path: Path, **kw) -> Instance:
    return read_instance(path, **kw)

def _route_latency(inst: Instance, depot: int, s) -> float:
    """Uncounted core of route_latency for a non-empty customer sequence s (memoised by depot and customer sequence).

    Latency of the route = sum of the arrival times of its customers, the vehicle leaving the depot at time 0 and never returning:
        t_1 = d(depot, s_1),  t_k = t_{k-1} + d(s_{k-1}, s_k),  z = t_1 + ... + t_L.
    Accumulated left to right; neighborhoods._len and walker use the identical arithmetic, so the delta layer is bit-identical.
    """
    key=(depot,tuple(s)); cache=inst._dc
    z=cache.get(key)
    if z is None:
        dcc=inst.dcc
        t=inst.ddc[depot][s[0]]; z=t
        a=s[0]
        for b in s[1:]:
            t+=dcc[a][b]; z+=t; a=b
        if len(cache)>=_MEMO_MAX: cache.clear()
        cache[key]=z
    return z

def route_latency(inst: Instance, route: Route) -> float:
    """Sum of the arrival times of the customers of the route (no return arc), memoised by depot and customer sequence."""
    _CTR[1] += 1
    s=route.seq
    if not s: return 0.0
    return _route_latency(inst,route.depot,s)

# Historical names of the CLRP code base (the closed-tour length); in this kit they denote the route latency.
_route_distance=_route_latency
route_distance=route_latency

def arrival_times(inst: Instance, depot: int, s) -> List[float]:
    """[t_1, ..., t_L], the arrival time at each customer of the route depot -> s."""
    if not s: return []
    dcc=inst.dcc; t=inst.ddc[depot][s[0]]; out=[t]; a=s[0]
    for b in s[1:]:
        t+=dcc[a][b]; out.append(t); a=b
    return out

def used_depots(sol: Solution):
    return {r.depot for r in sol if r.seq}

def routing_cost(inst: Instance, sol: Solution) -> float:
    return sum(route_latency(inst,r) for r in sol if r.seq)

def objective_components(inst: Instance, sol: Solution):
    rr=[r for r in sol if r.seq]
    route=routing_cost(inst,rr)
    vehicle=inst.vehicle_cost*len(rr)
    opening=sum(inst.open_cost[d] for d in used_depots(rr))
    return opening,vehicle,route

def objective(inst: Instance, sol: Solution) -> float:
    _CTR[0] += 1
    opening,vehicle,route=objective_components(inst,sol)
    return opening+vehicle+route

def clone_solution(sol: Solution) -> Solution:
    return [Route(r.depot,r.seq.copy(),r.load) for r in sol if r.seq]

def recompute_load(inst: Instance, r: Route) -> float:
    """sum of the demands on the route, in visiting order (memoised by customer sequence)."""
    key=tuple(r.seq); cache=inst._lc
    v=cache.get(key)
    if v is None:
        v=sum(map(inst.demand.__getitem__,key))
        if len(cache)>=_MEMO_MAX: cache.clear()
        cache[key]=v
    return v

def normalize(inst: Instance, sol: Solution) -> Solution:
    out=[]
    for r in sol:
        if r.seq:
            r.load=recompute_load(inst,r); out.append(r)
    return out

def depot_loads(inst: Instance, sol: Solution):
    loads=[0.0]*inst.m
    for r in sol:
        if r.seq: loads[r.depot]+=recompute_load(inst,r)
    return loads

def feasible(inst: Instance, sol: Solution, K: int | None=None, p: int | None=None) -> bool:
    rr=[r for r in sol if r.seq]
    # K = N_v (fleet size: at most K non-empty routes) and p = N_d (at most p open depots) are the bounds of the instance, see
    # params.reference_kp. None disables a bound. Using fewer routes or depots than the bound is feasible (never better in the
    # optimum: splitting a route and opening a free depot cannot increase the latency), so "at most" is the exact semantics.
    if K is not None and len(rr)>K: return False
    if p is not None and len(used_depots(rr))>p: return False
    n=inst.n; m=inst.m
    seen=[]
    for r in rr:
        if r.depot<0 or r.depot>=m: return False
        seen.extend(r.seq)
    # every customer exactly once (same test as sorted(seen)==list(range(n)) for integer customers)
    if len(seen)!=n: return False
    if n and (min(seen)<0 or max(seen)>=n or len(set(seen))!=n): return False
    q_max=inst.Q+1e-9
    loads=[0.0]*m
    for r in rr:
        ld=recompute_load(inst,r)
        if ld>q_max or abs(ld-r.load)>1e-7: return False
        loads[r.depot]+=ld
    cap=inst.depot_cap
    return all(loads[d]<=cap[d]+1e-9 for d in range(m))


def fast_eval_ok(inst: Instance) -> bool:
    """True when neighborhoods.Scan may evaluate candidates by changing only the touched routes.

    The delta layer reproduces the full evaluation bit for bit when demands are integer valued
    (then every load and depot load is exact in floating point, whatever the order of the additions).
    Distances need no assumption: route latencies are always recomputed left to right and summed in route order with the same
    sum() as objective(). All LLRP benchmark sets (P, B, T) have integer demands; any other instance
    simply uses the reference operators of reference_ops.py.
    """
    v=inst._fast
    if v is None:
        lim=2.0**50
        v=bool(all(float(x).is_integer() and abs(x)<lim for x in inst.demand)
               and all(float(x).is_integer() and abs(x)<lim for x in inst.open_cost)
               and float(inst.vehicle_cost).is_integer())
        inst._fast=v
    return v
