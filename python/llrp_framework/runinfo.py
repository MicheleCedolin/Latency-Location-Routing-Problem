"""Run identity and budget semantics shared by the runner, the launcher, the collector and the auditor.

* config_id    identifies a *method configuration*: code, interpreter family, method, local search,
               neighbourhood preset, budget policy and every hyper-parameter. Runs may only be pooled
               when their config_id is equal.
* fingerprint  identifies one *invocation*: config_id plus the instances, seeds, and the hashes of the
               instance files and reference records. The launcher resumes a finished run only when the
               stored fingerprint equals the one the current code would produce.
* budget_outcome  decides which solution is the reported result and what status the run gets.
"""
from __future__ import annotations
import hashlib, json, math, platform
from pathlib import Path

# Arguments that do not change what a run computes (where it writes, what it prints) or that identify the job.
_NOT_CONFIG = {'kit_root', 'out_dir', 'list_neighborhoods', 'list_heuristics', 'print_fingerprint', 'instances', 'seeds'}


def sha256_file(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def source_sha256(root, package, runner):
    """Hash of every Python file that can influence a result (package + runner), independent of file order."""
    root = Path(root)
    files = sorted((root / package).glob('*.py')) + [root / runner]
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode()); h.update(b'\0'); h.update(f.read_bytes()); h.update(b'\0')
    return h.hexdigest()


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def python_family():
    v = platform.python_version_tuple()
    return f'{v[0]}.{v[1]}'


def solver_stack(args):
    """Third-party software that a run depends on (LLRP kit: the MILP depot layer of the CLRP kit is not ported, so this is empty for every supported run).

    Returned as a plain dict that is empty for every other run, so the config_id of a pure-standard-library
    run does not change. scipy is identified by its major.minor family in config_id (HiGHS is bundled with
    scipy; a different minor release may bundle a different HiGHS and so a different tie-break), and by the full
    version strings in config.json for the record."""
    if getattr(args, 'depot_layer', 'none') != 'mip':
        return {}
    out = {'scipy': None, 'numpy': None}
    try:
        import scipy
        out['scipy'] = scipy.__version__
    except Exception:       # missing: the layer then fails with its own message; record the absence
        pass
    try:
        import numpy
        out['numpy'] = numpy.__version__
    except Exception:
        pass
    return out


def _family(version):
    return None if version is None else '.'.join(str(version).split('.')[:2])


def run_identity(args, root, package, runner, instance_files, reference_records):
    """Return dict(config_id, fingerprint, source_sha256, python_family, instance_sha256, reference_sha256, solver_stack)."""
    root = Path(root)
    cfg = {k: v for k, v in vars(args).items() if k not in _NOT_CONFIG}
    src = source_sha256(root, package, runner)
    vfile = root / 'VERSION'
    version = vfile.read_text().strip() if vfile.exists() else 'unknown'
    stack = solver_stack(args)
    ident = dict(source=src, version=version, python=python_family(), args=cfg)
    if stack:                                   # only mip runs: keeps every other config_id unchanged
        ident['scipy_family'] = _family(stack['scipy'])
    config_id = _digest(ident)
    inst_hash = {name: sha256_file(path) for name, path in sorted(instance_files.items())}
    ref_hash = {name: _digest(rec) for name, rec in sorted(reference_records.items())}
    fingerprint = _digest(dict(config_id=config_id, instances=args.instances, seeds=args.seeds,
                               instance_sha256=inst_hash, reference=ref_hash))
    return dict(config_id=config_id, fingerprint=fingerprint, source_sha256=src, python_family=python_family(),
                instance_sha256=inst_hash, reference_sha256=ref_hash, code_version=version, solver_stack=stack)


def budget_outcome(trace_best, trace_sol, raw_sol, raw_z, budget_mode):
    """Which solution is the reported result of a run?

    Returns (status, solution, objective, trace_missing).

    fixed_time:   the reported result is the best feasible incumbent exposed to the tracer no later than the
                  deadline. A solution that the solver returns after the deadline is never promoted to the
                  result (it stays a diagnostic, raw_solver_objective); if there is no in-budget incumbent the
                  run has status 'no_incumbent_within_budget' and no objective.
    fixed_trials: there is no deadline; the traced incumbent is the result, and an untraced raw solution is
                  accepted (trace_missing=True flags it).
    """
    if trace_best is not None and trace_sol is not None:
        return 'ok', trace_sol, float(trace_best), False
    raw_ok = bool(raw_sol) and raw_z is not None and math.isfinite(float(raw_z))
    if budget_mode == 'fixed_trials' and raw_ok:
        return 'ok', raw_sol, float(raw_z), True
    return ('no_incumbent_within_budget' if raw_ok else 'no_solution'), None, None, True
