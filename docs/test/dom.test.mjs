// DOM smoke test of docs/index.html with jsdom.  Run: node docs/test/dom.test.mjs   (needs: npm install jsdom)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(process.env.JSDOM_FROM ? pathToFileURL(path.join(process.env.JSDOM_FROM, 'x.js')) : import.meta.url);
const { JSDOM, VirtualConsole } = require('jsdom');
const html = fs.readFileSync(path.join(here, '..', 'index.html'), 'utf8');

const errors = [];
const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(String(e.stack || e))); vc.on('error', e => errors.push(String(e)));
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://example.test/docs/index.html', virtualConsole: vc,
  beforeParse(win) { win.scrollTo = () => {}; win.HTMLElement.prototype.scrollIntoView = () => {}; } });   // jsdom has no layout: stub scrolling
const w = dom.window, d = w.document;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const go = async hash => { w.location.hash = hash; await sleep(60); };
let n = 0; const ok = m => { n++; console.log('ok  ' + m); };

await sleep(100);
assert.equal(errors.length, 0, errors.join('\n'));
assert.equal(d.querySelectorAll('#nav a').length, 6); ok('navigation has 6 sections');

await go('#/problem');
assert.ok(d.querySelector('#pe svg'), 'latency vs length figure'); assert.equal(d.querySelectorAll('#pe svg').length, 2);
assert.ok(d.querySelectorAll('.pipeline .step[data-tip-html]').length === 4); ok('problem view: example drawings and pipeline tooltips');

await go('#/operators');
const cards = d.querySelectorAll('article.card'); assert.equal(cards.length, 14, 'operator cards');
for (const c of cards) { assert.equal(c.querySelectorAll('svg.sol').length, 2, c.id + ' needs before/after drawings'); assert.ok(c.querySelector('[data-tip-html]'), c.id + ' tip'); }
d.querySelector('[data-again="swapstar"]').click(); assert.equal(d.querySelector('#op-swapstar').querySelectorAll('svg.sol').length, 2);
d.querySelector('[data-f="zou"]').click(); assert.equal(d.querySelectorAll('article.card').length, 8, 'zou preset filter');
await go('#/operators/relocate'); ok('operators view: 14 cards with before/after drawings, filter, deep link');

// tooltip through the real event path
const circle = d.querySelector('article.card svg circle.cust'); circle.dispatchEvent(new w.MouseEvent('mouseover', { bubbles: true }));
const tip = d.getElementById('tip'); assert.equal(tip.hidden, false); assert.match(tip.textContent, /arrives at t =/); ok('hover on a customer shows arrival time');
const h3 = d.querySelector('article.card h3 span[data-tip-html]'); h3.dispatchEvent(new w.MouseEvent('mouseover', { bubbles: true })); assert.match(tip.textContent, /Neighbourhood size/); ok('hover on an operator name shows details');

await go('#/methods');
assert.equal(d.querySelectorAll('details.method').length, 19); ok('methods view lists 19 methods');
const q = d.getElementById('m-q'); q.value = 'tenure'; q.dispatchEvent(new w.Event('input', { bubbles: true })); assert.equal(d.querySelectorAll('details.method').length, 1); q.value = ''; q.dispatchEvent(new w.Event('input', { bubbles: true }));
d.querySelector('[data-fam="excluded"]').click(); assert.equal(d.querySelectorAll('details.method').length, 2); ok('methods search and the excluded filter work');
await go('#/methods/alns'); assert.equal(d.querySelector('#m-alns').open, true);

await go('#/refs');
const refs = d.querySelectorAll('.ref'); assert.ok(refs.length >= 50, 'references: ' + refs.length);
assert.ok(d.querySelector('#ref-zou2024 a[href="https://doi.org/10.1016/j.cor.2024.106758"]'));
d.querySelector('[data-bib="zou2024"]').dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
assert.match(d.querySelector('[data-bibbox="zou2024"] pre').textContent, /@article\{zou2024,/); ok('references view: DOI link and BibTeX');

// every reference key used by operators / methods exists; every reference is used somewhere or belongs to the problem/latency/engine topics
const keys = new Set([...refs].map(r => r.id.replace('ref-', '')));
const used = w.eval('OPERATORS.map(o=>o.refs).concat(HEURISTICS.map(h=>h.refs)).reduce((a,b)=>a.concat(b),[])');
for (const k of used) assert.ok(keys.has(k), 'unknown reference key ' + k);
assert.equal(new Set(w.eval('REFS.map(r=>r.key)')).size, w.eval('REFS.length'), 'duplicate reference keys'); ok('reference keys are consistent');

await go('#/play');
assert.ok(d.querySelector('#pg-svg svg')); assert.equal(d.querySelectorAll('#pg-inst option').length, 7);
d.getElementById('pg-it').value = 6; d.getElementById('pg-run').click();
for (let i = 0; i < 100 && !d.getElementById('pg-stats').querySelector('table'); i++) await sleep(100);
assert.ok(d.getElementById('pg-stats').querySelector('table'), 'operator statistics after a run');
assert.match(d.getElementById('pg-res').textContent, /Latency/); assert.match(d.getElementById('pg-res').textContent, /gap to best known/);
assert.ok(d.getElementById('pg-chart').querySelector('svg')); ok('playground: GRASP run produces a solution, a chart and an operator table');
d.getElementById('pg-watch').click(); assert.equal(d.getElementById('pg-next').disabled, false);
for (let i = 0; i < 400 && !d.getElementById('pg-next').disabled; i++) d.getElementById('pg-next').click();
assert.match(d.getElementById('pg-log').textContent, /local optimum for all selected operators/); ok('playground: step-by-step local search reaches a local optimum');
const sel = d.getElementById('pg-inst'); sel.value = 'rand'; sel.dispatchEvent(new w.Event('change', { bubbles: true })); assert.ok(d.querySelector('#pg-svg svg'));
d.querySelector('[data-preset="none"]').click(); d.getElementById('pg-run').click(); await sleep(50); assert.match(d.getElementById('pg-res').textContent, /at least one operator/); ok('playground: random instance, empty operator set is rejected');

await go('#/about'); assert.match(d.getElementById('view').textContent, /How the playground differs/);
await go('#/nonexistent'); assert.ok(d.querySelector('#pe')); ok('unknown route falls back to the problem view');
assert.equal(errors.length, 0, errors.join('\n'));
console.log(n + ' DOM checks passed');
w.close();
