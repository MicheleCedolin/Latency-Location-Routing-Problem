"""Joint depot-set perturbation and route reconstruction for the LLRP (descendant of the CLRP clean.6.3.1 layer).

All randomized decisions use the solver's per-seed RNG. Every returned candidate is complete and independently feasible.
This module NEVER changes the routing neighborhood order of the host.

What differs from the CLRP layer (the objective is the sum of customer arrival times, no opening costs, at most p open depots,
at most K routes, usually uncapacitated depots):
  * the depot universe of the layer is range(inst.m), not the host's `allowed`: a host that enumerates p-subsets would otherwise
    never see a closed depot. Every target set has at most p depots, so the bound holds by construction;
  * target sets are ranked by the p-median bound  LB(S) = sum_c min_{d in S} d(d, c)  (a lower bound on the latency of any
    solution that opens only depots of S, because every arrival time is at least the distance from the customer's depot), not by
    opening costs. Kinds: 'swap' (one open depot replaced by a closed one), 'swap2' (two replaced by two), 'open' (a closed depot
    added while fewer than p are open: closing is never useful, opening is free);
  * the reinsertion (insert_pool) carries the fleet look-ahead of construction.py, because K is tight;
  * the tight-capacity MILP backstop of the CLRP layer (depot assignment) is replaced by the packing-first constructor.
"""
from __future__ import annotations
import itertools
import time
from bisect import bisect_left
from .core import Route, clone_solution, feasible, normalize, objective, used_depots, depot_loads
from .construction import _route_deltas, _new_route_cost, _pack_ok, pack_construct, _MAX_REJECT

EPS=1e-8
KINDS=('swap2','open','swap')
_MAX_SWAP2=150          # candidate two-for-two exchanges that are scored per call (sampled when there are more)


def pmedian_bound(inst, S):
    """sum over customers of the distance to the nearest depot of S: a lower bound on the latency of every solution using only S."""
    ddc=inst.ddc; S=tuple(S)
    if len(S)==1: return sum(ddc[S[0]])
    return sum(min(ddc[d][c] for d in S) for c in range(inst.n))


def ranked_sets(inst, sol, allowed, rng, kind, limit=6, p=None):
    """Depot-set targets of the given kind, best first (smallest p-median bound), at most `limit` of them: (target, old, new).

    `allowed` is accepted for interface compatibility and ignored: the universe is range(inst.m). Only sets with at most p depots
    (p=None: no bound), and whose capacities cover the total demand, are proposed.
    """
    active=sorted(used_depots(sol)); inactive=sorted(set(range(inst.m))-set(active))
    base=pmedian_bound(inst,active)
    options=[]
    def add(cfg,old,new):
        options.append((pmedian_bound(inst,cfg)-base+rng.random()*.05,tuple(sorted(cfg)),old,new))
    if kind=='swap':
        for old in active:
            for new in inactive:
                add((set(active)-{old})|{new},old,new)
    elif kind=='swap2':
        pairs=list(itertools.combinations(active,2)); news=list(itertools.combinations(inactive,2))
        combos=[(a,b) for a in pairs for b in news]
        if len(combos)>_MAX_SWAP2: combos=rng.sample(combos,_MAX_SWAP2)
        for a,b in combos: add((set(active)-set(a))|set(b),a,b)
    elif kind=='open':
        if p is not None and len(active)<p:
            for new in inactive: add(set(active)|{new},None,new)
    else:
        raise ValueError(kind)
    options.sort(key=lambda x:x[0])
    total=sum(inst.demand); out=[]
    for _,cfg,old,new in options:
        if p is not None and len(cfg)>p: continue
        if sum(inst.depot_cap[d] for d in cfg)+EPS < total: continue
        out.append((cfg,old,new))
        if len(out)>=limit: break
    return out


def insert_pool(inst, K, kept, pool, permitted, deadline, rng, required=None, randomized=False):
    """Reinsert a pool by cheapest insertion into the routes of `kept` (all at depots of `permitted`) or into new routes, with a
    cost-biased RCL when randomized. Customers are taken by decreasing demand. The fleet look-ahead of construction.py rejects a
    choice after which the demands still to be placed cannot be packed into the residual capacities and the unused vehicles. Returns the
    routes or None; the caller still tests feasibility.

    required: a depot that must receive a route (the new depot of a swap); it is seeded with the nearest pool customer first."""
    routes=clone_solution(kept)
    dload=depot_loads(inst,routes)
    used=used_depots(routes)
    pool=list(pool)
    required=required if required is not None and required not in used else None
    if required is not None and not pool:return None
    cap=inst.depot_cap; dm=inst.demand; Q=inst.Q
    permitted=tuple(permitted)
    if sum(cap[d]-dload[d] for d in permitted)+EPS < sum(dm[c] for c in pool):return None
    if randomized:
        rng.shuffle(pool)
        pool.sort(key=lambda c:(-dm[c], rng.random()*max(1.0,dm[c])*0.2))
    else:
        pool.sort(key=lambda c:(-dm[c],-max(inst.ddc[d][c] for d in permitted)+min(inst.ddc[d][c] for d in permitted)))
    if required is not None:
        if len(routes)>=K:return None
        feasible_seed=[c for c in pool if dm[c]<=cap[required]+EPS]
        if not feasible_seed:return None
        seed=min(feasible_seed,key=lambda c:inst.ddc[required][c])
        pool.remove(seed)
        routes.append(Route(required,[seed],dm[seed])); dload[required]+=dm[seed];used.add(required)
    neg=sorted(-dm[c] for c in pool)
    look=_pack_ok(neg,[Q-r.load for r in routes]+[Q]*(K-len(routes)),Q)
    for c in pool:
        if deadline is not None and time.perf_counter()>=deadline:return None
        dem=dm[c]; choices=[]
        for ri,r in enumerate(routes):
            if r.depot not in permitted or r.load+dem>Q+EPS or dload[r.depot]+dem>cap[r.depot]+EPS:
                continue
            vals=_route_deltas(inst,r,c)
            pos=min(range(len(vals)),key=vals.__getitem__)
            choices.append((vals[pos], 'insert',ri,pos,r.depot))
        if len(routes)<K and dem<=Q+EPS:
            for d in permitted:
                if dload[d]+dem<=cap[d]+EPS:
                    choices.append((_new_route_cost(inst,used,c,d),'new',len(routes),0,d))
        if not choices:return None
        choices.sort(key=lambda x:x[0])
        if randomized:
            k=rng.randrange(min(len(choices),3)); choices=[choices[k]]+choices[:k]+choices[k+1:]
        i=bisect_left(neg,-dem); del neg[i]
        chosen=choices[0]
        if look:
            nrt=len(routes)
            for ch in choices[:_MAX_REJECT]:
                res=[Q-r.load for r in routes]
                if ch[1]=='new': res.append(Q-dem)
                else: res[ch[2]]-=dem
                res.extend([Q]*(K-nrt-(1 if ch[1]=='new' else 0)))
                if _pack_ok(neg,res,Q): chosen=ch; break
        _,typ,ri,pos,d=chosen
        if typ=='new':
            routes.append(Route(d,[c],dem)); used.add(d)
        else:
            routes[ri].seq.insert(pos,c); routes[ri].load+=dem
        dload[d]+=dem
    return routes


def rebuild(inst,sol,K,p,allowed,target,old,new,rng,deadline):
    """Try preserving routes, then coordinated large-ruin/rebuild, then the packing-first constructor.

    The target set is strict (the result uses depots of the target only); `new` (a depot or a tuple of depots) must receive a route.
    """
    target=tuple(target)
    if not target:return None
    news=() if new is None else ((new,) if isinstance(new,int) else tuple(new))
    removed=[c for r in sol if r.depot not in target for c in r.seq]
    safe=[r for r in sol if r.depot in target]
    strategies=(0.0, 0.30, 0.65, 1.0)
    for frac in strategies:
        if deadline is not None and time.perf_counter()>=deadline:return None
        if frac>=1:
            kept=[];pool=list(range(inst.n))
        else:
            count=round(len(safe)*frac)
            ranked=sorted(safe,key=lambda r:(-min(inst.ddc[d][r.seq[0]] for d in target if d!=r.depot) if len(target)>1 else 0.0,
                                              rng.random()))
            ruin={id(r) for r in ranked[:count]}
            kept=[Route(r.depot,r.seq.copy(),r.load) for r in safe if id(r) not in ruin]
            pool=removed+[c for r in safe if id(r) in ruin for c in r.seq]
        for randomized in (False,True):
            if deadline is not None and time.perf_counter()>=deadline:return None
            req=None
            for nd in news:
                if nd not in used_depots(kept): req=nd; break
            cand=insert_pool(inst,K,kept,pool,target,deadline,rng,required=req,randomized=randomized)
            if cand is None:continue
            cand=normalize(inst,cand)
            if feasible(inst,cand,K,p) and set(used_depots(cand)).issubset(target):
                if all(nd in used_depots(cand) for nd in news):
                    return cand
    return pack_rebuild(inst,K,p,target,rng,news)


def pack_rebuild(inst,K,p,target,rng,news=()):
    """Last resort of rebuild: a packing-first solution (construction.pack_construct) on the target depots; the depots in `news` must be used."""
    for _ in range(4):
        cand=pack_construct(inst,K,target,rng)
        if cand is None:return None
        cand=normalize(inst,cand)
        if feasible(inst,cand,K,p) and all(nd in used_depots(cand) for nd in news):return cand
    return None


def diversify(inst,sol,K,p,allowed,rng,deadline,preferred=None):
    """Generate one feasible change to the depot set, without an LS budget.

    The caller subsequently applies its ORIGINAL loffler9 first-descent before accepting the candidate, so only the location
    mechanism is changed.
    """
    kinds=KINDS if preferred not in KINDS else (preferred,)
    attempted=0
    for kind in kinds:
        for cfg,old,new in ranked_sets(inst,sol,allowed,rng,kind,limit=4,p=p):
            if deadline is not None and time.perf_counter()>=deadline:
                return None,attempted,kind
            attempted+=1
            cand=rebuild(inst,sol,K,p,allowed,cfg,old,new,rng,deadline)
            if cand is not None and set(used_depots(cand))!=set(used_depots(sol)):
                return cand,attempted,kind
    return None,attempted,kinds[-1]
