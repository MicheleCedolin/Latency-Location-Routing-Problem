from __future__ import annotations
import functools
import heapq
import random
from bisect import bisect_left, insort
from functools import reduce
from operator import add, itemgetter
from . import core as _core
from .core import Instance, Route, used_depots, depot_loads, count_construction, _MEMO_MAX


_RCL_MODE = "cardinality"
_RCL_MAX = 7

def set_rcl_policy(mode="cardinality", rcl_max=7):
    global _RCL_MODE, _RCL_MAX
    if mode not in {"cardinality", "value"}:
        raise ValueError(f"Unknown RCL mode: {mode}")
    if int(rcl_max) < 1:
        raise ValueError("rcl_max must be >= 1")
    _RCL_MODE = mode
    _RCL_MAX = int(rcl_max)

def _counted(fn):
    """Count construction attempts and dead ends (a constructor returns None when it cannot complete).
    Diagnostic only: the counters never change what the constructor returns."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        count_construction(result is not None)
        return result
    return wrapper


def _route_prefix(inst: Instance, r: Route):
    """Tables for the insertion costs of a route (latency objective), memoised by (depot, customer sequence).

    For a route s of length L with arrival times T[i] (T[0] = d(depot, s_0), T[i] = T[i-1] + F[i]) and arc costs F[0] = d(depot, s_0),
    F[i] = d(s_{i-1}, s_i): z = sum(T) is the latency of the route. Returns (z, T, F).
    """
    key=(r.depot,tuple(r.seq)); cache=inst._pc
    v=cache.get(key)
    if v is None:
        s=key[1]; L=len(s); row=inst.ddc[r.depot]; dcc=inst.dcc
        F=[row[s[0]]]+[dcc[s[i-1]][s[i]] for i in range(1,L)]
        T=[0.0]*L; t=0.0
        for i in range(L):
            t+=F[i]; T[i]=t
        v=(sum(T),T,F)
        if len(cache)>=_MEMO_MAX: cache.clear()
        cache[key]=v
    return v


def _route_deltas(inst: Instance, r: Route, c: int):
    """insertion_delta(inst, r, c, pos) for pos = 0..len(r.seq), as a list: the increase of the route latency when c is inserted
    before position pos (pos = L appends).

    Inserting c between u (the depot for pos = 0) and v (none for pos = L) gives c the arrival time a = T_u + d(u,c) and delays each
    of the L - pos customers behind it by  Delta = d(u,c) + d(c,v) - d(u,v):   delta = a + (L - pos) * Delta.
    The value equals the latency of the new route minus the old one up to floating-point rounding (tests use 1e-9 relative):
    it is a construction score only; the objective of every solution is recomputed by core.objective. Counts 2 route evaluations
    per value, as the original did.
    """
    _,T,F=_route_prefix(inst,r)
    s=r.seq; L=len(s); dcc=inst.dcc; rowc=inst.ddc[r.depot][c]; dc=dcc[c]
    out=[rowc+L*(rowc+dc[s[0]]-F[0])]                      # pos 0: u = depot, a = d(depot,c), d(u,v) = F[0]
    for pos in range(1,L):
        duc=dcc[s[pos-1]][c]
        out.append(T[pos-1]+duc+(L-pos)*(duc+dc[s[pos]]-F[pos]))
    out.append(T[L-1]+dcc[s[L-1]][c])                      # pos L: nothing behind c
    _core._CTR[1]+=2*(L+1)
    return out


def insertion_delta(inst: Instance, r: Route, c: int, pos: int) -> float:
    """Increase of the route latency when c is inserted at position pos of route r (reference: route_latency of the new route - old)."""
    return _route_deltas(inst,r,c)[pos]


def _new_route_cost(inst: Instance, used, c: int, depot: int) -> float:
    # a new single-customer route has latency d(depot, c); `used` is the set of depots that already have a route
    opening=0.0 if depot in used else inst.open_cost[depot]
    return opening+inst.vehicle_cost+inst.ddc[depot][c]


def new_route_delta(inst: Instance, routes, c: int, depot: int) -> float:
    opening=0.0 if depot in used_depots(routes) else inst.open_cost[depot]
    return opening+inst.vehicle_cost+inst.ddc[depot][c]


def _depot_residual(inst,routes):
    loads=depot_loads(inst,routes)
    return [inst.depot_cap[d]-loads[d] for d in range(inst.m)]


# ----------------------------------------------------------------------------------------------------------------------------
# Fleet look-ahead. K is tight in the LLRP benchmarks (K*Q is only 3-20 % above the total demand, and for many instances a
# first-fit-decreasing packing needs K or K+1 bins), and the latency objective makes a new route cheap (d(depot,c)), so a plain cheapest
# insertion opens the K routes early and strands the large customers. Before a move is committed, the demands that are still unrouted
# are packed (best fit decreasing) into the residual capacities of the routes of the partial solution and the vehicles not yet used.
# A move that leaves them unpackable is rejected (lazily: only the move drawn from the RCL is tested). The test is sufficient, not
# necessary, so after _MAX_REJECT rejections in a step the drawn move is accepted; a dead end then falls back to pack_construct.
# ----------------------------------------------------------------------------------------------------------------------------
_MAX_REJECT = 25


def _pack_ok(neg_items, residuals, Q):
    """Best-fit-decreasing test: can the items (neg_items = ascending list of -demand) be packed into bins with the given residual
    capacities? True is a certificate, False only means that BFD found no packing."""
    if not neg_items: return True
    if sum(residuals)+1e-9 < -sum(neg_items): return False
    res=sorted(residuals)
    for nd in neg_items:
        it=-nd
        k=bisect_left(res,it-1e-9)
        if k==len(res): return False
        r=res[k]-it
        del res[k]
        if r>1e-9: insort(res,r)
    return True


def _root_pack_ok(inst: Instance, K: int) -> bool:
    """Does BFD pack all customers into K vehicles? (cached on the instance)"""
    cache=inst.__dict__.setdefault('_rootpack',{})
    v=cache.get(K)
    if v is None:
        v=_pack_ok(sorted(-d for d in inst.demand),[inst.Q]*K,inst.Q)
        cache[K]=v
    return v


def _pack_bins(inst: Instance, K: int, rng: random.Random, tries: int=60):
    """Partition of the customers into at most K groups of total demand <= Q, or None. Randomised best fit decreasing, then the
    minimum-bin-slack procedure of Gupta and Ho (1999) (each bin is filled by a subset-sum maximum that contains the largest
    remaining item) with random tie breaking. Geography is ignored: this is the last resort of the constructors."""
    n=inst.n; Q=int(inst.Q+1e-9); dem=inst.demand
    integral=all(float(x).is_integer() for x in dem) and float(inst.Q).is_integer()
    for t in range(tries):
        noise=0.0 if t==0 else 0.25
        order=sorted(range(n),key=lambda c:-(dem[c]*(1.0+noise*rng.random())))
        bins=[]; res=[]
        for c in order:
            best=-1; bestr=None
            for b,r in enumerate(res):
                if r>=dem[c]-1e-9 and (bestr is None or r<bestr): best=b; bestr=r
            if best<0:
                if len(bins)>=K: break
                bins.append([c]); res.append(inst.Q-dem[c])
            else:
                bins[best].append(c); res[best]-=dem[c]
        else:
            return bins
    if not integral: return None
    for t in range(tries):
        left=sorted(range(n),key=lambda c:(-dem[c],rng.random())); bins=[]
        while left and len(bins)<=K:
            first=left[0]; rest=left[1:]; cap=Q-int(dem[first])
            reach={0:()}                                     # sum -> chosen indices into rest (a persistent tuple chain)
            idx=list(range(len(rest))); rng.shuffle(idx)
            for i in idx:
                w=int(dem[rest[i]])
                if w>cap: continue
                for sm in sorted(reach,reverse=True):
                    ns=sm+w
                    if ns<=cap and ns not in reach: reach[ns]=(i,reach[sm])
            top=max(reach); ch=reach[top]; chosen=[]
            while ch: chosen.append(ch[0]); ch=ch[1]
            cs=set(chosen)
            bins.append([first]+[rest[i] for i in chosen]); left=[x for j,x in enumerate(rest) if j not in cs]
        if not left and len(bins)<=K: return bins
    return None


def pack_construct(inst: Instance, K: int, allowed_depots, rng: random.Random):
    """Packing-first construction used when the insertion constructors dead-end: a vehicle-capacity packing into at most K groups
    (_pack_bins), each group to the permitted depot with the smallest summed distance (respecting depot capacities when they bind),
    each group sequenced by cheapest insertion in order of increasing distance from its depot. None if no packing is found."""
    bins=_pack_bins(inst,K,rng)
    if bins is None: return None
    allowed=tuple(allowed_depots); cap=inst.depot_cap; dem=inst.demand; dl=[0.0]*inst.m; routes=[]
    for bn in sorted(bins,key=lambda b:-sum(dem[c] for c in b)):
        ld=sum(dem[c] for c in bn)
        cand=[d for d in allowed if dl[d]+ld<=cap[d]+1e-9]
        if not cand: return None
        d=min(cand,key=lambda x:(sum(inst.ddc[x][c] for c in bn),x))
        dl[d]+=ld
        seq=[]
        for c in sorted(bn,key=lambda c:(inst.ddc[d][c],c)):
            if not seq: seq=[c]; continue
            vals=_route_deltas(inst,Route(d,seq,0.0),c)
            seq.insert(min(range(len(vals)),key=vals.__getitem__),c)
        routes.append(Route(d,seq,ld))
    return routes


@_counted
def grasp_construct(inst: Instance, K: int, allowed_depots, rng: random.Random, alpha: float):
    routes=[]; remaining=set(range(inst.n)); rem_d=sum(inst.demand)
    allowed=tuple(allowed_depots)
    cap=inst.depot_cap; q_max=inst.Q+1e-9; Q=inst.Q
    neg=sorted(-d for d in inst.demand)                      # unrouted demands, descending (as negatives, ascending)
    look=_root_pack_ok(inst,K)                               # fleet look-ahead only when BFD can pack the whole instance
    while remaining:
        dloads=depot_loads(inst,routes); moves=[]; fmoves=[]
        used=used_depots(routes); nrt=len(routes)
        # Global depot-capacity look-ahead (binds only with depot_capacity='enforce'): conservative and cheap;
        # exact depot assignment remains part of the search. The residual does not depend on the move,
        # only on the customer's demand, so it is computed once per step.
        res_base=sum(max(0.0,cap[d]-dloads[d]) for d in range(inst.m))
        for c in remaining:
            dem=inst.demand[c]; start=len(moves)
            for ri,r in enumerate(routes):
                if r.load+dem<=q_max and dloads[r.depot]+dem<=cap[r.depot]+1e-9:
                    dep=r.depot
                    for pos,dl in enumerate(_route_deltas(inst,r,c)):
                        moves.append((dl,'ins',c,ri,pos,dep))
            if nrt<K and dem<=q_max:
                for d in allowed:
                    if dloads[d]+dem<=cap[d]+1e-9:
                        moves.append((_new_route_cost(inst,used,c,d),'new',c,nrt,0,d))
            if rem_d-dem<=(res_base-dem)+1e-9: fmoves.extend(moves[start:])
        if not moves: return pack_construct(inst,K,allowed,rng)
        if fmoves: moves=fmoves
        rejected=0
        while True:
            if _RCL_MODE == "cardinality":
                # Randomized cardinality RCL: choose a size in 1..rcl_max and
                # sample uniformly from the best-ranked candidates (the rcl_size smallest, ties in generation order).
                rcl_size=rng.randint(1,min(_RCL_MAX,len(moves)))
                rcl=heapq.nsmallest(rcl_size,moves,key=itemgetter(0))
            else:
                # Legacy value-based RCL retained for sensitivity analysis.
                moves.sort(key=lambda x:x[0])
                lo,hi=moves[0][0],moves[-1][0]
                threshold=lo+alpha*(hi-lo)
                rcl=[x for x in moves if x[0]<=threshold+1e-12]
                cap_n=max(5,int(0.15*len(moves)))
                if len(rcl)>cap_n:
                    rcl=moves[:cap_n]
            pick=rng.choice(rcl); _,typ,c,ri,pos,dpt=pick; dem=inst.demand[c]
            if not look or rejected>=_MAX_REJECT: break
            i=bisect_left(neg,-dem); after=neg[:i]+neg[i+1:]
            res=[Q-r.load for r in routes]
            if typ=='new': res.append(Q-dem)
            else: res[ri]-=dem
            res.extend([Q]*(K-nrt-(1 if typ=='new' else 0)))
            if _pack_ok(after,res,Q): break
            moves=[x for x in moves if x is not pick]; rejected+=1
            if not moves: return pack_construct(inst,K,allowed,rng)
        if typ=='new': routes.append(Route(dpt,[c],dem))
        else: routes[ri].seq.insert(pos,c); routes[ri].load+=dem
        remaining.remove(c); rem_d-=dem
        i=bisect_left(neg,-dem); del neg[i]
    return routes


@_counted
def priority_construct(inst: Instance, K: int, allowed_depots, priority, rng: random.Random | None=None,
                       randomized_ties: bool=False):
    rng=rng or random.Random(0); routes=[]; allowed=tuple(allowed_depots)
    cap=inst.depot_cap; q_max=inst.Q+1e-9; Q=inst.Q
    look=_root_pack_ok(inst,K)
    neg=sorted(-d for d in inst.demand)
    for c in priority:
        dem=inst.demand[c]; dloads=depot_loads(inst,routes); moves=[]
        for ri,r in enumerate(routes):
            if r.load+dem<=q_max and dloads[r.depot]+dem<=cap[r.depot]+1e-9:
                dep=r.depot
                for pos,dl in enumerate(_route_deltas(inst,r,c)):
                    moves.append((dl,'ins',ri,pos,dep))
        nrt=len(routes)
        if nrt<K and dem<=q_max:
            used=used_depots(routes)
            for d in allowed:
                if dloads[d]+dem<=cap[d]+1e-9:
                    moves.append((_new_route_cost(inst,used,c,d),'new',nrt,0,d))
        if not moves: return pack_construct(inst,K,allowed,rng)
        i=bisect_left(neg,-dem); after=neg[:i]+neg[i+1:]
        if randomized_ties:
            moves.sort(key=lambda x:x[0])
            best=moves[0][0]; tied=[x for x in moves if abs(x[0]-best)<=1e-12]; mv=rng.choice(tied)
            ordered=[mv]+[x for x in moves if x is not mv]
        elif look:
            ordered=sorted(moves,key=itemgetter(0))           # stable: ties keep the generation order
        else:
            ordered=[min(moves,key=itemgetter(0))]
        mv=ordered[0]
        if look:
            for mv in ordered[:_MAX_REJECT]:
                typ,ri_=mv[1],mv[2]
                res=[Q-r.load for r in routes]
                if typ=='new': res.append(Q-dem)
                else: res[ri_]-=dem
                res.extend([Q]*(K-nrt-(1 if typ=='new' else 0)))
                if _pack_ok(after,res,Q): break
            else: mv=ordered[0]
        _,typ,ri,pos,dpt=mv
        if typ=='new': routes.append(Route(dpt,[c],dem))
        else: routes[ri].seq.insert(pos,c); routes[ri].load+=dem
        del neg[bisect_left(neg,-dem)]
    return routes
