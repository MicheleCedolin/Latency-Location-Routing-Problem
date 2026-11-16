# LLRP Lab: the interactive guide

A single-page web guide to the latency location-routing problem (LLRP) and to the heuristics of this repository. It needs no server
and no installation: it is served by GitHub Pages straight from this folder.

| Tab | What it shows |
|---|---|
| Problem | The objective (sum of arrival times), a worked example, and why the shortest route is not the fastest one. |
| Operators | The 14 local-search operators with a real before/after move each; hover for details, hover over customers for arrival times. |
| Methods | The 19 metaheuristics: steps, parameters, defaults, tuning ranges, references; search and filter. |
| Playground | GRASP + RVND on benchmark or random instances, operator selection, convergence chart, per-operator statistics, move-by-move local search. |
| References | All cited papers with DOI / arXiv links where checked, Google Scholar and Crossref searches, BibTeX (single entry, all, or download). |

## Use it

* Online (after Pages is enabled): `https://michelecedolin.github.io/Latency-Location-Routing-Problem/`
* Locally: open `docs/index.html` in any modern browser (double-click it). Nothing is downloaded at run time.

## Enable GitHub Pages (once)

Repository **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch `main`, folder `/docs` → Save.**
The page appears at the address above after about a minute. Note that on a free GitHub plan Pages is served only for **public**
repositories: if the repository is made private later, the page stops being served (the file itself stays in the repository and
still works locally).

## Edit it

The page is generated: edit the files in `docs/src/` and rebuild.

| File | Content |
|---|---|
| `src/engine.js` | The small JavaScript LLRP engine: instances, objective, the 14 operators, RVND, construction, GRASP. Works in the browser and in Node. |
| `src/data_ops.js` | Operator descriptions, presets, glossary. |
| `src/data_heur.js` | The 19 methods: summaries, steps, parameters, ranges. |
| `src/data_refs.js` | References (add a DOI only after checking it against the publisher). |
| `src/app_core.js`, `src/app_views.js`, `src/app.js` | Tooltips, drawing, views, router. |
| `src/style.css`, `src/template.html` | Look and page skeleton. |
| `build.py` | Bundles everything plus six benchmark instances from `cpp/inst/` into `index.html`. |

```bash
python3 docs/build.py            # write docs/index.html
python3 docs/build.py --check    # fail if index.html is stale (used in CI)
node docs/test/engine.test.mjs   # engine tests, no dependencies
npm install --prefix /tmp/jsd jsdom && JSDOM_FROM=/tmp/jsd node docs/test/dom.test.mjs   # page smoke test
```

## What the playground is and is not

The engine in `src/engine.js` re-implements the ideas of `cpp/src/llrp_fast.cpp` for explanation. It re-evaluates candidate routes from scratch
(the C++ engine uses constant-time evaluation by sub-sequence concatenation), treats capacity as a hard constraint (no strategic oscillation),
and uses a simple savings construction. On the small instances it reaches or comes close to the best-known values (see
`docs/test/engine.test.mjs`), but it is not the research code: use `cpp/` for experiments.
