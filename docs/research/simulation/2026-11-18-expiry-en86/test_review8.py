"""Reporting-only post-score correction checks; no financial re-score."""
import json,unittest
import review8

class ReviewTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        r=review8.normalize({'p':dict(eligible=0,missing=3,support=0,net={'ordinary':0,'adverse':0})})
        self.assertIsNone(r['p']['net']['ordinary']);self.assertEqual(r['p']['verdict'],'DATA UNAVAILABLE')
    def test_no_observations_not_evaluated(self):
        r=review8.normalize({'p':dict(eligible=0,missing=0,support=0,net={'ordinary':0,'adverse':0})})
        self.assertEqual(r['p']['verdict'],'NOT EVALUATED');self.assertFalse(r['p']['qualified'])
    def test_tail_screen_cannot_hide_wallet_failure(self):
        r=review8.practical_scores(dict(hypotheses={'EN91|NIFTY':dict(status='TAIL SCREEN — SOURCE UNVALIDATED')},
                                     arms={'EN91|NIFTY':{'wallet|ordinary':{'halted':10}}}))
        self.assertIn('REJECT',r['EN91|NIFTY']['practical_review']);self.assertFalse(r['EN91|NIFTY']['qualified'])

if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
    review8.score8.write(review8.runner8.HERE/'review-checks8.json',dict(status='PASS' if r.wasSuccessful() else 'FAIL',tests=r.testsRun,failures=len(r.failures),errors=len(r.errors)))
    raise SystemExit(0 if r.wasSuccessful() else 1)
