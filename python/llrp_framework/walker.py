"""Incremental random walk over feasible neighbours (sa, ta, tabu).

meta_utils.random_feasible_neighbor clones the solution, applies one random move, normalises and re-validates the whole result for
every attempt, and the solver then evaluates the full objective of the returned solution. Walker produces exactly the same neighbours
from exactly the same random numbers, but keeps the per-route data of the current solution (neighborhoods.Scan) and evaluates a
proposal by recomputing only the one or two touched routes, with the same arithmetic as core.objective (bit-identical objective).
A proposal is a lightweight Move; the neighbour solution is built only when it is needed (accepted, incumbent for the tracer).

Protocol (replaces `cand = random_feasible_neighbor(...)`, `z = objective(inst, cand)`, `cur = cand`):
    walk = Walker(inst, cur, K, p, allowed)          # copies cur; walk.routes is the current solution (a list of Route)
    mv = walk.propose(rng)                           # same random numbers and same neighbour as random_feasible_neighbor, or None
    walk.evaluated(mv)                               # where the solver called objective(): effort counters; mv.z is the objective
    walk.trace(mv)                                   # trace_consider(mv.z, neighbour) without building the neighbour unless needed
    walk.signature(mv)                               # == solution_signature(neighbour)
    walk.accept(mv)                                  # the neighbour becomes the current solution (walk.routes is updated in place)
    walk.reset(sol)                                  # continue from another solution (after a local search)
Anything the fast path cannot guarantee (non-integer demands or opening costs, a current solution that is not feasible/normalised) is
delegated to random_feasible_neighbor, so the behaviour never differs. LLRP_REFERENCE_OPS=1 forces that fallback.
"""
from __future__ import annotations
from . import core as _core
from .core import Route, clone_solution, normalize, objective, trace_consider, trace_wants
from . import neighborhoods as _nb
from .neighborhoods import Scan, _len
from .core import fast_eval_ok, feasible
from . import neighborhoods as _nbm
from .meta_utils import random_feasible_neighbor, solution_signature

_OPS = ['intra_swap', 'intra_2opt', 'inter_swap', 'inter_relocate', 'depot_reassign', 'route_split', 'route_merge']
_CTR = _core._CTR


class _QuietScan(Scan):
    """Scan whose evaluators leave the effort counters and the local-search deadline alone (the Walker books the effort of the
    objective() call it replaces itself, in evaluated()). Same arithmetic as Scan.e1/e2/eD/eS."""

    def e1(self, i, ns):
        w = self.w; old = w[i]
        w[i] = _len(self.ddc[self.dep[i]], self.dcc, ns)
        zr = sum(w); w[i] = old
        return self.ov + zr

    def e2(self, i, si, li, j, sj, lj):
        qmax = self.qmax
        if li > qmax or lj > qmax: return None
        dep = self.dep; di = dep[i]; dj = dep[j]
        if di != dj:
            DL = self.DL; cap = self.cap; ld = self.ld
            if DL[di] + (li - ld[i]) > cap[di] + 1e-9 or DL[dj] + (lj - ld[j]) > cap[dj] + 1e-9: return None
        ddc = self.ddc; dcc = self.dcc; w = self.w
        if si and sj:
            oi = w[i]; oj = w[j]
            w[i] = _len(ddc[di], dcc, si); w[j] = _len(ddc[dj], dcc, sj)
            zr = sum(w); w[i] = oi; w[j] = oj
            return self.ov + zr
        lst = w.copy(); drop = []
        if si: lst[i] = _len(ddc[di], dcc, si)
        else: drop.append(i)
        if sj: lst[j] = _len(ddc[dj], dcc, sj)
        else: drop.append(j)
        drop.sort(reverse=True)
        for k in drop: del lst[k]
        nr = self.R - len(drop); op = self.opening; cnt = self.cnt; oc = self.oc
        if not si:
            if cnt[di] == (2 if (not sj and dj == di) else 1): op -= oc[di]
        if not sj and (si or dj != di):
            if cnt[dj] == 1: op -= oc[dj]
        return (op + self.vc * nr) + sum(lst)

    def eR(self, i):
        """Objective of the solution without route i (a singleton route that disappears)."""
        lst = self.w.copy(); del lst[i]
        d = self.dep[i]; op = self.opening
        if self.cnt[d] == 1: op -= self.oc[d]
        return (op + self.vc * (self.R - 1)) + sum(lst)

    def eD(self, i, d):
        o = self.dep[i]
        if self.DL[d] + self.ld[i] > self.cap[d] + 1e-9: return None
        cnt = self.cnt; op = self.opening; nu = self.nused; oc = self.oc
        if cnt[o] == 1: op -= oc[o]; nu -= 1
        if cnt[d] == 0: op += oc[d]; nu += 1
        if nu > self.p: return None
        w = self.w; old = w[i]
        w[i] = _len(self.ddc[d], self.dcc, self.sol[i].seq)
        zr = sum(w); w[i] = old
        return (op + self.vc * self.R) + zr

    def eS(self, i, left, ll, right, lr, d2):
        nr = self.R + 1
        if nr > self.K: return None
        qmax = self.qmax
        if ll > qmax or lr > qmax: return None
        di = self.dep[i]; op = self.opening; nu = self.nused
        if d2 != di:
            if self.DL[d2] + lr > self.cap[d2] + 1e-9: return None
            if self.cnt[d2] == 0: op += self.oc[d2]; nu += 1
        if nu > self.p: return None
        w = self.w; old = w[i]; ddc = self.ddc; dcc = self.dcc
        w[i] = _len(ddc[di], dcc, left); w.append(_len(ddc[d2], dcc, right))
        zr = sum(w); w.pop(); w[i] = old
        return (op + self.vc * nr) + zr


def _make_scan(inst, sol, K, p):
    """_QuietScan of a feasible, normalised solution, or None when the original sampler has to be used."""
    if _nbm._FORCE_REFERENCE or not fast_eval_ok(inst): return None
    for r in sol:
        if not r.seq: return None
    if not feasible(inst, sol, K, p): return None
    return _QuietScan(inst, sol, K, p)


class Move:
    __slots__ = ('kind', 'a', 'z', 'nr', 'sol', 'sig')

    def __init__(self, kind, a, z, nr, sol=None):
        self.kind = kind; self.a = a; self.z = z; self.nr = nr; self.sol = sol; self.sig = None


class Walker:
    def __init__(self, inst, sol, K, p, allowed, max_attempts=40):
        self.inst = inst; self.K = K; self.p = p; self.allowed = allowed; self.max_attempts = max_attempts
        self.reset(sol)

    # ------------------------------------------------------------------ state
    def reset(self, sol):
        self.routes = clone_solution(sol)
        self.keys = None
        # None -> delegate every proposal to random_feasible_neighbor
        self.sc = _make_scan(self.inst, self.routes, self.K, self.p) if self.routes else None

    def _keys(self):
        if self.keys is None:
            self.keys = [(r.depot, tuple(r.seq)) for r in self.routes]
        return self.keys

    # ------------------------------------------------------------------ proposals
    def propose(self, rng):
        sc = self.sc
        if sc is None:
            s = random_feasible_neighbor(self.inst, self.routes, self.K, self.p, self.allowed, rng, self.max_attempts)
            return None if s is None else Move('F', None, None, len(s), s)
        rs = self.routes; inst = self.inst; dem = inst.demand; qm = inst.Q + 1e-9; allowed = self.allowed
        e1 = sc.e1; e2 = sc.e2; eD = sc.eD; eS = sc.eS; K = self.K
        for _ in range(self.max_attempts):
            op = rng.choice(_OPS)
            try:
                if op == 'intra_swap':
                    cand = [i for i, r in enumerate(rs) if len(r.seq) >= 2]
                    if not cand: continue
                    i = rng.choice(cand); a, b = rng.sample(range(len(rs[i].seq)), 2)
                    ns = rs[i].seq.copy(); ns[a], ns[b] = ns[b], ns[a]
                    z = e1(i, ns)
                    if z is not None: return Move('1', (i, ns), z, sc.R)
                elif op == 'intra_2opt':
                    cand = [i for i, r in enumerate(rs) if len(r.seq) >= 3]
                    if not cand: continue
                    i = rng.choice(cand); a, b = sorted(rng.sample(range(len(rs[i].seq)), 2))
                    if a == b: continue
                    sq = rs[i].seq
                    ns = sq[:a] + sq[a:b + 1][::-1] + sq[b + 1:]
                    z = e1(i, ns)
                    if z is not None: return Move('1', (i, ns), z, sc.R)
                elif op == 'inter_swap':
                    cand = list(range(len(rs)))
                    if len(cand) < 2: continue
                    i, j = rng.sample(cand, 2); ai = rng.randrange(len(rs[i].seq)); bj = rng.randrange(len(rs[j].seq))
                    ca, cb = rs[i].seq[ai], rs[j].seq[bj]
                    new_i = rs[i].load - dem[ca] + dem[cb]; new_j = rs[j].load - dem[cb] + dem[ca]
                    if new_i > qm or new_j > qm: continue
                    si = rs[i].seq.copy(); si[ai] = cb; sj = rs[j].seq.copy(); sj[bj] = ca
                    z = e2(i, si, new_i, j, sj, new_j)
                    if z is not None: return Move('2', (i, si, new_i, j, sj, new_j), z, sc.R)
                elif op == 'inter_relocate':
                    src = list(range(len(rs)))
                    if len(src) < 2: continue
                    i, j = rng.sample(src, 2); ai = rng.randrange(len(rs[i].seq)); c = rs[i].seq[ai]
                    if rs[j].load + dem[c] > qm: continue
                    pos = rng.randrange(len(rs[j].seq) + 1)
                    sq = rs[i].seq; si = sq[:ai] + sq[ai + 1:]
                    tq = rs[j].seq; sj = tq[:pos] + [c] + tq[pos:]
                    li = rs[i].load - dem[c]; lj = rs[j].load + dem[c]
                    z = e2(i, si, li, j, sj, lj)
                    if z is not None: return Move('2', (i, si, li, j, sj, lj), z, sc.R - (0 if si else 1))
                elif op == 'depot_reassign':
                    if not allowed: continue
                    i = rng.randrange(len(rs)); choices = [d for d in allowed if d != rs[i].depot]
                    if not choices: continue
                    d = rng.choice(choices)
                    z = eD(i, d)
                    if z is not None: return Move('D', (i, d), z, sc.R)
                elif op == 'route_split':
                    if len(rs) >= K: continue
                    cand = [i for i, r in enumerate(rs) if len(r.seq) >= 2]
                    if not cand: continue
                    i = rng.choice(cand); cut = rng.randrange(1, len(rs[i].seq))
                    sq = rs[i].seq; left = sq[:cut]; right = sq[cut:]
                    d2 = rng.choice(list(allowed))
                    ll = sum(map(dem.__getitem__, left)); lr = sum(map(dem.__getitem__, right))
                    z = eS(i, left, ll, right, lr, d2)
                    if z is not None: return Move('S', (i, left, ll, right, lr, d2), z, sc.R + 1)
                else:  # route_merge
                    if len(rs) < 2: continue
                    i, j = sorted(rng.sample(range(len(rs)), 2))
                    if rs[i].load + rs[j].load > qm: continue
                    ns = rs[i].seq + rs[j].seq if rng.random() < 0.5 else rs[j].seq + rs[i].seq
                    li = rs[i].load + rs[j].load
                    z = e2(i, ns, li, j, [], 0.0)
                    if z is not None: return Move('2', (i, ns, li, j, [], 0.0), z, sc.R - 1)
            except (ValueError, IndexError):
                continue
        return None

    # ------------------------------------------------------------------ use of a proposal
    def evaluated(self, mv):
        """Counters of objective(inst, neighbour); for a delegated neighbour this evaluates it."""
        if mv.kind == 'F':
            mv.z = objective(self.inst, mv.sol)
        else:
            _CTR[0] += 1; _CTR[1] += mv.nr

    def solution(self, mv):
        """The neighbour as random_feasible_neighbor would have returned it (a new, normalised list)."""
        if mv.kind == 'F': return mv.sol
        s = clone_solution(self.routes); a = mv.a
        if mv.kind == '1': s[a[0]].seq = list(a[1])
        elif mv.kind == '2':
            s[a[0]].seq = list(a[1]); s[a[3]].seq = list(a[4])
        elif mv.kind == 'D': s[a[0]].depot = a[1]
        else:
            s[a[0]].seq = list(a[1]); s.append(Route(a[5], list(a[3]), 0.0))
        return normalize(self.inst, s)

    def trace(self, mv):
        if trace_wants(mv.z): trace_consider(mv.z, self.solution(mv))

    def signature(self, mv):
        if mv.sig is None:
            if mv.kind == 'F':
                mv.sig = solution_signature(mv.sol)
            else:
                ks = self._keys().copy(); a = mv.a; rs = self.routes
                if mv.kind == '1': ks[a[0]] = (rs[a[0]].depot, tuple(a[1]))
                elif mv.kind == '2':
                    i, si, _, j, sj, _ = a
                    ks[i] = (rs[i].depot, tuple(si)); ks[j] = (rs[j].depot, tuple(sj))
                elif mv.kind == 'D': ks[a[0]] = (a[1], tuple(rs[a[0]].seq))
                else:
                    ks[a[0]] = (rs[a[0]].depot, tuple(a[1])); ks.append((a[5], tuple(a[3])))
                mv.sig = tuple(sorted(k for k in ks if k[1]))
        return mv.sig

    def accept(self, mv):
        if mv.kind == 'F':
            self.routes = mv.sol; self.keys = None
            self.sc = _make_scan(self.inst, self.routes, self.K, self.p)
            return
        rs = self.routes; sc = self.sc; a = mv.a; ddc = self.inst.ddc; dcc = self.inst.dcc
        self.keys = None
        if mv.kind == '1':
            i, ns = a
            rs[i].seq = ns
            sc.dist[i] = sc.w[i] = _len(ddc[rs[i].depot], dcc, ns)
            return                                       # loads, depots and every aggregate are unchanged
        if mv.kind == '2':
            i, si, li, j, sj, lj = a
            rs[i].seq = si; rs[i].load = li; rs[j].seq = sj; rs[j].load = lj
            sc.ld[i] = li; sc.ld[j] = lj
            if si: sc.dist[i] = sc.w[i] = _len(ddc[rs[i].depot], dcc, si)
            if sj: sc.dist[j] = sc.w[j] = _len(ddc[rs[j].depot], dcc, sj)
            for k in sorted([k for k, s in ((i, si), (j, sj)) if not s], reverse=True):
                del rs[k], sc.dep[k], sc.ld[k], sc.dist[k], sc.w[k]
        elif mv.kind == 'D':
            i, d = a
            rs[i].depot = d; sc.dep[i] = d
            sc.dist[i] = sc.w[i] = _len(ddc[d], dcc, rs[i].seq)
        else:
            i, left, ll, right, lr, d2 = a
            rs[i].seq = left; rs[i].load = ll; sc.ld[i] = ll
            sc.dist[i] = sc.w[i] = _len(ddc[rs[i].depot], dcc, left)
            rs.append(Route(d2, right, lr)); sc.dep.append(d2); sc.ld.append(lr)
            x = _len(ddc[d2], dcc, right); sc.dist.append(x); sc.w.append(x)
        sc.refresh()
