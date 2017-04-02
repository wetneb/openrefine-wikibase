
import unittest
from propertypath import PropertyFactory
from propertypath import tokenize_property
from funcparserlib.lexer import Token
from itemstore import ItemStore
from config import redis_client

class PropertyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.itemstore = ItemStore(redis_client)
        cls.f = PropertyFactory(cls.itemstore)

    def test_lexer(self):
        self.assertEqual(list(tokenize_property('P17')),
                    [Token('PID','P17')])
        self.assertEqual(list(tokenize_property('P17/P297')),
                    [Token('PID','P17'),Token('SLASH','/'),Token('PID','P297')])
        self.assertEqual(list(tokenize_property('(P17/P297)')),
                    [Token('LBRA', '('),
                    Token('PID','P17'),
                    Token('SLASH','/'),
                    Token('PID','P297'),
                    Token('RBRA',')')])

    def test_parse(self):
        samples = [
            '.',
            'P17',
            'P17/P297',
            '(P131/P17|P17)',
            'P14/(P131/P17|P17)',
            'P131/(P17|.)',
        ]
        for sample in samples:
            self.assertEqual(str(self.f.parse(sample)), sample)

    def test_invalid_expression(self):
        with self.assertRaises(ValueError):
            self.f.parse('P') # lexing error

        with self.assertRaises(ValueError):
            self.f.parse('P78/') # parsing error

        with self.assertRaises(ValueError):
            self.f.parse('(P78/P17') # parsing error

    def resolve(self, exp, qid, **kwargs):
        path = self.f.parse(exp)
        return path.evaluate(qid, **kwargs)

    def test_resolve_property_path(self):
        self.assertEqual(
            self.resolve('P297', 'Q142'),
            ['FR'])

        self.assertEqual(
            self.resolve('P17/P297', 'Q83259'),
            ['FR'])

        self.assertTrue(
            'France' in
            self.resolve('P17', 'Q83259')
        )

        self.assertTrue(
            'International Journal of Medical Sciences' in
            self.resolve('P1433', 'Q24791449')
        )

        # With preferred language
        self.assertEqual(
            self.resolve('P17', 'Q83259', lang='de'),
            ['Frankreich'])

        # Without resolving labels
        self.assertEqual(
            self.resolve('P17', 'Q34433', fetch_labels=False),
            ['Q145'])

        # With dot
        self.assertEqual(
            self.resolve('./P2427', 'Q34433', fetch_labels=False),
                ['grid.4991.5'])
        self.assertEqual(
            self.resolve('P2427/.', 'Q34433', fetch_labels=False),
                ['grid.4991.5'])

        # With disjunction
        self.assertSetEqual(
            set(self.resolve('P17', # country
                        'Q1011981', # google china
                        fetch_labels=False)),
                    {'Q148'}) # china
        self.assertSetEqual(
            set(self.resolve('P749/P17', # parent org. / country
                        'Q1011981', # google china
                         fetch_labels=False)),
                    {'Q30'}) # USA
        self.assertSetEqual(
            set(self.resolve('P17|(P749/P17)', # brackets not actually needed
                        'Q1011981', fetch_labels=False)),
                    {'Q148','Q30'}) # USA + China

    def resolve_by_sparql(self, prop_path, qid):
        path = self.f.parse(prop_path)
        results = self.f.resolve_by_sparql([qid],path)
        return results[qid]

    def test_get_property_values_by_sparql(self):
        self.assertEqual(
            self.resolve_by_sparql('P297', 'Q142'),
            [('FR',None)])

        self.assertEqual(
            self.resolve_by_sparql('P17/P297', 'Q83259'),
            [('FR',None)])

        self.assertTrue(
            ('Q142',('France','fr')) in
            self.resolve_by_sparql('P17', 'Q83259')
        )

        self.assertTrue(
            ('Q10927439',('International Journal of Medical Sciences','en')) in
            self.resolve_by_sparql('P1433', 'Q24791449')
        )

        self.assertSetEqual(
            set(qid for qid,_ in self.resolve_by_sparql('P17|(P749/P17)', # brackets not actually needed
                        'Q1011981')),
                    {'Q148','Q30'}) # USA + China

    def test_is_unique_identifier(self):
        self.assertTrue(
            self.f.parse('P3500').is_unique_identifier())
        self.assertTrue(
            self.f.parse('P2427').is_unique_identifier())
        self.assertTrue(
            self.f.parse('./P2427').is_unique_identifier())
        self.assertTrue(
            self.f.parse('(P2427|P3500)').is_unique_identifier())
        self.assertFalse(
            self.f.parse('.').is_unique_identifier())
        self.assertFalse(
            self.f.parse('P31').is_unique_identifier())
        self.assertFalse(
            self.f.parse('P3500/P2427').is_unique_identifier())
        self.assertFalse(
            self.f.parse('(P3500|P17)').is_unique_identifier())

    def test_ends_with_identifier(self):
        self.assertTrue(
            self.f.parse('P3500').ends_with_identifier())
        self.assertTrue(
            self.f.parse('P2427').ends_with_identifier())
        self.assertTrue(
            self.f.parse('P749/P2427').ends_with_identifier())
        self.assertTrue(
            self.f.parse('P749/(P2427|P3500)').ends_with_identifier())
        self.assertFalse(
            self.f.parse('.').ends_with_identifier())
        self.assertFalse(
            self.f.parse('P31').ends_with_identifier())
        self.assertFalse(
            self.f.parse('P3500/P17').ends_with_identifier())
        self.assertFalse(
            self.f.parse('(P3500|P17)').ends_with_identifier())

    def fetch_by_values(self, path_string, values, lang='en'):
        path = self.f.parse(path_string)
        return path.fetch_qids_by_values(values, lang)

    def test_fetch_qids_by_values(self):
        # Just one value, VIAF id for Oxford
        self.assertDictEqual(
            self.fetch_by_values('P214', ['142129514']),
            {'142129514':[('Q34433', 'University of Oxford')]})

        # Two values, for different entities
        self.assertDictEqual(
            self.fetch_by_values('P214', ['142129514','144834915']),
            {'142129514':[('Q34433', 'University of Oxford')],
             '144834915':[('Q1377', 'University of Ljubljana')]})

        # Two different properties
        self.assertDictEqual(
            self.fetch_by_values('(P214|P3500)', ['142129514','1990']),
            {'142129514':[('Q34433', 'University of Oxford')],
             '1990':[('Q49108', 'Massachusetts Institute of Technology')]})

        # No label defined
        self.assertDictEqual(
            self.fetch_by_values('P213', ['0000 0001 2169 3027'], lang='ko'),
            {'0000 0001 2169 3027':[('Q273600', 'École nationale vétérinaire d’Alfort')]})

