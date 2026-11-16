"""Reference implementation of the 15 neighbourhoods and of the first-improvement moves.

Every candidate is built as a full copy of the solution, normalised, tested with core.feasible() and evaluated with
core.objective(). This is the original (clean.4.2) code, kept unchanged in behaviour as the specification of the fast
delta-evaluation operators of neighborhoods.py / local_search.py, which must return exactly the same moves, objective
values, counters and solutions (tests/test_delta_equivalence.py). It is also the fallback of the fast operators for a base
solution that is not feasible/normalised or for an instance with non-integer demands or opening costs (core.fast_eval_ok).
"""
from __future__ import annotations
import time
from typing import Callable, Dict, Tuple
from .core import Route, Solution, clone_solution, normalize, objective, feasible, trace_consider
from . import core as _core

EPS=1e-10
Candidate=Tuple[float,Solution]


def _accept(inst, cand, K,p, best_obj, best):
    # Every candidate of every reference operator passes through here: one place for the deadline check and for
    # exposing a new global incumbent to the anytime tracer at the moment it is evaluated.
    _core._CTR[4]+=1
    dl=_core._SCAN_DL[0]
    if dl is not None and time.perf_counter()>=dl:
        raise _core.ScanTimeout
    cand=normalize(inst,cand)
    if not feasible(inst,cand,K,p):
        return best_obj,best
    z=objective(inst,cand)
    if z<best_obj-EPS:
        trace_consider(z,cand)
        return z,cand
    return best_obj,best

def intra_relocate1(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for ri,r in enumerate(sol):
        n=len(r.seq)
        for i in range(n):
            c=r.seq[i]
            base=r.seq[:i]+r.seq[i+1:]
            for j in range(n):
                ns=base[:j]+[c]+base[j:]
                if ns==r.seq: continue
                cand=clone_solution(sol); cand[ri].seq=ns
                best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def intra_relocate2(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for ri,r in enumerate(sol):
        n=len(r.seq)
        for i in range(n-1):
            block=r.seq[i:i+2]; rem=r.seq[:i]+r.seq[i+2:]
            for j in range(len(rem)+1):
                ns=rem[:j]+block+rem[j:]
                if ns==r.seq: continue
                cand=clone_solution(sol); cand[ri].seq=ns
                best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def intra_swap11(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for ri,r in enumerate(sol):
        for i in range(len(r.seq)):
            for j in range(i+1,len(r.seq)):
                ns=r.seq.copy(); ns[i],ns[j]=ns[j],ns[i]
                cand=clone_solution(sol); cand[ri].seq=ns
                best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def intra_2opt(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for ri,r in enumerate(sol):
        n=len(r.seq)
        for i in range(n-1):
            for j in range(i+1,n):
                ns=r.seq[:i]+list(reversed(r.seq[i:j+1]))+r.seq[j+1:]
                if ns==r.seq: continue
                cand=clone_solution(sol); cand[ri].seq=ns
                best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def depot_reassign(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for ri,r in enumerate(sol):
        for d in allowed:
            if d==r.depot: continue
            cand=clone_solution(sol); cand[ri].depot=d
            best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def inter_relocate1(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for i,a in enumerate(sol):
        for ix,c in enumerate(a.seq):
            dem=inst.demand[c]
            for j,b in enumerate(sol):
                if i==j or b.load+dem>inst.Q+1e-9: continue
                for pos in range(len(b.seq)+1):
                    cand=clone_solution(sol)
                    cc=cand[i].seq.pop(ix)
                    cand[j].seq.insert(pos,cc)
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def _inter_relocate2(inst, sol, K,p,allowed, reverse=False):
    best_obj=objective(inst,sol); best=None
    for i,a in enumerate(sol):
        for ix in range(len(a.seq)-1):
            block=a.seq[ix:ix+2]
            if reverse: block=list(reversed(block))
            dem=sum(inst.demand[c] for c in block)
            for j,b in enumerate(sol):
                if i==j or b.load+dem>inst.Q+1e-9: continue
                for pos in range(len(b.seq)+1):
                    cand=clone_solution(sol)
                    del cand[i].seq[ix:ix+2]
                    cand[j].seq[pos:pos]=block
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def inter_relocate2(inst, sol, K,p,allowed): return _inter_relocate2(inst,sol,K,p,allowed,False)
def inter_relocate2_rev(inst, sol, K,p,allowed): return _inter_relocate2(inst,sol,K,p,allowed,True)

def inter_swap11(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for i in range(len(sol)):
        for j in range(i+1,len(sol)):
            for ia,ca in enumerate(sol[i].seq):
                for ib,cb in enumerate(sol[j].seq):
                    cand=clone_solution(sol)
                    cand[i].seq[ia]=cb; cand[j].seq[ib]=ca
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def inter_swap21(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for i in range(len(sol)):
        for j in range(len(sol)):
            if i==j: continue
            a,b=sol[i],sol[j]
            for ia in range(len(a.seq)-1):
                pair=a.seq[ia:ia+2]
                for ib,cb in enumerate(b.seq):
                    cand=clone_solution(sol)
                    cand[i].seq[ia:ia+2]=[cb]
                    cand[j].seq[ib:ib+1]=pair
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def _inter_swap22(inst, sol, K,p,allowed, reverse=False):
    best_obj=objective(inst,sol); best=None
    for i in range(len(sol)):
        for j in range(i+1,len(sol)):
            a,b=sol[i],sol[j]
            for ia in range(len(a.seq)-1):
                pa=a.seq[ia:ia+2]
                for ib in range(len(b.seq)-1):
                    pb=b.seq[ib:ib+2]
                    x=list(reversed(pb)) if reverse else pb
                    y=list(reversed(pa)) if reverse else pa
                    cand=clone_solution(sol)
                    cand[i].seq[ia:ia+2]=x
                    cand[j].seq[ib:ib+2]=y
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def inter_swap22(inst, sol, K,p,allowed): return _inter_swap22(inst,sol,K,p,allowed,False)
def inter_swap22_rev(inst, sol, K,p,allowed): return _inter_swap22(inst,sol,K,p,allowed,True)

def two_opt_star(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for i in range(len(sol)):
        for j in range(i+1,len(sol)):
            a,b=sol[i],sol[j]
            for ca in range(len(a.seq)+1):
                for cb in range(len(b.seq)+1):
                    if ca==len(a.seq) and cb==len(b.seq): continue
                    na=a.seq[:ca]+b.seq[cb:]
                    nb=b.seq[:cb]+a.seq[ca:]
                    if na==a.seq and nb==b.seq: continue
                    cand=clone_solution(sol); cand[i].seq=na; cand[j].seq=nb
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def two_opt_star_rev(inst, sol, K,p,allowed):
    best_obj=objective(inst,sol); best=None
    for i in range(len(sol)):
        for j in range(i+1,len(sol)):
            a,b=sol[i],sol[j]
            for ca in range(len(a.seq)+1):
                for cb in range(len(b.seq)+1):
                    ta=list(reversed(a.seq[ca:])); tb=list(reversed(b.seq[cb:]))
                    na=a.seq[:ca]+tb; nb=b.seq[:cb]+ta
                    if na==a.seq and nb==b.seq: continue
                    cand=clone_solution(sol); cand[i].seq=na; cand[j].seq=nb
                    best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

def route_split(inst, sol, K,p,allowed):
    if len(sol)>=K: return None
    best_obj=objective(inst,sol); best=None
    for i,r in enumerate(sol):
        if len(r.seq)<2: continue
        for cut in range(1,len(r.seq)):
            left=r.seq[:cut]; right=r.seq[cut:]
            for d2 in allowed:
                cand=clone_solution(sol)
                cand[i].seq=left
                cand.append(Route(d2,right,0.0))
                best_obj,best=_accept(inst,cand,K,p,best_obj,best)
    return (best_obj,best) if best is not None else None

REFERENCE_NEIGHBORHOODS: Dict[str,Callable] = {
    'intra_relocate1': intra_relocate1,
    'intra_relocate2': intra_relocate2,
    'intra_swap11': intra_swap11,
    'intra_2opt': intra_2opt,
    'depot_reassign': depot_reassign,
    'inter_relocate1': inter_relocate1,
    'inter_relocate2': inter_relocate2,
    'inter_relocate2_rev': inter_relocate2_rev,
    'inter_swap11': inter_swap11,
    'inter_swap21': inter_swap21,
    'inter_swap22': inter_swap22,
    'inter_swap22_rev': inter_swap22_rev,
    'two_opt_star': two_opt_star,
    'two_opt_star_rev': two_opt_star_rev,
    'route_split': route_split,
}


def _accept_first(inst,cand,K,p,z):
    _core._CTR[4]+=1
    cand=normalize(inst,cand)
    if not feasible(inst,cand,K,p):
        return None
    z2=objective(inst,cand)
    if z2 < z-EPS:
        return cand,z2
    return None


def first_improving_move(name, inst, sol, K,p,allowed,z,deadline=None):
    """Return the first feasible improving move in deterministic enumeration order.

    This routine intentionally differs from neighborhoods.py, whose operators scan a
    whole neighborhood and return its best improving move.  Phase-A native local
    improvement uses this routine to reproduce a lightweight first-improvement descent
    without invoking the common Phase-B VND module.
    """
    def expired():
        return deadline is not None and time.perf_counter()>=deadline

    if name=='intra_relocate1':
        for ri,r in enumerate(sol):
            n=len(r.seq)
            for i in range(n):
                c=r.seq[i]; base=r.seq[:i]+r.seq[i+1:]
                for j in range(len(base)+1):
                    if expired(): return None
                    ns=base[:j]+[c]+base[j:]
                    if ns==r.seq: continue
                    cand=clone_solution(sol); cand[ri].seq=ns
                    res=_accept_first(inst,cand,K,p,z)
                    if res is not None: return res
        return None

    if name=='inter_relocate1':
        for i,a in enumerate(sol):
            for ix,c in enumerate(a.seq):
                dem=inst.demand[c]
                for j,b in enumerate(sol):
                    if i==j or b.load+dem>inst.Q+1e-9: continue
                    for pos in range(len(b.seq)+1):
                        if expired(): return None
                        cand=clone_solution(sol)
                        cc=cand[i].seq.pop(ix); cand[j].seq.insert(pos,cc)
                        res=_accept_first(inst,cand,K,p,z)
                        if res is not None: return res
        return None

    if name=='intra_swap11':
        for ri,r in enumerate(sol):
            for i in range(len(r.seq)):
                for j in range(i+1,len(r.seq)):
                    if expired(): return None
                    cand=clone_solution(sol)
                    cand[ri].seq[i],cand[ri].seq[j]=cand[ri].seq[j],cand[ri].seq[i]
                    res=_accept_first(inst,cand,K,p,z)
                    if res is not None: return res
        return None

    if name=='inter_swap11':
        for i in range(len(sol)):
            for j in range(i+1,len(sol)):
                for ia in range(len(sol[i].seq)):
                    for ib in range(len(sol[j].seq)):
                        if expired(): return None
                        cand=clone_solution(sol)
                        cand[i].seq[ia],cand[j].seq[ib]=cand[j].seq[ib],cand[i].seq[ia]
                        res=_accept_first(inst,cand,K,p,z)
                        if res is not None: return res
        return None

    if name=='intra_2opt':
        for ri,r in enumerate(sol):
            n=len(r.seq)
            for i in range(n-1):
                for j in range(i+1,n):
                    if expired(): return None
                    ns=r.seq[:i]+list(reversed(r.seq[i:j+1]))+r.seq[j+1:]
                    if ns==r.seq: continue
                    cand=clone_solution(sol); cand[ri].seq=ns
                    res=_accept_first(inst,cand,K,p,z)
                    if res is not None: return res
        return None

    if name=='depot_reassign':
        for ri,r in enumerate(sol):
            for d in allowed:
                if expired(): return None
                if d==r.depot: continue
                cand=clone_solution(sol); cand[ri].depot=d
                res=_accept_first(inst,cand,K,p,z)
                if res is not None: return res
        return None

    if name=='intra_relocate2':
        for ri,r in enumerate(sol):
            n=len(r.seq)
            for i in range(n-1):
                block=r.seq[i:i+2]; rem=r.seq[:i]+r.seq[i+2:]
                for j in range(len(rem)+1):
                    if expired(): return None
                    ns=rem[:j]+block+rem[j:]
                    if ns==r.seq: continue
                    cand=clone_solution(sol); cand[ri].seq=ns
                    res=_accept_first(inst,cand,K,p,z)
                    if res is not None: return res
        return None

    if name=='inter_relocate2':
        for i,a in enumerate(sol):
            for ix in range(len(a.seq)-1):
                block=a.seq[ix:ix+2]
                dem=sum(inst.demand[c] for c in block)
                for j,b in enumerate(sol):
                    if i==j or b.load+dem>inst.Q+1e-9: continue
                    for pos in range(len(b.seq)+1):
                        if expired(): return None
                        cand=clone_solution(sol)
                        del cand[i].seq[ix:ix+2]
                        cand[j].seq[pos:pos]=block
                        res=_accept_first(inst,cand,K,p,z)
                        if res is not None: return res
        return None

    if name=='inter_swap22':
        for i in range(len(sol)):
            for j in range(i+1,len(sol)):
                a,b=sol[i],sol[j]
                for ia in range(len(a.seq)-1):
                    pa=a.seq[ia:ia+2]
                    for ib in range(len(b.seq)-1):
                        if expired(): return None
                        pb=b.seq[ib:ib+2]
                        cand=clone_solution(sol)
                        cand[i].seq[ia:ia+2]=pb
                        cand[j].seq[ib:ib+2]=pa
                        res=_accept_first(inst,cand,K,p,z)
                        if res is not None: return res
        return None

    if name=='two_opt_star':
        for i in range(len(sol)):
            for j in range(i+1,len(sol)):
                a,b=sol[i],sol[j]
                for ca in range(len(a.seq)+1):
                    for cb in range(len(b.seq)+1):
                        if ca==len(a.seq) and cb==len(b.seq): continue
                        if expired(): return None
                        na=a.seq[:ca]+b.seq[cb:]
                        nb=b.seq[:cb]+a.seq[ca:]
                        if na==a.seq and nb==b.seq: continue
                        cand=clone_solution(sol); cand[i].seq=na; cand[j].seq=nb
                        res=_accept_first(inst,cand,K,p,z)
                        if res is not None: return res
        return None

    if name=='route_split':
        if len(sol)>=K: return None
        for i,r in enumerate(sol):
            if len(r.seq)<2: continue
            for cut in range(1,len(r.seq)):
                left=r.seq[:cut]; right=r.seq[cut:]
                for d2 in allowed:
                    if expired(): return None
                    cand=clone_solution(sol)
                    cand[i].seq=left
                    cand.append(Route(d2,right,0.0))
                    res=_accept_first(inst,cand,K,p,z)
                    if res is not None: return res
        return None

    raise ValueError(f"first-improvement is not implemented for neighborhood '{name}'")


