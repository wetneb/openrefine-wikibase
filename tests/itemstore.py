
import unittest
import requests_mock
import re
import requests
from itemstore import ItemStore
from config import redis_client

class ItemStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = ItemStore(redis_client)

    def setUp(self):
        redis_client.flushall()

    def test_label(self):
        self.assertEqual(self.s.get_label('Q3918', 'en'),
                        'university')

    def test_caching(self):
        item = self.s.get_item('Q750483')
        with requests_mock.Mocker() as mocker: # disable all HTTP reqs
            item2 = self.s.get_item('Q750483')
            # we still get the same item
            self.assertEqual(set(item), set(item2))

    def test_500_error(self):
        with requests_mock.Mocker() as mocker: # disable all HTTP reqs
            mocker.get(re.compile('.*\.wikidata\.org/.*'), status_code=500)
            with self.assertRaises(requests.exceptions.HTTPError):
                item = self.s.get_item('Q750484')

