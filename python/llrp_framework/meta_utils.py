from __future__ import annotations
import random
from .core import Route, clone_solution, normalize, feasible


def solution_signature(sol):
    """Canonical signature preserving route order internally but not route list order."""
    return tuple(sorted((r.depot, tuple(r.seq)) for r in sol if r.seq))


def flatten_solution(sol):
    out=[]
    for r in sol:
        out.extend(r.seq)
    return out


def random_feasible_neighbor(inst, sol, K, p, allowed, rng: random.Random, max_attempts=40):
    """Return one randomized feasible neighbor.

    The move family is sampled from route-safe operators that may worsen the objective. This is
    intentionally different from neighborhoods.py, whose operators return only improving moves.
    """
    if not sol:
        return None
    ops=['intra_swap','intra_2opt','inter_swap','inter_relocate','depot_reassign','route_split','route_merge']
    for _ in range(max_attempts):
        op=rng.choice(ops)
        s=clone_solution(sol)
        try:
            if op=='intra_swap':
                cand=[i for i,r in enumerate(s) if len(r.seq)>=2]
                if not cand: continue
                i=rng.choice(cand); a,b=rng.sample(range(len(s[i].seq)),2)
                s[i].seq[a],s[i].seq[b]=s[i].seq[b],s[i].seq[a]
            elif op=='intra_2opt':
                cand=[i for i,r in enumerate(s) if len(r.seq)>=3]
                if not cand: continue
                i=rng.choice(cand); a,b=sorted(rng.sample(range(len(s[i].seq)),2))
                if a==b: continue
                s[i].seq[a:b+1]=reversed(s[i].seq[a:b+1])
            elif op=='inter_swap':
                cand=[i for i,r in enumerate(s) if r.seq]
                if len(cand)<2: continue
                i,j=rng.sample(cand,2); ai=rng.randrange(len(s[i].seq)); bj=rng.randrange(len(s[j].seq))
                ca,cb=s[i].seq[ai],s[j].seq[bj]
                new_i=s[i].load-inst.demand[ca]+inst.demand[cb]
                new_j=s[j].load-inst.demand[cb]+inst.demand[ca]
                if new_i>inst.Q+1e-9 or new_j>inst.Q+1e-9: continue
                s[i].seq[ai],s[j].seq[bj]=cb,ca
                s[i].load,s[j].load=new_i,new_j
            elif op=='inter_relocate':
                src=[i for i,r in enumerate(s) if r.seq]
                if len(src)<2: continue
                i,j=rng.sample(src,2); ai=rng.randrange(len(s[i].seq)); c=s[i].seq[ai]
                if s[j].load+inst.demand[c]>inst.Q+1e-9: continue
                s[i].seq.pop(ai); s[j].seq.insert(rng.randrange(len(s[j].seq)+1),c)
                s[i].load-=inst.demand[c]; s[j].load+=inst.demand[c]
            elif op=='depot_reassign':
                if not allowed: continue
                i=rng.randrange(len(s)); choices=[d for d in allowed if d!=s[i].depot]
                if not choices: continue
                s[i].depot=rng.choice(choices)
            elif op=='route_split':
                if len(s)>=K: continue
                cand=[i for i,r in enumerate(s) if len(r.seq)>=2]
                if not cand: continue
                i=rng.choice(cand); cut=rng.randrange(1,len(s[i].seq))
                right=s[i].seq[cut:]; s[i].seq=s[i].seq[:cut]
                d=rng.choice(list(allowed)); s.append(Route(d,right,0.0))
            elif op=='route_merge':
                if len(s)<2: continue
                i,j=sorted(rng.sample(range(len(s)),2))
                if s[i].load+s[j].load>inst.Q+1e-9: continue
                # Try both concatenation orders and keep one at random to preserve diversification.
                if rng.random()<0.5:
                    s[i].seq=s[i].seq+s[j].seq
                else:
                    s[i].seq=s[j].seq+s[i].seq
                s.pop(j)
            s=normalize(inst,s)
            if feasible(inst,s,K,p):
                return s
        except (ValueError, IndexError):
            continue
    return None


def shake(inst, sol, K, p, allowed, rng, strength=1):
    cur=clone_solution(sol)
    applied=0
    for _ in range(max(1,strength)):
        nxt=random_feasible_neighbor(inst,cur,K,p,allowed,rng)
        if nxt is None:
            continue
        cur=nxt; applied+=1
    return cur if applied else None


def ordered_crossover(p1, p2, rng):
    n=len(p1)
    if n<2: return p1.copy()
    a,b=sorted(rng.sample(range(n),2))
    child=[None]*n
    child[a:b+1]=p1[a:b+1]
    fill=[x for x in p2 if x not in child]
    k=0
    for i in list(range(b+1,n))+list(range(0,a)):
        child[i]=fill[k]; k+=1
    return child


def mutate_permutation(perm, rng, rate=0.2):
    q=perm.copy()
    if len(q)>=2 and rng.random()<rate:
        i,j=rng.sample(range(len(q)),2); q[i],q[j]=q[j],q[i]
    if len(q)>=3 and rng.random()<rate/2:
        i,j=sorted(rng.sample(range(len(q)),2)); q[i:j+1]=reversed(q[i:j+1])
    return q


def roulette(weights, rng):
    total=sum(max(1e-12,w) for w in weights)
    x=rng.random()*total
    acc=0.0
    for i,w in enumerate(weights):
        acc+=max(1e-12,w)
        if acc>=x: return i
    return len(weights)-1
