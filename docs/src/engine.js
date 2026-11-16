/* LLRP toy engine -- a small, readable JavaScript re-implementation of the ideas of the C++ engine (cpp/src/llrp_fast.cpp),
 * written for the interactive learning app.  It is NOT the research code: no O(1) move evaluation (candidates are re-evaluated
 * from scratch), no strategic oscillation (capacity is a hard constraint), no tuning.  Use it to see what the operators do.
 * Works in the browser (global LLRP) and in Node (module.exports).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LLRP = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const EPS = 1e-9;

  /* ---------------------------------------------------------------- random numbers (mulberry32) */
  function makeRng(seed) {
    let a = (seed >>> 0) || 1;
    const next = function () {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    return {
      next: next,
      int: function (n) { return Math.floor(next() * n); },
      pick: function (arr) { return arr[Math.floor(next() * arr.length)]; },
      shuffle: function (arr) { for (let i = arr.length - 1; i > 0; i--) { const j = Math.floor(next() * (i + 1)); const t = arr[i]; arr[i] = arr[j]; arr[j] = t; } return arr; },
      sample: function (arr, k) { return this.shuffle(arr.slice()).slice(0, k); }
    };
  }

  /* ---------------------------------------------------------------- instances */
  // spec: {name, dep: [[x,y],...], cust: [[x,y,q],...], Q, Nv, Ng, bks?}
  function makeInstance(spec) {
    const n = spec.cust.length, m = spec.dep.length;
    const dist = function (a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); };
    const dcc = [], ddc = [];
    for (let i = 0; i < n; i++) { dcc.push([]); for (let j = 0; j < n; j++) dcc[i].push(dist(spec.cust[i], spec.cust[j])); }
    for (let d = 0; d < m; d++) { ddc.push([]); for (let j = 0; j < n; j++) ddc[d].push(dist(spec.dep[d], spec.cust[j])); }
    return {
      name: spec.name || 'instance', n: n, m: m, Q: spec.Q, Nv: spec.Nv, Ng: spec.Ng, bks: spec.bks || null,
      dep: spec.dep, cust: spec.cust.map(function (c) { return [c[0], c[1]]; }), q: spec.cust.map(function (c) { return c[2]; }),
      dcc: dcc, ddc: ddc
    };
  }

  // random instance on a 100 x 100 square; capacity leaves ~30 % slack over the total demand
  function randomInstance(o) {
    const rng = makeRng(o.seed || 1), n = o.n, m = o.m;
    const cust = [], dep = [];
    const nCl = o.clustered ? Math.max(2, Math.round(n / 8)) : 0, centres = [];
    for (let k = 0; k < nCl; k++) centres.push([12 + rng.next() * 76, 12 + rng.next() * 76]);
    for (let i = 0; i < n; i++) {
      let x, y;
      if (nCl) { const c = rng.pick(centres); x = c[0] + (rng.next() + rng.next() - 1) * 16; y = c[1] + (rng.next() + rng.next() - 1) * 16; }
      else { x = rng.next() * 100; y = rng.next() * 100; }
      cust.push([Math.min(99, Math.max(1, x)), Math.min(99, Math.max(1, y)), 1 + rng.int(9)]);
    }
    for (let d = 0; d < m; d++) dep.push([6 + rng.next() * 88, 6 + rng.next() * 88]);
    let tot = 0; cust.forEach(function (c) { tot += c[2]; });
    const Nv = o.Nv, Q = Math.ceil(1.3 * tot / Nv);
    return makeInstance({ name: 'random n=' + n + ' m=' + m + ' seed=' + (o.seed || 1), dep: dep, cust: cust, Q: Q, Nv: Nv, Ng: Math.min(o.Ng, m) });
  }

  /* ---------------------------------------------------------------- objective */
  // latency of a route (depot index, customer sequence): sum of customer arrival times; no return to the depot
  function routeLat(inst, depot, seq) {
    const L = seq.length;
    if (!L) return 0;
    let s = L * inst.ddc[depot][seq[0]];
    for (let j = 1; j < L; j++) s += (L - j) * inst.dcc[seq[j - 1]][seq[j]];
    return s;
  }
  function routeLoad(inst, seq) { let s = 0; for (let i = 0; i < seq.length; i++) s += inst.q[seq[i]]; return s; }
  function arrivals(inst, depot, seq) {
    const t = []; let acc = 0, prev = -1;
    for (let j = 0; j < seq.length; j++) { acc += prev < 0 ? inst.ddc[depot][seq[j]] : inst.dcc[prev][seq[j]]; t.push(acc); prev = seq[j]; }
    return t;
  }
  function solCost(inst, sol) { let s = 0; sol.routes.forEach(function (r) { s += routeLat(inst, r.depot, r.seq); }); return s; }
  function cloneSol(sol) { return { routes: sol.routes.map(function (r) { return { depot: r.depot, seq: r.seq.slice() }; }) }; }
  function openDepots(sol) {
    const s = {}; sol.routes.forEach(function (r) { if (r.seq.length) s[r.depot] = 1; });
    return Object.keys(s).map(Number).sort(function (a, b) { return a - b; });
  }
  function validate(inst, sol) {
    const errs = [], seen = new Array(inst.n).fill(0);
    sol.routes.forEach(function (r, i) {
      if (!r.seq.length) errs.push('route ' + i + ' is empty');
      if (routeLoad(inst, r.seq) > inst.Q + EPS) errs.push('route ' + i + ' exceeds Q');
      r.seq.forEach(function (c) { seen[c]++; });
    });
    for (let c = 0; c < inst.n; c++) if (seen[c] !== 1) errs.push('customer ' + c + ' visited ' + seen[c] + ' times');
    if (sol.routes.length > inst.Nv) errs.push('more than Nv routes');
    if (openDepots(sol).length > inst.Ng) errs.push('more than Ng open depots');
    return { ok: errs.length === 0, errors: errs };
  }

  /* ---------------------------------------------------------------- neighbourhood scanner */
  // A candidate move is a list of route replacements {i, depot, seq}.  Invariants (as in llrp_fast.cpp): no route becomes empty,
  // the number of routes is unchanged, every customer stays in exactly one route, capacity holds, the open-depot set is unchanged except by `ds`.
  function makeScanner(inst, sol) {
    const R = sol.routes, lat = R.map(function (r) { return routeLat(inst, r.depot, r.seq); });
    const S = { R: R, best: null, evals: 0 };
    S.consider = function (changes, desc) {
      S.evals++;
      let delta = 0;
      for (let k = 0; k < changes.length; k++) {
        const c = changes[k];
        if (!c.seq.length) return;
        if (!c.keepLoad && routeLoad(inst, c.seq) > inst.Q + EPS) return;
        delta += routeLat(inst, c.depot, c.seq) - lat[c.i];
      }
      if (S.best === null || delta < S.best.delta - 1e-12) S.best = { delta: delta, changes: changes, desc: desc };
    };
    return S;
  }
  const rev = function (a) { return a.slice().reverse(); };
  const ins = function (a, q, blk) { return a.slice(0, q).concat(blk, a.slice(q)); };

  function opOrOpt(inst, S, k, name) {
    const R = S.R;
    for (let a = 0; a < R.length; a++) {
      const A = R[a].seq;
      for (let i = 0; i + k <= A.length; i++) {
        const blk = A.slice(i, i + k), rest = A.slice(0, i).concat(A.slice(i + k));
        const orient = k > 1 ? [false, true] : [false];
        for (let oi = 0; oi < orient.length; oi++) {
          const b2 = orient[oi] ? rev(blk) : blk;
          for (let q = 0; q <= rest.length; q++) {                        // same route
            if (q === i && !orient[oi]) continue;
            S.consider([{ i: a, depot: R[a].depot, seq: ins(rest, q, b2) }], { op: name, text: 'block of ' + k + ' moves inside its route' + (orient[oi] ? ' (reversed)' : '') });
          }
          if (rest.length) for (let b = 0; b < R.length; b++) {            // another route
            if (b === a) continue;
            const B = R[b].seq;
            for (let q = 0; q <= B.length; q++)
              S.consider([{ i: a, depot: R[a].depot, seq: rest }, { i: b, depot: R[b].depot, seq: ins(B, q, b2) }], { op: name, text: 'block of ' + k + ' moves to another route' + (orient[oi] ? ' (reversed)' : '') });
          }
        }
      }
    }
  }

  function opSwap(inst, S, K, L, name) {
    const R = S.R, sym = K === L;
    for (let a = 0; a < R.length; a++) for (let b = 0; b < R.length; b++) {          // two routes
      if (a === b || (sym && b < a)) continue;
      const A = R[a].seq, B = R[b].seq;
      for (let i = 0; i + K <= A.length; i++) for (let j = 0; j + L <= B.length; j++) {
        const ba = A.slice(i, i + K), bb = B.slice(j, j + L);
        for (let ra = 0; ra < (K > 1 ? 2 : 1); ra++) for (let rb = 0; rb < (L > 1 ? 2 : 1); rb++) {
          const xa = ra ? rev(ba) : ba, xb = rb ? rev(bb) : bb;
          S.consider([{ i: a, depot: R[a].depot, seq: A.slice(0, i).concat(xb, A.slice(i + K)) },
                      { i: b, depot: R[b].depot, seq: B.slice(0, j).concat(xa, B.slice(j + L)) }], { op: name, text: 'a block of ' + K + ' and a block of ' + L + ' trade places (two routes)' });
        }
      }
    }
    const sizes = sym ? [[K, L]] : [[K, L], [L, K]];                                   // inside one route
    for (let a = 0; a < R.length; a++) {
      const A = R[a].seq;
      for (let si = 0; si < sizes.length; si++) {
        const s1 = sizes[si][0], s2 = sizes[si][1];
        for (let i = 0; i + s1 <= A.length; i++) for (let j = i + s1; j + s2 <= A.length; j++) {
          const b1 = A.slice(i, i + s1), b2 = A.slice(j, j + s2);
          for (let r1 = 0; r1 < (s1 > 1 ? 2 : 1); r1++) for (let r2 = 0; r2 < (s2 > 1 ? 2 : 1); r2++) {
            const x1 = r1 ? rev(b1) : b1, x2 = r2 ? rev(b2) : b2;
            S.consider([{ i: a, depot: R[a].depot, seq: A.slice(0, i).concat(x2, A.slice(i + s1, j), x1, A.slice(j + s2)) }], { op: name, text: 'two blocks trade places inside one route' });
          }
        }
      }
    }
  }

  function op2opt(inst, S) {
    const R = S.R;
    for (let a = 0; a < R.length; a++) {
      const A = R[a].seq;
      for (let i = 0; i < A.length - 1; i++) for (let j = i + 1; j < A.length; j++)
        S.consider([{ i: a, depot: R[a].depot, seq: A.slice(0, i).concat(rev(A.slice(i, j + 1)), A.slice(j + 1)) }], { op: '2opt', text: 'a segment of one route is reversed' });
    }
  }

  function op2optStar(inst, S) {
    const R = S.R;
    for (let a = 0; a < R.length; a++) for (let b = a + 1; b < R.length; b++) {
      const A = R[a].seq, B = R[b].seq;
      for (let i = 0; i <= A.length; i++) for (let j = 0; j <= B.length; j++) {
        if ((i === A.length && j === B.length) || (i === 0 && j === 0)) continue;       // identity; i=j=0 is dexch
        S.consider([{ i: a, depot: R[a].depot, seq: A.slice(0, i).concat(B.slice(j)) }, { i: b, depot: R[b].depot, seq: B.slice(0, j).concat(A.slice(i)) }], { op: '2opt*', text: 'the tails of two routes are exchanged' });
      }
    }
  }

  function bestInsertion(inst, depot, rest, c) {                                       // cheapest position of customer c in a route
    let bq = 0, bl = Infinity;
    for (let q = 0; q <= rest.length; q++) { const l = routeLat(inst, depot, ins(rest, q, [c])); if (l < bl) { bl = l; bq = q; } }
    return bq;
  }
  function opSwapStar(inst, S) {
    const R = S.R;
    for (let a = 0; a < R.length; a++) for (let b = a + 1; b < R.length; b++) {
      const A = R[a].seq, B = R[b].seq;
      for (let i = 0; i < A.length; i++) for (let j = 0; j < B.length; j++) {
        const u = A[i], v = B[j];
        const restA = A.slice(0, i).concat(A.slice(i + 1)), restB = B.slice(0, j).concat(B.slice(j + 1));
        const qa = bestInsertion(inst, R[a].depot, restA, v), qb = bestInsertion(inst, R[b].depot, restB, u);
        S.consider([{ i: a, depot: R[a].depot, seq: ins(restA, qa, [v]) }, { i: b, depot: R[b].depot, seq: ins(restB, qb, [u]) }], { op: 'swapstar', text: 'two customers swap routes; each is re-inserted at its best position' });
      }
    }
  }

  function opDexch(inst, S) {
    const R = S.R;
    for (let a = 0; a < R.length; a++) for (let b = a + 1; b < R.length; b++) {
      if (R[a].depot === R[b].depot) continue;
      S.consider([{ i: a, depot: R[b].depot, seq: R[a].seq, keepLoad: true }, { i: b, depot: R[a].depot, seq: R[b].seq, keepLoad: true }], { op: 'dexch', text: 'two routes exchange their depots' });
    }
  }

  function opRDepot(inst, S) {
    const R = S.R, cnt = {};
    R.forEach(function (r) { cnt[r.depot] = (cnt[r.depot] || 0) + 1; });
    const open = Object.keys(cnt).map(Number);
    for (let a = 0; a < R.length; a++) {
      if (cnt[R[a].depot] < 2) continue;                                               // the depot must stay open
      for (let k = 0; k < open.length; k++) {
        const d = open[k];
        if (d === R[a].depot) continue;
        S.consider([{ i: a, depot: d, seq: R[a].seq, keepLoad: true }], { op: 'rdepot', text: 'a route moves to another open depot' });
        if (R[a].seq.length > 1) S.consider([{ i: a, depot: d, seq: rev(R[a].seq), keepLoad: true }], { op: 'rdepot', text: 'a route moves to another open depot (reversed)' });
      }
    }
  }

  function opDS(inst, S) {
    const R = S.R, used = {};
    R.forEach(function (r) { used[r.depot] = 1; });
    const open = Object.keys(used).map(Number), closed = [];
    for (let d = 0; d < inst.m; d++) if (!used[d]) closed.push(d);
    for (let x = 0; x < open.length; x++) for (let y = 0; y < closed.length; y++) {
      const o = open[x], c = closed[y], ch = [];
      R.forEach(function (r, i) { if (r.depot === o) ch.push({ i: i, depot: c, seq: r.seq, keepLoad: true }); });
      S.consider(ch, { op: 'ds', text: 'an open depot is replaced by a closed one; its routes move along' });
    }
  }

  const OPS = {
    'relocate': function (i, S) { opOrOpt(i, S, 1, 'relocate'); }, 'oropt2': function (i, S) { opOrOpt(i, S, 2, 'oropt2'); }, 'oropt3': function (i, S) { opOrOpt(i, S, 3, 'oropt3'); },
    'swap11': function (i, S) { opSwap(i, S, 1, 1, 'swap11'); }, 'swap21': function (i, S) { opSwap(i, S, 2, 1, 'swap21'); }, 'swap22': function (i, S) { opSwap(i, S, 2, 2, 'swap22'); },
    'swap31': function (i, S) { opSwap(i, S, 3, 1, 'swap31'); }, 'swap32': function (i, S) { opSwap(i, S, 3, 2, 'swap32'); },
    '2opt': op2opt, '2opt*': op2optStar, 'swapstar': opSwapStar, 'dexch': opDexch, 'rdepot': opRDepot, 'ds': opDS
  };
  const OP_NAMES = ['relocate', 'oropt2', 'oropt3', 'swap11', 'swap21', 'swap22', 'swap31', 'swap32', '2opt', '2opt*', 'swapstar', 'dexch', 'rdepot', 'ds'];

  // best (most improving, or least worsening) move of one operator, or null when the neighbourhood is empty
  function bestMove(inst, sol, op) {
    const S = makeScanner(inst, sol);
    OPS[op](inst, S);
    if (!S.best) return null;
    S.best.evals = S.evals;
    return S.best;
  }
  function applyMove(sol, mv) {
    const out = cloneSol(sol);
    mv.changes.forEach(function (c) { out.routes[c.i] = { depot: c.depot, seq: c.seq.slice() }; });
    return out;
  }

  /* ---------------------------------------------------------------- local search (RVND) */
  function newStats() { const s = {}; OP_NAMES.forEach(function (o) { s[o] = { calls: 0, evals: 0, applied: 0, gain: 0, ms: 0 }; }); return s; }
  // Randomised variable neighbourhood descent, best improvement per neighbourhood: after every improvement the list is reshuffled.
  function rvnd(inst, sol, ops, rng, stats) {
    let cur = sol, list = rng.shuffle(ops.slice()), k = 0, z = solCost(inst, cur);
    while (k < list.length) {
      const op = list[k], t0 = Date.now(), mv = bestMove(inst, cur, op);
      if (stats) { stats[op].calls++; stats[op].ms += Date.now() - t0; if (mv) stats[op].evals += mv.evals; }
      if (mv && mv.delta < -EPS) {
        cur = applyMove(cur, mv); z += mv.delta;
        if (stats) { stats[op].applied++; stats[op].gain += -mv.delta; }
        list = rng.shuffle(ops.slice()); k = 0;
      } else k++;
    }
    return cur;
  }

  /* ---------------------------------------------------------------- construction (Clarke-Wright-like merging with a restricted candidate list) */
  function construct(inst, allowed, rcl, rng) {
    let routes = [];
    for (let c = 0; c < inst.n; c++) {
      let bd = allowed[0];
      for (let k = 0; k < allowed.length; k++) if (inst.ddc[allowed[k]][c] < inst.ddc[bd][c]) bd = allowed[k];
      routes.push({ depot: bd, seq: [c], load: inst.q[c], lat: inst.ddc[bd][c] });
    }
    for (;;) {
      const cands = [];
      for (let i = 0; i < routes.length; i++) for (let j = 0; j < routes.length; j++) {
        if (i === j || routes[i].load + routes[j].load > inst.Q + EPS) continue;
        const seq = routes[i].seq.concat(routes[j].seq), ds = routes[i].depot === routes[j].depot ? [routes[i].depot] : [routes[i].depot, routes[j].depot];
        for (let k = 0; k < ds.length; k++) cands.push({ delta: routeLat(inst, ds[k], seq) - routes[i].lat - routes[j].lat, i: i, j: j, d: ds[k], seq: seq });
      }
      if (!cands.length) break;
      cands.sort(function (a, b) { return a.delta - b.delta; });
      const must = routes.length > inst.Nv;
      let pool = cands.slice(0, Math.min(rcl, cands.length));
      if (!must) { pool = pool.filter(function (c) { return c.delta < 0; }); if (!pool.length) break; }
      const ch = rng.pick(pool), a = routes[ch.i], b = routes[ch.j];
      routes = routes.filter(function (_, idx) { return idx !== ch.i && idx !== ch.j; });
      routes.push({ depot: ch.d, seq: ch.seq, load: a.load + b.load, lat: routeLat(inst, ch.d, ch.seq) });
    }
    if (routes.length > inst.Nv) return null;
    return { routes: routes.map(function (r) { return { depot: r.depot, seq: r.seq }; }) };
  }

  // fallback for tight capacities: best-fit-decreasing packing into Nv bins, each bin sequenced by nearest neighbour from its closest allowed depot
  function packConstruct(inst, allowed, rng) {
    const order = []; for (let c = 0; c < inst.n; c++) order.push(c);
    order.sort(function (a, b) { return (inst.q[b] - inst.q[a]) || (rng.next() - 0.5); });
    const bins = [], load = [];
    for (let b = 0; b < inst.Nv; b++) { bins.push([]); load.push(0); }
    for (let k = 0; k < order.length; k++) {
      const c = order[k]; let bb = -1;
      for (let b = 0; b < bins.length; b++) if (load[b] + inst.q[c] <= inst.Q + EPS && (bb < 0 || load[b] > load[bb] || (load[b] === load[bb] && rng.next() < 0.5))) bb = b;
      if (bb < 0) return null;
      bins[bb].push(c); load[bb] += inst.q[c];
    }
    const routes = [];
    bins.forEach(function (bin) {
      if (!bin.length) return;
      let bd = allowed[0], bc = bin[0], bv = Infinity;
      allowed.forEach(function (d) { bin.forEach(function (c) { if (inst.ddc[d][c] < bv) { bv = inst.ddc[d][c]; bd = d; bc = c; } }); });
      const seq = [bc], left = bin.filter(function (c) { return c !== bc; });
      while (left.length) {
        const last = seq[seq.length - 1]; let bi = 0;
        for (let i = 1; i < left.length; i++) if (inst.dcc[last][left[i]] < inst.dcc[last][left[bi]]) bi = i;
        seq.push(left.splice(bi, 1)[0]);
      }
      routes.push({ depot: bd, seq: seq });
    });
    return { routes: routes };
  }

  // random feasible solution (used by the operator demos): random bins, random sequences, random depots among Ng chosen ones
  function randomSolution(inst, rng) {
    for (let attempt = 0; attempt < 200; attempt++) {
      const allowed = rng.sample(Array.from({ length: inst.m }, function (_, i) { return i; }), Math.min(inst.Ng, inst.m));
      const order = rng.shuffle(Array.from({ length: inst.n }, function (_, i) { return i; }));
      const bins = [], load = [];
      for (let b = 0; b < inst.Nv; b++) { bins.push([]); load.push(0); }
      let ok = true;
      for (let k = 0; k < order.length && ok; k++) {
        const c = order[k], opts = [];
        for (let b = 0; b < inst.Nv; b++) if (load[b] + inst.q[c] <= inst.Q + EPS) opts.push(b);
        if (!opts.length) { ok = false; break; }
        const b = rng.pick(opts); bins[b].push(c); load[b] += inst.q[c];
      }
      if (!ok) continue;
      const routes = [];
      bins.forEach(function (bin) { if (bin.length) routes.push({ depot: rng.pick(allowed), seq: bin }); });
      return { routes: routes };
    }
    return null;
  }

  /* ---------------------------------------------------------------- GRASP + RVND */
  // opts: {iters, rcl, ops, seed}; hooks: {onIter(info)} may return a promise (the loop awaits it, so a UI can stay responsive)
  async function grasp(inst, opts, hooks) {
    const rng = makeRng(opts.seed || 1), stats = newStats(), rcl = opts.rcl || 5;
    const all = Array.from({ length: inst.m }, function (_, i) { return i; });
    let best = null, bestZ = Infinity;
    const history = [], t0 = Date.now();
    for (let it = 0; it < opts.iters; it++) {
      const intensify = (it % 8) >= 5 && best;                                          // 5 diversification + 3 intensification iterations
      const allowed = intensify ? openDepots(best) : rng.sample(all, Math.min(inst.Ng, inst.m));
      let s = null;
      for (let tries = 0; tries < 8 && !s; tries++) s = construct(inst, allowed, rcl, rng);
      if (!s) s = packConstruct(inst, allowed, rng);
      if (!s) { history.push({ it: it, start: null, cost: null, best: bestZ }); continue; }
      const z0 = solCost(inst, s);
      s = rvnd(inst, s, opts.ops, rng, stats);
      const z = solCost(inst, s);
      if (z < bestZ - EPS) { best = s; bestZ = z; }
      const info = { it: it, start: z0, cost: z, best: bestZ, bestSol: best, phase: intensify ? 'intensification' : 'diversification' };
      history.push({ it: it, start: z0, cost: z, best: bestZ });
      if (hooks && hooks.onIter) { const r = hooks.onIter(info); if (r && r.then) await r; }
      if (hooks && hooks.cancelled && hooks.cancelled()) break;
    }
    return { best: best, bestCost: bestZ, history: history, stats: stats, ms: Date.now() - t0 };
  }

  /* ---------------------------------------------------------------- operator demo (a move on a small random instance) */
  function demoFor(op, startSeed, preferImproving) {
    // stage 0 starts from a solution of the savings constructor (clearer pictures), stage 1 from a random solution (always has something to improve)
    let fallback = null;
    for (let stage = 0; stage < 2; stage++) {
      for (let k = 0; k < 60; k++) {
        const seed = startSeed + k;
        const inst = randomInstance({ n: 14, m: 4, Nv: 3, Ng: 2, seed: 100 + seed });
        const rng = makeRng(7000 + seed);
        const sol = stage === 0 ? construct(inst, rng.sample([0, 1, 2, 3], 2), 4, rng) : randomSolution(inst, rng);
        if (!sol) continue;
        const mv = bestMove(inst, sol, op);
        if (!mv) continue;
        const res = { inst: inst, before: sol, after: applyMove(sol, mv), move: mv, delta: mv.delta, seed: seed, improving: mv.delta < -EPS, stage: stage };
        if (!preferImproving) return res;
        if (res.improving && -mv.delta >= 0.015 * solCost(inst, sol)) return res;      // a move large enough to be visible in the picture
        if (res.improving && (!fallback || !fallback.improving)) fallback = res; else if (!fallback) fallback = res;
      }
    }
    return fallback;
  }

  return {
    EPS: EPS, OP_NAMES: OP_NAMES, makeRng: makeRng, makeInstance: makeInstance, randomInstance: randomInstance,
    routeLat: routeLat, routeLoad: routeLoad, arrivals: arrivals, solCost: solCost, cloneSol: cloneSol, openDepots: openDepots, validate: validate,
    bestMove: bestMove, applyMove: applyMove, rvnd: rvnd, construct: construct, packConstruct: packConstruct, randomSolution: randomSolution,
    grasp: grasp, newStats: newStats, demoFor: demoFor
  };
});
