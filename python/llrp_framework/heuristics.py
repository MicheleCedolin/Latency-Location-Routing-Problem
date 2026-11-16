from __future__ import annotations
import heapq, itertools, math, random, time
from collections import deque
from operator import itemgetter
from .core import Route, clone_solution, feasible, normalize, objective, trace_consider, depot_loads, used_depots, arm_reset, arm_best
from .construction import grasp_construct, priority_construct, insertion_delta, new_route_delta, _route_deltas, _new_route_cost, _pack_ok
from .local_search import run_local_search
from .walker import Walker, _QuietScan
from . import core as _core, neighborhoods as _nbm
from .core import fast_eval_ok
from .meta_utils import (flatten_solution, mutate_permutation, ordered_crossover,
                         random_feasible_neighbor, roulette, shake, solution_signature)

EPS=1e-10


def _pmedian_ranking(inst,p):
    """All p-subsets of the depots, ascending by the p-median bound sum_c min_{d in S} d(d,c) (a lower bound on the latency of a solution
    that opens only the depots of S). Values are rounded to 1e-6 before ranking and ties are broken by the combination order, so the ranking is the same with and without numpy (summation order differs at ~1e-13). Cached on the instance."""
    cache=inst.__dict__.setdefault('_pmrank',{})
    r=cache.get(p)
    if r is None:
        combos=list(itertools.combinations(range(inst.m),p))
        try:
            import numpy as np
            D=np.asarray(inst.ddc,dtype=float); idx=np.asarray(combos,dtype=int)
            vals=np.empty(len(combos))
            for a in range(0,len(combos),4096):
                ch=idx[a:a+4096]; vals[a:a+4096]=D[ch].min(axis=1).sum(axis=1)
            order=np.argsort(np.round(vals,6),kind='stable'); r=[combos[i] for i in order]
        except ImportError:
            ddc=inst.ddc
            r=sorted(combos,key=lambda S:round(sum(min(ddc[d][c] for d in S) for c in range(inst.n)),6))
        cache[p]=r
    return r


# ----------------------------------------------------------------------------------------------------------------------------
# Search configuration shared by every subset-loop method (set once per run by configure_search; defaults reproduce v0.4.2).
#   START_MIX  probability that a start solution is built by random-priority insertion (the constructor of the random-key decoders)
#              instead of grasp_construct. grasp_construct opens its K routes at the depot that is cheapest for the next customer,
#              so with a tight fleet it can put every route at one depot of the allowed set and the first-improvement descent with
#              the loffler9 neighbourhoods (no depot move) cannot leave that basin. rng.random() is drawn only when START_MIX > 0,
#              so START_MIX = 0 gives bit-identical runs to the previous versions.
#   RACE_*     parameters of the depot-set race (--depot-mode race: rank-prior exponent, exploration period), see DepotRace.
# ----------------------------------------------------------------------------------------------------------------------------
START_MIX=[0.0]
RACE_GAMMA=[2.0]
RACE_EXPLORE=[8]


def configure_search(start_mix=0.0, race_gamma=2.0, race_explore=8):
    if not 0.0<=float(start_mix)<=1.0: raise ValueError('start_mix must be in [0,1]')
    if float(race_gamma)<0.0 or int(race_explore)<0: raise ValueError('race_gamma >= 0 and race_explore >= 0')
    START_MIX[0]=float(start_mix); RACE_GAMMA[0]=float(race_gamma); RACE_EXPLORE[0]=int(race_explore)


def _start(inst,K,depots,rng,alpha):
    q=START_MIX[0]
    if q>0.0 and rng.random()<q:
        perm=list(range(inst.n)); rng.shuffle(perm)
        s=priority_construct(inst,K,depots,perm,rng)
        if s is not None: return s
    return grasp_construct(inst,K,depots,rng,alpha)


class DepotRace:
    """Prior-weighted budget allocation over the depot sets of the p-median ranking (--depot-mode race).

    The arms are the `sample` best depot sets of the p-median bound, in rank order. The best-known depot set of the 72 benchmark instances
    has p-median rank 1 for 53 instances (74 %), rank <= 5 for 69 (96 %) and rank 26 for one (reference/pmedian_rank_of_published_depot_sets.csv).
    A pull is one block of the host method (construction, local search, its improvement phase) on one arm. A single block is a noisy
    measurement (ILS blocks on n = 100 range from 7 % to 12 % above the best-known value while 39 blocks on the right arm reach 2 %), so
    the allocation is driven by the rank prior and corrected only mildly by the evidence:

        weight(arm) = rank_prior(r) * exp(-lambda * excess(arm)),   rank_prior(r) = 1 / (r + 1)**gamma
        excess(arm) = relative distance of the best objective found on the arm to the best objective over all arms (arms with >= 2 pulls)
        next arm    = argmin (pulls + 1) / weight             (stride scheduling: pull counts follow the weights)
        every `explore`-th pull goes to the best-ranked arm that has not been pulled yet, so the tail of the ranking is not lost for good.

    The score of an arm is the smallest objective seen during its pulls (core.arm_best). The rule only decides which depot set the method
    works on next; nothing inside a block changes. One call of the generator = one pass of the host method = `batch` pulls.
    """
    LAMBDA=5.0

    def __init__(self,inst,p,sample,gamma=2.0,explore=8,batch=6):
        self.arms=list(_pmedian_ranking(inst,p)[:max(1,sample)])
        self.rank={S:i for i,S in enumerate(self.arms)}
        self.prior={S:1.0/((i+1)**gamma) for i,S in enumerate(self.arms)}
        self.best={S:float('inf') for S in self.arms}; self.pulls={S:0 for S in self.arms}
        self.explore=int(explore); self.batch=max(1,min(int(batch),len(self.arms))); self.t=0

    def _weight(self,S):
        w=self.prior[S]
        if self.pulls[S]>=2:
            ref=min(self.best.values())
            if ref>0 and ref<float('inf'): w*=math.exp(-self.LAMBDA*max(0.0,(self.best[S]-ref)/ref))
        return w

    def _next(self):
        self.t+=1
        if self.explore>0 and self.t%self.explore==0:
            fresh=[S for S in self.arms if self.pulls[S]==0]
            if fresh: return fresh[0]
        return min(self.arms,key=lambda S:((self.pulls[S]+1)/self._weight(S),self.rank[S]))

    def _pass(self):
        for _ in range(self.batch):
            S=self._next()
            arm_reset()
            yield S
            z=arm_best()
            if z<self.best[S]: self.best[S]=z
            self.pulls[S]+=1

    def round(self):
        race=self
        class _Pass:
            def __iter__(self_): return race._pass()
            def __len__(self_): return race.batch
            def __getitem__(self_,i): return race.arms[i]          # sequence protocol only (scatter indexes the subsets); no feedback
        return _Pass()


def _depot_subsets(inst,p,rng,mode='enumerate',sample=50):
    """The depot sets (tuples of p depots) a solver works through in one pass.
    enumerate: all C(m,p) subsets in random order; sample: `sample` random subsets;
    pmedian: the `sample` subsets with the smallest p-median bound, in random order (the same sets in every pass).
    race: the same arms, scheduled by DepotRace (one round per call; the loop must consume the result with `for`)."""
    if mode=='race':
        race=getattr(rng,'_depot_race',None)
        if race is None:
            race=DepotRace(inst,p,sample,RACE_GAMMA[0],RACE_EXPLORE[0]); rng._depot_race=race
        return race.round()
    if mode=='pmedian':
        top=list(_pmedian_ranking(inst,p)[:max(1,sample)]); rng.shuffle(top); return top
    allc=list(itertools.combinations(range(inst.m),p))
    rng.shuffle(allc)
    if mode=='enumerate' or len(allc)<=sample:
        return allc
    return allc[:sample]


def _deadline(start,time_limit):
    return start+time_limit if time_limit is not None and time_limit>0 else None


def _expired(deadline):
    return deadline is not None and time.perf_counter()>=deadline


def _check_budget(budget_mode,time_limit):
    if budget_mode not in {'fixed_trials','fixed_time'}:
        raise ValueError(budget_mode)
    if budget_mode=='fixed_time' and (time_limit is None or time_limit<=0):
        raise ValueError('fixed_time requires a positive time_limit')


def _finish(best,bestz,trials,ls_moves,start,passes):
    return best,bestz,trials,ls_moves,time.perf_counter()-start,passes


def solve_grasp(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
                depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',**kwargs):
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        dep_sets=_depot_subsets(inst,p,rng,depot_mode,depot_sample); passes+=1
        for depots in dep_sets:
            for _ in range(restarts):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                trials+=1
                s=_start(inst,K,depots,rng,alpha)
                if s is None: continue
                s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                if not feasible(inst,s,K,p): raise RuntimeError('Internal feasibility failure')
                if z<bestz-EPS: bestz=z; best=clone_solution(s)
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def _perturb(inst, sol, K,p,allowed,rng,strength=2):
    return shake(inst,sol,K,p,allowed,rng,strength)


def solve_ils(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
              depot_mode='enumerate',depot_sample=50,ils_iters=25,perturb_strength=2,
              budget_mode='fixed_trials',**kwargs):
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        dep_sets=_depot_subsets(inst,p,rng,depot_mode,depot_sample); passes+=1
        for depots in dep_sets:
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            s=_start(inst,K,depots,rng,alpha)
            if s is None: continue
            trials+=1
            s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            cur,curz=s,z
            if z<bestz-EPS: best,bestz=clone_solution(s),z
            for _ in range(ils_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                cand=_perturb(inst,cur,K,p,depots,rng,perturb_strength)
                if cand is None: continue
                cand,z,mv=run_local_search(ls_method,inst,cand,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                trials+=1
                if z<curz-EPS: cur,curz=cand,z
                if z<bestz-EPS: best,bestz=clone_solution(cand),z
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_vns(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
              depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
              vns_kmax=5,vns_iters=50,**kwargs):
    """Basic/GVNS-style search: shaking of strength k followed by optional VND/RVND."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            s=_start(inst,K,depots,rng,alpha)
            if s is None: continue
            s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            cur,curz=s,z; trials+=1
            if z<bestz-EPS: best,bestz=clone_solution(s),z
            k=1; it=0
            while it<vns_iters:
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                cand=shake(inst,cur,K,p,depots,rng,k)
                if cand is None: k=1+(k%vns_kmax); it+=1; continue
                cand,z,mv=run_local_search(ls_method,inst,cand,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv; trials+=1
                if z<curz-EPS:
                    cur,curz=cand,z; k=1
                else:
                    k=1+(k%vns_kmax)
                if z<bestz-EPS: best,bestz=clone_solution(cand),z
                it+=1
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_sa(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
             depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
             sa_iters=4000,sa_t0_factor=0.08,sa_cooling=0.995,sa_reheat=0.35,**kwargs):
    """Simulated annealing on feasible routing solutions with geometric cooling."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            T0=max(1e-6,sa_t0_factor*max(curz/inst.n,1.0)); T=T0
            noacc=0
            walk=Walker(inst,cur,K,p,depots)       # incremental neighbour sampler: same neighbours and random numbers as random_feasible_neighbor
            for _ in range(sa_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                nb=walk.propose(rng)
                if nb is None: continue
                walk.evaluated(nb); z=nb.z; walk.trace(nb); trials+=1; dz=z-curz
                if dz<=0 or rng.random()<math.exp(-dz/max(T,1e-12)):
                    walk.accept(nb); cur=walk.routes; curz=z; noacc=0
                    if z<bestz-EPS:
                        # Optional intensification only when a new global incumbent appears.
                        if ls_method!='none':
                            cand2,z2,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                            if z2<z: cur,curz=cand2,z2; z=z2; walk.reset(cur)
                        best,bestz=clone_solution(cur),curz
                else:
                    noacc+=1
                T*=sa_cooling
                if T<T0*1e-4 or noacc>500:
                    T=max(T0*sa_reheat,T); noacc=0
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_tabu(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
               depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
               tabu_iters=1200,tabu_tenure=25,tabu_candidates=30,**kwargs):
    """Solution-memory tabu search with aspiration on a randomized feasible candidate set."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            q=deque(maxlen=max(1,tabu_tenure)); tabuset=set(); sig=solution_signature(cur); q.append(sig); tabuset.add(sig)
            walk=Walker(inst,cur,K,p,depots)       # incremental neighbour sampler: same neighbours and random numbers as random_feasible_neighbor
            for _ in range(tabu_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                chosen=None; chosenz=float('inf'); chosensig=None
                seen=set()
                for _c in range(tabu_candidates):
                    nb=walk.propose(rng)
                    if nb is None: continue
                    cs=walk.signature(nb)
                    if cs in seen: continue
                    seen.add(cs); walk.evaluated(nb); z=nb.z; walk.trace(nb); trials+=1
                    if cs in tabuset and z>=bestz-EPS: continue  # aspiration if global best
                    if z<chosenz:
                        chosen,chosenz,chosensig=nb,z,cs
                if chosen is None: break
                walk.accept(chosen); cur,curz=walk.routes,chosenz
                if len(q)==q.maxlen:
                    old=q[0]; tabuset.discard(old)
                q.append(chosensig); tabuset.add(chosensig)
                if curz<bestz-EPS:
                    if ls_method!='none':
                        s2,z2,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                        if z2<curz: cur,curz=s2,z2; walk.reset(cur)
                    best,bestz=clone_solution(cur),curz
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def _random_depots(inst_m, p, rng):
    max_open=max(1,min(int(p),inst_m))
    h=rng.randint(1,max_open)
    return tuple(sorted(rng.sample(range(inst_m),h)))


def _mutate_depots(depots, inst_m, p, rng, rate):
    d=list(depots); max_open=max(1,min(int(p),inst_m))
    if rng.random()<rate:
        outside=[x for x in range(inst_m) if x not in d]
        ops=[]
        if outside and len(d)<max_open: ops.append('add')
        if len(d)>1: ops.append('drop')
        if outside and d: ops.append('swap')
        if ops:
            op=rng.choice(ops)
            if op=='add': d.append(rng.choice(outside))
            elif op=='drop': d.pop(rng.randrange(len(d)))
            else: d[rng.randrange(len(d))]=rng.choice(outside)
    d=sorted(set(d))
    if not d: d=[rng.randrange(inst_m)]
    return tuple(d[:max_open])


def _tournament(pop,rng,k=3):
    cand=rng.sample(pop,min(k,len(pop)))
    return min(cand,key=lambda x:x['z'])


def solve_ga(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
             depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
             ga_pop=30,ga_generations=200,ga_mutation=0.25,ga_elite=2,**kwargs):
    """Route-decoded genetic algorithm. With local_search != none it becomes a memetic GA."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    pop=[]; trials=0; ls_moves=0; generations=0
    attempts=0
    while len(pop)<ga_pop and attempts<ga_pop*20:
        attempts+=1
        dep=_random_depots(inst.m,p,rng)
        s=_start(inst,K,dep,rng,alpha)
        if s is None: continue
        s,z,mv=run_local_search(ls_method,inst,s,K,p,dep,ls_preset,rng,deadline); ls_moves+=mv
        pop.append({'sol':s,'z':z,'dep':tuple(dep),'perm':flatten_solution(s)}); trials+=1
        if _expired(deadline): break
    if not pop:
        return _finish(None,float('inf'),trials,ls_moves,start,generations)
    while True:
        if _expired(deadline): break
        pop.sort(key=lambda x:x['z'])
        if budget_mode=='fixed_trials' and generations>=ga_generations: break
        new=[{'sol':clone_solution(x['sol']),'z':x['z'],'dep':x['dep'],'perm':x['perm'].copy()} for x in pop[:min(ga_elite,len(pop))]]
        while len(new)<ga_pop:
            if _expired(deadline): break
            a=_tournament(pop,rng); b=_tournament(pop,rng)
            perm=ordered_crossover(a['perm'],b['perm'],rng)
            perm=mutate_permutation(perm,rng,ga_mutation)
            dep=a['dep'] if rng.random()<0.5 else b['dep']
            dep=_mutate_depots(dep,inst.m,p,rng,ga_mutation/2)
            s=priority_construct(inst,K,dep,perm,rng)
            if s is None: continue
            s,z,mv=run_local_search(ls_method,inst,s,K,p,dep,ls_preset,rng,deadline); ls_moves+=mv
            new.append({'sol':s,'z':z,'dep':tuple(dep),'perm':flatten_solution(s)}); trials+=1
        if new: pop=new
        generations+=1
    pop.sort(key=lambda x:x['z']); best=pop[0]
    return _finish(clone_solution(best['sol']),best['z'],trials,ls_moves,start,generations)


def _partial_remove(inst, sol, removed):
    rem=set(removed); out=[]
    for r in clone_solution(sol):
        r.seq=[c for c in r.seq if c not in rem]
        if r.seq:
            r.load=sum(inst.demand[c] for c in r.seq); out.append(r)
    return out


def _destroy_random(inst,sol,q,rng):
    allc=flatten_solution(sol); return rng.sample(allc,min(q,len(allc)))


def _destroy_related(inst,sol,q,rng):
    allc=flatten_solution(sol)
    if not allc: return []
    seed=rng.choice(allc); sx,sy=inst.cust[seed]
    ranked=sorted(allc,key=lambda c:(inst.cust[c][0]-sx)**2+(inst.cust[c][1]-sy)**2)
    head=ranked[:max(q,min(len(ranked),2*q))]
    rng.shuffle(head); return head[:q]


def _destroy_worst_scores_ref(inst,sol):
    base=objective(inst,sol); scores=[]
    for c in flatten_solution(sol):
        part=_partial_remove(inst,sol,[c]); scores.append((base-objective(inst,part),c))
    return scores


def _destroy_worst_scores(inst,sol):
    """(objective(sol) - objective(sol without c), c) for every customer c, in flatten_solution order.

    The objective of a solution without one customer only changes in that customer's route, so it is obtained from the per-route
    lengths of neighborhoods.Scan (same arithmetic as core.objective: bit-identical). The effort counters are booked as the full
    evaluations would book them (one objective evaluation for the base and one per customer; their non-empty routes)."""
    if _nbm._FORCE_REFERENCE or not fast_eval_ok(inst) or any(not r.seq for r in sol):
        return _destroy_worst_scores_ref(inst,sol)
    sc=_QuietScan(inst,sol,inst.n,inst.m); base=sc.ov+sum(sc.w)
    scores=[]; nr=sc.R; ctr=_core._CTR; nc=0; e1=sc.e1; eR=sc.eR
    for i,r in enumerate(sol):
        seq=r.seq
        for k,c in enumerate(seq):
            ns=seq[:k]+seq[k+1:]
            scores.append((base-(e1(i,ns) if ns else eR(i)),c))
            nr+=sc.R if ns else sc.R-1
            nc+=1
    ctr[0]+=1+nc; ctr[1]+=nr
    return scores


def _destroy_worst(inst,sol,q,rng):
    scores=_destroy_worst_scores(inst,sol)
    scores.sort(reverse=True)
    pool=[c for _,c in scores[:max(q,min(len(scores),2*q))]]
    # Some randomness prevents deterministic cycling while retaining worst-removal bias.
    out=[]
    while pool and len(out)<q:
        idx=min(len(pool)-1,int((rng.random()**2)*len(pool))); out.append(pool.pop(idx))
    return out


def _insertion_options(inst,partial,K,allowed,c):
    """The two cheapest insertions of c (cheapest first, ties in generation order); callers only use options 0 and 1."""
    dem=inst.demand[c]; moves=[]; dloads=depot_loads(inst,partial); cap=inst.depot_cap; q_max=inst.Q+1e-9
    for ri,r in enumerate(partial):
        if r.load+dem<=q_max and dloads[r.depot]+dem<=cap[r.depot]+1e-9:
            dep=r.depot
            for pos,dl in enumerate(_route_deltas(inst,r,c)):
                moves.append((dl,'ins',ri,pos,dep))
    if len(partial)<K:
        used=used_depots(partial)
        for d in allowed:
            if dloads[d]+dem<=cap[d]+1e-9:
                moves.append((_new_route_cost(inst,used,c,d),'new',len(partial),0,d))
    return heapq.nsmallest(2,moves,key=itemgetter(0))


# ---- fleet look-ahead of the greedy / regret repairs (LLRP: K is a binding bound and K*Q is only 3-20 % above the total demand) ----
# A repair that inserts the cheapest customer first can fill the slack of the existing routes with the wrong customers and leave a
# large one without a vehicle (dead end -> the move is lost; ~11 % of the repairs on 100-5-1). The repair therefore keeps a
# best-fit-decreasing (BFD) certificate: a move is taken only if the other unplaced customers still pack (BFD) into the residual
# capacities of the routes and of the unused vehicles; if no cheap move keeps the certificate, the largest unplaced customer goes to its
# BFD bin (always possible, and the certificate is kept). A repair that starts without a certificate, or with a vehicle for every
# unplaced customer (cannot dead-end), runs exactly as before. Depot capacities are not part of the certificate.
def _repair_guard(inst,routes,K,rem):
    free=K-len(routes)
    if free>=len(rem): return False
    Q=inst.Q
    return _pack_ok(sorted(-inst.demand[c] for c in rem),[Q-r.load for r in routes]+[Q]*free,Q)


def _after_ok(inst,routes,K,rem,c,mv):
    """BFD certificate for rem minus c after move mv (routes = the working solution the move refers to)."""
    typ=mv[1]; ri=mv[2]; dem=inst.demand[c]; Q=inst.Q
    free=K-len(routes)-(1 if typ=='new' else 0)
    others=[x for x in rem if x!=c]
    if free>=len(others): return True
    res=[Q-r.load-(dem if (typ=='ins' and i==ri) else 0) for i,r in enumerate(routes)]
    if typ=='new': res.append(Q-dem)
    res.extend([Q]*free)
    return _pack_ok(sorted(-inst.demand[x] for x in others),res,Q)


def _bfd_move(inst,t,rem):
    """Fallback step of a certified repair: the largest unplaced customer into its best-fit bin (the existing route with the least
    sufficient residual, else a new route) at the cheapest position. Returns (customer, move); move is None if no such bin exists."""
    s=t.s; Q=inst.Q; dem=inst.demand; c=max(rem,key=lambda x:(dem[x],-x)); d=dem[c]; cap=inst.depot_cap; dl=t.dl
    for _,ri in sorted((Q-r.load,i) for i,r in enumerate(s) if Q-r.load>=d-1e-9):
        r=s[ri]
        if dl[r.depot]+d<=cap[r.depot]+1e-9:
            dls=_route_deltas(inst,r,c); v=min(dls)
            return c,(v,'ins',ri,dls.index(v),r.depot)
    if len(s)<t.K:
        used=t.used; best=None
        for dp in t.allowed:
            if dl[dp]+d<=cap[dp]+1e-9:
                v=_new_route_cost(inst,used,c,dp)
                if best is None or v<best[0]: best=(v,'new',len(s),0,dp)
        if best is not None: return c,best
    return c,None


def _repair_core(inst,t,rem,kind):
    """Greedy ('greedy': cheapest insertion first) or regret-2 repair on the provider t (_InsertionTable or _RefState), with the
    fleet look-ahead above. t.options(c) -> the two cheapest moves of c; t.apply(c, move); t.s, t.K, t.allowed, t.used, t.dl."""
    K=t.K; guard=_repair_guard(inst,t.s,K,rem)
    while rem:
        banned=set()
        while True:
            pick=None
            for c in rem:
                if c in banned: continue
                ops=t.options(c)
                if not ops: continue
                if kind=='greedy': key=ops[0][0]
                else: key=((ops[1][0]-ops[0][0]) if len(ops)>1 else 1e6,-ops[0][0])
                if pick is None or (key<pick[0] if kind=='greedy' else key>pick[0]): pick=(key,c,ops[0])
            if pick is None: break
            _,c,mv=pick
            if not guard or _after_ok(inst,t.s,K,rem,c,mv): break
            banned.add(c)
        if pick is None:
            if not guard: return None
            c,mv=_bfd_move(inst,t,rem)
            if mv is None: return None
        t.apply(c,mv); rem.remove(c)
    return normalize(inst,t.s)


class _RefState:
    """Reference provider of the repairs: every option is recomputed from scratch (the speed-up _InsertionTable must equal this)."""
    __slots__=('inst','s','K','allowed')

    def __init__(self,inst,partial,K,allowed):
        self.inst=inst; self.s=clone_solution(partial); self.K=K; self.allowed=allowed

    def options(self,c): return _insertion_options(self.inst,self.s,self.K,self.allowed,c)

    def apply(self,c,mv): self.s=_apply_insert(self.inst,self.s,c,mv)

    @property
    def used(self): return used_depots(self.s)

    @property
    def dl(self): return depot_loads(self.inst,self.s)


def _apply_insert(inst,partial,c,mv):
    _,typ,ri,pos,d=mv; s=clone_solution(partial); dem=inst.demand[c]
    if typ=='new': s.append(Route(d,[c],dem))
    else: s[ri].seq.insert(pos,c); s[ri].load+=dem
    return s


class _InsertionTable:
    """Insertion costs of the unplaced customers for the greedy / regret repairs, kept between steps.

    _insertion_options(inst, s, K, allowed, c) recomputes the cost of inserting c at every position of every route after every
    insertion, but an insertion changes one route only. This table keeps, for each customer and route, the two cheapest positions
    (value, position; ties in position order) and recomputes them only for a route that has changed since. options(c) returns the
    same two options (cheapest first, ties in generation order: routes in order, positions in order, new routes last) as
    _insertion_options, because the two best of a whole list are among the two best of each of its parts. Depot loads and the
    set of used depots are updated incrementally (exact: integer demands, see core.fast_eval_ok). The effort counters are booked
    as the full recomputation would book them. apply() changes the working copy in place."""
    __slots__=('inst','s','K','allowed','dl','used','ver','tab')

    def __init__(self,inst,partial,K,allowed):
        self.inst=inst; self.s=clone_solution(partial); self.K=K; self.allowed=allowed
        self.dl=depot_loads(inst,self.s); self.used=used_depots(self.s)
        self.ver=[0]*len(self.s); self.tab={}

    def options(self,c):
        inst=self.inst; s=self.s; dl=self.dl; cap=inst.depot_cap; dem=inst.demand[c]; qm=inst.Q+1e-9; ver=self.ver
        tab=self.tab.get(c)
        if tab is None: tab=self.tab[c]=[None]*len(s)
        elif len(tab)<len(s): tab.extend([None]*(len(s)-len(tab)))
        inf=float('inf'); b1v=b2v=inf; b1=b2=None; hits=0
        for ri,r in enumerate(s):
            dep=r.depot
            if r.load+dem<=qm and dl[dep]+dem<=cap[dep]+1e-9:
                e=tab[ri]
                if e is None or e[0]!=ver[ri]:
                    dls=_route_deltas(inst,r,c)                # books 2*(L+1) route evaluations
                    v1=min(dls); p1=dls.index(v1)
                    if len(dls)>1:
                        rest=dls[:p1]+dls[p1+1:]; v2=min(rest); p2=rest.index(v2)
                        if p2>=p1: p2+=1
                    else: v2=inf; p2=-1
                    e=tab[ri]=(ver[ri],v1,p1,v2,p2)
                else: hits+=2*(len(r.seq)+1)
                v=e[1]
                if v<b1v: b2v=b1v; b2=b1; b1v=v; b1=(v,'ins',ri,e[2],dep)
                elif v<b2v: b2v=v; b2=(v,'ins',ri,e[2],dep)
                v=e[3]
                if v<b1v: b2v=b1v; b2=b1; b1v=v; b1=(v,'ins',ri,e[4],dep)
                elif v<b2v: b2v=v; b2=(v,'ins',ri,e[4],dep)
        _core._CTR[1]+=hits
        if len(s)<self.K:
            used=self.used; nr=len(s)
            for d in self.allowed:
                if dl[d]+dem<=cap[d]+1e-9:
                    v=_new_route_cost(inst,used,c,d)
                    if v<b1v: b2v=b1v; b2=b1; b1v=v; b1=(v,'new',nr,0,d)
                    elif v<b2v: b2v=v; b2=(v,'new',nr,0,d)
        if b1 is None: return []
        return [b1] if b2 is None else [b1,b2]

    def apply(self,c,mv):
        _,typ,ri,pos,d=mv; dem=self.inst.demand[c]
        if typ=='new':
            self.s.append(Route(d,[c],dem)); self.ver.append(0); self.used.add(d)
        else:
            r=self.s[ri]; r.seq.insert(pos,c); r.load+=dem; self.ver[ri]+=1
        self.dl[d]+=dem


def _fast_repair(inst):
    return not _nbm._FORCE_REFERENCE and fast_eval_ok(inst)


def _repair_greedy(inst,partial,removed,K,allowed,rng):
    if not _fast_repair(inst): return _repair_greedy_ref(inst,partial,removed,K,allowed,rng)
    rem=list(removed); rng.shuffle(rem)
    return _repair_core(inst,_InsertionTable(inst,partial,K,allowed),rem,'greedy')


def _repair_regret2(inst,partial,removed,K,allowed,rng):
    if not _fast_repair(inst): return _repair_regret2_ref(inst,partial,removed,K,allowed,rng)
    return _repair_core(inst,_InsertionTable(inst,partial,K,allowed),list(removed),'regret2')


def _repair_greedy_ref(inst,partial,removed,K,allowed,rng):
    rem=list(removed); rng.shuffle(rem)
    return _repair_core(inst,_RefState(inst,partial,K,allowed),rem,'greedy')


def _repair_regret2_ref(inst,partial,removed,K,allowed,rng):
    return _repair_core(inst,_RefState(inst,partial,K,allowed),list(removed),'regret2')


def _destroy_size(inst,rng,frac,mode='fixed',lo_frac=0.10,hi_frac=0.40,q_min=4,q_floor=7):
    """Number of customers a ruin-and-recreate step removes.
    fixed: round(frac * n) (no random number is drawn, runs of the earlier versions are reproduced exactly).
    range: uniform in [max(q_min, ceil(lo_frac n)), ceil(hi_frac n)] per step, after Ropke and Pisinger (2006, q in [4, 0.4 n]).
    floor: max(q_floor, round(frac * n)) (q_floor = 7; identical to fixed for n >= 35, no random number drawn).
    A fixed 0.2 n removes only 4 customers at n = 20 and then cannot leave local optima that are optimal for every ruin set of up to 5
    customers (tools/ruin_neighbourhood_probe.py, claude/llrp_ruin_size_study_20-5-2)."""
    n=inst.n
    if mode=='range':
        hi=max(1,min(n-1,int(math.ceil(hi_frac*n)))); lo=max(1,min(hi,max(q_min,int(math.ceil(lo_frac*n)))))
        return rng.randint(lo,hi)
    if mode=='floor': return max(1,min(n-1,max(q_floor,int(round(frac*n)))))
    return max(1,min(n-1,int(round(frac*n))))


def solve_alns(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
               depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
               alns_iters=2500,alns_destroy_frac=0.20,alns_reaction=0.2,alns_cooling=0.997,destroy_mode=None,**kwargs):
    """Adaptive Large Neighborhood Search with 3 destroy and 2 repair operators."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    destroys=[_destroy_random,_destroy_related,_destroy_worst]; repairs=[_repair_greedy,_repair_regret2]
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            dw=[1.0]*len(destroys); rw=[1.0]*len(repairs); ds=[0.0]*len(destroys); rs=[0.0]*len(repairs); du=[0]*len(destroys); ru=[0]*len(repairs)
            T0=max(1e-6,0.05*max(curz/inst.n,1.0)); T=T0
            for it in range(alns_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                di=roulette(dw,rng); ri=roulette(rw,rng); du[di]+=1; ru[ri]+=1
                q=_destroy_size(inst,rng,alns_destroy_frac,destroy_mode or 'floor')
                removed=destroys[di](inst,cur,q,rng); partial=_partial_remove(inst,cur,removed)
                cand=repairs[ri](inst,partial,removed,K,depots,rng)
                if cand is None or not feasible(inst,cand,K,p): continue
                z=objective(inst,cand); trace_consider(z,cand); trials+=1; reward=0.0
                accept=(z<=curz+EPS or rng.random()<math.exp(-(z-curz)/max(T,1e-12)))
                if z<bestz-EPS:
                    if ls_method!='none':
                        c2,z2,mv=run_local_search(ls_method,inst,cand,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                        if z2<z: cand,z=c2,z2
                    best,bestz=clone_solution(cand),z; reward=5.0; accept=True
                elif z<curz-EPS: reward=2.0
                elif accept: reward=0.5
                if accept: cur,curz=cand,z
                ds[di]+=reward; rs[ri]+=reward; T*=alns_cooling
                if (it+1)%50==0:
                    for i in range(len(dw)):
                        if du[i]: dw[i]=(1-alns_reaction)*dw[i]+alns_reaction*(ds[i]/du[i]+1e-6)
                        ds[i]=0; du[i]=0
                    for i in range(len(rw)):
                        if ru[i]: rw[i]=(1-alns_reaction)*rw[i]+alns_reaction*(rs[i]/ru[i]+1e-6)
                        rs[i]=0; ru[i]=0
                    if T<T0*1e-4: T=T0*0.25
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_msls(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
               depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
               msls_starts=100,**kwargs):
    """Multi-start local search using random priority decodes and optional VND/RVND."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        dep_sets=_depot_subsets(inst,p,rng,depot_mode,depot_sample); passes+=1
        for depots in dep_sets:
            for _ in range(msls_starts):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                perm=list(range(inst.n)); rng.shuffle(perm)
                s=priority_construct(inst,K,depots,perm,rng,randomized_ties=True)
                if s is None: continue
                trials+=1
                s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                if z<bestz-EPS: best,bestz=clone_solution(s),z
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_lns(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
              depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
              lns_iters=2500,lns_destroy_frac=0.20,destroy_mode=None,**kwargs):
    """Non-adaptive large-neighborhood search with fixed destroy/repair pools and improving acceptance."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    destroys=[_destroy_random,_destroy_related,_destroy_worst]; repairs=[_repair_greedy,_repair_regret2]
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            for _ in range(lns_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                d=rng.choice(destroys); r=rng.choice(repairs)
                q=_destroy_size(inst,rng,lns_destroy_frac,destroy_mode or 'floor')
                removed=d(inst,cur,q,rng); partial=_partial_remove(inst,cur,removed)
                cand=r(inst,partial,removed,K,depots,rng)
                if cand is None or not feasible(inst,cand,K,p): continue
                z=objective(inst,cand); trace_consider(z,cand); trials+=1
                if z<curz-EPS:
                    if ls_method!='none':
                        c2,z2,mv=run_local_search(ls_method,inst,cand,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                        if z2<z: cand,z=c2,z2
                    cur,curz=cand,z
                    if z<bestz-EPS: best,bestz=clone_solution(cand),z
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def _decode_random_keys(inst,K,p,chrom,rng,ls_method,ls_preset,deadline):
    """Decode customer priorities and a depot subset of cardinality h in {1,...,p}.

    LLRP: p is the binding upper bound on the number of used depots (opening is free, so using
    fewer depots is never required but may be chosen).  One cardinality key lets the chromosome
    pick h; the h best-ranked depot keys give the candidate subset.  The routes are then built by
    the latency-aware priority constructor (fleet bound K respected) and polished by local search.
    """
    cust_keys=chrom[:inst.n]
    dep_keys=chrom[inst.n:inst.n+inst.m]
    card_key=chrom[inst.n+inst.m] if len(chrom)>inst.n+inst.m else 0.5
    max_open=max(1,min(int(p),inst.m))
    h=1+min(max_open-1,int(card_key*max_open))
    depots=tuple(sorted(sorted(range(inst.m),key=lambda d:dep_keys[d])[:h]))
    perm=sorted(range(inst.n),key=lambda c:cust_keys[c])
    s=priority_construct(inst,K,depots,perm,rng)
    if s is None: return None,float('inf'),0,depots
    s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline)
    return s,z,mv,depots


def solve_brkga(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
                depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
                brkga_pop=40,brkga_generations=250,brkga_elite_frac=0.20,
                brkga_mutant_frac=0.10,brkga_rho=0.70,**kwargs):
    """Biased random-key GA with customer-priority and depot-selection keys."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    dim=inst.n+inst.m+1; trials=0; ls_moves=0; generations=0
    pop=[]
    attempts=0
    while len(pop)<brkga_pop and attempts<brkga_pop*30:
        attempts+=1; chrom=[rng.random() for _ in range(dim)]
        s,z,mv,_=_decode_random_keys(inst,K,p,chrom,rng,ls_method,ls_preset,deadline); ls_moves+=mv
        if s is None: continue
        pop.append((z,chrom,s)); trials+=1
        if _expired(deadline): break
    if not pop: return _finish(None,float('inf'),trials,ls_moves,start,generations)
    while True:
        if _expired(deadline): break
        pop.sort(key=lambda x:x[0])
        if budget_mode=='fixed_trials' and generations>=brkga_generations: break
        E=max(1,min(len(pop)-1,int(round(brkga_elite_frac*len(pop))))) if len(pop)>1 else 1
        M=max(1,int(round(brkga_mutant_frac*brkga_pop)))
        elites=pop[:E]; non=pop[E:] or pop[:]
        new=[(z,c.copy(),clone_solution(s)) for z,c,s in elites]
        while len(new)<brkga_pop-M:
            if _expired(deadline): break
            pe=rng.choice(elites)[1]; pn=rng.choice(non)[1]
            child=[pe[j] if rng.random()<brkga_rho else pn[j] for j in range(dim)]
            s,z,mv,_=_decode_random_keys(inst,K,p,child,rng,ls_method,ls_preset,deadline); ls_moves+=mv
            if s is None: continue
            new.append((z,child,s)); trials+=1
        while len(new)<brkga_pop:
            if _expired(deadline): break
            child=[rng.random() for _ in range(dim)]
            s,z,mv,_=_decode_random_keys(inst,K,p,child,rng,ls_method,ls_preset,deadline); ls_moves+=mv
            if s is None: continue
            new.append((z,child,s)); trials+=1
        if new: pop=new
        generations+=1
    pop.sort(key=lambda x:x[0]); z,_,s=pop[0]
    return _finish(clone_solution(s),z,trials,ls_moves,start,generations)


def _weighted_choice(items, weights, rng):
    total=sum(max(1e-15,w) for w in weights)
    x=rng.random()*total; acc=0.0
    for it,w in zip(items,weights):
        acc+=max(1e-15,w)
        if acc>=x: return it
    return items[-1]


def _sample_depots_aco(inst,p,tau_dep,beta,rng,tau_card=None):
    max_open=max(1,min(int(p),inst.m))
    if tau_card is None:
        h=max_open
    else:
        cards=list(range(1,max_open+1))
        h=_weighted_choice(cards,tau_card[:max_open],rng)
    remaining=list(range(inst.m)); chosen=[]
    avg=[sum(inst.ddc[d])/max(1,inst.n) for d in range(inst.m)]
    for _ in range(h):
        ws=[tau_dep[d]*(1.0/(avg[d]+1e-9))**beta for d in remaining]
        d=_weighted_choice(remaining,ws,rng); chosen.append(d); remaining.remove(d)
    return tuple(sorted(chosen))


def _aco_priority(inst,depots,tau_cc,tau_start,a,beta,rng):
    un=set(range(inst.n)); perm=[]
    first_items=list(un)
    fw=[]
    for c in first_items:
        eta=1.0/(min(inst.ddc[d][c] for d in depots)+1e-9)
        ph=sum(tau_start[d][c] for d in depots)/len(depots)
        fw.append((ph**a)*(eta**beta))
    cur=_weighted_choice(first_items,fw,rng); perm.append(cur); un.remove(cur)
    while un:
        items=list(un); ws=[]
        for j in items:
            eta=1.0/(inst.dcc[cur][j]+1e-9)
            ws.append((tau_cc[cur][j]**a)*(eta**beta))
        cur=_weighted_choice(items,ws,rng); perm.append(cur); un.remove(cur)
    return perm


def solve_aco(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
              depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
              aco_ants=24,aco_iterations=200,aco_alpha=1.0,aco_beta=2.0,
              aco_evap=0.20,aco_q=100.0,**kwargs):
    """ACO-style priority-decoder search with customer-order and depot-selection pheromones."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    tau_cc=[[1.0]*inst.n for _ in range(inst.n)]; tau_start=[[1.0]*inst.n for _ in range(inst.m)]; tau_dep=[1.0]*inst.m
    tau_card=[1.0]*max(1,min(int(p),inst.m))
    best=None; bestz=float('inf'); trials=0; ls_moves=0; iters=0
    while True:
        if _expired(deadline): break
        if budget_mode=='fixed_trials' and iters>=aco_iterations: break
        colony=[]
        for _ in range(aco_ants):
            if _expired(deadline): break
            depots=_sample_depots_aco(inst,p,tau_dep,aco_beta,rng,tau_card)
            perm=_aco_priority(inst,depots,tau_cc,tau_start,aco_alpha,aco_beta,rng)
            s=priority_construct(inst,K,depots,perm,rng)
            if s is None: continue
            s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            trials+=1; colony.append((z,s,depots))
            if z<bestz-EPS: best,bestz=clone_solution(s),z
        evap=max(0.0,min(0.99,aco_evap)); keep=1.0-evap
        for i in range(inst.n):
            for j in range(inst.n): tau_cc[i][j]=max(1e-8,tau_cc[i][j]*keep)
        for d in range(inst.m):
            tau_dep[d]=max(1e-8,tau_dep[d]*keep)
            for c in range(inst.n): tau_start[d][c]=max(1e-8,tau_start[d][c]*keep)
        for h in range(len(tau_card)): tau_card[h]=max(1e-8,tau_card[h]*keep)
        if colony:
            colony.sort(key=lambda x:x[0])
            for z,s,depots in colony[:max(1,len(colony)//5)]:
                delta=aco_q/max(z,1e-9)
                for d in depots: tau_dep[d]+=delta
                if depots: tau_card[len(depots)-1]+=delta
                for r in s:
                    if not r.seq: continue
                    tau_start[r.depot][r.seq[0]]+=delta
                    for a,b in zip(r.seq,r.seq[1:]): tau_cc[a][b]+=delta
        iters+=1
    return _finish(best,bestz,trials,ls_moves,start,iters)


def solve_rtr(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
              depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
              rtr_iters=5000,rtr_threshold_frac=0.02,rtr_decay=0.999,**kwargs):
    """Record-to-record travel with randomized feasible moves and a decaying acceptance threshold.

    EXCLUDED FROM ALL CAMPAIGNS (see EXCLUDED_HEURISTICS). The acceptance test compares a candidate with the GLOBAL record
    (`bestz`), but every pass after the first starts from a fresh construction that is far above that record, so no move is
    ever accepted again: in the P20/P50 pilot the median time to the best value was 0.4 s of 60 s and 0.9 s of 120 s, and a
    diagnostic run accepted 0 moves in each of the passes 2..n. The code is kept unchanged only so that the golden fingerprints
    still cover it; do not use it for results.
    """
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            threshold=max(1e-9,rtr_threshold_frac*curz)
            for _ in range(rtr_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                cand=random_feasible_neighbor(inst,cur,K,p,depots,rng)
                if cand is None: continue
                z=objective(inst,cand); trace_consider(z,cand); trials+=1
                if z<=bestz+threshold+EPS:
                    cur,curz=cand,z
                    if z<bestz-EPS:
                        if ls_method!='none':
                            c2,z2,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                            if z2<z: cur,curz=c2,z2; z=z2
                        best,bestz=clone_solution(cur),curz
                threshold*=rtr_decay
                if threshold<1e-8: threshold=max(1e-9,rtr_threshold_frac*bestz*0.25)
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_ta(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
             depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
             ta_iters=5000,ta_threshold_frac=0.03,ta_decay=0.999,**kwargs):
    """Threshold Accepting with a monotonically shrinking deterministic acceptance band."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            threshold=max(1e-9,ta_threshold_frac*max(curz,1.0))
            walk=Walker(inst,cur,K,p,depots)       # incremental neighbour sampler: same neighbours and random numbers as random_feasible_neighbor
            for _ in range(ta_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                nb=walk.propose(rng)
                if nb is None: continue
                walk.evaluated(nb); z=nb.z; walk.trace(nb); trials+=1
                if z<=curz+threshold+EPS:
                    walk.accept(nb); cur=walk.routes; curz=z
                    if z<bestz-EPS:
                        if ls_method!='none':
                            c2,z2,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                            if z2<z: cur,curz=c2,z2; z=z2; walk.reset(cur)
                        best,bestz=clone_solution(cur),curz
                threshold*=ta_decay
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_ig(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
             depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
             ig_iters=2500,ig_destroy_frac=0.15,ig_accept_frac=0.0,destroy_mode=None,**kwargs):
    """Iterated Greedy: fixed destroy + greedy reconstruction with optional mild acceptance."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            cur=_start(inst,K,depots,rng,alpha)
            if cur is None: continue
            cur,curz,mv=run_local_search(ls_method,inst,cur,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
            if curz<bestz-EPS: best,bestz=clone_solution(cur),curz
            for _ in range(ig_iters):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                q=_destroy_size(inst,rng,ig_destroy_frac,destroy_mode or 'fixed')
                removed=_destroy_random(inst,cur,q,rng)
                partial=_partial_remove(inst,cur,removed)
                cand=_repair_greedy(inst,partial,removed,K,depots,rng)
                if cand is None or not feasible(inst,cand,K,p): continue
                z=objective(inst,cand); trace_consider(z,cand); trials+=1
                accept=z<curz-EPS or (ig_accept_frac>0 and z<=bestz*(1.0+ig_accept_frac)+EPS)
                if accept:
                    if z<curz-EPS and ls_method!='none':
                        c2,z2,mv=run_local_search(ls_method,inst,cand,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                        if z2<z: cand,z=c2,z2
                    cur,curz=cand,z
                    if z<bestz-EPS: best,bestz=clone_solution(cand),z
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def _path_relink_priority(inst,K,p,depots,start_sol,guide_sol,rng,ls_method,ls_preset,deadline,max_steps=None):
    """Permutation path relinking under a fixed allowed-depot set."""
    cur=flatten_solution(start_sol); guide=flatten_solution(guide_sol)
    if len(cur)!=inst.n or len(guide)!=inst.n: return clone_solution(start_sol),objective(inst,start_sol),0,0
    best=clone_solution(start_sol); bestz=objective(inst,best); trace_consider(bestz,best); trials=0; ls_moves=0
    steps=0
    while cur!=guide and (max_steps is None or steps<max_steps):
        if _expired(deadline): break
        mism=[i for i in range(inst.n) if cur[i]!=guide[i]]
        if not mism: break
        candidate_records=[]
        # Candidate moves place a desired guide customer at one mismatched position.
        for i in mism:
            want=guide[i]
            try: j=cur.index(want)
            except ValueError: continue
            q=cur.copy(); x=q.pop(j); q.insert(i,x)
            s=priority_construct(inst,K,depots,q,rng)
            if s is None: continue
            z=objective(inst,s); trace_consider(z,s); trials+=1
            candidate_records.append((z,q,s))
            if _expired(deadline): break
        if not candidate_records: break
        z,cur,s=min(candidate_records,key=lambda x:x[0])
        if z<bestz-EPS:
            if ls_method!='none':
                s2,z2,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv
                if z2<z: s,z=s2,z2; cur=flatten_solution(s)
            best,bestz=clone_solution(s),z
        steps+=1
    return best,bestz,trials,ls_moves


def solve_grasppr(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
                  depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
                  grasppr_starts=80,grasppr_elite=6,grasppr_steps=20,**kwargs):
    """GRASP with an elite pool and permutation path relinking."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        for depots in _depot_subsets(inst,p,rng,depot_mode,depot_sample):
            elite=[]
            for _ in range(grasppr_starts):
                if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
                s=_start(inst,K,depots,rng,alpha)
                if s is None: continue
                s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv; trials+=1
                if z<bestz-EPS: best,bestz=clone_solution(s),z
                if elite:
                    guide=rng.choice(elite)[1]
                    pr,prz,tr,mv=_path_relink_priority(inst,K,p,depots,s,guide,rng,ls_method,ls_preset,deadline,grasppr_steps)
                    trials+=tr; ls_moves+=mv
                    if prz<z: s,z=pr,prz
                    if z<bestz-EPS: best,bestz=clone_solution(s),z
                sig=solution_signature(s)
                if all(solution_signature(e[1])!=sig for e in elite):
                    elite.append((z,clone_solution(s))); elite.sort(key=lambda x:x[0]); elite=elite[:max(1,grasppr_elite)]
            passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_scatter(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
                  depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
                  scatter_pool=24,scatter_refset=8,scatter_iters=30,scatter_steps=20,**kwargs):
    """Compact scatter-search style reference set with path relinking combinations."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    while True:
        if _expired(deadline): break
        # Build a diversified pool across depot subsets.
        pool=[]
        dep_sets=_depot_subsets(inst,p,rng,depot_mode,depot_sample)
        attempts=0
        while len(pool)<scatter_pool and attempts<scatter_pool*20:
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            attempts+=1; depots=rng.choice(dep_sets)
            perm=list(range(inst.n)); rng.shuffle(perm)
            s=priority_construct(inst,K,depots,perm,rng,randomized_ties=True)
            if s is None: continue
            s,z,mv=run_local_search(ls_method,inst,s,K,p,depots,ls_preset,rng,deadline); ls_moves+=mv; trials+=1
            rec=(z,clone_solution(s),tuple(depots))
            if all(solution_signature(x[1])!=solution_signature(s) for x in pool): pool.append(rec)
            if z<bestz-EPS: best,bestz=clone_solution(s),z
        if not pool: break
        pool.sort(key=lambda x:x[0]); ref=pool[:max(2,min(scatter_refset,len(pool)))]
        for _it in range(scatter_iters):
            if _expired(deadline): return _finish(best,bestz,trials,ls_moves,start,passes)
            generated=[]
            for i in range(len(ref)):
                for j in range(i+1,len(ref)):
                    if _expired(deadline): break
                    # Relink under each parent's allowed depot set to permit different depot subsets.
                    for a,b in ((ref[i],ref[j]),(ref[j],ref[i])):
                        pr,prz,tr,mv=_path_relink_priority(inst,K,p,a[2],a[1],b[1],rng,ls_method,ls_preset,deadline,scatter_steps)
                        trials+=tr; ls_moves+=mv
                        if pr is not None: generated.append((prz,clone_solution(pr),a[2]))
                        if prz<bestz-EPS: best,bestz=clone_solution(pr),prz
            if not generated: break
            merged=ref+generated; merged.sort(key=lambda x:x[0]); new=[]; seen=set()
            for rec in merged:
                sig=solution_signature(rec[1])
                if sig in seen: continue
                new.append(rec); seen.add(sig)
                if len(new)>=max(2,scatter_refset): break
            if [solution_signature(x[1]) for x in new]==[solution_signature(x[1]) for x in ref]: break
            ref=new
        passes+=1
        if budget_mode=='fixed_trials': break
    return _finish(best,bestz,trials,ls_moves,start,passes)


def _rk_decode_eval(inst,K,p,vec,rng,ls_method,ls_preset,deadline):
    s,z,mv,depots=_decode_random_keys(inst,K,p,vec,rng,ls_method,ls_preset,deadline)
    return s,z,mv,depots


def solve_rkrs(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
               depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',**kwargs):
    """Random-key random search control using exactly the same decoder as BRKGA/PSO/DE."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    dim=inst.n+inst.m+1; best=None; bestz=float('inf'); trials=0; ls_moves=0; passes=0
    target=max(1,int(kwargs.get('rkrs_trials',5000)))
    while True:
        if _expired(deadline): break
        if budget_mode=='fixed_trials' and trials>=target: break
        vec=[rng.random() for _ in range(dim)]
        sol,z,mv,_=_rk_decode_eval(inst,K,p,vec,rng,ls_method,ls_preset,deadline); ls_moves+=mv
        if sol is None: continue
        trials+=1
        if z<bestz-EPS: best,bestz=clone_solution(sol),z
    return _finish(best,bestz,trials,ls_moves,start,passes)


def solve_pso(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
              depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
              pso_particles=28,pso_iters=250,pso_w=0.72,pso_c1=1.45,pso_c2=1.45,**kwargs):
    """Random-key particle swarm optimization decoded into feasible LLRP routes."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    dim=inst.n+inst.m+1; particles=[]; trials=0; ls_moves=0; iters=0
    gbest=None; gbestz=float('inf'); gbestpos=None
    for _ in range(pso_particles):
        if _expired(deadline): break
        pos=[rng.random() for _ in range(dim)]; vel=[rng.uniform(-0.1,0.1) for _ in range(dim)]
        s,z,mv,_=_rk_decode_eval(inst,K,p,pos,rng,ls_method,ls_preset,deadline); ls_moves+=mv
        if s is None: continue
        trials+=1; particles.append({'pos':pos,'vel':vel,'pbest':pos.copy(),'pbestz':z,'sol':s})
        if z<gbestz: gbest,gbestz,gbestpos=clone_solution(s),z,pos.copy()
    if not particles: return _finish(None,float('inf'),trials,ls_moves,start,iters)
    while True:
        if _expired(deadline): break
        if budget_mode=='fixed_trials' and iters>=pso_iters: break
        for pt in particles:
            if _expired(deadline): break
            for d in range(dim):
                r1=rng.random(); r2=rng.random()
                pt['vel'][d]=pso_w*pt['vel'][d]+pso_c1*r1*(pt['pbest'][d]-pt['pos'][d])+pso_c2*r2*(gbestpos[d]-pt['pos'][d])
                pt['vel'][d]=max(-0.5,min(0.5,pt['vel'][d])); pt['pos'][d]=(pt['pos'][d]+pt['vel'][d])%1.0
            s,z,mv,_=_rk_decode_eval(inst,K,p,pt['pos'],rng,ls_method,ls_preset,deadline); ls_moves+=mv
            if s is None: continue
            trials+=1; pt['sol']=s
            if z<pt['pbestz']-EPS: pt['pbestz']=z; pt['pbest']=pt['pos'].copy()
            if z<gbestz-EPS: gbest,gbestz,gbestpos=clone_solution(s),z,pt['pos'].copy()
        iters+=1
    return _finish(gbest,gbestz,trials,ls_moves,start,iters)


def solve_de(inst,K,p,seed,restarts,alpha,ls_method,ls_preset,time_limit=None,
             depot_mode='enumerate',depot_sample=50,budget_mode='fixed_trials',
             de_pop=30,de_iters=250,de_f=0.7,de_cr=0.85,**kwargs):
    """Random-key differential evolution (DE/rand/1/bin) with the common priority decoder."""
    _check_budget(budget_mode,time_limit)
    rng=random.Random(seed); start=time.perf_counter(); deadline=_deadline(start,time_limit)
    dim=inst.n+inst.m+1; pop=[]; trials=0; ls_moves=0; iters=0
    attempts=0
    while len(pop)<de_pop and attempts<de_pop*20:
        if _expired(deadline): break
        attempts+=1; x=[rng.random() for _ in range(dim)]
        s,z,mv,_=_rk_decode_eval(inst,K,p,x,rng,ls_method,ls_preset,deadline); ls_moves+=mv
        if s is None: continue
        pop.append([x,z,s]); trials+=1
    if not pop: return _finish(None,float('inf'),trials,ls_moves,start,iters)
    while True:
        if _expired(deadline): break
        if budget_mode=='fixed_trials' and iters>=de_iters: break
        for i in range(len(pop)):
            if _expired(deadline): break
            idx=[j for j in range(len(pop)) if j!=i]
            if len(idx)<3: break
            a,b,c=rng.sample(idx,3); xa,xb,xc=pop[a][0],pop[b][0],pop[c][0]
            mutant=[(xa[d]+de_f*(xb[d]-xc[d]))%1.0 for d in range(dim)]
            jrand=rng.randrange(dim); trial=[mutant[d] if (rng.random()<de_cr or d==jrand) else pop[i][0][d] for d in range(dim)]
            s,z,mv,_=_rk_decode_eval(inst,K,p,trial,rng,ls_method,ls_preset,deadline); ls_moves+=mv
            if s is None: continue
            trials+=1
            if z<pop[i][1]-EPS: pop[i]=[trial,z,s]
        iters+=1
    pop.sort(key=lambda x:x[1]); return _finish(clone_solution(pop[0][2]),pop[0][1],trials,ls_moves,start,iters)


# Heuristics that are registered (golden tests, diagnostics) but must not be part of any campaign or comparison.
EXCLUDED_HEURISTICS={
    'grasppr': 'its path relinking (n x steps constructions per start) lets a 10 s run finish only ~1.3 depot subsets of a 10-subset instance: the first, random subset decides the result (P20 screening, 9.7 % mean gap vs <= 1.9 % for every other campaign method, 2026-11-07)',
    'rtr': 'acceptance compares restarts with the global record, so it is idle after its first pass (P20/P50 pilot, Oct 2026)',
}

SOLVERS={
    'grasp': solve_grasp,
    'ils': solve_ils,
    'vns': solve_vns,
    'sa': solve_sa,
    'tabu': solve_tabu,
    'ga': solve_ga,
    'alns': solve_alns,
    'msls': solve_msls,
    'lns': solve_lns,
    'brkga': solve_brkga,
    'aco': solve_aco,
    'rtr': solve_rtr,
    'ta': solve_ta,
    'ig': solve_ig,
    'grasppr': solve_grasppr,
    'scatter': solve_scatter,
    'pso': solve_pso,
    'de': solve_de,
    'rkrs': solve_rkrs,
}
