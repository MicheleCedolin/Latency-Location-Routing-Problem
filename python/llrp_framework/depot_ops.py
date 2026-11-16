"""Coordinated depot operators (opt-in, clean.6.0).

The 15 operators of neighborhoods.py move one route or one or two customers at a time. Closing a depot, opening a closed one
or moving a whole depot needs many such moves in a row and an uphill step in between (the opening cost of the new depot is
paid before the old one is saved), so the open depot set is largely fixed by the construction. These three operators change
the depot set in one move and are scanned like every other neighbourhood (best improving move, same contract):

  depot_close     close an open depot d: its customers (largest demand first) are re-inserted, by cheapest insertion, into the
                  routes of the other open depots or into new routes at them;
  depot_move_all  move every route of depot d to another depot j (closed or open): d closes, j opens or absorbs the routes;
  depot_open      open a closed depot j with a cluster: the customers nearest to j (up to 1, 2 or 3 vehicle loads, capped by the
                  depot capacity) are taken out of their routes and rebuilt into routes at j by cheapest insertion.

Candidates are complete solutions evaluated through reference_ops._accept (deadline, tracer, feasibility test and objective exactly
as for the reference operators, candidate counter included). A rebuilt solution is rough (customers were inserted greedily around a
changed depot structure), so before it is compared with the current solution it is polished by a short descent over the cheap
Core-5 moves without the depot move (intra_relocate1, intra_2opt, inter_relocate1, inter_swap11); this is how location moves are
judged in the LRP literature (a depot move is assessed after the routes have been re-optimised). Set depot_ops.POLISH = False to
compare the raw candidate instead. The operators are deterministic (no random numbers) and are not part of any frozen preset: use
the presets `common5_depot` (Core-5 plus the three) and `hgamp_depot` (Ext-15 plus the three).
"""
from __future__ import annotations
import time
from .core import Route, objective, recompute_load, used_depots, depot_loads
from .construction import _route_deltas, _new_route_cost
from . import reference_ops as _ref

DEPOT_OPERATORS = ('depot_close', 'depot_move_all', 'depot_open')
POLISH = True
POLISH_NAMES = ('intra_relocate1', 'intra_2opt', 'inter_relocate1', 'inter_swap11')
_POLISH_OPS = []          # filled by neighborhoods.py once the operators exist (avoids a circular import)
EPS = 1e-10


def set_polish_ops(ops):
    _POLISH_OPS[:] = list(ops)


def _polish(inst, sol, K, p, allowed):
    """VND over the polish operators (basic scheme: restart from the first neighbourhood after each improvement). The scan deadline
    is left untouched, so a ScanTimeout still propagates to the caller."""
    cur = sol; z = objective(inst, cur); k = 0
    while k < len(_POLISH_OPS):
        res = _POLISH_OPS[k](inst, cur, K, p, allowed)
        if res is not None and res[0] < z - EPS:
            z, cur = res; k = 0
        else:
            k += 1
    return z, cur


def _judge(inst, cand, K, p, allowed, best_obj, best):
    """Evaluate a rebuilt solution (feasibility, objective, candidate counter, deadline), polish it, and keep it if it beats best_obj."""
    z, c = _ref._accept(inst, cand, K, p, float('inf'), None)
    if c is None: return best_obj, best
    if POLISH and _POLISH_OPS:
        z, c = _polish(inst, c, K, p, allowed)
    if z < best_obj - EPS: return z, c
    return best_obj, best


def _clone_routes(inst, sol, skip=None):
    return [Route(r.depot, r.seq.copy(), recompute_load(inst, r)) for r in sol if r.seq and (skip is None or not skip(r))]


def _insert_all(inst, K, routes, customers, targets, only_depot=None, deadline=None):
    """Cheapest-insertion of `customers` (in this order) into `routes` (modified in place) or into a new route at one of `targets`.

    Same candidate set and tie-break as construction.priority_construct (first minimum in generation order), restricted to routes at
    `only_depot` when given. Returns routes, or None when a customer fits nowhere.
    """
    cap = inst.depot_cap; q_max = inst.Q + 1e-9
    dloads = depot_loads(inst, routes)
    for c in customers:
        dem = inst.demand[c]; best = None
        for ri, r in enumerate(routes):
            if deadline is not None and time.perf_counter() >= deadline: return None
            if only_depot is not None and r.depot != only_depot: continue
            if r.load + dem <= q_max and dloads[r.depot] + dem <= cap[r.depot] + 1e-9:
                for pos, dl in enumerate(_route_deltas(inst, r, c)):
                    if best is None or dl < best[0]: best = (dl, 'ins', ri, pos, r.depot)
        if len(routes) < K and dem <= q_max:
            used = used_depots(routes)
            for d in targets:
                if dloads[d] + dem <= cap[d] + 1e-9:
                    cst = _new_route_cost(inst, used, c, d)
                    if best is None or cst < best[0]: best = (cst, 'new', len(routes), 0, d)
        if best is None: return None
        _, typ, ri, pos, dpt = best
        if typ == 'new': routes.append(Route(dpt, [c], dem))
        else:
            routes[ri].seq.insert(pos, c); routes[ri].load += dem
        dloads[dpt] += dem
    return routes


def _open_depots(sol):
    return sorted({r.depot for r in sol if r.seq})


def depot_close(inst, sol, K, p, allowed):
    used = _open_depots(sol)
    if len(used) < 2: return None
    best_obj = objective(inst, sol); best = None; ok = set(allowed)
    for d in used:
        targets = [x for x in used if x != d and x in ok]
        if not targets: continue
        keep = _clone_routes(inst, sol, skip=lambda r: r.depot == d)
        rem = sorted((c for r in sol if r.seq and r.depot == d for c in r.seq), key=lambda c: (-inst.demand[c], c))
        cand = _insert_all(inst, K, keep, rem, targets)
        if cand is None: continue
        best_obj, best = _judge(inst, cand, K, p, allowed, best_obj, best)
    return (best_obj, best) if best is not None else None


def depot_move_all(inst, sol, K, p, allowed):
    used = _open_depots(sol)
    if not used: return None
    best_obj = objective(inst, sol); best = None
    for d in used:
        for j in allowed:
            if j == d: continue
            cand = _clone_routes(inst, sol)
            for r in cand:
                if r.depot == d: r.depot = j
            best_obj, best = _judge(inst, cand, K, p, allowed, best_obj, best)
    return (best_obj, best) if best is not None else None


def depot_open(inst, sol, K, p, allowed):
    used = _open_depots(sol)
    closed = [j for j in allowed if j not in used]
    if not closed: return None
    best_obj = objective(inst, sol); best = None; dm = inst.demand
    for j in closed:
        order = sorted(range(inst.n), key=lambda c: (inst.ddc[j][c], c))
        seen = set()
        for t in (1, 2, 3):
            budget = min(t * inst.Q, inst.depot_cap[j])
            chosen = []; tot = 0.0
            for c in order:
                if tot + dm[c] > budget + 1e-9: continue
                chosen.append(c); tot += dm[c]
                if tot >= budget - 1e-9: break
            key = tuple(chosen)
            if not chosen or key in seen: continue
            seen.add(key)
            cs = set(chosen)
            keep = []
            for r in sol:
                if not r.seq: continue
                s = [c for c in r.seq if c not in cs]
                if s: keep.append(Route(r.depot, s, recompute_load(inst, Route(r.depot, s, 0.0))))
            cand = _insert_all(inst, K, keep, chosen, [j], only_depot=j)
            if cand is None: continue
            best_obj, best = _judge(inst, cand, K, p, allowed, best_obj, best)
    return (best_obj, best) if best is not None else None


DEPOT_NEIGHBORHOODS = {
    'depot_close': depot_close,
    'depot_move_all': depot_move_all,
    'depot_open': depot_open,
}
