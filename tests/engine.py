
import unittest
from engine import ReconcileEngine
from config import redis_client

class ReconcileEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ReconcileEngine(redis_client)

    # Helpers

    def query(self, query_string, **kwargs):
        kwargs['query'] = query_string
        return self.r.process_single_query(kwargs)

    def results(self, *args, **kwargs):
        return self.query(*args, **kwargs)['result']

    def best_match_id(self, *args, **kwargs):
        return self.results(*args, **kwargs)[0]['id']

    # Tests start here

    def test_exact(self):
        self.assertEqual(
            self.best_match_id('Recumbent bicycle'),
            'Q750483')

    def test_limit(self):
        self.assertEqual(
            len(self.results('Cluny', limit=1)),
            1)
        self.assertEqual(
            len(self.results('Cluny', limit=3)),
            3)
        self.assertTrue(
            len(self.results('Cluny', limit=20)) <= 20)


