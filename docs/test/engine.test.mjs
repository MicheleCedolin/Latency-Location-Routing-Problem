// Tests of the toy engine (docs/src/engine.js).  Run: node docs/test/engine.test.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const L = require('../src/engine.js');
const here = path.dirname(fileURLToPath(import.meta.url));

let passed = 0;
const queue = [];
function test(name, fn) { queue.push([name, fn]); }
const close = (a, b, eps = 1e-7) => assert.ok(Math.abs(a - b) <= eps * Math.max(1, Math.abs(a), Math.abs(b)), a + ' != ' + b);

function parseInst(file) {                       // cpp/inst/*.inst
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
  const kv = {}, dep = [], cust = []; let mode = 'h';
  for (const ln of lines) {
    const t = ln.trim(); if (!t) continue;
    if (t === 'depots') { mode = 'd'; continue; } if (t === 'customers') { mode = 'c'; continue; }
    const p = t.split(/\s+/);
    if (mode === 'h') kv[p[0]] = p[1]; else if (mode === 'd') dep.push([+p[0], +p[1]]); else cust.push([+p[0], +p[1], +p[2]]);
  }
  return L.makeInstance({ name: kv.name, dep, cust, Q: +kv.Q, Nv: +kv.Nv, Ng: +kv.Ng, bks: +kv.bks });
}

test('latency = sum of arrival times (hand example)', () => {
  const inst = L.makeInstance({ dep: [[0, 0]], cust: [[3, 4, 1], [3, 8, 1], [6, 8, 1]], Q: 10, Nv: 1, Ng: 1 });
  // arrivals: 5, 9, 12  -> 26 ; formula 3*5 + 2*4 + 1*3 = 26
  close(L.routeLat(inst, 0, [0, 1, 2]), 26);
  const t = L.arrivals(inst, 0, [0, 1, 2]); close(t[0], 5); close(t[1], 9); close(t[2], 12);
  close(t.reduce((a, b) => a + b, 0), L.routeLat(inst, 0, [0, 1, 2]));
  close(L.routeLat(inst, 0, []), 0);
});

test('every operator: delta equals the recomputed cost change; invariants hold', () => {
  let moves = 0;
  for (let seed = 1; seed <= 12; seed++) {
    const inst = L.randomInstance({ n: 12 + (seed % 4) * 2, m: 4, Nv: 3 + (seed % 2), Ng: 2, seed });
    const sol = L.randomSolution(inst, L.makeRng(seed));
    assert.ok(sol && L.validate(inst, sol).ok);
    for (const op of L.OP_NAMES) {
      const mv = L.bestMove(inst, sol, op);
      if (!mv) continue;
      const after = L.applyMove(sol, mv);
      const v = L.validate(inst, after); assert.ok(v.ok, op + ': ' + v.errors.join('; '));
      close(L.solCost(inst, after) - L.solCost(inst, sol), mv.delta, 1e-9);
      assert.equal(after.routes.length, sol.routes.length, op + ' changed the number of routes');
      if (op !== 'ds') assert.deepEqual(L.openDepots(after), L.openDepots(sol), op + ' changed the open-depot set');
      moves++;
    }
  }
  assert.ok(moves > 100, 'too few moves were generated: ' + moves);
});

test('best move is really the best of its neighbourhood (relocate, brute force)', () => {
  const inst = L.randomInstance({ n: 10, m: 3, Nv: 3, Ng: 2, seed: 5 });
  const sol = L.randomSolution(inst, L.makeRng(5)), base = L.solCost(inst, sol);
  let best = Infinity;
  sol.routes.forEach((ra, a) => ra.seq.forEach((c, i) => sol.routes.forEach((rb, b) => {
    const restA = ra.seq.filter((_, k) => k !== i);
    if (a !== b && !restA.length) return;
    const tgt = a === b ? restA : rb.seq;
    for (let q = 0; q <= tgt.length; q++) {
      const routes = sol.routes.map(r => ({ depot: r.depot, seq: r.seq.slice() }));
      routes[a].seq = restA; const t2 = a === b ? restA.slice() : rb.seq.slice(); t2.splice(q, 0, c); routes[b].seq = t2;
      if (a === b && q === i) continue;
      if (routes.some(r => L.routeLoad(inst, r.seq) > inst.Q + 1e-9)) continue;
      best = Math.min(best, L.solCost(inst, { routes }) - base);
    }
  })));
  close(L.bestMove(inst, sol, 'relocate').delta, best, 1e-9);
});

test('rvnd ends in a local optimum of all its operators', () => {
  const inst = L.randomInstance({ n: 14, m: 4, Nv: 3, Ng: 2, seed: 3 });
  const rng = L.makeRng(3), s0 = L.randomSolution(inst, rng), z0 = L.solCost(inst, s0);
  const s1 = L.rvnd(inst, s0, L.OP_NAMES, rng, L.newStats());
  assert.ok(L.solCost(inst, s1) <= z0 + 1e-9);
  assert.ok(L.validate(inst, s1).ok);
  for (const op of L.OP_NAMES) { const mv = L.bestMove(inst, s1, op); assert.ok(!mv || mv.delta >= -1e-9, op + ' still improves'); }
});

test('construction is feasible and GRASP is deterministic and monotone', async () => {
  const inst = L.randomInstance({ n: 16, m: 4, Nv: 4, Ng: 2, seed: 9 });
  const a = await L.grasp(inst, { iters: 6, rcl: 5, ops: ['relocate', 'swap11', '2opt', 'dexch', 'ds'], seed: 4 });
  const b = await L.grasp(inst, { iters: 6, rcl: 5, ops: ['relocate', 'swap11', '2opt', 'dexch', 'ds'], seed: 4 });
  assert.equal(a.bestCost, b.bestCost);
  assert.ok(L.validate(inst, a.best).ok);
  for (let i = 1; i < a.history.length; i++) assert.ok(a.history[i].best <= a.history[i - 1].best + 1e-12);
  close(L.solCost(inst, a.best), a.bestCost);
});

test('demo helper returns a before/after pair for every operator', () => {
  for (const op of L.OP_NAMES) {
    const d = L.demoFor(op, 1, true);
    assert.ok(d, 'no demo for ' + op);
    close(L.solCost(d.inst, d.after) - L.solCost(d.inst, d.before), d.delta, 1e-9);
  }
});

const instDir = path.resolve(here, '../../cpp/inst');
if (fs.existsSync(instDir)) {
  test('real benchmark instances: feasible solutions, close to the best-known value', async () => {
    for (const f of ['prins/20-5-1b-5.inst', 'prins/20-5-2b-5.inst', 'barreto/Gaskell29-5.inst']) {
      const inst = parseInst(path.join(instDir, f));
      const r = await L.grasp(inst, { iters: 24, rcl: 5, ops: L.OP_NAMES, seed: 1 });
      assert.ok(r.best, f + ': no solution');
      assert.ok(L.validate(inst, r.best).ok, f);
      const gap = 100 * (r.bestCost - inst.bks) / inst.bks;
      console.log('     ' + inst.name + ': ' + r.bestCost.toFixed(2) + ' vs BKS ' + inst.bks + ' (gap ' + gap.toFixed(2) + ' %, ' + r.ms + ' ms)');
      assert.ok(gap > -0.5 && gap < 8, f + ' gap ' + gap);
    }
  });
}
for (const [name, fn] of queue) { await fn(); passed++; console.log('ok  ' + name); }
console.log(passed + ' tests passed');
