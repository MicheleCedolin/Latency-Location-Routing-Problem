"""Shared helpers for the LLRP test-suite."""
import importlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / 'tests'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PROBLEM = 'LLRP'
PKG = 'llrp_framework'
RUNNER = 'run_llrp.py'
SMOKE_INSTANCE = 'coord20-5-1'
GOLDEN_TAG = 'v12_1'          # bump when behaviour is changed on purpose, then regenerate the golden files


def mod(name):
    return importlib.import_module(f'{PKG}.{name}')


def reference():
    return json.loads((ROOT / 'reference' / f'{PROBLEM}_reference.json').read_text())


def py_family():
    """Trajectories for a given seed depend on the interpreter: math.hypot changed in 3.10 (distances differ in the last bit)
    and sum() of floats became compensated in 3.12 (tie-breaks change). Golden files exist for 3.10-3.11 and >= 3.12;
    there is none for 3.9, where test_golden skips."""
    if sys.version_info >= (3, 12):
        return 'py312plus'
    return 'py310_311' if sys.version_info >= (3, 10) else 'py39'


def golden_path():
    return ROOT / 'tests' / 'golden' / f'{PROBLEM.lower()}_{GOLDEN_TAG}_{py_family()}.json'
