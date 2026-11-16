from __future__ import annotations
import random, time
from . import core as _core
from .core import objective, clone_solution, trace_consider, Route
from .neighborhoods import NEIGHBORHOODS, PRESETS, ScanTimeout, set_scan_deadline, make_scan, _mat, _mat_depot
from . import reference_ops as _ref

_perf=time.perf_counter

EPS=1e-10


def _names(preset_or_csv):
    if preset_or_csv in PRESETS:
        return PRESETS[preset_or_csv].copy()
    names=[x.strip() for x in preset_or_csv.split(',') if x.strip()]
    bad=[x for x in names if x not in NEIGHBORHOODS]
    if bad: raise ValueError(f'Unknown neighborhoods: {bad}')
    return names


def vnd(inst, sol, K,p,allowed, neighborhoods='light', deadline=None):
    names=_names(neighborhoods); cur=clone_solution(sol); z=objective(inst,cur); trace_consider(z,cur); k=0; moves=0
    set_scan_deadline(deadline)
    try:
        while k<len(names):
            if deadline and time.perf_counter()>=deadline: break
            res=NEIGHBORHOODS[names[k]](inst,cur,K,p,allowed)
            if res is not None and res[0] < z-EPS:
                z,cur=res; trace_consider(z,cur); moves+=1; k=0
            else:
                k+=1
    except ScanTimeout:
        pass
    finally:
        set_scan_deadline(None)
    return cur,z,moves


def rvnd(inst, sol, K,p,allowed, neighborhoods='hgamp', rng=None, deadline=None):
    rng=rng or random.Random(0); base_names=_names(neighborhoods)
    cur=clone_solution(sol); z=objective(inst,cur); trace_consider(z,cur); active=base_names.copy(); rng.shuffle(active); moves=0
    set_scan_deadline(deadline)
    try:
        while active:
            if deadline and time.perf_counter()>=deadline: break
            idx=rng.randrange(len(active)); name=active[idx]
            res=NEIGHBORHOODS[name](inst,cur,K,p,allowed)
            if res is not None and res[0] < z-EPS:
                z,cur=res; trace_consider(z,cur); moves+=1; active=base_names.copy(); rng.shuffle(active)
            else:
                active.pop(idx)
    except ScanTimeout:
        pass
    finally:
        set_scan_deadline(None)
    return cur,z,moves


def best_descent(inst, sol, K,p,allowed, neighborhoods='hgamp', deadline=None):
    names=_names(neighborhoods); cur=clone_solution(sol); z=objective(inst,cur); trace_consider(z,cur); moves=0
    set_scan_deadline(deadline)
    try:
        while True:
            if deadline and time.perf_counter()>=deadline: break
            best=None
            for name in names:
                if deadline and time.perf_counter()>=deadline: break
                res=NEIGHBORHOODS[name](inst,cur,K,p,allowed)
                if res is not None and (best is None or res[0]<best[0]-EPS): best=res
            if best is None or best[0]>=z-EPS: break
            z,cur=best; trace_consider(z,cur); moves+=1
    except ScanTimeout:
        pass
    finally:
        set_scan_deadline(None)
    return cur,z,moves


_FIRST_OPS=('intra_relocate1','inter_relocate1','intra_swap11','inter_swap11','intra_2opt','depot_reassign',
           'intra_relocate2','inter_relocate2','inter_swap22','two_opt_star','route_split')   # the last five: clean.6.2, preset loffler9


def _first_improving_move(name, inst, sol, K,p,allowed,z,deadline=None):
    """Return the first feasible improving move in deterministic enumeration order.

    This routine intentionally differs from neighborhoods.py, whose operators scan a
    whole neighborhood and return its best improving move.  Phase-A native local
    improvement uses this routine to reproduce a lightweight first-improvement descent
    without invoking the common Phase-B VND module.

    Candidates are evaluated with the delta layer of neighborhoods.Scan (only the touched routes are recomputed);
    reference_ops.first_improving_move is the full-recomputation specification and the fallback. Both return
    (normalised candidate, objective) of the same move.
    """
    if name not in _FIRST_OPS:
        raise ValueError(f"first-improvement is not implemented for neighborhood '{name}'")
    sc=make_scan(inst,sol,K,p)
    if sc is None:
        return _ref.first_improving_move(name,inst,sol,K,p,allowed,z,deadline)
    lim=z-EPS

    if name=='intra_relocate1':
        e1=sc.e1
        for ri,r in enumerate(sol):
            seq=r.seq; n=len(seq)
            for i in range(n):
                c=seq[i]; base=seq[:i]+seq[i+1:]
                for j in range(len(base)+1):
                    if deadline is not None and _perf()>=deadline: return None
                    ns=base[:j]+[c]+base[j:]
                    if ns==seq: continue
                    z2=e1(ri,ns)
                    if z2 is not None and z2<lim: return _mat(inst,sol,((ri,ns),)),z2
        return None

    if name=='inter_relocate1':
        e2=sc.e2; ld=sc.ld; dm=inst.demand; qm=inst.Q+1e-9
        for i,a in enumerate(sol):
            aseq=a.seq; Li=ld[i]
            for ix,c in enumerate(aseq):
                dem=dm[c]
                si=aseq[:ix]+aseq[ix+1:]; li=Li-dem
                for j,b in enumerate(sol):
                    if i==j or b.load+dem>qm: continue
                    bseq=b.seq; lj=ld[j]+dem
                    for pos in range(len(bseq)+1):
                        if deadline is not None and _perf()>=deadline: return None
                        sj=bseq[:pos]+[c]+bseq[pos:]
                        z2=e2(i,si,li,j,sj,lj)
                        if z2 is not None and z2<lim: return _mat(inst,sol,((i,si),(j,sj))),z2
        return None

    if name=='intra_swap11':
        e1=sc.e1
        for ri,r in enumerate(sol):
            seq=r.seq
            for i in range(len(seq)):
                for j in range(i+1,len(seq)):
                    if deadline is not None and _perf()>=deadline: return None
                    ns=seq.copy(); ns[i],ns[j]=ns[j],ns[i]
                    z2=e1(ri,ns)
                    if z2 is not None and z2<lim: return _mat(inst,sol,((ri,ns),)),z2
        return None

    if name=='inter_swap11':
        e2=sc.e2; ld=sc.ld; dm=inst.demand
        for i in range(len(sol)):
            aseq=sol[i].seq; Li=ld[i]
            for j in range(i+1,len(sol)):
                bseq=sol[j].seq; Lj=ld[j]
                for ia in range(len(aseq)):
                    ca=aseq[ia]
                    for ib in range(len(bseq)):
                        if deadline is not None and _perf()>=deadline: return None
                        cb=bseq[ib]
                        si=aseq.copy(); si[ia]=cb; sj=bseq.copy(); sj[ib]=ca
                        z2=e2(i,si,Li-dm[ca]+dm[cb],j,sj,Lj-dm[cb]+dm[ca])
                        if z2 is not None and z2<lim: return _mat(inst,sol,((i,si),(j,sj))),z2
        return None

    if name=='intra_2opt':
        e1=sc.e1
        for ri,r in enumerate(sol):
            seq=r.seq; n=len(seq)
            for i in range(n-1):
                for j in range(i+1,n):
                    if deadline is not None and _perf()>=deadline: return None
                    ns=seq[:i]+list(reversed(seq[i:j+1]))+seq[j+1:]
                    if ns==seq: continue
                    z2=e1(ri,ns)
                    if z2 is not None and z2<lim: return _mat(inst,sol,((ri,ns),)),z2
        return None

    if name=='intra_relocate2':
        e1=sc.e1
        for ri,r in enumerate(sol):
            seq=r.seq; n=len(seq)
            for i in range(n-1):
                block=seq[i:i+2]; rem=seq[:i]+seq[i+2:]
                for j in range(len(rem)+1):
                    if deadline is not None and _perf()>=deadline: return None
                    ns=rem[:j]+block+rem[j:]
                    if ns==seq: continue
                    z2=e1(ri,ns)
                    if z2 is not None and z2<lim: return _mat(inst,sol,((ri,ns),)),z2
        return None

    if name=='inter_relocate2':
        e2=sc.e2; ld=sc.ld; qm=inst.Q+1e-9
        for i,a in enumerate(sol):
            aseq=a.seq; Li=ld[i]
            for ix in range(len(aseq)-1):
                block=aseq[ix:ix+2]
                dem=sum(inst.demand[c] for c in block)
                si=aseq[:ix]+aseq[ix+2:]; li=Li-dem
                for j,b in enumerate(sol):
                    if i==j or b.load+dem>qm: continue
                    bseq=b.seq; lj=ld[j]+dem
                    for pos in range(len(bseq)+1):
                        if deadline is not None and _perf()>=deadline: return None
                        sj=bseq[:pos]+block+bseq[pos:]
                        z2=e2(i,si,li,j,sj,lj)
                        if z2 is not None and z2<lim: return _mat(inst,sol,((i,si),(j,sj))),z2
        return None

    if name=='inter_swap22':
        e2=sc.e2; ld=sc.ld; dm=inst.demand
        for i in range(len(sol)):
            aseq=sol[i].seq; Li=ld[i]
            for j in range(i+1,len(sol)):
                bseq=sol[j].seq; Lj=ld[j]
                for ia in range(len(aseq)-1):
                    pa=aseq[ia:ia+2]; dpa=dm[pa[0]]+dm[pa[1]]
                    for ib in range(len(bseq)-1):
                        if deadline is not None and _perf()>=deadline: return None
                        pb=bseq[ib:ib+2]; dpb=dm[pb[0]]+dm[pb[1]]
                        si=aseq[:ia]+pb+aseq[ia+2:]
                        sj=bseq[:ib]+pa+bseq[ib+2:]
                        z2=e2(i,si,Li-dpa+dpb,j,sj,Lj-dpb+dpa)
                        if z2 is not None and z2<lim: return _mat(inst,sol,((i,si),(j,sj))),z2
        return None

    if name=='two_opt_star':
        e2=sc.e2; ld=sc.ld
        for i in range(len(sol)):
            aseq=sol[i].seq; Li=ld[i]; la_=len(aseq); pre_a=sc.prefix_loads(i)
            for j in range(i+1,len(sol)):
                bseq=sol[j].seq; Lj=ld[j]; lb_=len(bseq); pre_b=sc.prefix_loads(j)
                for ca in range(la_+1):
                    for cb in range(lb_+1):
                        if ca==la_ and cb==lb_: continue
                        if deadline is not None and _perf()>=deadline: return None
                        na=aseq[:ca]+bseq[cb:]
                        nb=bseq[:cb]+aseq[ca:]
                        if na==aseq and nb==bseq: continue
                        z2=e2(i,na,pre_a[ca]+(Lj-pre_b[cb]),j,nb,pre_b[cb]+(Li-pre_a[ca]))
                        if z2 is not None and z2<lim: return _mat(inst,sol,((i,na),(j,nb))),z2
        return None

    if name=='route_split':
        if len(sol)>=K: return None
        eS=sc.eS; ld=sc.ld
        for i,r in enumerate(sol):
            seq=r.seq
            if len(seq)<2: continue
            Li=ld[i]; pre=sc.prefix_loads(i)
            for cut in range(1,len(seq)):
                left=seq[:cut]; right=seq[cut:]; ll=pre[cut]; lr=Li-ll
                for d2 in allowed:
                    if deadline is not None and _perf()>=deadline: return None
                    z2=eS(i,left,ll,right,lr,d2)
                    if z2 is not None and z2<lim: return _mat(inst,sol,((i,left),),Route(d2,right,0.0)),z2
        return None

    # depot_reassign
    eD=sc.eD
    for ri,r in enumerate(sol):
        for d in allowed:
            if deadline is not None and _perf()>=deadline: return None
            if d==r.depot: continue
            z2=eD(ri,d)
            if z2 is not None and z2<lim: return _mat_depot(inst,sol,ri,d),z2
    return None


def first_descent(inst, sol, K,p,allowed, neighborhoods='baseline_route', deadline=None):
    names=_names(neighborhoods); cur=clone_solution(sol); z=objective(inst,cur); trace_consider(z,cur); moves=0
    while True:
        if deadline and time.perf_counter()>=deadline: break
        improved=False
        for name in names:
            if deadline and time.perf_counter()>=deadline: break
            res=_first_improving_move(name,inst,cur,K,p,allowed,z,deadline)
            if res is not None:
                cur,z=res; trace_consider(z,cur); moves+=1; improved=True
                break
        if not improved: break
    return cur,z,moves


def run_local_search(method, inst, sol, K,p,allowed, preset, rng, deadline=None):
    # The original 6.2 routing LS remains unchanged. Depot intervention is
    # entirely opt-in and only enabled for the first/loffler9 campaign.
    if method=='vnd': out=vnd(inst,sol,K,p,allowed,preset,deadline)
    elif method=='rvnd': out=rvnd(inst,sol,K,p,allowed,preset,rng,deadline)
    elif method=='best': out=best_descent(inst,sol,K,p,allowed,preset,deadline)
    elif method=='first': out=first_descent(inst,sol,K,p,allowed,preset,deadline)
    elif method=='none':
        z=objective(inst,sol); trace_consider(z,sol); out=(sol,z,0)
    else: raise ValueError(method)
    if method=='first' and preset=='loffler9':
        from .depot_impact import maybe
        s,z,mv=out
        # A following kick is optimized by the *same* deterministic first descent.
        nxt,nz,extra=maybe(inst,s,z,K,p,allowed,rng,deadline,
                           lambda i,c,k,pp,a,d: first_descent(i,c,k,pp,a,'loffler9',d))
        out=(nxt,nz,mv+extra)
    h=_core._POOL_HOOK[0]
    if h is not None: h(out[0],out[1])           # route pool of the set-partitioning polish (--sp-share); None otherwise
    return out
