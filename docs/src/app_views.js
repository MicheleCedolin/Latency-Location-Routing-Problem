/* ---- views ---- */
'use strict';
function tunedCount(h) { return h.params.filter(function (p) { return !p.fixed && p.r && p.r !== 'not tuned'; }).length; }
function opId(key) { return 'op-' + key.replace('*', 'star'); }          // '*' is not valid in a CSS id selector
var DEMO = {};           // operator key -> current demo seed
var PRESET_OPS = { legacy5: ['relocate', 'swap11', '2opt', 'swap22', 'swap21'], zou: ['relocate', 'swap11', '2opt', 'oropt2', 'swap21', 'swap22', 'swapstar', 'dexch'], full: L.OP_NAMES.slice(), none: [] };

/* ============================== Problem ============================== */
function permExample(seed) {
  var last = null;
  for (var s = seed; s < seed + 120; s++) {
    var inst = L.randomInstance({ n: 7, m: 1, Nv: 1, Ng: 1, seed: s }), n = inst.n, a = [0, 1, 2, 3, 4, 5, 6], c = [0, 0, 0, 0, 0, 0, 0], i = 1;
    var bestLen = { v: Infinity, p: null }, bestLat = { v: Infinity, p: null };
    function visit(p) {
      var len = inst.ddc[0][p[0]]; for (var j = 1; j < n; j++) len += inst.dcc[p[j - 1]][p[j]];
      if (len < bestLen.v) bestLen = { v: len, p: p.slice() };
      var lat = L.routeLat(inst, 0, p); if (lat < bestLat.v) bestLat = { v: lat, p: p.slice() };
    }
    visit(a);
    while (i < n) { if (c[i] < i) { var k = i % 2 ? c[i] : 0, t = a[k]; a[k] = a[i]; a[i] = t; visit(a); c[i]++; i = 1; } else { c[i] = 0; i++; } }
    var latOfShort = L.routeLat(inst, 0, bestLen.p), lenOfFast = 0; var q = bestLat.p; lenOfFast = inst.ddc[0][q[0]]; for (var j = 1; j < n; j++) lenOfFast += inst.dcc[q[j - 1]][q[j]];
    last = { seed: s, inst: inst, short: bestLen, fast: bestLat, latOfShort: latOfShort, lenOfFast: lenOfFast };
    if (latOfShort > bestLat.v * 1.03 && lenOfFast > bestLen.v * 1.03) return last;
  }
  return last;
}
function viewProblem(root) {
  var ex = L.makeInstance({ dep: [[0, 0]], cust: [[3, 4, 1], [3, 8, 1], [6, 8, 1]], Q: 10, Nv: 1, Ng: 1 }), seq = [0, 1, 2], t = L.arrivals(ex, 0, seq);
  var legs = [ex.ddc[0][0], ex.dcc[0][1], ex.dcc[1][2]], total = L.routeLat(ex, 0, seq);
  root.innerHTML =
    '<h1>The latency location-routing problem</h1>' +
    '<p class="lede">The LLRP asks where to open depots and how to route vehicles from them so that customers are reached as early as possible, on average, not so that the routes are short. This page explains the problem, the local-search operators and the metaheuristics of this repository, and lets you run a small version of the search in your browser.</p>' +
    '<div class="panel"><h2>The problem</h2>' +
    '<ul><li>Given are customers with demands, candidate depots, and at most <b>Nv</b> vehicles of capacity <b>Q</b>. At most <b>Ng</b> depots may be opened. Hover over the terms: ' + kw('latency', 'latency') + ', ' + kw('depot', 'depot') + ', ' + kw('Nv', 'Nv') + ', ' + kw('Ng', 'Ng') + ', ' + kw('Q', 'Q') + '.</li>' +
    '<li>Every route starts at an open depot, visits its customers once and <b>does not return</b>.</li>' +
    '<li>The <b>latency</b> of a customer is the time at which its vehicle arrives. The objective is the <b>sum of the latencies of all customers</b>.</li></ul>' +
    '<p>For a route that visits <i>L</i> customers c<sub>1</sub>, …, c<sub>L</sub> from depot d, the two equal ways to write its latency are</p>' +
    '<p class="mono" style="padding-left:12px">Σ<sub>j</sub> arrival(c<sub>j</sub>) &nbsp;=&nbsp; Σ<sub>j</sub> (L − j + 1) · dist(c<sub>j−1</sub>, c<sub>j</sub>), &nbsp; with c<sub>0</sub> = d.</p>' +
    '<p>The second form shows why latency differs from route length: the first leg is paid by all <i>L</i> customers, the last leg by only one. Customers early in the route are cheap to serve, and a long route makes everyone wait for its first leg.</p>' +
    '<div class="scroll" style="max-width:640px"><table><thead><tr><th>Customer</th><th class="num">Leg length</th><th class="num">Arrival time</th><th class="num">Customers paying this leg</th></tr></thead><tbody>' +
    seq.map(function (c, j) { return '<tr><td>' + (c + 1) + '</td><td class="num">' + fmt(legs[j], 0) + '</td><td class="num">' + fmt(t[j], 0) + '</td><td class="num">' + (seq.length - j) + '</td></tr>'; }).join('') +
    '<tr><td><b>Sum</b></td><td class="num"></td><td class="num"><b>' + fmt(t.reduce(function (a, b) { return a + b; }, 0), 0) + '</b></td><td class="num muted">3·5 + 2·4 + 1·3 = ' + fmt(total, 0) + '</td></tr></tbody></table></div>' +
    '<p class="muted" style="margin-top:8px">Example: depot at (0, 0), customers at (3, 4), (3, 8), (6, 8), visited in this order.</p></div>' +
    '<div class="panel"><h2>The shortest route is not the fastest one</h2>' +
    '<p>Both routes below visit the same 7 customers from one depot. The left route is the shortest; the right one has the lowest sum of arrival times (numbers at the customers are arrival times). Hover over a customer for details. Because of this difference, operators that are exact for distance (such as 2-opt) cannot be evaluated by looking at the changed edges only.</p>' +
    '<div class="row" style="margin-bottom:8px"><button class="btn" id="pe-new" type="button">Another example</button></div><div class="grid" id="pe"></div></div>' +
    '<div class="panel"><h2>How the solver is built</h2><p>The engine of this repository combines two classical ideas, GRASP and RVND. Hover over the steps.</p>' +
    '<div class="pipeline">' +
    '<div class="step" tabindex="0"' + tipHtml('<b>1. Choose depots</b>Pick at most Ng depots. The engine alternates 5 diversification iterations (a new, random depot set) with 3 intensification iterations (the depot set of the best solution so far).') + '><b>1. Choose depots</b>diversify / intensify</div><div class="arrow">→</div>' +
    '<div class="step" tabindex="0"' + tipHtml('<b>2. Construct</b>A Clarke and Wright style savings procedure merges single-customer routes. A ' + GLOSSARY.rcl + ' (width = alpha) randomizes it, so every iteration starts from a different solution.') + '><b>2. Construct</b>savings merging + RCL</div><div class="arrow">→</div>' +
    '<div class="step" tabindex="0"' + tipHtml('<b>3. Improve</b>' + GLOSSARY.rvnd + ' Each operator scans its full neighbourhood and applies the best improving move.') + '><b>3. Improve</b>RVND over the operators</div><div class="arrow">→</div>' +
    '<div class="step" tabindex="0"' + tipHtml('<b>4. Keep the best</b>The best solution over all iterations is returned. Optional extensions of the C++ engine: strategic oscillation (temporarily allowing capacity violations with an adaptive penalty) and iterated local search.') + '><b>4. Keep the best</b>repeat until budget ends</div></div>' +
    '<p>The C++ engine evaluates a move in constant time by concatenating precomputed sub-sequence data (Silva et al., 2012). The page below uses a simpler JavaScript engine that re-evaluates routes from scratch, which is fast enough for instances of 20 to 30 customers. See the <a href="#/play">Playground</a> and the <a href="#/about">About</a> page.</p></div>' +
    '<div class="panel"><h2>Benchmarks</h2><p>The repository covers 76 instances: 10 from Barreto et al. (2007), 30 from Prins et al. (2006) and 36 from Tüzün and Burke (1999), with 20 to 200 customers. The best-known values and their provenance are in <code>bks/LLRP_BKS.csv</code>; the instance files are in <code>cpp/inst/</code>.</p>' +
    '<div class="row"><a class="btn" href="#/operators">Explore the operators</a><a class="btn" href="#/methods">Explore the 19 methods</a><a class="btn" href="#/play">Open the playground</a><a class="btn" href="#/refs">References</a></div></div>';
  var seed = 1;
  function draw() {
    var e = permExample(seed);
    var A = drawSol(e.inst, { routes: [{ depot: 0, seq: e.short.p }] }, { times: true, w: 330, h: 270, label: 'Shortest route' });
    var B = drawSol(e.inst, { routes: [{ depot: 0, seq: e.fast.p }] }, { times: true, w: 330, h: 270, label: 'Lowest latency route' });
    $('#pe').innerHTML = '<figure style="margin:0">' + A + '<figcaption>Shortest route: length ' + fmt(e.short.v, 1) + ', latency ' + fmt(e.latOfShort, 1) + '</figcaption></figure>' +
      '<figure style="margin:0">' + B + '<figcaption>Lowest latency: length ' + fmt(e.lenOfFast, 1) + ', latency <b>' + fmt(e.fast.v, 1) + '</b></figcaption></figure>';
    seed = e.seed + 1;
  }
  $('#pe-new').addEventListener('click', draw); draw();
}

/* ============================== Operators ============================== */
function opTip(o) {
  var pre = o.presets.map(function (p) { return p; }).join(', ');
  return '<b>' + esc(o.label) + ' <span style="opacity:.7;font-weight:400">(' + esc(o.key) + ')</span></b>' + esc(o.what) + '<span class="sub">' + esc(o.latency) + '</span><span class="sub">Neighbourhood size: ' + esc(o.size) + '. In presets: ' + esc(pre) + '.</span>';
}
function renderDemo(card, o, seed) {
  var d = L.demoFor(o.key, seed, true), box = $('[data-demo]', card), dl = $('[data-delta]', card);
  if (!d) { box.innerHTML = '<p class="muted">No move of this type exists on the random example.</p>'; dl.textContent = ''; return; }
  var changed = d.move.changes.map(function (c) { return c.i; }), moved = movedCustomers(d.inst, d.before, d.after);
  box.innerHTML = '<figure>' + drawSol(d.inst, d.before, { w: 300, h: 260, changed: changed, label: o.label + ': before' }) + '<figcaption>before: ' + fmt(L.solCost(d.inst, d.before), 1) + '</figcaption></figure>' +
    '<figure>' + drawSol(d.inst, d.after, { w: 300, h: 260, changed: changed, moved: moved, label: o.label + ': after' }) + '<figcaption>after: ' + fmt(L.solCost(d.inst, d.after), 1) + '</figcaption></figure>';
  dl.innerHTML = 'Best move of this type: <span class="delta ' + (d.delta < 0 ? 'neg' : 'pos') + '">' + (d.delta < 0 ? '' : '+') + fmt(d.delta, 1) + '</span>' + (d.improving ? '' : ' (no improving move here)');
  DEMO[o.key] = d.seed;
}
function viewOperators(root, ctx) {
  var groups = []; OPERATORS.forEach(function (o) { if (groups.indexOf(o.group) < 0) groups.push(o.group); });
  root.innerHTML = '<h1>Local-search operators</h1>' +
    '<p class="lede">Every operator scans its complete neighbourhood and applies the best improving move (or the first one, with <code>--select first</code>). All operators keep the same invariants: no route becomes empty, the number of routes is unchanged, each customer stays in exactly one route, capacity holds, and the set of open depots is unchanged except by the depot-set change <code>ds</code>.</p>' +
    '<p>Each card shows a real best move of that operator on a random 14-customer example (dashed rings: customers whose neighbours changed; thick lines: changed routes). Hover over titles for details and over customers for arrival times.</p>' +
    '<div class="toolbar"><span class="muted">Show:</span><div class="chips" id="op-filter"></div></div><div id="op-groups"></div>' +
    '<div class="panel"><h3>Presets</h3><ul>' + Object.keys(OP_PRESETS).map(function (k) { return '<li><b>' + k + '</b> (' + OP_PRESETS[k].size + '): ' + esc(OP_PRESETS[k].text) + '</li>'; }).join('') + '</ul>' +
    '<p class="muted">Reading the examples: latency is measured as the sum of arrival times. The examples are random and small; they illustrate the move, not typical gains.</p></div>';
  var filter = 'all';
  var chips = [['all', 'All 14']].concat(Object.keys(OP_PRESETS).map(function (k) { return [k, k + ' (' + OP_PRESETS[k].size + ')']; }));
  $('#op-filter').innerHTML = chips.map(function (c) { return '<button class="chip" type="button" data-f="' + c[0] + '" aria-pressed="' + (c[0] === filter) + '">' + esc(c[1]) + '</button>'; }).join('');
  function paint() {
    $('#op-groups').innerHTML = groups.map(function (g) {
      var ops = OPERATORS.filter(function (o) { return o.group === g && (filter === 'all' || o.presets.indexOf(filter) >= 0); });
      if (!ops.length) return '';
      return '<h2 style="margin-top:18px">' + esc(g) + '</h2><div class="grid ops">' + ops.map(function (o) {
        return '<article class="card" id="' + opId(o.key) + '"><h3><span tabindex="0"' + tipHtml(opTip(o)) + '>' + esc(o.label) + '</span><code>' + esc(o.key) + '</code></h3>' +
          '<div><span class="tag">' + esc(o.scope) + '</span>' + o.presets.map(function (p) { return '<span class="tag plain">' + p + '</span>'; }).join('') + '</div>' +
          '<p' + tipHtml(opTip(o)) + '>' + esc(o.short) + '</p><div class="pair" data-demo></div>' +
          '<div class="row"><span class="stat muted" data-delta></span><button class="btn" type="button" data-again="' + o.key + '">Another example</button></div>' +
          '<details><summary>Details</summary><p>' + esc(o.what) + '</p><p>' + esc(o.latency) + '</p><p class="muted">Neighbourhood size: ' + esc(o.size) + '</p><p class="muted">References: ' + refChips(o.refs) + '</p></details></article>';
      }).join('') + '</div>';
    }).join('');
    OPERATORS.forEach(function (o) { var card = document.getElementById(opId(o.key)); if (card) renderDemo(card, o, DEMO[o.key] || 1); });
  }
  root.addEventListener('click', function (e) {
    var f = e.target.closest && e.target.closest('[data-f]'), a = e.target.closest && e.target.closest('[data-again]');
    if (f) { filter = f.getAttribute('data-f'); $$('#op-filter .chip').forEach(function (b) { b.setAttribute('aria-pressed', String(b === f)); }); paint(); }
    if (a) { var o = byKey(OPERATORS, a.getAttribute('data-again')); renderDemo(document.getElementById(opId(o.key)), o, (DEMO[o.key] || 1) + 1); }
  });
  paint();
  if (ctx.sub && document.getElementById(opId(ctx.sub))) { var c = document.getElementById(opId(ctx.sub)); c.scrollIntoView(); c.style.outline = '2px solid var(--accent)'; }
}

/* ============================== Methods ============================== */
function methodHtml(h) {
  var fam = FAMILIES.filter(function (f) { return f[0] === h.family; })[0];
  return '<details class="method" id="m-' + h.key + '"' + tipHtml('<b>' + esc(h.name) + '</b>' + esc(h.summary)) + '><summary><span class="nm">' + esc(h.name) + '</span><span>' + esc(h.summary) + '</span>' +
    '<span class="tg"><span class="tag">' + esc(fam[1]) + '</span>' + (h.campaign ? '' : '<span class="tag warn">excluded</span>') + '</span><span class="muted mono">' + (tunedCount(h) ? tunedCount(h) + ' tuned parameter' + (tunedCount(h) > 1 ? 's' : '') : 'no tuned parameters') + '</span></summary>' +
    '<div class="body"><div>' + (h.excluded ? '<p class="note"><b>Why excluded.</b> ' + esc(h.excluded) + '</p>' : '') + '<h4>How it works here</h4><ol>' + h.steps.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ol>' +
    '<p class="muted">References: ' + refChips(h.refs) + '</p>' + (h.note ? '<p class="muted">' + esc(h.note) + '</p>' : '') + '</div>' +
    '<div class="scroll"><h4>Parameters</h4><table><thead><tr><th>Name</th><th class="num">Default</th><th>Tuning range</th></tr></thead><tbody>' +
    h.params.map(function (p) { return '<tr' + tipText(p.m) + '><td class="mono">' + esc(p.c) + '</td><td class="num">' + esc(p.d) + '</td><td class="mono">' + (p.fixed ? '<span class="muted">fixed budget</span>' : esc(p.r || '')) + '</td></tr>'; }).join('') + '</tbody></table>' +
    '<p class="muted" style="margin-top:6px">Hover over a row for the meaning of the parameter. “Tuning range” is the interval explored by irace; fixed budget parameters were not tuned.</p></div></div></details>';
}
function viewMethods(root, ctx) {
  root.innerHTML = '<h1>The 19 metaheuristics</h1>' +
    '<p class="lede">All methods are implemented in <code>python/llrp_framework/heuristics.py</code> on top of the same constructors, neighbourhoods and local searches, so that differences in results come from the search strategy. 17 of them take part in the comparison campaign; two are kept for regression tests only, with the reason given.</p>' +
    '<div class="panel"><h2>What all methods share</h2><dl style="margin:0;display:grid;grid-template-columns:max-content 1fr;gap:6px 14px">' + SHARED_FRAME.map(function (p) { return '<dt><b>' + esc(p[0]) + '</b></dt><dd style="margin:0;max-width:72ch">' + esc(p[1]) + '</dd>'; }).join('') + '</dl></div>' +
    '<div class="toolbar"><input type="search" id="m-q" placeholder="Search a method or parameter (e.g. tabu, evaporation, cr)" aria-label="Search methods" style="flex:1 1 260px"><span class="muted" id="m-n"></span>' +
    '<button class="btn" id="m-open" type="button">Expand all</button><button class="btn" id="m-close" type="button">Collapse all</button></div>' +
    '<div class="chips" id="m-fam" style="margin-bottom:12px"></div><div id="m-list"></div>';
  var fam = 'all', term = '';
  $('#m-fam').innerHTML = [['all', 'All']].concat(FAMILIES.map(function (f) { return [f[0], f[1]]; })).concat([['excluded', 'Excluded']]).map(function (c) { return '<button class="chip" type="button" data-fam="' + c[0] + '" aria-pressed="' + (c[0] === fam) + '"' + (c[0] !== 'all' && c[0] !== 'excluded' ? tipText(FAMILIES.filter(function (f) { return f[0] === c[0]; })[0][2]) : '') + '>' + esc(c[1]) + '</button>'; }).join('');
  function paint() {
    var list = HEURISTICS.filter(function (h) {
      if (fam === 'excluded' && h.campaign) return false;
      if (fam !== 'all' && fam !== 'excluded' && h.family !== fam) return false;
      if (!term) return true;
      var hay = (h.name + ' ' + h.summary + ' ' + h.steps.join(' ') + ' ' + h.params.map(function (p) { return p.c + ' ' + p.m; }).join(' ')).toLowerCase();
      return hay.indexOf(term) >= 0;
    });
    $('#m-list').innerHTML = list.map(methodHtml).join('') || '<p class="muted">No method matches.</p>';
    $('#m-n').textContent = list.length + ' of ' + HEURISTICS.length;
  }
  root.addEventListener('input', function (e) { if (e.target.id === 'm-q') { term = e.target.value.trim().toLowerCase(); paint(); } });
  root.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-fam]');
    if (b) { fam = b.getAttribute('data-fam'); $$('#m-fam .chip').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); }); paint(); }
    if (e.target.id === 'm-open') $$('details.method').forEach(function (d) { d.open = true; });
    if (e.target.id === 'm-close') $$('details.method').forEach(function (d) { d.open = false; });
  });
  paint();
  if (ctx.sub && $('#m-' + ctx.sub)) { var d = $('#m-' + ctx.sub); d.open = true; d.scrollIntoView(); }
}

/* ============================== Playground ============================== */
function viewPlay(root, ctx) {
  var S = { inst: null, sol: null, bestCost: Infinity, hist: [], running: false, cancel: false, ls: null, timer: null }, gens = 0;
  var opOpts = L.OP_NAMES.map(function (k) { var o = byKey(OPERATORS, k); return '<label' + tipHtml('<b>' + esc(o.label) + '</b>' + esc(o.short)) + '><input type="checkbox" data-op="' + k + '" checked> ' + esc(o.label) + '</label>'; }).join('');
  root.innerHTML = '<h1>Playground</h1>' +
    '<p class="lede">Run a small GRASP + RVND search on a benchmark instance or a random one, choose which operators it may use, and watch what each of them contributes. The engine here is a simplified JavaScript version of the C++ solver, meant for learning; see About for the differences.</p>' +
    '<div class="cols"><div><div class="panel"><div id="pg-info" class="muted" style="margin-bottom:8px"></div><div id="pg-svg"></div><div id="pg-res" style="margin-top:8px" aria-live="polite"></div></div>' +
    '<div class="panel"><h3>Convergence</h3><div id="pg-chart"><p class="muted">Run the search to see it.</p></div></div>' +
    '</div>' +
    '<div><div class="panel"><h3>Instance</h3><div class="ctl"><label for="pg-inst">Instance</label><select id="pg-inst"></select></div>' +
    '<div id="pg-rand" class="ctl"><label for="r-n">Customers</label><input id="r-n" type="number" min="8" max="40" value="20"><label for="r-m">Depots</label><input id="r-m" type="number" min="2" max="6" value="5"><label for="r-v">Routes (Nv)</label><input id="r-v" type="number" min="1" max="8" value="4"><label for="r-g">Open depots (Ng)</label><input id="r-g" type="number" min="1" max="6" value="2"><label for="r-s">Random seed</label><input id="r-s" type="number" min="1" value="1"><label for="r-c">Clustered</label><input id="r-c" type="checkbox"></div>' +
    '<button class="btn" id="pg-gen" type="button">Generate</button></div>' +
    '<div class="panel"><h3>Operators</h3><div class="row" style="margin-bottom:6px"><span class="muted">Preset:</span>' + ['legacy5', 'zou', 'full', 'none'].map(function (k) { return '<button class="btn" type="button" data-preset="' + k + '">' + k + '</button>'; }).join('') + '</div><div class="opbox" id="pg-ops">' + opOpts + '</div></div>' +
    '<div class="panel"><h3>Search</h3><div class="ctl"><label for="pg-it">GRASP iterations</label><input id="pg-it" type="number" min="1" max="200" value="24"><label for="pg-rcl">RCL width' + '</label><input id="pg-rcl" type="number" min="1" max="10" value="5"><label for="pg-seed">Seed</label><input id="pg-seed" type="number" min="1" value="1"><label for="pg-times">Show arrival times</label><input id="pg-times" type="checkbox"></div>' +
    '<div class="row"><button class="btn primary" id="pg-run" type="button">Run GRASP</button><button class="btn" id="pg-stop" type="button" disabled>Stop</button></div>' +
    '<h4 style="margin-top:14px">Or watch one local search, move by move</h4><div class="row"><button class="btn" id="pg-watch" type="button">Construct a solution</button><button class="btn" id="pg-next" type="button" disabled>Next step</button><button class="btn" id="pg-auto" type="button" disabled>Auto-play</button></div>' +
    '<div class="log" id="pg-log" style="margin-top:8px" aria-live="polite"></div></div></div></div>' +
    '<div class="panel"><h3>What did each operator do?</h3><div id="pg-stats"><p class="muted">After a run, the table shows for every operator how often it was called, how many moves it evaluated, how many it applied and how much latency it removed.</p></div></div>';
  var $i = function (id) { return document.getElementById(id); };
  var sel = $i('pg-inst'); sel.innerHTML = INSTANCES.map(function (d, k) { return '<option value="' + k + '">' + esc(d.name) + ' (n=' + d.cust.length + ', best known ' + d.bks + ')</option>'; }).join('') + '<option value="rand">Random instance…</option>';
  function ops() { return $$('#pg-ops input:checked').map(function (c) { return c.getAttribute('data-op'); }); }
  function setOps(list) { $$('#pg-ops input').forEach(function (c) { c.checked = list.indexOf(c.getAttribute('data-op')) >= 0; }); }
  function log(text, cls) { var d = document.createElement('div'); d.textContent = text; if (cls) d.className = cls; var b = $i('pg-log'); b.appendChild(d); b.scrollTop = b.scrollHeight; while (b.childNodes.length > 300) b.removeChild(b.firstChild); }
  function draw(sol, o) {
    o = o || {}; o.w = 520; o.h = 400; o.times = $i('pg-times').checked; o.focusable = true; o.label = 'Current solution';
    $i('pg-svg').innerHTML = drawSol(S.inst, sol, o);
    var z = L.solCost(S.inst, sol), gap = S.inst.bks ? ' · gap to best known ' + (z >= S.inst.bks ? '+' : '') + fmt(100 * (z - S.inst.bks) / S.inst.bks, 2) + ' %' : '';
    $i('pg-res').innerHTML = 'Latency <b class="stat">' + fmt(z, 2) + '</b>' + gap + ' · routes ' + sol.routes.length + ' · open depots ' + L.openDepots(sol).map(function (d) { return 'D' + (d + 1); }).join(', ');
  }
  function loadInstance() {
    stop(); var v = sel.value, inst;
    $i('pg-rand').style.display = v === 'rand' ? '' : 'none'; $i('pg-gen').style.display = v === 'rand' ? '' : 'none';
    if (v === 'rand') inst = L.randomInstance({ n: +$i('r-n').value, m: +$i('r-m').value, Nv: +$i('r-v').value, Ng: +$i('r-g').value, seed: +$i('r-s').value, clustered: $i('r-c').checked });
    else { var d = INSTANCES[+v]; inst = L.makeInstance(d); inst.name = d.name; }
    S.inst = inst; S.sol = null; S.bestCost = Infinity; S.hist = []; S.ls = null;
    $i('pg-info').innerHTML = '<b>' + esc(inst.name) + '</b> · ' + inst.n + ' customers · ' + inst.m + ' depots · at most ' + inst.Nv + ' routes and ' + inst.Ng + ' open depots · capacity ' + inst.Q + (inst.bks ? ' · best known ' + inst.bks : '');
    $i('pg-svg').innerHTML = drawSol(inst, { routes: [] }, { w: 520, h: 400, label: 'Instance' }); $i('pg-res').textContent = 'Customers are shown without routes. Press “Run GRASP” or construct a solution to watch the local search.';
    $i('pg-chart').innerHTML = '<p class="muted">Run the search to see it.</p>'; $i('pg-log').innerHTML = '';
    $i('pg-it').max = inst.n > 30 ? 30 : 200; if (+$i('pg-it').value > +$i('pg-it').max) $i('pg-it').value = $i('pg-it').max;
    $i('pg-next').disabled = true; $i('pg-auto').disabled = true;
  }
  function setBusy(b) { S.running = b; $i('pg-run').disabled = b; $i('pg-stop').disabled = !b; $i('pg-watch').disabled = b; }
  function stop() { S.cancel = true; stopAuto(); }
  function stopAuto() { if (S.timer) { clearInterval(S.timer); S.timer = null; } $i('pg-auto').textContent = 'Auto-play'; }
  function statsTable(stats, total) {
    var rows = L.OP_NAMES.map(function (k) { return { k: k, s: stats[k] }; }).filter(function (r) { return r.s.calls > 0; }).sort(function (a, b) { return b.s.gain - a.s.gain; }), g = rows.reduce(function (a, r) { return a + r.s.gain; }, 0) || 1;
    return '<div class="scroll"><table class="nw"><thead><tr><th>Operator</th><th class="num">Calls</th><th class="num">Moves evaluated</th><th class="num">Applied</th><th class="num">Latency removed</th><th>Share</th><th class="num">ms</th></tr></thead><tbody>' +
      rows.map(function (r) { var o = byKey(OPERATORS, r.k); return '<tr><td' + tipHtml('<b>' + esc(o.label) + '</b>' + esc(o.short)) + '>' + esc(o.label) + '</td><td class="num">' + r.s.calls + '</td><td class="num">' + r.s.evals + '</td><td class="num">' + r.s.applied + '</td><td class="num">' + fmt(r.s.gain, 1) + '</td><td><span class="bar" style="width:' + Math.round(100 * r.s.gain / g) + 'px"></span> ' + Math.round(100 * r.s.gain / g) + ' %</td><td class="num">' + r.s.ms + '</td></tr>'; }).join('') + '</tbody></table></div>' +
      '<p class="muted" style="margin-top:6px">“Latency removed” adds the gains of all applied moves, including those on solutions that later turned out worse than the best. The share depends on the order in which the operators are tried (RVND shuffles it), so the first operators to run take the easy gains.</p>';
  }
  async function run() {
    var list = ops(); if (!list.length) { $i('pg-res').textContent = 'Select at least one operator.'; return; }
    stop(); await sleep(0); S.cancel = false; setBusy(true); S.hist = []; S.sol = null; S.bestCost = Infinity; $i('pg-log').innerHTML = '';
    var iters = Math.max(1, Math.min(+$i('pg-it').max, +$i('pg-it').value || 1));
    var res = await L.grasp(S.inst, { iters: iters, rcl: Math.max(1, +$i('pg-rcl').value || 5), ops: list, seed: +$i('pg-seed').value || 1 }, {
      cancelled: function () { return S.cancel; },
      onIter: function (info) {
        S.hist.push({ it: info.it, start: info.start, cost: info.cost, best: info.best });
        if (info.best < S.bestCost - 1e-9) { S.bestCost = info.best; S.sol = info.bestSol; draw(S.sol); log('iteration ' + (info.it + 1) + ' (' + info.phase + '): new best ' + fmt(info.best, 2), 'imp'); }
        $i('pg-chart').innerHTML = chartHistory(S.hist, S.inst.bks, 520, 190);
        return sleep(0);
      } });
    setBusy(false);
    if (!res.best) { $i('pg-res').textContent = 'No feasible solution could be constructed with this instance and setting.'; return; }
    $i('pg-stats').innerHTML = statsTable(res.stats, res.bestCost);
    log('finished: ' + S.hist.length + ' iterations in ' + res.ms + ' ms' + (S.cancel ? ' (stopped)' : ''), 'no');
  }
  function watchStart() {
    var list = ops(); if (!list.length) { $i('pg-res').textContent = 'Select at least one operator.'; return; }
    stop(); S.cancel = false; var rng = L.makeRng(+$i('pg-seed').value || 1), inst = S.inst;
    var allowed = rng.sample(Array.from({ length: inst.m }, function (_, i) { return i; }), Math.min(inst.Ng, inst.m)), s = null, rcl = Math.max(1, +$i('pg-rcl').value || 5);
    for (var t = 0; t < 8 && !s; t++) s = L.construct(inst, allowed, rcl, rng); if (!s) s = L.packConstruct(inst, allowed, rng);
    if (!s) { $i('pg-res').textContent = 'No feasible solution could be constructed.'; return; }
    S.ls = { cur: s, list: rng.shuffle(list.slice()), k: 0, rng: rng, done: false, ops: list, n: 0 };
    $i('pg-log').innerHTML = ''; draw(s); log('constructed solution (savings merging with RCL): ' + fmt(L.solCost(inst, s), 2));
    log('operator order (shuffled): ' + S.ls.list.join(', ')); $i('pg-next').disabled = false; $i('pg-auto').disabled = false;
  }
  function watchStep() {
    var ls = S.ls; if (!ls || ls.done) return;
    var op = ls.list[ls.k], mv = L.bestMove(S.inst, ls.cur, op);
    if (mv && mv.delta < -L.EPS) {
      var nxt = L.applyMove(ls.cur, mv); draw(nxt, { changed: mv.changes.map(function (c) { return c.i; }), moved: movedCustomers(S.inst, ls.cur, nxt) });
      ls.cur = nxt; ls.n++; log(op + ': improving move, change ' + fmt(mv.delta, 2) + ' → ' + fmt(L.solCost(S.inst, nxt), 2) + ' (' + mv.desc.text + '); order reshuffled', 'imp');
      ls.list = ls.rng.shuffle(ls.ops.slice()); ls.k = 0;
    } else { log(op + ': no improving move' + (mv ? ' (best change ' + fmt(mv.delta, 2) + ')' : ' (neighbourhood empty)'), 'no'); ls.k++; }
    if (ls.k >= ls.list.length) { ls.done = true; stopAuto(); $i('pg-next').disabled = true; $i('pg-auto').disabled = true; log('local optimum for all selected operators after ' + ls.n + ' improving moves: ' + fmt(L.solCost(S.inst, ls.cur), 2), 'imp'); }
  }
  sel.addEventListener('change', loadInstance); $i('pg-gen').addEventListener('click', loadInstance);
  $i('pg-run').addEventListener('click', run); $i('pg-stop').addEventListener('click', stop); $i('pg-watch').addEventListener('click', watchStart); $i('pg-next').addEventListener('click', watchStep);
  $i('pg-auto').addEventListener('click', function () { if (S.timer) { stopAuto(); return; } $i('pg-auto').textContent = 'Pause'; S.timer = setInterval(watchStep, 450); });
  $i('pg-times').addEventListener('change', function () { var s = S.ls ? S.ls.cur : S.sol; if (s) draw(s); });
  $i('pg-ops').parentNode.addEventListener('click', function (e) { var p = e.target.getAttribute && e.target.getAttribute('data-preset'); if (p) setOps(PRESET_OPS[p]); });
  ctx.cleanup = function () { S.cancel = true; stopAuto(); };
  loadInstance();
}

/* ============================== References ============================== */
var TOPICS = [['problem', 'The problem and its benchmarks'], ['latency', 'Latency and the minimum latency problem'], ['ls', 'Local search, construction and neighbourhoods'], ['engine', 'Engine components and tuning'], ['meta', 'Metaheuristics']];
function viewRefs(root, ctx) {
  root.innerHTML = '<h1>References</h1><p class="lede">Every operator and method in this guide points here. A DOI or arXiv link is shown only where it was checked; every entry also has Google Scholar and Crossref search links that always work. Please verify bibliographic details against the publisher before citing.</p>' +
    '<div class="toolbar"><input type="search" id="r-q" placeholder="Search authors, titles, years" aria-label="Search references" style="flex:1 1 260px"><span class="muted" id="r-n"></span><button class="btn" id="r-all" type="button">Copy all BibTeX</button><button class="btn" id="r-dl" type="button">Download .bib</button></div><div id="r-list"></div>';
  var term = '';
  function paint() {
    var out = [], n = 0;
    TOPICS.forEach(function (t) {
      var items = REFS.filter(function (r) { return r.topic === t[0] && (!term || (r.authors + ' ' + r.title + ' ' + r.year).toLowerCase().indexOf(term) >= 0); }).sort(function (a, b) { return a.authors.localeCompare(b.authors) || a.year - b.year; });
      if (!items.length) return; n += items.length;
      out.push('<h2 style="margin-top:20px">' + esc(t[1]) + '</h2>' + items.map(function (r) {
        var by = citedBy(r.key);
        return '<div class="ref" id="ref-' + r.key + '"><p class="cite">' + refCite(r) + '</p><div class="links">' + refLinks(r) + ' · <a href="#" data-bib="' + r.key + '">BibTeX</a></div>' +
          (by.length ? '<div class="used">Cited in: ' + by.map(function (b) { return '<a href="#/' + b.kind + '/' + b.key + '">' + esc(b.label) + '</a>'; }).join(', ') + '</div>' : '') + '<div data-bibbox="' + r.key + '"></div></div>';
      }).join(''));
    });
    $('#r-list').innerHTML = out.join('') || '<p class="muted">No reference matches.</p>'; $('#r-n').textContent = n + ' of ' + REFS.length;
  }
  function allBib() { return '% LLRP Lab references. Check every entry against the publisher record before use.\n\n' + REFS.map(bibtex).join('\n\n') + '\n'; }
  function copy(text, btn) {
    var done = function () { if (btn) { var o = btn.textContent; btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = o; }, 1200); } };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () { }); else { var ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); done(); } catch (e) { } document.body.removeChild(ta); }
  }
  root.addEventListener('input', function (e) { if (e.target.id === 'r-q') { term = e.target.value.trim().toLowerCase(); paint(); } });
  root.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-bib]');
    if (b) { e.preventDefault(); var box = $('[data-bibbox="' + b.getAttribute('data-bib') + '"]'), r = byKey(REFS, b.getAttribute('data-bib')); box.innerHTML = box.innerHTML ? '' : '<pre class="bib">' + esc(bibtex(r)) + '</pre><button class="btn" type="button" data-copy="' + r.key + '">Copy</button>'; }
    var c = e.target.closest && e.target.closest('[data-copy]'); if (c) copy(bibtex(byKey(REFS, c.getAttribute('data-copy'))), c);
    if (e.target.id === 'r-all') copy(allBib(), e.target);
    if (e.target.id === 'r-dl') { var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([allBib()], { type: 'text/plain' })); a.download = 'llrp-lab-references.bib'; document.body.appendChild(a); a.click(); document.body.removeChild(a); }
  });
  paint();
  if (ctx.sub && $('#ref-' + ctx.sub)) { var r = $('#ref-' + ctx.sub); r.classList.add('hl'); r.scrollIntoView(); }
}

/* ============================== About ============================== */
function viewAbout(root) {
  var repo = 'https://github.com/MicheleCedolin/Latency-Location-Routing-Problem';
  root.innerHTML = '<h1>About this guide</h1><div class="panel"><h2>What is here</h2><ul>' +
    '<li><b>Operators</b>: the 14 neighbourhoods of the local-search library, with a worked move for each.</li>' +
    '<li><b>Methods</b>: the 19 metaheuristics of the Python framework, with steps, parameters, tuning ranges and references.</li>' +
    '<li><b>Playground</b>: GRASP + RVND in your browser, with per-operator statistics and a move-by-move local search.</li>' +
    '<li><b>References</b>: papers with DOI or arXiv links where checked, search links for all, and BibTeX.</li></ul></div>' +
    '<div class="panel"><h2>How the playground differs from the research code</h2><ul>' +
    '<li>It is a JavaScript re-implementation written for explanation. It re-evaluates every candidate route from scratch; the C++ engine evaluates moves in constant time and is orders of magnitude faster.</li>' +
    '<li>Capacity is a hard constraint. The C++ engine can also use strategic oscillation (adaptive penalty on capacity violation) and iterated local search.</li>' +
    '<li>The construction is a simple savings procedure with a restricted candidate list, with a packing fallback for tight capacities. It is not tuned.</li>' +
    '<li>Results therefore differ from the published or repository results. Use the playground to understand the operators, and the C++ engine for experiments.</li></ul></div>' +
    '<div class="panel"><h2>Run the real code</h2><p>Source, instances, best-known values and build instructions are in the <a href="' + repo + '" target="_blank" rel="noopener">repository</a>.</p>' +
    '<pre class="bib">git clone ' + repo + '.git\ncd Latency-Location-Routing-Problem\n# C++ engine\nmake -C cpp\n# Python framework\npython3 python/run_llrp.py --help\n# rebuild this page after editing docs/src\npython3 docs/build.py\n# test the playground engine\nnode docs/test/engine.test.mjs</pre>' +
    '<p class="muted" style="margin-top:8px">See the README files in the repository for the exact commands of each component.</p></div>';
}
