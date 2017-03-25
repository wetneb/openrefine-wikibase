
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
        kwargs['type'] = kwargs.get('typ')
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

    def test_get_label(self):
        self.assertEqual(
            self.r.item_store.get_label('Q949879', 'en'),
            'Elf')

    def test_match_strings(self):
        # Matching identifiers
        self.assertEqual(
            self.r.match_strings('Q1234','R1234'),
            0)
        self.assertEqual(
            self.r.match_strings('https://www.wikidata.org/entity/Q1234','Q1234'),
            100)
        self.assertEqual(
            self.r.match_strings('12345','1234'),
            0)

        # Matching strings with different case and diacritics
        self.assertEqual(
            self.r.match_strings('Février','Fevrier'),
            100)
        self.assertTrue(
            self.r.match_strings('PEMBERLEY','Pemberley') > 90)

        # Match urls
        self.assertTrue(
            self.r.match_strings('gnu.org', 'http://gnu.org') > 50)

    def test_match_strings_symmetric(self):
        pairs = [('a','b c'),
                ('aa bb', 'b aa'),
                ('a b', 'b c'),
                ('small birch tree','BirchTree'),
                ]
        for a, b in pairs:
            self.assertEqual(self.r.match_strings(a,b),
                             self.r.match_strings(b,a))

