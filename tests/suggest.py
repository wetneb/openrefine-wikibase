
import unittest
from wdreconcile.suggest import SuggestEngine, commons_image_url
from config import redis_client

class SuggestEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = SuggestEngine(redis_client)

    # Helpers

    def query(self, typ, query_string, **kwargs):
        kwargs['prefix'] = query_string
        if typ == 'type':
            return self.s.find_type(kwargs)
        elif typ == 'property':
            return self.s.find_property(kwargs)
        elif typ == 'entity':
            return self.s.find_entity(kwargs)

    def results(self, *args, **kwargs):
        return self.query(*args, **kwargs)['result']

    def best_match_id(self, *args, **kwargs):
        return self.results(*args, **kwargs)[0]['id']

    def preview(self, **kwargs):
        return self.s.preview(kwargs)

    def propose(self, resolved_type, **kwargs):
        kwargs['type'] = resolved_type
        if 'lang' not in kwargs:
            kwargs['lang'] = 'en'
        return self.s.propose_properties(kwargs)['properties']

    # Tests start here

    def test_exact(self):
        self.assertEqual(
            self.best_match_id('entity', 'Recumbent bicycle'),
            'Q750483')
        self.assertEqual(
            self.best_match_id('entity', 'Vélo couché', lang='fr'),
            'Q750483')
        self.assertEqual(
            self.best_match_id('property', 'Ringgold identifier'),
            'P3500')

    def test_alias(self):
        self.assertEqual(
            self.best_match_id('entity', 'Institut Supérieur des Techniques de la Performance', lang='fr'),
            'Q3152604')

    def test_sparql(self):
        self.assertEqual(
            self.best_match_id('property', 'P17/P297'),
            'P17/P297')
        self.assertEqual(
            self.best_match_id('property', 'P17/(P297|.)'),
            'P17/(P297|.)')

    def test_custom_language(self):
        self.assertTrue('ville' in
            self.preview(id='Q350',lang='fr'))

    def test_propose_property(self):
        # We follow wdt:P279 to find properties higher up:
        # number of students (P2196) is marked on "institutional
        # education", whose "university (Q3918)" is a subclass of.
        self.assertTrue('P2196' in
            [p['id'] for p in self.propose('Q3918', limit=50)])

        # Check the limits
        self.assertEqual(len(self.propose('Q3918', limit=10)), 10)

        # Check the language
        self.assertTrue("nombre d'étudiants" in
            [p['name'] for p in self.propose('Q3918', lang='fr', limit=50)])


class CommonsImageTest(unittest.TestCase):

    def test_commons_url(self):
        self.assertTrue(commons_image_url('Wikidata-logo-en.svg').endswith('.png'))

