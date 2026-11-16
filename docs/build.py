#!/usr/bin/env python3
"""Build docs/index.html (one self-contained page) from docs/src/*.

    python3 docs/build.py            write docs/index.html
    python3 docs/build.py --check    exit 1 if docs/index.html is not up to date (used by CI)

The page embeds the stylesheet, the scripts and a few benchmark instances read from cpp/inst, so GitHub Pages can serve it from /docs
without any build step on the server.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = HERE / "src"
INST_DIR = ROOT / "cpp" / "inst"
# (file stem, short note shown in the playground)
PLAY_INSTANCES = [
    ("prins/20-5-1-5", "Prins et al., 20 customers, loose capacity"),
    ("prins/20-5-1b-5", "Prins et al., 20 customers, tight capacity"),
    ("prins/20-5-2-5", "Prins et al., 20 customers, loose capacity"),
    ("prins/20-5-2b-5", "Prins et al., 20 customers, tight capacity"),
    ("barreto/Gaskell21-5", "Barreto et al. (Gaskell), 21 customers"),
    ("barreto/Mi27-5", "Barreto et al. (Min), 27 customers"),
]
JS_ORDER = ["engine.js", "data_refs.js", "data_ops.js", "data_heur.js"]
APP_ORDER = ["app_core.js", "app_views.js", "app.js"]      # run after the embedded instance data


def parse_inst(path):
    kv, dep, cust, mode = {}, [], [], "h"
    for line in path.read_text().splitlines():
        t = line.strip()
        if not t:
            continue
        if t == "depots":
            mode = "d"; continue
        if t == "customers":
            mode = "c"; continue
        p = t.split()
        if mode == "h":
            kv[p[0]] = p[1]
        elif mode == "d":
            dep.append([float(p[0]), float(p[1])])
        else:
            cust.append([float(p[0]), float(p[1]), float(p[2])])
    return dict(name=kv["name"], Q=float(kv["Q"]), Nv=int(kv["Nv"]), Ng=int(kv["Ng"]), bks=float(kv["bks"]), dep=dep, cust=cust)


def build():
    insts = []
    for stem, note in PLAY_INSTANCES:
        d = parse_inst(INST_DIR / (stem + ".inst"))
        d["note"] = note
        d["file"] = "cpp/inst/" + stem + ".inst"
        insts.append(d)
    css = (SRC / "style.css").read_text()
    js = "\n".join((SRC / f).read_text() for f in JS_ORDER)
    js += "\nvar INSTANCES = " + json.dumps(insts, separators=(",", ":")) + ";\n"
    js += "\n".join((SRC / f).read_text() for f in APP_ORDER)
    js = js.replace("</", "<\\/")                       # never let the data close the <script> element
    html = (SRC / "template.html").read_text().replace("/*__CSS__*/", css).replace("/*__JS__*/", js)
    return html


if __name__ == "__main__":
    out = HERE / "index.html"
    html = build()
    if "--check" in sys.argv:
        if not out.exists() or out.read_text() != html:
            print("docs/index.html is out of date: run  python3 docs/build.py"); sys.exit(1)
        print("docs/index.html is up to date"); sys.exit(0)
    out.write_text(html)
    print("wrote %s (%d KB)" % (out.relative_to(ROOT), len(html) // 1024))
