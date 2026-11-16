"""Placeholder for the CLRP depot layers 'halving' and 'mip' (clean.6.0), which are NOT ported to the LLRP kit.

They assume p = m (every depot allowed) and a CLRP routing proxy (star trip with a round trip, opening costs) for their MILP candidates.
In the LLRP the depot-set decision is made by the p-subset passes of the solvers (--depot-mode, including the p-median ranking) and by the
adaptive layer (--depot-impact adaptive, depot_adaptive64.py). The names below keep run_llrp.py's interface.
"""
LAYERS = ('none',)
LAST_INFO = {}
PRIMARY_KEY = {}


class LayerConfig:
    @staticmethod
    def from_args(a):
        raise NotImplementedError('depot layers halving / mip are not available in the LLRP kit')


def run_layer(*a, **k):
    raise NotImplementedError('depot layers halving / mip are not available in the LLRP kit')
