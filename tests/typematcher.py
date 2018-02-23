
import unittest
import requests_mock
import re
import requests

from wdreconcile.typematcher import TypeMatcher
from config import redis_client

class TypeMatcherTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = TypeMatcher(redis_client)

    def setUp(self):
        redis_client.flushall()

    def test_correctness(self):
        self.assertTrue(self.m.is_subclass('Q3918', 'Q43229'))
        self.assertFalse(self.m.is_subclass('Q3918', 'Q215380'))

    def test_instance_of_not_followed(self):
        # we only deal with subclass of, not instance of
        self.assertFalse(self.m.is_subclass('Q1327288', 'Q486972'))

    def test_caching(self):
        first_answer = self.m.is_subclass('Q750483', 'Q486972')
        with requests_mock.Mocker() as mocker: # disable all HTTP reqs
            second_answer = self.m.is_subclass('Q750483', 'Q486972')
            self.assertEqual(first_answer, second_answer)
            # another query, which should also be cached
            self.assertTrue(self.m.is_subclass('Q484170', 'Q486972'))

    def test_disambig(self):
        """
        We add this test to make sure disambiguation pages are instances
        of "Wikimedia internal stuff" because we rely on it to filter them out
        """
        self.assertTrue(self.m.is_subclass('Q4167410', 'Q17442446'))

