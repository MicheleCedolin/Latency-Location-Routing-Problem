/* ---- router and start-up ---- */
'use strict';
var ROUTES = [['problem', 'Problem', viewProblem, 'The latency location-routing problem'], ['operators', 'Operators', viewOperators, 'Local-search operators'], ['methods', 'Methods', viewMethods, 'The 19 metaheuristics'],
  ['play', 'Playground', viewPlay, 'Playground'], ['refs', 'References', viewRefs, 'References'], ['about', 'About', viewAbout, 'About']];
var CURRENT = { cleanup: null };
function parseHash() { var h = (location.hash || '').replace(/^#\/?/, '').split('/'); return { name: h[0] || 'problem', sub: h[1] ? decodeURIComponent(h[1]) : '' }; }
function render() {
  var r = parseHash(), route = ROUTES.filter(function (x) { return x[0] === r.name; })[0] || ROUTES[0];
  if (CURRENT.cleanup) { try { CURRENT.cleanup(); } catch (e) { } CURRENT.cleanup = null; }
  hideTip();
  var view = $('#view'), ctx = { sub: r.sub, cleanup: null };
  view.innerHTML = ''; route[2](view, ctx); CURRENT.cleanup = ctx.cleanup;
  document.title = route[3] + ' · LLRP Lab';
  $$('#nav a').forEach(function (a) { if (a.getAttribute('data-r') === route[0]) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  if (!r.sub) window.scrollTo(0, 0);
}
function start() {
  initTooltip();
  $('#nav').innerHTML = ROUTES.map(function (r) { return '<a href="#/' + r[0] + '" data-r="' + r[0] + '">' + r[1] + '</a>'; }).join('');
  $('#foot').innerHTML = 'LLRP Lab, part of the <a href="https://github.com/MicheleCedolin/Latency-Location-Routing-Problem" target="_blank" rel="noopener">Latency-Location-Routing-Problem</a> repository. The playground uses a simplified JavaScript engine; see About.';
  var root = document.documentElement, saved = null; try { saved = localStorage.getItem('llrp-theme'); } catch (e) { }
  if (saved) root.setAttribute('data-theme', saved);
  $('#theme').addEventListener('click', function () {
    var dark = root.getAttribute('data-theme') ? root.getAttribute('data-theme') === 'dark' : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var next = dark ? 'light' : 'dark'; root.setAttribute('data-theme', next); try { localStorage.setItem('llrp-theme', next); } catch (e) { }
  });
  window.addEventListener('hashchange', render);
  render();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
