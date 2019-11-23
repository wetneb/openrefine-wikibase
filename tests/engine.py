import unittest
from wdreconcile.engine import ReconcileEngine
import json
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
        res = self.query(*args, **kwargs)['result']
        # try to dump it as JSOn
        json.dumps(res)
        return res

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

    def test_wikidata_search_sucks(self):
        """
        The default search interface of Wikidata sucks, mainly
        because it fails to rank correctly results by relevance.
        For instance, searching for "United States" does not return
        "United States of America" (Q30) in the first page of results:

        https://www.wikidata.org/w/index.php?search=&search=United+States&title=Special:Search&go=Go

        Therefore we ensure we fall back on autocompletion. Unfortunately
        autocompletion has other pitfalls:
        - a language has to be provided (only labels and aliases from that
          language will be considered)
        - it is less robust to variations. For instance, adding a few words
          in addition to an exact label match will not return anything.
        """
        self.assertEqual(
            self.best_match_id('United States', typ='Q6256'),
            'Q30')

    def test_wikidata_search_does_not_rank_aliases_high_enough(self):
        """
        Matches on aliases are not ranked high enough by the default search profile.
        """
        self.assertEqual(
            self.best_match_id('GER', typ='Q6256'),
            'Q183')

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

    def test_sitelink(self):
        self.assertEqual(
            self.best_match_id('https://de.wikipedia.org/wiki/Brüssel'),
            'Q9005')
        self.assertEqual(
            self.best_score('https://de.wikipedia.org/wiki/Brüssel'),
            100)
        self.assertTrue(
            self.best_score('Oxford', properties=[{'pid':'P17', 'v':'https://en.wikipedia.org/wiki/Cambridge'}])
            < 90)
        self.assertEqual(
            self.best_score('Oxford', properties=[{'pid':'P17', 'v':'https://en.wikipedia.org/wiki/United Kingdom'}]),
            100)

    def test_reconciled_properties(self):
        """
        For issue #32
        """
        self.assertEqual(
            self.best_score('Oxford', properties=[{'pid':'P17', 'v':{'id':'Q145'}}]),
            100)

    def test_shortest_qid_first(self):
        """
        We could one day want to replace this by something
        more clever like PageRank

        For issue #26
        """
        self.assertEqual(
            self.best_match_id('Amsterdam'),
            'Q727'
        )

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
        self.assertEqual(
            self.r.fetch_values({'item':'Q3068626','prop':'P463','label':'true', 'lang': 'fr'}),
            {'prop':'P463',
             'values': ['Académie lorraine des sciences'],
             'item':'Q3068626'})

    def test_fetch_properties_by_batch(self):
        # First, a simple test (two items, two properties)
        self.assertDictEqual(
            self.r.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q34433","Q83259"],
                                "properties":[{"id":"P2427"},{"id":"P17/P297"}]}}),
            {"rows": {"Q34433": {"P17/P297": [{"str": "GB"}], "P2427": [{"str": "grid.4991.5"}]},
                "Q83259": {"P17/P297": [{"str": "FR"}], "P2427": [{"str": "grid.5607.4"}]}},
             "meta": [{"name": "GRID ID", "id": "P2427"}, {"name": "P17/P297", "id": "P17/P297"}]})

        # Second, a test with counts
        # (number of children of Michael Jackson)
        self.assertDictEqual(
            self.r.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q2831"],
                                "properties":[{"id":"P40","settings":{"count":"on"}}]}}),
            {"rows": {"Q2831": {"P40": [{"float": 3}]}},
             "meta": [{"name": "child", "id": "P40", "settings" : {"count": "on"}}]})

        # Second, a test with counts and best ranks
        # (number of current currencies in France)
        self.assertDictEqual(
            self.r.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q142"],
                                "properties":[{"id":"P38","settings":{"rank":"best","count":"on"}}]}}),
            {"rows": {"Q142": {"P38": [{"float": 1}]}},
             "meta": [{"name": "currency", "id": "P38", "settings" : {"count": "on","rank":"best"}}]})

    def test_fetch_qids(self):
        self.assertDictEqual(
            self.r.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q34433"],
                "properties":[{"id":"qid"}]}}),
                {"meta": [{"id": "qid", "name": "Qid"}], "rows": {"Q34433": {"qid": [{"str":"Q34433"}]}}}
            )

    def test_fetch_years(self):
        self.assertDictEqual(
            self.r.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q34433"],"properties":[{"id":"P571"}]}}),
            {
                "rows": {
                    "Q34433": {
                        "P571": [{'date': '1096-01-01T00:00:00+00:00'}]
                    }
                },
                "meta": [
                    {
                        "name": "inception",
                        "id": "P571"
                    }
                ]

            })
