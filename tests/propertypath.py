
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

