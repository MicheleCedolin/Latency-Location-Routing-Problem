"""6.3 opt-in depot perturbation: feasibility, monotonic acceptance, isolation, deadlines."""
import random, time, unittest
from common import ROOT
from llrp_framework.core import read_dat, feasible, objective
from llrp_framework.construction import grasp_construct
from llrp_framework.local_search import run_local_search
from llrp_framework import depot_impact as di
from llrp_framework import depot_ops


class DepotImpact63(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst=read_dat(ROOT/'data/P/coord20-5-1.dat')
        cls.K=cls.inst.n; cls.p=cls.inst.m;cls.allowed=list(range(cls.inst.m))
        cls.sol=grasp_construct(cls.inst,cls.K,cls.allowed,random.Random(42),0.02)
        assert cls.sol and feasible(cls.inst,cls.sol,cls.K,cls.p)

    def test_randomized_structural_kicks_always_feasible(self):
        r=random.Random(37)
        for kind in di.KINDS:
            for _ in range(5):
                out=di._kick(kind,self.inst,self.sol,self.K,self.allowed,r,time.perf_counter()+2)
                if out is not None:
                    self.assertTrue(feasible(self.inst,out,self.K,self.p),kind)
                    self.assertTrue(objective(self.inst,out)>0)

    def test_deadline_guard_in_reinsertion(self):
        old=depot_ops._clone_routes(self.inst,self.sol)
        self.assertIsNone(depot_ops._insert_all(self.inst,self.K,old,list(range(5)),self.allowed,deadline=time.perf_counter()-1))

    def test_local_search_not_worse_when_depot_enabled(self):
        di.configure('off',10,seed=4,every=1)
        base,bz,_=run_local_search('first',self.inst,self.sol,self.K,self.p,self.allowed,'loffler9',random.Random(4))
        di.configure('balanced',10,seed=4,every=1,max_share=0.5,event_seconds=0.5,min_interval=0)
        got,z,_=run_local_search('first',self.inst,self.sol,self.K,self.p,self.allowed,'loffler9',random.Random(4))
        self.assertTrue(feasible(self.inst,base,self.K,self.p))
        self.assertTrue(feasible(self.inst,got,self.K,self.p))
        self.assertLessEqual(z,bz+1e-6)
        self.assertAlmostEqual(z,objective(self.inst,got))
        self.assertEqual(di.stats()['depot_events'],1)

    def test_mode_off_no_events(self):
        di.configure('off',60,seed=1)
        run_local_search('first',self.inst,self.sol,self.K,self.p,self.allowed,'loffler9',random.Random(7))
        self.assertEqual(di.stats()['depot_events'],0)
        self.assertEqual(di.stats()['depot_seconds'],0)

    def test_reject_bad_schedule(self):
        for opts in ({'every':0},{'max_share':0},{'max_share':2},{'event_seconds':0},{'min_interval':-1}):
            with self.assertRaises(ValueError):di.configure('balanced',60,**opts)

if __name__=='__main__': unittest.main()
