/* ---- helpers shared by all views: DOM, tooltips, drawing, references ---- */
'use strict';
var L = self.LLRP;
function $(s, r) { return (r || document).querySelector(s); }
function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
function byKey(list, key) { for (var i = 0; i < list.length; i++) if (list[i].key === key) return list[i]; return null; }
function tipHtml(html) { return ' data-tip-html="' + esc(html) + '"'; }
function tipText(text) { return ' data-tip="' + esc(text) + '"'; }
function kw(term, label) { return '<span class="k" tabindex="0"' + tipText(GLOSSARY[term] || '') + '>' + esc(label || term) + '</span>'; }
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

/* ---- tooltip: one floating element, driven by data-tip / data-tip-html on hover, focus and tap ---- */
var TIP = { el: null, owner: null };
function initTooltip() {
  var t = document.createElement('div'); t.id = 'tip'; t.setAttribute('role', 'tooltip'); t.hidden = true; document.body.appendChild(t); TIP.el = t;
  function find(n) { return n && n.closest ? n.closest('[data-tip],[data-tip-html]') : null; }
  document.addEventListener('mouseover', function (e) { var n = find(e.target); if (n) showTip(n); else hideTip(); });
  document.addEventListener('focusin', function (e) { var n = find(e.target); if (n) showTip(n); });
  document.addEventListener('focusout', hideTip);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hideTip(); });
  document.addEventListener('scroll', hideTip, true);
  document.addEventListener('click', function (e) {                                 // touch screens have no hover: a tap toggles the tip
    if (!window.matchMedia || !window.matchMedia('(hover: none)').matches) return;
    var n = find(e.target);
    if (n && n !== TIP.owner) { showTip(n); } else hideTip();
  });
}
function showTip(n) {
  var h = n.getAttribute('data-tip-html'), t = TIP.el;
  if (h != null) t.innerHTML = h; else t.textContent = n.getAttribute('data-tip');
  t.hidden = false; TIP.owner = n;
  var r = n.getBoundingClientRect(), tw = t.offsetWidth, th = t.offsetHeight, vw = document.documentElement.clientWidth, vh = window.innerHeight;
  var x = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), Math.max(8, vw - tw - 8));
  var y = r.bottom + 8; if (y + th > vh - 8) y = Math.max(8, r.top - th - 8);
  t.style.left = x + 'px'; t.style.top = y + 'px';
}
function hideTip() { if (TIP.el) { TIP.el.hidden = true; TIP.owner = null; } }

/* ---- drawing of instances and solutions (SVG as a string) ---- */
var PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9', '#8E6C8A', '#7F7F7F'];
function fmt(x, d) { return Number(x).toFixed(d == null ? 1 : d); }
function drawSol(inst, sol, o) {
  o = o || {};
  var W = o.w || 360, H = o.h || 300, pad = 18, xs = [], ys = [];
  inst.dep.forEach(function (d) { xs.push(d[0]); ys.push(d[1]); });
  inst.cust.forEach(function (c) { xs.push(c[0]); ys.push(c[1]); });
  var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
  var sc = Math.min((W - 2 * pad) / Math.max(1e-9, x1 - x0), (H - 2 * pad) / Math.max(1e-9, y1 - y0));
  var ox = pad + ((W - 2 * pad) - (x1 - x0) * sc) / 2, oy = pad + ((H - 2 * pad) - (y1 - y0) * sc) / 2;
  var X = function (x) { return ox + (x - x0) * sc; }, Y = function (y) { return H - (oy + (y - y0) * sc); };
  var changed = o.changed || null, moved = o.moved || {}, out = [], open = {}, nCust = {}, routeOf = [], posOf = [], lens = [];
  sol.routes.forEach(function (r, i) { open[r.depot] = (open[r.depot] || 0) + 1; nCust[r.depot] = (nCust[r.depot] || 0) + r.seq.length; lens.push(r.seq.length); r.seq.forEach(function (c, j) { routeOf[c] = i; posOf[c] = j; }); });
  out.push('<svg class="sol" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(o.label || 'Solution drawing') + '">');
  // routes and arrows
  sol.routes.forEach(function (r, i) {
    var col = PALETTE[i % PALETTE.length], hot = !changed || changed.indexOf(i) >= 0, pts = [inst.dep[r.depot]].concat(r.seq.map(function (c) { return inst.cust[c]; }));
    var d = pts.map(function (p, k) { return (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1); }).join(' ');
    out.push('<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="' + (changed && hot ? 2.8 : 1.6) + '" stroke-opacity="' + (hot ? 1 : 0.4) + '" stroke-linejoin="round"/>');
    for (var k = 1; k < pts.length; k++) {
      var ax = X(pts[k - 1][0]), ay = Y(pts[k - 1][1]), bx = X(pts[k][0]), by = Y(pts[k][1]), len = Math.hypot(bx - ax, by - ay);
      if (len < 16) continue;
      out.push('<path d="M-3.6,-2.7 L3.6,0 L-3.6,2.7 z" transform="translate(' + ((ax + bx) / 2).toFixed(1) + ',' + ((ay + by) / 2).toFixed(1) + ') rotate(' + (Math.atan2(by - ay, bx - ax) * 180 / Math.PI).toFixed(1) + ')" fill="' + col + '" fill-opacity="' + (hot ? 1 : 0.4) + '"/>');
    }
  });
  // customers
  var arr = sol.routes.map(function (r) { return L.arrivals(inst, r.depot, r.seq); });
  for (var c = 0; c < inst.n; c++) {
    var ri = routeOf[c];
    if (ri == null) { out.push('<circle class="cust" cx="' + X(inst.cust[c][0]).toFixed(1) + '" cy="' + Y(inst.cust[c][1]).toFixed(1) + '" r="4" fill="var(--muted)" stroke="var(--bg)"' + (o.focusable ? ' tabindex="0"' : '') + tipText('Customer ' + (c + 1) + '\ndemand ' + inst.q[c]) + '/>'); continue; }
    var col2 = PALETTE[ri % PALETTE.length], cx = X(inst.cust[c][0]).toFixed(1), cy = Y(inst.cust[c][1]).toFixed(1), len2 = lens[ri], pos = posOf[c];
    var tip = 'Customer ' + (c + 1) + '\ndemand ' + inst.q[c] + '\nroute ' + (ri + 1) + ', position ' + (pos + 1) + ' of ' + len2 + '\narrives at t = ' + fmt(arr[ri][pos], 1) +
      '\nthe leg into it is paid by ' + (len2 - pos) + ' customer' + (len2 - pos > 1 ? 's' : '') + ' (it and those behind it)';
    if (moved[c]) out.push('<circle cx="' + cx + '" cy="' + cy + '" r="8" fill="none" stroke="var(--fg)" stroke-width="1.6" stroke-dasharray="3 2"/>');
    out.push('<circle class="cust" cx="' + cx + '" cy="' + cy + '" r="4.4" fill="' + col2 + '" stroke="var(--bg)" stroke-width="1"' + (o.focusable ? ' tabindex="0"' : '') + tipText(tip) + '/>');
    if (o.times) out.push('<text x="' + (+cx + 6) + '" y="' + (+cy - 5) + '">' + fmt(arr[ri][pos], 0) + '</text>');
    else if (o.labels) out.push('<text x="' + (+cx + 6) + '" y="' + (+cy - 5) + '">' + (c + 1) + '</text>');
  }
  // depots
  inst.dep.forEach(function (d, k) {
    var x = X(d[0]), y = Y(d[1]), isOpen = open[k] != null;
    var tip = 'Depot ' + (k + 1) + (isOpen ? ' (open)\n' + open[k] + ' route' + (open[k] > 1 ? 's' : '') + ', ' + nCust[k] + ' customers' : ' (closed)');
    out.push('<rect x="' + (x - 5.5).toFixed(1) + '" y="' + (y - 5.5).toFixed(1) + '" width="11" height="11" rx="2" fill="' + (isOpen ? 'var(--fg)' : 'var(--bg)') + '" stroke="var(--fg)" stroke-width="1.4"' + (isOpen ? '' : ' stroke-dasharray="2.5 2"') + tipText(tip) + ' class="cust"/>');
    out.push('<text x="' + (x + 8).toFixed(1) + '" y="' + (y + 12).toFixed(1) + '">D' + (k + 1) + '</text>');
  });
  out.push('</svg>');
  return out.join('');
}

// customers whose neighbours (predecessor or successor) changed between two solutions
function movedCustomers(inst, a, b) {
  function nb(sol) { var m = {}; sol.routes.forEach(function (r) { r.seq.forEach(function (c, j) { m[c] = (j ? r.seq[j - 1] : 'D' + r.depot) + '>' + (j + 1 < r.seq.length ? r.seq[j + 1] : 'end'); }); }); return m; }
  var A = nb(a), B = nb(b), out = {}; for (var c = 0; c < inst.n; c++) if (A[c] !== B[c]) out[c] = 1; return out;
}

/* convergence chart: start cost and local optimum of each GRASP iteration, best so far, best-known value */
function chartHistory(hist, bks, W, H) {
  W = W || 520; H = H || 190;
  var pts = hist.filter(function (h) { return h.cost != null; });
  if (!pts.length) return '<p class="muted">No iteration finished yet.</p>';
  var ml = 52, mr = 10, mt = 10, mb = 26, vals = [];
  pts.forEach(function (h) { vals.push(h.cost, h.start, h.best); }); if (bks) vals.push(bks);
  var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals); if (hi - lo < 1e-9) { hi = lo + 1; }
  var n = Math.max(2, pts[pts.length - 1].it + 1), X = function (i) { return ml + (W - ml - mr) * i / (n - 1); }, Y = function (v) { return mt + (H - mt - mb) * (1 - (v - lo) / (hi - lo)); };
  var s = ['<svg viewBox="0 0 ' + W + ' ' + H + '" class="sol" role="img" aria-label="Convergence of GRASP iterations">'];
  [0, 0.5, 1].forEach(function (f) { var v = lo + f * (hi - lo), y = Y(v); s.push('<line x1="' + ml + '" x2="' + (W - mr) + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '" stroke="var(--line)"/><text x="' + (ml - 6) + '" y="' + (y + 3).toFixed(1) + '" text-anchor="end">' + fmt(v, hi - lo > 50 ? 0 : 1) + '</text>'); });
  s.push('<text x="' + (ml + (W - ml - mr) / 2) + '" y="' + (H - 6) + '" text-anchor="middle">GRASP iteration</text>');
  if (bks) s.push('<line x1="' + ml + '" x2="' + (W - mr) + '" y1="' + Y(bks).toFixed(1) + '" y2="' + Y(bks).toFixed(1) + '" stroke="var(--ok)" stroke-dasharray="5 3"/><text x="' + (W - mr - 2) + '" y="' + (Y(bks) - 4).toFixed(1) + '" text-anchor="end" style="fill:var(--ok)">best known ' + fmt(bks, 2) + '</text>');
  var path = 'M' + pts.map(function (h, k) { return X(h.it).toFixed(1) + ',' + Y(h.best).toFixed(1); }).join(' L');
  s.push('<path d="' + path + '" fill="none" stroke="var(--accent)" stroke-width="2"/>');
  pts.forEach(function (h) {
    s.push('<circle cx="' + X(h.it).toFixed(1) + '" cy="' + Y(h.start).toFixed(1) + '" r="2.4" fill="none" stroke="var(--muted)"' + tipText('iteration ' + (h.it + 1) + '\nconstructed solution: ' + fmt(h.start, 2)) + '/>');
    s.push('<circle cx="' + X(h.it).toFixed(1) + '" cy="' + Y(h.cost).toFixed(1) + '" r="2.8" fill="var(--accent)"' + tipText('iteration ' + (h.it + 1) + '\nafter local search: ' + fmt(h.cost, 2) + '\nbest so far: ' + fmt(h.best, 2)) + '/>');
  });
  s.push('</svg>');
  return s.join('') + '<div class="muted" style="font-size:12.5px">open circles: constructed solutions, filled circles: after local search, line: best so far</div>';
}

/* ---- references: formatting, links, BibTeX ---- */
function refAuthors(a) { var p = a.split(' and '); return p.length < 3 ? p.join(' & ') : p.slice(0, -1).join(', ') + ' & ' + p[p.length - 1]; }
function refVenue(r) {
  var v = r.journal || r.booktitle || r.school || r.institution || r.publisher || '';
  if (r.journal) v = '<i>' + esc(r.journal) + '</i>' + (r.volume ? ' ' + esc(r.volume) : '') + (r.number ? '(' + esc(r.number) + ')' : '') + (r.pages ? ', ' + esc(r.pages.replace('--', '–')) : '');
  else if (r.type === 'phdthesis') v = 'PhD thesis, ' + esc(r.school);
  else if (r.type === 'techreport') v = esc(r.institution) + ', ' + esc(r.number);
  else if (r.type === 'book') v = esc(r.publisher);
  else v = 'In: ' + esc(r.booktitle) + (r.publisher ? '. ' + esc(r.publisher) : '') + (r.pages ? ', ' + esc(r.pages.replace('--', '–')) : '');
  return v;
}
function refCite(r) { return esc(refAuthors(r.authors)) + ' (' + r.year + '). ' + esc(r.title) + '. ' + refVenue(r) + '.'; }
function refLinks(r) {
  var q = r.title + ' ' + r.authors.split(',')[0], l = [];
  if (r.doi) l.push('<a href="https://doi.org/' + encodeURI(r.doi) + '" target="_blank" rel="noopener">DOI ' + esc(r.doi) + '</a>');
  if (r.arxiv) l.push('<a href="https://arxiv.org/abs/' + encodeURI(r.arxiv) + '" target="_blank" rel="noopener">arXiv:' + esc(r.arxiv) + '</a>');
  l.push('<a href="https://scholar.google.com/scholar?q=' + encodeURIComponent('"' + r.title + '"') + '" target="_blank" rel="noopener">Google Scholar</a>');
  l.push('<a href="https://search.crossref.org/?q=' + encodeURIComponent(q) + '" target="_blank" rel="noopener">Crossref search</a>');
  return l.join(' · ');
}
function bibtex(r) {
  var f = [['author', r.authors], ['title', '{' + r.title + '}'], ['year', String(r.year)]];
  ['journal', 'booktitle', 'school', 'institution', 'volume', 'number', 'pages', 'publisher', 'doi'].forEach(function (k) { if (r[k] != null) f.push([k, String(r[k])]); });
  if (r.arxiv) f.push(['eprint', r.arxiv], ['archivePrefix', 'arXiv']);
  return '@' + r.type + '{' + r.key + ',\n' + f.map(function (p) { return '  ' + p[0] + ' = {' + p[1] + '}'; }).join(',\n') + '\n}';
}
// where is a reference cited?  -> [{kind, key, label}]
function citedBy(refKey) {
  var out = [];
  OPERATORS.forEach(function (o) { if (o.refs.indexOf(refKey) >= 0) out.push({ kind: 'operators', key: o.key, label: o.label }); });
  HEURISTICS.forEach(function (h) { if (h.refs.indexOf(refKey) >= 0) out.push({ kind: 'methods', key: h.key, label: h.name }); });
  return out;
}
function refChips(keys) { return keys.map(function (k) { var r = byKey(REFS, k); return r ? '<a href="#/refs/' + k + '"' + tipHtml('<b>' + esc(r.authors.split(' and ')[0].split(',')[0] + (r.authors.indexOf(' and ') > 0 ? ' et al.' : '') + ' (' + r.year + ')') + '</b>' + esc(r.title)) + '>' + esc(r.authors.split(' and ')[0].split(',')[0] + ' ' + r.year) + '</a>' : ''; }).join(', '); }
