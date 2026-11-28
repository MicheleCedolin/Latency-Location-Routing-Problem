#!/usr/bin/env python3
"""Pack the raw per-run files of the memetic-phase campaigns (stage 5, Appendix F) into the standard merged layout of study_results/.

  python3 -I pack_runs.py --res results_e_pilot --res results_e_ext --res results_e_rest14 --out results_memetic --tools cpp/bin/llrp_tools

Input: the cluster output of each campaign, `<res>/tar/<family>/<instance>_s<seed>_B1_eax40.tar` (one tar per run: run/routes/trace/ops/pool/dpm csv, .verify,
the per-generation log `.eax.csv` and `log/<run>.log`).
Output, per family: `<out>/<family>/B1_eax40/{run,routes,trace,ops,pool,dpm}.csv` (merged with `llrp_tools merge`, standard headers), `verify.txt` (one line per run,
cluster paths removed) and `eax_summary.csv` (the `eax on=1 ...` line of every run log, one row per run).
The per-generation logs `.eax.csv` (about 1.4 MB per run, 2.4 GB in total) are NOT copied: no number of the manuscript depends on them.
Only complete runs (a `.run.csv` exists) are packed; a duplicated run (same instance and seed in two result directories) is rejected.
"""
import argparse, csv, io, os, re, shutil, subprocess, sys, tarfile

EAX_KEYS = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tools", required=True)
    ap.add_argument("--tag", default="B1_eax40")
    a = ap.parse_args()
    seen = set()
    eax_rows = {}   # family -> list of dict
    ver_lines = {}  # family -> list of str
    nrun = 0
    for res in a.res:
        for root, _, files in os.walk(os.path.join(res, "tar")):
            fam = os.path.basename(root)
            for f in sorted(files):
                if not f.endswith(".tar"):
                    continue
                with tarfile.open(os.path.join(root, f)) as tf:
                    names = {m.name: m for m in tf.getmembers() if m.isfile()}
                    stems = [n[:-len(".run.csv")] for n in names if n.endswith(".run.csv") and "/" not in n]
                    if not stems:
                        continue
                    stem = stems[0]
                    m = re.match(r"^(.*)_s(\d+)_" + re.escape(a.tag) + "$", stem)
                    if not m:
                        sys.exit("unexpected run name: " + stem)
                    inst, seed = m.group(1), int(m.group(2))
                    if (inst, seed) in seen:
                        sys.exit("duplicate run %s seed %d" % (inst, seed))
                    seen.add((inst, seed))
                    d = os.path.join(a.out, fam, a.tag, "runs")
                    os.makedirs(os.path.join(d, "log"), exist_ok=True)
                    for n, mem in names.items():
                        if n.endswith(".eax.csv"):
                            continue
                        dest = os.path.join(d, n)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with open(dest, "wb") as out:
                            out.write(tf.extractfile(mem).read())
                    ver = tf.extractfile(names[stem + ".verify"]).read().decode().strip() if stem + ".verify" in names else "MISSING"
                    ver = re.sub(r"(OK|FAIL\w*)\s+\S+/runs/" + re.escape(stem), r"\1  " + stem, ver)
                    ver_lines.setdefault(fam, []).append((inst, seed, ver.splitlines()[0] if ver else "MISSING"))
                    row = {"Instance": inst, "Seed": seed}
                    lg = names.get("log/" + stem + ".log")
                    if lg is not None:
                        for line in tf.extractfile(lg).read().decode(errors="replace").splitlines():
                            if line.startswith("eax on=1"):
                                for kv in line.split()[2:]:
                                    if "=" in kv:
                                        k, v = kv.split("=", 1)
                                        row[k] = v
                    eax_rows.setdefault(fam, []).append(row)
                    nrun += 1
    keys = ["Instance", "Seed"]
    for rows in eax_rows.values():
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
    for fam in sorted(eax_rows):
        D = os.path.join(a.out, fam, a.tag)
        subprocess.run([a.tools, "merge", D], check=True, stdout=subprocess.DEVNULL)
        for ext in ("pool", "dpm"):   # logs with their own header line in every run file; `llrp_tools merge` does not handle them
            hdr, body = None, []
            for fn in sorted(os.listdir(os.path.join(D, "runs"))):
                if fn.endswith("." + ext + ".csv"):
                    lines = open(os.path.join(D, "runs", fn)).read().splitlines()
                    if lines:
                        hdr = hdr or lines[0]
                        body += lines[1:]
            if hdr:
                open(os.path.join(D, ext + ".csv"), "w").write("\n".join([hdr] + body) + "\n")
        shutil.rmtree(os.path.join(D, "runs"))
        with open(os.path.join(D, "verify.txt"), "w") as fh:
            for inst, seed, v in sorted(ver_lines[fam], key=lambda x: (x[0], x[1])):
                fh.write(v + "\n")
        with open(os.path.join(D, "eax_summary.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(keys)
            for r in sorted(eax_rows[fam], key=lambda r: (r["Instance"], r["Seed"])):
                w.writerow([r.get(k, "") for k in keys])
        print("%s: %d runs" % (fam, len(eax_rows[fam])))
    print("total %d runs" % nrun)


if __name__ == "__main__":
    main()
