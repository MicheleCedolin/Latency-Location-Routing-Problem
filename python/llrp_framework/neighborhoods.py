"""Neighbourhood operators with delta evaluation.

Each operator scans the whole neighbourhood of a feasible base solution and returns (objective, solution) of the best
improving candidate, or None -- exactly the contract and the results of the reference operators in reference_ops.py.
The difference is the cost of one candidate: instead of cloning the solution, normalising it and re-testing and re-evaluating
all of it, a Scan object holds the per-route data of the base solution (route latencies, loads, depot loads, route counts)
and evaluates a candidate that changes one or two routes by recomputing only those routes:

  * the latency of a new route is recomputed left to right (same arithmetic as core.route_latency),
  * the objective is  (opening + vehicle_cost * #routes, both zero in the llrp profile) + sum(route latencies in route order)  with the same sum() as
    core.objective, so the value is identical bit for bit, for integer and non-integer distances alike,
  * capacity tests: the touched routes, and the touched depots (loads are integer valued, hence exact),
  * the candidate solution is built only for the best move of a scan (and for a new global incumbent of the anytime tracer).

Effort counters keep their meaning: objective_evals and route_evals are counted as if the candidate had been evaluated in
full (core._CTR), and every candidate handed to the acceptance step increments the candidate counter used by
tools/ls_ablation.py. A base solution that is not feasible/normalised, or an instance with non-integer demands or opening
costs (core.fast_eval_ok), is handled by the reference operators. Set LLRP_REFERENCE_OPS=1 to run everything on them.
"""
from __future__ import annotations
import os, time
from itertools import accumulate
from typing import Callable, Dict
from . import core as _core
from .core import Route, Solution, clone_solution, normalize, objective, feasible, trace_consider, trace_wants, fast_eval_ok
from . import reference_ops as _ref
from . import depot_ops as _dep

EPS=1e-10
_perf=time.perf_counter
_CTR=_core._CTR


ScanTimeout=_core.ScanTimeout
_SCAN_DL=_core._SCAN_DL


def set_scan_deadline(deadline):
    """Deadline (time.perf_counter() value) for the scans of the current local search, or None.
    Set by vnd / rvnd / best_descent around their scans; one process runs one search at a time."""
    _SCAN_DL[0]=deadline


def _len(row, dcc, s):
    """Latency of the route depot -> s: sum of the arrival times, no return arc, accumulated left to right
    (identical to core._route_latency, bit for bit)."""
    t=row[s[0]]; z=t; a=s[0]
    for b in s[1:]:
        t+=dcc[a][b]; z+=t; a=b
    return z


class Scan:
    """Per-scan state of a feasible, normalised base solution; evaluates candidates that touch one or two routes.

    e1: one route gets a new customer sequence (same depot, same customers)      e2: two routes get new sequences/loads
    eD: one route moves to another depot                                          eS: one route is split, the tail becomes a new route
    Each returns the objective of the candidate, or None if it is infeasible, and updates the effort counters.
    """
    __slots__=('inst','sol','K','p','R','dep','ld','dist','w','DL','cnt','nused','opening','vc','ov','qmax','cap','oc','ddc','dcc','dem')

    def __init__(self, inst, sol, K, p):
        self.inst=inst; self.sol=sol; self.K=K; self.p=p
        R=len(sol); self.R=R
        rd=_core._route_distance; rl=_core.recompute_load
        self.dep=[r.depot for r in sol]
        self.ld=[rl(inst,r) for r in sol]
        self.dist=[rd(inst,r.depot,r.seq) for r in sol]
        self.w=self.dist.copy()
        m=inst.m; DL=[0.0]*m; cnt=[0]*m
        for r,l in zip(sol,self.ld):
            DL[r.depot]+=l; cnt[r.depot]+=1
        self.DL=DL; self.cnt=cnt
        used={r.depot for r in sol}                       # built like core.used_depots
        self.nused=len(used)
        self.opening=sum(inst.open_cost[d] for d in used)
        self.vc=inst.vehicle_cost
        self.ov=self.opening+inst.vehicle_cost*R          # opening + vehicle, as in core.objective
        self.qmax=inst.Q+1e-9; self.cap=inst.depot_cap; self.oc=inst.open_cost
        self.ddc=inst.ddc; self.dcc=inst.dcc; self.dem=inst.demand

    def refresh(self):
        """Recompute the aggregates (depot loads, route counts, used depots, opening cost) after the caller changed the route
        lists in place (walker.Walker.accept). Per-route arrays (dep, ld, dist, w) must already be consistent."""
        sol=self.sol; inst=self.inst; R=len(sol); self.R=R
        m=inst.m; DL=[0.0]*m; cnt=[0]*m
        for d,l in zip(self.dep,self.ld):
            DL[d]+=l; cnt[d]+=1
        self.DL=DL; self.cnt=cnt
        used={r.depot for r in sol}                       # built like core.used_depots
        self.nused=len(used)
        self.opening=sum(inst.open_cost[d] for d in used)
        self.ov=self.opening+self.vc*R

    def prefix_loads(self, k):
        """[0, d(s0), d(s0)+d(s1), ...] for route k (exact: integer demands)."""
        return list(accumulate(map(self.dem.__getitem__,self.sol[k].seq),initial=0))

    def e1(self, i, ns):
        _CTR[4]+=1
        dl=_SCAN_DL[0]
        if dl is not None and _perf()>=dl: raise ScanTimeout
        w=self.w; old=w[i]
        w[i]=_len(self.ddc[self.dep[i]],self.dcc,ns)
        zr=sum(w); w[i]=old
        _CTR[0]+=1; _CTR[1]+=self.R
        return self.ov+zr

    def e2(self, i, si, li, j, sj, lj):
        _CTR[4]+=1
        dl=_SCAN_DL[0]
        if dl is not None and _perf()>=dl: raise ScanTimeout
        qmax=self.qmax
        if li>qmax or lj>qmax: return None
        dep=self.dep; di=dep[i]; dj=dep[j]
        if di!=dj:
            DL=self.DL; cap=self.cap; ld=self.ld
            if DL[di]+(li-ld[i])>cap[di]+1e-9 or DL[dj]+(lj-ld[j])>cap[dj]+1e-9: return None
        ddc=self.ddc; dcc=self.dcc; w=self.w
        if si and sj:
            oi=w[i]; oj=w[j]
            w[i]=_len(ddc[di],dcc,si); w[j]=_len(ddc[dj],dcc,sj)
            zr=sum(w); w[i]=oi; w[j]=oj
            _CTR[0]+=1; _CTR[1]+=self.R
            return self.ov+zr
        # at least one of the two routes becomes empty and disappears
        lst=w.copy(); drop=[]
        if si: lst[i]=_len(ddc[di],dcc,si)
        else: drop.append(i)
        if sj: lst[j]=_len(ddc[dj],dcc,sj)
        else: drop.append(j)
        drop.sort(reverse=True)
        for k in drop: del lst[k]
        nr=self.R-len(drop); op=self.opening; cnt=self.cnt; oc=self.oc
        if not si:
            if cnt[di]==(2 if (not sj and dj==di) else 1): op-=oc[di]
        if not sj and (si or dj!=di):
            if cnt[dj]==1: op-=oc[dj]
        _CTR[0]+=1; _CTR[1]+=nr
        return (op+self.vc*nr)+sum(lst)

    def eD(self, i, d):
        _CTR[4]+=1
        dl=_SCAN_DL[0]
        if dl is not None and _perf()>=dl: raise ScanTimeout
        o=self.dep[i]
        if self.DL[d]+self.ld[i]>self.cap[d]+1e-9: return None
        cnt=self.cnt; op=self.opening; nu=self.nused; oc=self.oc
        if cnt[o]==1: op-=oc[o]; nu-=1
        if cnt[d]==0: op+=oc[d]; nu+=1
        if nu>self.p: return None
        w=self.w; old=w[i]
        w[i]=_len(self.ddc[d],self.dcc,self.sol[i].seq)
        zr=sum(w); w[i]=old
        _CTR[0]+=1; _CTR[1]+=self.R
        return (op+self.vc*self.R)+zr

    def eS(self, i, left, ll, right, lr, d2):
        _CTR[4]+=1
        dl=_SCAN_DL[0]
        if dl is not None and _perf()>=dl: raise ScanTimeout
        nr=self.R+1
        if nr>self.K: return None
        qmax=self.qmax
        if ll>qmax or lr>qmax: return None
        di=self.dep[i]; op=self.opening; nu=self.nused
        if d2!=di:
            if self.DL[d2]+lr>self.cap[d2]+1e-9: return None
            if self.cnt[d2]==0: op+=self.oc[d2]; nu+=1
        if nu>self.p: return None
        w=self.w; old=w[i]; ddc=self.ddc; dcc=self.dcc
        w[i]=_len(ddc[di],dcc,left); w.append(_len(ddc[d2],dcc,right))
        zr=sum(w); w.pop(); w[i]=old
        _CTR[0]+=1; _CTR[1]+=nr
        return (op+self.vc*nr)+zr


def make_scan(inst, sol, K, p):
    """Scan for the base solution, or None when the reference operators must be used."""
    if _FORCE_REFERENCE or not fast_eval_ok(inst): return None
    for r in sol:
        if not r.seq: return None
    if not feasible(inst,sol,K,p): return None
    return Scan(inst,sol,K,p)


def _mat(inst, sol, changes, extra=None):
    """The normalised candidate with the given (route index, sequence) replacements and an optional appended route."""
    cand=clone_solution(sol)
    for k,s in changes: cand[k].seq=s
    if extra is not None: cand.append(extra)
    return normalize(inst,cand)


def _mat_depot(inst, sol, ri, d):
    cand=clone_solution(sol); cand[ri].depot=d
    return normalize(inst,cand)


def intra_relocate1(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.intra_relocate1(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e1=sc.e1
    for ri,r in enumerate(sol):
        seq=r.seq; n=len(seq)
        for i in range(n):
            c=seq[i]
            base=seq[:i]+seq[i+1:]
            for j in range(n):
                ns=base[:j]+[c]+base[j:]
                if ns==seq: continue
                z=e1(ri,ns)
                if z is not None and z<best_obj-EPS:
                    if trace_wants(z): trace_consider(z,_mat(inst,sol,((ri,ns),)))
                    best_obj=z; best=(ri,ns)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),))) if best is not None else None

def intra_relocate2(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.intra_relocate2(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e1=sc.e1
    for ri,r in enumerate(sol):
        seq=r.seq; n=len(seq)
        for i in range(n-1):
            block=seq[i:i+2]; rem=seq[:i]+seq[i+2:]
            for j in range(len(rem)+1):
                ns=rem[:j]+block+rem[j:]
                if ns==seq: continue
                z=e1(ri,ns)
                if z is not None and z<best_obj-EPS:
                    if trace_wants(z): trace_consider(z,_mat(inst,sol,((ri,ns),)))
                    best_obj=z; best=(ri,ns)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),))) if best is not None else None

def intra_swap11(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.intra_swap11(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e1=sc.e1
    for ri,r in enumerate(sol):
        seq=r.seq
        for i in range(len(seq)):
            for j in range(i+1,len(seq)):
                ns=seq.copy(); ns[i],ns[j]=ns[j],ns[i]
                z=e1(ri,ns)
                if z is not None and z<best_obj-EPS:
                    if trace_wants(z): trace_consider(z,_mat(inst,sol,((ri,ns),)))
                    best_obj=z; best=(ri,ns)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),))) if best is not None else None

def intra_2opt(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.intra_2opt(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e1=sc.e1
    for ri,r in enumerate(sol):
        seq=r.seq; n=len(seq)
        for i in range(n-1):
            for j in range(i+1,n):
                ns=seq[:i]+list(reversed(seq[i:j+1]))+seq[j+1:]
                if ns==seq: continue
                z=e1(ri,ns)
                if z is not None and z<best_obj-EPS:
                    if trace_wants(z): trace_consider(z,_mat(inst,sol,((ri,ns),)))
                    best_obj=z; best=(ri,ns)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),))) if best is not None else None

def depot_reassign(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.depot_reassign(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; eD=sc.eD
    for ri,r in enumerate(sol):
        for d in allowed:
            if d==r.depot: continue
            z=eD(ri,d)
            if z is not None and z<best_obj-EPS:
                if trace_wants(z): trace_consider(z,_mat_depot(inst,sol,ri,d))
                best_obj=z; best=(ri,d)
    return (best_obj,_mat_depot(inst,sol,best[0],best[1])) if best is not None else None

def inter_relocate1(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.inter_relocate1(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld; dm=inst.demand; qm=inst.Q+1e-9
    for i,a in enumerate(sol):
        aseq=a.seq; Li=ld[i]
        for ix,c in enumerate(aseq):
            dem=dm[c]
            si=aseq[:ix]+aseq[ix+1:]; li=Li-dem
            for j,b in enumerate(sol):
                if i==j or b.load+dem>qm: continue
                bseq=b.seq; lj=ld[j]+dem
                for pos in range(len(bseq)+1):
                    sj=bseq[:pos]+[c]+bseq[pos:]
                    z=e2(i,si,li,j,sj,lj)
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,si),(j,sj))))
                        best_obj=z; best=(i,si,j,sj)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def _inter_relocate2(inst, sol, K,p,allowed, reverse=False):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref._inter_relocate2(inst,sol,K,p,allowed,reverse)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld; qm=inst.Q+1e-9
    for i,a in enumerate(sol):
        aseq=a.seq; Li=ld[i]
        for ix in range(len(aseq)-1):
            block=aseq[ix:ix+2]
            if reverse: block=list(reversed(block))
            dem=sum(inst.demand[c] for c in block)
            si=aseq[:ix]+aseq[ix+2:]; li=Li-dem
            for j,b in enumerate(sol):
                if i==j or b.load+dem>qm: continue
                bseq=b.seq; lj=ld[j]+dem
                for pos in range(len(bseq)+1):
                    sj=bseq[:pos]+block+bseq[pos:]
                    z=e2(i,si,li,j,sj,lj)
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,si),(j,sj))))
                        best_obj=z; best=(i,si,j,sj)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def inter_relocate2(inst, sol, K,p,allowed): return _inter_relocate2(inst,sol,K,p,allowed,False)
def inter_relocate2_rev(inst, sol, K,p,allowed): return _inter_relocate2(inst,sol,K,p,allowed,True)

def inter_swap11(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.inter_swap11(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld; dm=inst.demand
    for i in range(len(sol)):
        aseq=sol[i].seq; Li=ld[i]
        for j in range(i+1,len(sol)):
            bseq=sol[j].seq; Lj=ld[j]
            for ia,ca in enumerate(aseq):
                for ib,cb in enumerate(bseq):
                    si=aseq.copy(); si[ia]=cb; sj=bseq.copy(); sj[ib]=ca
                    z=e2(i,si,Li-dm[ca]+dm[cb],j,sj,Lj-dm[cb]+dm[ca])
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,si),(j,sj))))
                        best_obj=z; best=(i,si,j,sj)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def inter_swap21(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.inter_swap21(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld; dm=inst.demand
    for i in range(len(sol)):
        aseq=sol[i].seq; Li=ld[i]
        for j in range(len(sol)):
            if i==j: continue
            bseq=sol[j].seq; Lj=ld[j]
            for ia in range(len(aseq)-1):
                pair=aseq[ia:ia+2]; dp=dm[pair[0]]+dm[pair[1]]
                for ib,cb in enumerate(bseq):
                    si=aseq[:ia]+[cb]+aseq[ia+2:]
                    sj=bseq[:ib]+pair+bseq[ib+1:]
                    z=e2(i,si,Li-dp+dm[cb],j,sj,Lj-dm[cb]+dp)
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,si),(j,sj))))
                        best_obj=z; best=(i,si,j,sj)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def _inter_swap22(inst, sol, K,p,allowed, reverse=False):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref._inter_swap22(inst,sol,K,p,allowed,reverse)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld; dm=inst.demand
    for i in range(len(sol)):
        aseq=sol[i].seq; Li=ld[i]
        for j in range(i+1,len(sol)):
            bseq=sol[j].seq; Lj=ld[j]
            for ia in range(len(aseq)-1):
                pa=aseq[ia:ia+2]; dpa=dm[pa[0]]+dm[pa[1]]
                for ib in range(len(bseq)-1):
                    pb=bseq[ib:ib+2]; dpb=dm[pb[0]]+dm[pb[1]]
                    x=list(reversed(pb)) if reverse else pb
                    y=list(reversed(pa)) if reverse else pa
                    si=aseq[:ia]+x+aseq[ia+2:]
                    sj=bseq[:ib]+y+bseq[ib+2:]
                    z=e2(i,si,Li-dpa+dpb,j,sj,Lj-dpb+dpa)
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,si),(j,sj))))
                        best_obj=z; best=(i,si,j,sj)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def inter_swap22(inst, sol, K,p,allowed): return _inter_swap22(inst,sol,K,p,allowed,False)
def inter_swap22_rev(inst, sol, K,p,allowed): return _inter_swap22(inst,sol,K,p,allowed,True)

def two_opt_star(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.two_opt_star(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld
    for i in range(len(sol)):
        aseq=sol[i].seq; Li=ld[i]; la_=len(aseq); pre_a=sc.prefix_loads(i)
        for j in range(i+1,len(sol)):
            bseq=sol[j].seq; Lj=ld[j]; lb_=len(bseq); pre_b=sc.prefix_loads(j)
            for ca in range(la_+1):
                for cb in range(lb_+1):
                    if ca==la_ and cb==lb_: continue
                    na=aseq[:ca]+bseq[cb:]
                    nb=bseq[:cb]+aseq[ca:]
                    if na==aseq and nb==bseq: continue
                    z=e2(i,na,pre_a[ca]+(Lj-pre_b[cb]),j,nb,pre_b[cb]+(Li-pre_a[ca]))
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,na),(j,nb))))
                        best_obj=z; best=(i,na,j,nb)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def two_opt_star_rev(inst, sol, K,p,allowed):
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.two_opt_star_rev(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; e2=sc.e2; ld=sc.ld
    for i in range(len(sol)):
        aseq=sol[i].seq; Li=ld[i]; la_=len(aseq); pre_a=sc.prefix_loads(i)
        for j in range(i+1,len(sol)):
            bseq=sol[j].seq; Lj=ld[j]; lb_=len(bseq); pre_b=sc.prefix_loads(j)
            for ca in range(la_+1):
                for cb in range(lb_+1):
                    ta=list(reversed(aseq[ca:])); tb=list(reversed(bseq[cb:]))
                    na=aseq[:ca]+tb; nb=bseq[:cb]+ta
                    if na==aseq and nb==bseq: continue
                    z=e2(i,na,pre_a[ca]+(Lj-pre_b[cb]),j,nb,pre_b[cb]+(Li-pre_a[ca]))
                    if z is not None and z<best_obj-EPS:
                        if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,na),(j,nb))))
                        best_obj=z; best=(i,na,j,nb)
    return (best_obj,_mat(inst,sol,((best[0],best[1]),(best[2],best[3])))) if best is not None else None

def route_split(inst, sol, K,p,allowed):
    if len(sol)>=K: return None
    sc=make_scan(inst,sol,K,p)
    if sc is None: return _ref.route_split(inst,sol,K,p,allowed)
    best_obj=objective(inst,sol); best=None; eS=sc.eS; ld=sc.ld
    for i,r in enumerate(sol):
        seq=r.seq
        if len(seq)<2: continue
        Li=ld[i]; pre=sc.prefix_loads(i)
        for cut in range(1,len(seq)):
            left=seq[:cut]; right=seq[cut:]; ll=pre[cut]; lr=Li-ll
            for d2 in allowed:
                z=eS(i,left,ll,right,lr,d2)
                if z is not None and z<best_obj-EPS:
                    if trace_wants(z): trace_consider(z,_mat(inst,sol,((i,left),),Route(d2,right,0.0)))
                    best_obj=z; best=(i,left,right,d2)
    if best is None: return None
    return best_obj,_mat(inst,sol,((best[0],best[1]),),Route(best[3],best[2],0.0))

NEIGHBORHOODS: Dict[str,Callable] = {
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
# Coordinated depot operators (opt-in; not part of the frozen presets Core-5 / Ext-15 / baseline_route).
NEIGHBORHOODS.update(_dep.DEPOT_NEIGHBORHOODS)
_dep.set_polish_ops([NEIGHBORHOODS[x] for x in _dep.POLISH_NAMES])

# LLRP_REFERENCE_OPS=1: every operator (and local_search.first_descent) runs the full-recomputation reference code.
_FORCE_REFERENCE=os.environ.get('LLRP_REFERENCE_OPS')=='1'

PRESETS = {
    # Native local improvement of GRASP / ILS / VNS / MSLS / GRASP+PR / Scatter in Phase A.
    # It is run with local_search='first' (local_search.first_descent: the first feasible
    # improving move in deterministic enumeration order, no depot move). This is
    # deliberately not VND; the common VND of Phase B is the 'common5' preset below.
    'baseline_route': [
        'intra_relocate1','inter_relocate1','intra_swap11','inter_swap11','intra_2opt'
    ],
    # Frozen common VND for the second experimental phase. Keep this exact
    # order in both LLRP and LLRP so that the intensification layer is identical.
    'common5': [
        'intra_relocate1','intra_2opt','inter_relocate1','inter_swap11','depot_reassign'
    ],
    'light': [
        'intra_relocate1','intra_2opt','depot_reassign','inter_relocate1','inter_swap11'
    ],
    # HGAMP-inspired: same move families visible in HGAMP LS.cpp, but all move
    # evaluations are recomputed under the LLRP latency objective.
    'hgamp': [
        'intra_relocate1','intra_relocate2','inter_relocate1','inter_relocate2',
        'inter_relocate2_rev','intra_swap11','inter_swap11','inter_swap21',
        'inter_swap22','inter_swap22_rev','intra_2opt','two_opt_star',
        'two_opt_star_rev','depot_reassign','route_split'
    ],
    # clean.6.2, opt-in: Loffler-aligned set. The operators of the VND of Loffler, Bartolini, Schneider (2023, EJCO 11:100063, Table 1)
    # that exist in this framework, in the relative order of that table (Relocate-1, Exchange-1, Relocate-2, Exchange-2, Split-b/f,
    # 2-Opt*); it is meant for the first-improvement driver (local_search='first'), as in that paper. Not Loffler's VND: no Split-1/2,
    # Relocate-b/f, Exchange-b, feasible candidates only. No intra-route 2-opt and no depot move, as in that table.
    'loffler9': [
        'intra_relocate1','inter_relocate1','intra_swap11','inter_swap11','intra_relocate2','inter_relocate2',
        'inter_swap22','route_split','two_opt_star'
    ],
    # clean.6.0, opt-in: the frozen presets plus the coordinated depot operators of depot_ops.py
    'common5_depot': [
        'intra_relocate1','intra_2opt','inter_relocate1','inter_swap11','depot_reassign',
        'depot_close','depot_move_all','depot_open'
    ],
    'hgamp_depot': [
        'intra_relocate1','intra_relocate2','inter_relocate1','inter_relocate2',
        'inter_relocate2_rev','intra_swap11','inter_swap11','inter_swap21',
        'inter_swap22','inter_swap22_rev','intra_2opt','two_opt_star',
        'two_opt_star_rev','depot_reassign','route_split',
        'depot_close','depot_move_all','depot_open'
    ],
}
