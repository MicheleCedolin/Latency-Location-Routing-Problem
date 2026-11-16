"""Budget-aware depot perturbations around the *unchanged* loffler9 descent (LLRP port of the CLRP clean.6.3 / 6.3.1 / 6.4.0 layer).

Opt-in, applied across all heuristics from the shared run_local_search boundary.
Kicks may worsen objective temporarily, but never replace the LS result unless
subsequent routing improvement yields a strictly lower feasible objective.
One call = one independent Python solver process. Counters are reset per seed.
"""
from __future__ import annotations
import random
import sys
import time
from .core import Route, clone_solution, feasible, normalize, objective, used_depots, depot_loads
from . import depot_ops as dep
from .neighborhoods import NEIGHBORHOODS, ScanTimeout, set_scan_deadline

EPS=1e-9
S={}
_THIS=sys.modules[__name__]     # this very module object (the adaptive layer receives it explicitly)
KINDS=('reassign','close','open','move_all')


def configure(mode='off', budget=None, seed=1, every=8, max_share=0.10,
              event_seconds=1.5, min_interval=2.0, first_frac=0.05, period_frac=0.06,
              exploit_start=0.30, exploit_slice=0.04, cap_exp=3.0):
    """The last five parameters act only in mode 'adaptive' (clean.6.4.0); the other modes ignore them."""
    if mode not in ('off','balanced','structural','adaptive'):
        raise ValueError('depot-impact must be off, balanced, structural or adaptive')
    if every<1 or not (0<max_share<=1) or event_seconds<=0 or min_interval<0:
        raise ValueError('Invalid depot impact scheduling parameters')
    if not (0<=first_frac<1) or period_frac<=0 or exploit_start<=0 or not (0<exploit_slice<=1) or cap_exp<0:
        raise ValueError('Invalid adaptive depot impact parameters')
    S.clear()
    S.update(mode=mode, start=time.perf_counter(), budget=budget, seed=seed, calls=0,
             every=every, max_share=max_share, event_seconds=event_seconds,
             min_interval=min_interval, last_event=-1e30, events=0,
             candidates=0, accepted=0, accepted_set=0, seconds=0.0,
             reassignment=0, reassign=0, close=0, open=0, move_all=0,
             accepted_reassignment=0, accepted_reassign=0, accepted_close=0, accepted_open=0, accepted_move_all=0,
             elites={}, struct_attempts=0, struct_rebuilds=0, struct_accepted=0,
             struct_accepted_swap=0, struct_accepted_swap2=0, struct_accepted_open=0, struct_three_depots_seen=0,
             struct_min_depots_seen=0, struct_candidates_polished=0,
             first_frac=first_frac, period_frac=period_frac, exploit_start=exploit_start,
             exploit_slice=exploit_slice, cap_exp=cap_exp,
             adapt_since_explore=0, adapt_stall=0, adapt_explore=0, adapt_exploit=0, adapt_exploit_iters=0, adapt_exploit_improved=0,
             adapt_exploit_seconds=0.0, adapt_first_event_s=-1.0, adapt_last_cap_s=0.0, tried=set(),
             rng=random.Random(int(seed)*7919+13))   # layer-private stream: adaptive events never touch the host's RNG


def stats():
    out={f'depot_{k}': S.get(k,0) for k in (
        'calls','events','candidates','accepted','accepted_set','seconds',
        'reassignment','reassign','close','open','move_all',
        'accepted_reassignment','accepted_reassign','accepted_close','accepted_open','accepted_move_all',
        'struct_attempts','struct_rebuilds','struct_accepted','struct_accepted_swap',
        'struct_accepted_swap2','struct_accepted_open','struct_three_depots_seen','struct_min_depots_seen',
        'struct_candidates_polished','elite_sets')}
    if S.get('mode')=='adaptive':            # extra columns exist only in adaptive reports (collect.py unions the columns)
        out.update({f'depot_{k}': S.get(k,0) for k in (
            'adapt_explore','adapt_exploit','adapt_exploit_iters','adapt_exploit_improved',
            'adapt_exploit_seconds','adapt_first_event_s','adapt_last_cap_s')})
        out['depot_adapt_tried_sets']=len(S.get('tried',()))
    return out


def _reassign(inst, sol, allowed, rng):
    """Randomized route-to-depot move; allows a new depot, and an uphill move."""
    if not sol: return None
    loads=depot_loads(inst,sol)
    routes=list(range(len(sol)))
    rng.shuffle(routes)
    for ri in routes:
        r=sol[ri]
        choices=[d for d in allowed if d!=r.depot and loads[d]+r.load<=inst.depot_cap[d]+1e-9]
        if not choices: continue
        # Favor geographical proximity sometimes, random diversification otherwise.
        choices.sort(key=lambda d:(inst.ddc[d][r.seq[0]] + inst.ddc[d][r.seq[-1]],d))
        chosen=choices[0] if rng.random()<0.5 else rng.choice(choices)
        cand=clone_solution(sol);cand[ri].depot=chosen
        return cand
    return None


def _move_all(inst, sol, allowed, rng):
    """Relocate all routes of one open depot as one joint move."""
    if not sol:return None
    used=list(used_depots(sol));rng.shuffle(used)
    loads=depot_loads(inst,sol)
    for old in used:
        targets=[d for d in allowed if d!=old and loads[d]+loads[old]<=inst.depot_cap[d]+1e-9]
        if not targets:continue
        # Prefer an unused target half of the time (real location change).
        unused=[d for d in targets if d not in used]
        new=rng.choice(unused if unused and rng.random()<0.65 else targets)
        cand=clone_solution(sol)
        for r in cand:
            if r.depot==old:r.depot=new
        return cand
    return None


def _close(inst,sol,K,allowed,rng,deadline=None):
    """Close a depot with cheapest reinsertions; can require an uphill route step."""
    used=list(used_depots(sol))
    if len(used)<2:return None
    rng.shuffle(used)
    for old in used:
        targets=[d for d in used if d!=old and d in allowed]
        keep=dep._clone_routes(inst,sol,skip=lambda r:r.depot==old)
        rem=[c for r in sol if r.depot==old for c in r.seq]
        # Keep existing 6.2 depot_ops reconstruction rule.
        rem.sort(key=lambda c:(-inst.demand[c],c))
        cand=dep._insert_all(inst,K,keep,rem,targets,deadline=deadline)
        if cand is not None:return cand
    return None


def _open(inst,sol,K,allowed,rng,deadline=None):
    """Seed a closed depot with a geographically proximal customer cluster."""
    used=used_depots(sol)
    closed=[d for d in allowed if d not in used]
    if not closed:return None
    rng.shuffle(closed)
    for new in closed:
        capacity=min(inst.Q,inst.depot_cap[new])
        order=sorted(range(inst.n),key=lambda c:(inst.ddc[new][c],c))
        selected=[];load=0.0
        for c in order:
            if load+inst.demand[c]<=capacity+1e-9:
                selected.append(c);load+=inst.demand[c]
            if load>=0.80*capacity:break
        if not selected:continue
        selected_set=set(selected);keep=[]
        for r in sol:
            seq=[c for c in r.seq if c not in selected_set]
            if seq:keep.append(Route(r.depot,seq,sum(inst.demand[c] for c in seq)))
        # Directly restrict new cluster to newly opened depot.
        cand=dep._insert_all(inst,K,keep,selected,[new],only_depot=new,deadline=deadline)
        if cand is not None and new in used_depots(cand):return cand
    return None


def _kick(kind,inst,sol,K,allowed,rng,deadline=None):
    if kind=='reassign':return _reassign(inst,sol,allowed,rng)
    if kind=='close':return _close(inst,sol,K,allowed,rng,deadline)
    if kind=='open':return _open(inst,sol,K,allowed,rng,deadline)
    return _move_all(inst,sol,allowed,rng)


def maybe(inst, sol, z, K, p, allowed, rng, deadline, polish):
    """Optional event after regular loffler9. `polish` is the original first_descent.

    Total depot impact work capped by a share of the per-run budget, individual
    events by event_seconds, and all work by the solver deadline. Only strictly
    improving feasible proposals are returned (base search is never degraded).
    """
    if S.get('mode')=='structural':
        return _structural_maybe(inst,sol,z,K,p,allowed,rng,deadline,polish)
    if S.get('mode')=='adaptive':
        from .depot_adaptive64 import adaptive_maybe
        return adaptive_maybe(_THIS,inst,sol,z,K,p,allowed,rng,deadline,polish)
    if S.get('mode')!='balanced' or not sol:return sol,z,0
    S['calls']+=1
    if S['calls']%S['every']:return sol,z,0
    now=time.perf_counter()
    if now-S['last_event']<S['min_interval']:return sol,z,0
    budget=S['budget']
    remaining_share= (budget*S['max_share']-S['seconds']) if budget is not None else S['event_seconds']
    if remaining_share<=0.05:return sol,z,0
    event_end=min(now+S['event_seconds'],now+remaining_share)
    if deadline is not None:event_end=min(event_end,deadline-0.02)
    if event_end-now<0.05:return sol,z,0
    S['events']+=1;S['last_event']=now
    start=now;best=sol;bestz=z;ls_moves=0;origin=set(used_depots(sol))
    try:
        # Cheap improving move: route-to-depot reassignment (uses 6.2 delta code).
        if time.perf_counter()<event_end:
            set_scan_deadline(event_end)
            try:
                res=NEIGHBORHOODS['depot_reassign'](inst,sol,K,p,allowed)
            except ScanTimeout:
                res=None
            finally:
                set_scan_deadline(None)
            if res is not None:
                candidate=normalize(inst,res[1])
                if feasible(inst,candidate,K,p):
                    S['candidates']+=1;S['reassignment']+=1
                    if time.perf_counter()<event_end:
                        candidate,cost,mv=polish(inst,candidate,K,p,allowed,event_end)
                        ls_moves+=mv
                    else:
                        cost=objective(inst,candidate)
                    if cost<bestz-EPS:
                        best,bestz=candidate,cost
                        S['accepted']+=1;S['accepted_reassignment']+=1
                        if set(used_depots(candidate))!=origin:S['accepted_set']+=1

        # Two rotating structural kicks: can cross uphill depot configurations.
        offset=S['events']-1
        for j in range(2):
            if time.perf_counter()>=event_end:break
            kind=KINDS[(offset*2+j)%len(KINDS)]
            S[kind]+=1
            candidate=_kick(kind,inst,sol,K,allowed,rng,event_end)
            if candidate is None:continue
            candidate=normalize(inst,candidate)
            if not feasible(inst,candidate,K,p):
                raise RuntimeError(f'depot {kind} generated an infeasible candidate')
            S['candidates']+=1
            # Routing is reoptimized after any depot move before judgment.
            if time.perf_counter()<event_end:
                candidate,cost,mv=polish(inst,candidate,K,p,allowed,event_end)
                ls_moves+=mv
            else:
                cost=objective(inst,candidate)
            if cost<bestz-EPS:
                best,bestz=candidate,cost
                S['accepted']+=1;S['accepted_'+kind]+=1
                if set(used_depots(candidate))!=origin:S['accepted_set']+=1
    finally:
        S['seconds']+=time.perf_counter()-start
    if not feasible(inst,best,K,p):
        raise RuntimeError('depot impact returned infeasible solution')
    return best,bestz,ls_moves


# -- clean.6.3.1 structural depot-set reconstruction (the BALANCED path above
#    stays byte-for-byte unchanged apart from its mode dispatch). --
def _elite_register(sol, z):
    if not sol:return
    key=tuple(sorted(used_depots(sol)))
    e=S['elites']; prev=e.get(key)
    if prev is None or z<prev[0]-EPS:
        e[key]=(float(z),clone_solution(sol))
        if len(e)>8:
            # Retain a small diverse list of the cheapest depot configurations.
            worst=max(e,key=lambda k:e[k][0])
            del e[worst]
    S['elite_sets']=len(e)
    S['struct_min_depots_seen']=(min(S['struct_min_depots_seen'],len(key)) if S['struct_min_depots_seen'] else len(key))
    if len(key)<=3:S['struct_three_depots_seen']+=1


def _structural_maybe(inst,sol,z,K,p,allowed,rng,deadline,polish):
    from .depot_structural631 import diversify
    if not sol:return sol,z,0
    _elite_register(sol,z)
    S['calls']+=1
    if S['calls']%S['every']:return sol,z,0
    now=time.perf_counter()
    if now-S['last_event']<S['min_interval']:return sol,z,0
    budget=S['budget']
    remaining_share=(budget*S['max_share']-S['seconds']) if budget is not None else S['event_seconds']
    if remaining_share<=.10:return sol,z,0
    end=min(now+S['event_seconds'],now+remaining_share)
    if deadline is not None:end=min(end,deadline-.03)
    if end-now<=.10:return sol,z,0
    S['events']+=1;S['last_event']=now
    start=now; best=sol;bestz=z;moves=0
    try:
        # Explore current incumbent and, every third event, a different
        # already-improved depot configuration. Same run / same seed only.
        base=sol
        if S['events']%3==0 and len(S['elites'])>1:
            choices=sorted(S['elites'].items(),key=lambda kv:(len(kv[0]),kv[1][0]))
            for key,(_,candidate) in choices:
                if key!=tuple(sorted(used_depots(sol))):
                    base=candidate;break
        # Alternate between depot closing and depot swapping. In either case
        # coordinated route ruin/rebuild can cross initially worse objectives.
        kind=('swap2','open','swap')[(S['events']-1)%3]
        cand,attempts,actual=diversify(inst,base,K,p,allowed,rng,end,preferred=kind)
        S['struct_attempts']+=attempts
        if cand is not None:
            S['struct_rebuilds']+=1;S['candidates']+=1
            S['struct_min_depots_seen']=(min(S['struct_min_depots_seen'],len(used_depots(cand))) if S['struct_min_depots_seen'] else len(used_depots(cand)))
            if len(used_depots(cand))<=3:S['struct_three_depots_seen']+=1
            if time.perf_counter()<end:
                # The original 6.2 loffler9 first-descent and fixed-time cap.
                cand,cz,mv=polish(inst,cand,K,p,sorted(used_depots(cand)),end)
                S['struct_candidates_polished']+=1;moves+=mv
            else:
                cz=objective(inst,cand)
            if not feasible(inst,cand,K,p):
                raise RuntimeError('structural depot perturbation produced infeasible result')
            _elite_register(cand,cz)
            if cz<bestz-EPS:
                best,bestz=cand,cz
                S['accepted']+=1;S['struct_accepted']+=1
                S['struct_accepted_'+actual]+=1
                if used_depots(best)!=used_depots(sol):S['accepted_set']+=1
        S['elite_sets']=len(S['elites'])
    finally:
        S['seconds']+=time.perf_counter()-start
    return best,bestz,moves
