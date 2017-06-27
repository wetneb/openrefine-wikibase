import unittest
from wdreconcile.engine import ReconcileEngine
from config import redis_client

class ReconcileEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ReconcileEngine(redis_client)

    # Helpers

    def query(self, query_string, **kwargs):
        kwargs['query'] = query_string
        kwargs['type'] = kwargs.get('typ')
        return self.r.process_single_query(kwargs)

    def results(self, *args, **kwargs):
        return self.query(*args, **kwargs)['result']

    def result_ids(self, *args, **kwargs):
        return [r['id'] for r in self.query(*args, **kwargs)['result']]

    def best_match_id(self, *args, **kwargs):
        return self.result_ids(*args, **kwargs)[0]

    def best_score(self, *args, **kwargs):
        return self.results(*args, **kwargs)[0]['score']

    # Tests start here

    def test_exact(self):
        self.assertEqual(
            self.best_match_id('Recumbent bicycle'),
            'Q750483')

    def test_empty(self):
        self.assertEqual(
            self.results(''),
            [])

    def test_limit(self):
        self.assertEqual(
            len(self.results('Cluny', limit=1)),
            1)
        self.assertTrue(
            len(self.results('Cluny', limit=3)) <= 3)
        self.assertTrue(
            len(self.results('Cluny', limit=20)) <= 20)

    def test_type(self):
        self.assertEqual(
            self.best_match_id('Oxford', typ='Q3918'), # university
            'Q34433')
        self.assertNotEqual(
            self.best_match_id('Oxford', typ='Q3957'), # town
            'Q34433')

    def test_qid(self):
        self.assertEqual(
            self.best_match_id('Q29568422'),
            'Q29568422')
        self.assertEqual(
            self.best_score('Q29568422'),
            100)

    def test_unique_id(self):
        """
        We can fetch items by unique ids!
        """
        # The search string does not matter: it is ignored
        # because we found an exact match by identifier.
        self.assertEqual(
            self.result_ids('this string is ignored',
            properties=[{'v':'142129514','pid':'P214'}]),
            ['Q34433'])

        # Not proving an id doesn't mess up the reconciliation
        self.assertEqual(
            self.best_match_id('University of Oxford',
            properties=[{'v':' ','pid':'P214'}]),
            'Q34433')

        # Providing two conflicting identifiers gives
        # two reconciliation candidates with maximum score.
        # They are therefore not matched automatically.
        self.assertSetEqual(
            set(self.result_ids('this string is ignored',
            properties=[{'v':'142129514','pid':'P214'},
                        {'v':'144834915','pid':'P214'}])),
            {'Q34433','Q1377'})

        # If no unique ID match is found, we fall back on
        # standard matching with same scoring as without
        # the unique ids (so that we can still get 100%
        # matches).
        self.assertEqual(
            self.best_score('Warsaw',
                properties=[{'v':'fictuous id','pid':'P1566'},
                 {'v':'PL','pid':'P17/P297'}]),
            100)

    def test_items_without_types(self):
        """
        Items without types can be returned only when
        there are no other typed items that match.
        """
        self.assertEqual(
            len(self.results('oxford', typ='Q3918')),
            2) # Oxford Brookes university and University of Oxford

    def test_forbidden_type(self):
        self.assertEqual(
            len(self.results('Category:Oxford')),
            0)

    def test_subfields(self):
        # Exact match on the year of birth
        self.assertEqual(
            self.best_score("Steve Clark",
                    typ="Q5",
                    properties=[{"pid":"P569@year","v":"1943"}]),
            100)
        # Inexact match
        self.assertTrue(
            self.best_score("Steve Clark",
                    typ="Q5",
                    properties=[{"pid":"P569@year","v":"1342"}])
            < 100)

        # Float that is slightly off gets a non-zero score
        score = self.best_score("Ramsden",
                    typ="Q486972",
                    properties=[{"pid":"P625@lat","v":"51.837"}])
        self.assertTrue(score
            > 80)


    def test_get_label(self):
        self.assertEqual(
            self.r.item_store.get_label('Q949879', 'en'),
            'Elf')

    def test_fetch_values(self):
        self.assertDictEqual(
            self.r.fetch_values({'item':'Q881333','prop':'P213', 'lang':'de'}),
            {'prop': 'P213', 'values': ['0000 0004 0547 722X'], 'item': 'Q881333'})
        self.assertEqual(
            self.r.fetch_values({'item':'Q881333','prop':'P213', 'lang':'de', 'flat':'true'}),
            '0000 0004 0547 722X')
