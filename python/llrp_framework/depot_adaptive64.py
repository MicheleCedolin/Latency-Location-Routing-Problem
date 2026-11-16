"""Time-scheduled depot-set exploration followed by set-restricted intensification (LLRP port of the CLRP clean.6.4.0 layer).

Opt-in (`--depot-impact adaptive`), built on the clean.6.3.1 structural layer (depot_structural631) and the unchanged
6.2 `first / loffler9` descent. Off / balanced / structural are not touched. What this module changes relative to
`structural`, each point traced to the clean.6.3.1 pilot (`pilot631_off_vs_structural_first_look_2026-11-02`):

1. Time schedule instead of "every 8th hook call". The hook frequency of the host methods differs by orders of magnitude
   (ALNS 9-27 calls per run, GRASP 13-130), so the 6.3.1 trigger gave 7.5 events per run at n = 100 and 0.9 at n = 200,
   and the single event of a P200 run came after 60-120 s of a 120 s budget. Here the first event is allowed after
   `first_frac` of the budget and later events `period_frac` of the budget apart (counted from the end of the previous one).
2. Event cap scaled with the instance size: cap = event_seconds * max(1, (n / 100) ** cap_exp). The 4 s cap of the
   pilot was reached by 3 of the 4 events that polished a candidate at n = 200 (cost of a descent grows steeply with n).
   One event never takes more than half of the remaining depot-impact share.
3. Exploration does not repeat itself: depot-set targets already tried in this run are skipped (6.3.1 re-proposed the same
   top-ranked target; two GRASP seeds ended on the identical solution).
4. Exploitation: from `exploit_start` of the budget on, events intensify the best elite depot sets (the two best sets are
   raced once, then the better one is kept) with spatial ruin-and-recreate restricted to that set, each recreated solution
   polished by the unchanged first / loffler9 descent restricted to the set. Only strict improvements are kept. Every
   fourth event after `exploit_start` is still an exploration event, and two exploitation events in a row without a
   new best elite (PATIENCE) send the schedule back to exploration (clean.6.3.1 pilot smoke: a stalled elite set
   consumed three further slices with no improvement).

Contract inherited from 6.3.x: the hook returns a solution only if it is feasible and strictly better than the one it was
given; improvements are exposed to the incumbent tracer by the descent itself, so the reported result never depends on
what the host does with the returned solution. Fixed-trials runs have no clock: adaptive then behaves exactly as structural.
"""
from __future__ import annotations
import os
import sys
import time
from .core import Route, feasible, normalize, objective, used_depots
from .depot_structural631 import ranked_sets, rebuild, insert_pool

EPS = 1e-9
RUIN_FRACTIONS = (0.05, 0.10, 0.18, 0.30)
KINDS = ('swap2', 'open', 'swap')       # LLRP: depot-set exchange kinds of depot_structural631 (no closing: opening is free)
PATIENCE = 2        # consecutive exploitation events without a new best elite before events return to exploration
_DEBUG = bool(os.environ.get('LLRP_DEPOT_DEBUG'))      # diagnostic only: one stderr line per event, no effect on the search


def _log(S, msg):
    if _DEBUG:
        print(f"[depot-adaptive t={time.perf_counter() - S['start']:.1f}s] {msg}", file=sys.stderr, flush=True)


def _propose(inst, base, K, p, allowed, rng, end, preferred, tried):
    """First feasible candidate for a depot-set target not tried before in this run. Returns (cand, attempts, kind)."""
    attempts = 0
    order = (preferred,) + tuple(k for k in KINDS if k != preferred)
    for kind in order:
        for cfg, old, new in ranked_sets(inst, base, allowed, rng, kind, limit=8, p=p):
            if time.perf_counter() >= end:
                return None, attempts, kind
            if cfg in tried:
                continue
            tried.add(cfg)
            attempts += 1
            cand = rebuild(inst, base, K, p, allowed, cfg, old, new, rng, end)
            if cand is not None and set(used_depots(cand)) != set(used_depots(base)):
                return cand, attempts, kind
    return None, attempts, order[-1]


def ruin_recreate(inst, K, sol, target, rng, frac, deadline):
    """Remove the round(frac * n) customers nearest to a random seed customer, reinsert them inside `target` only."""
    n = inst.n
    r = max(2, int(round(frac * n)))
    c0 = rng.randrange(n)
    d0 = inst.dcc[c0]
    removed = set(sorted(range(n), key=d0.__getitem__)[:r])
    kept = []
    for rt in sol:
        seq = [c for c in rt.seq if c not in removed]
        if seq:
            kept.append(Route(rt.depot, seq, sum(inst.demand[c] for c in seq)))
    cand = insert_pool(inst, K, kept, sorted(removed), target, deadline, rng, randomized=True)
    return None if cand is None else normalize(inst, cand)


def intensify(inst, sol, z, K, p, rng, end, polish):
    """Set-restricted iterated ruin-and-recreate with strict acceptance. Returns (best, bestz, moves, iters, improved)."""
    target = tuple(sorted(used_depots(sol)))
    best, bz = sol, z
    moves = iters = improved = misses = 0
    while time.perf_counter() < end - 0.02 and misses < 50:
        cand = ruin_recreate(inst, K, best, target, rng, rng.choice(RUIN_FRACTIONS), end)
        if cand is None or not feasible(inst, cand, K, p):
            misses += 1
            continue
        cand, cz, mv = polish(inst, cand, K, p, list(target), end)
        moves += mv
        iters += 1
        if cz < bz - EPS and feasible(inst, cand, K, p):
            best, bz = cand, cz
            improved += 1
    return best, bz, moves, iters, improved


def adaptive_maybe(di, inst, sol, z, K, p, allowed, rng, deadline, polish):
    """`di` is the depot_impact module that dispatched here (passed explicitly: robust against package re-imports)."""
    S = di.S
    host_rng = rng                                  # only the fixed_trials fallback (= structural) uses the host stream
    rng = S['rng']                                  # clean.6.4.0: private stream, so an event never shifts the host's random numbers
    if not sol:
        return sol, z, 0
    B = S['budget']
    if B is None:                                   # fixed_trials: no clock, fall back to the 6.3.1 call-count schedule
        return di._structural_maybe(inst, sol, z, K, p, allowed, host_rng, deadline, polish)
    di._elite_register(sol, z)
    S['calls'] += 1
    now = time.perf_counter()
    elapsed = now - S['start']
    if elapsed < S['first_frac'] * B:
        return sol, z, 0
    if now - S['last_event'] < max(S['min_interval'], S['period_frac'] * B):
        return sol, z, 0
    share_left = B * S['max_share'] - S['seconds']
    if share_left <= 0.10:
        return sol, z, 0
    hard_end = (deadline - 0.03) if deadline is not None else S['start'] + B - 0.03
    exploit_phase = S['exploit_start'] < 1.0 and elapsed >= S['exploit_start'] * B
    best_before = min(v[0] for v in S['elites'].values())
    # three exploit events, then one exploration event; two exploit events without a new best elite also end exploitation
    do_exploit = exploit_phase and S['adapt_since_explore'] < 3 and S['adapt_stall'] < PATIENCE
    # slice of this event
    if do_exploit:
        cap = S['exploit_slice'] * B
    else:
        cap = S['event_seconds'] * max(1.0, (inst.n / 100.0) ** S['cap_exp'])
    cap = min(cap, 0.5 * share_left if not do_exploit else share_left)
    end = min(now + cap, hard_end)
    if end - now <= 0.10:
        return sol, z, 0
    S['events'] += 1
    S['adapt_last_cap_s'] = end - now
    if S['adapt_first_event_s'] < 0:
        S['adapt_first_event_s'] = elapsed
    start = now
    best, bestz, moves = sol, z, 0
    try:
        if do_exploit:
            ranked = sorted(S['elites'].items(), key=lambda kv: kv[1][0])
            if ranked:
                j = S['adapt_exploit']
                pick = ranked[1] if (j == 1 and len(ranked) > 1) else ranked[0]
                S['adapt_exploit'] += 1
                S['adapt_since_explore'] += 1
                t0 = time.perf_counter()
                cand, cz, mv, iters, improved = intensify(inst, pick[1][1], pick[1][0], K, p, rng, end, polish)
                S['adapt_exploit_seconds'] += time.perf_counter() - t0
                S['adapt_exploit_iters'] += iters
                S['adapt_exploit_improved'] += 1 if improved else 0
                moves += mv
                _log(S, f"EXPLOIT set={sorted(used_depots(pick[1][1]))} z {pick[1][0]:.0f} -> {cz:.0f} iters={iters} improved={improved} "
                     f"host_z={z:.0f} elites={[(list(k), round(v[0])) for k, v in sorted(S['elites'].items(), key=lambda kv: kv[1][0])][:4]}")
                if improved:
                    di._elite_register(cand, cz)
                if feasible(inst, cand, K, p) and cz < bestz - EPS:
                    best, bestz = cand, cz
                    S['accepted'] += 1
        else:
            S['adapt_explore'] += 1
            S['adapt_since_explore'] = 0
            base = sol
            if S['adapt_explore'] % 3 == 0 and len(S['elites']) > 1:
                cur = tuple(sorted(used_depots(sol)))
                for key, (_, cand_e) in sorted(S['elites'].items(), key=lambda kv: (len(kv[0]), kv[1][0])):
                    if key != cur:
                        base = cand_e
                        break
            cand, attempts, actual = _propose(inst, base, K, p, allowed, rng, end,
                                              KINDS[(S['adapt_explore'] - 1) % 3], S['tried'])
            S['struct_attempts'] += attempts
            _log(S, f"EXPLORE kind={actual} attempts={attempts} base={sorted(used_depots(base))} cap={end - now:.1f}s "
                 f"cand={None if cand is None else sorted(used_depots(cand))} host_z={z:.0f}")
            if cand is not None:
                S['struct_rebuilds'] += 1
                S['candidates'] += 1
                nd = len(used_depots(cand))
                S['struct_min_depots_seen'] = min(S['struct_min_depots_seen'], nd) if S['struct_min_depots_seen'] else nd
                if nd <= 3:
                    S['struct_three_depots_seen'] += 1
                if time.perf_counter() < end:
                    cand, cz, mv = polish(inst, cand, K, p, sorted(used_depots(cand)), end)
                    S['struct_candidates_polished'] += 1
                    moves += mv
                else:
                    cz = objective(inst, cand)
                if not feasible(inst, cand, K, p):
                    raise RuntimeError('adaptive depot exploration produced an infeasible result')
                di._elite_register(cand, cz)
                _log(S, f"   polished cz={cz:.0f} vs host_z={z:.0f} -> {'ACCEPT' if cz < bestz - EPS else 'reject'}")
                if cz < bestz - EPS:
                    best, bestz = cand, cz
                    S['accepted'] += 1
                    S['struct_accepted'] += 1
                    S['struct_accepted_' + actual] += 1
                    if used_depots(best) != used_depots(sol):
                        S['accepted_set'] += 1
        S['elite_sets'] = len(S['elites'])
        if min(v[0] for v in S['elites'].values()) < best_before - EPS:
            S['adapt_stall'] = 0
        elif do_exploit:
            S['adapt_stall'] += 1
    finally:
        S['seconds'] += time.perf_counter() - start
        S['last_event'] = time.perf_counter()
    return best, bestz, moves
