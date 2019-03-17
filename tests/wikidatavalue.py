
import unittest

from wdreconcile.wikidatavalue import TimeValue

class WikidataValueTest(unittest.TestCase):

    def test_year_to_openrefine(self):
        v = TimeValue(precision=9,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1096-01-01T00:00:00Z')
        self.assertEqual({'date': '1096-01-01T00:00:00+00:00'}, v._as_cell('en',None))

        v = TimeValue(time='+2017-00-00T00:00:00Z',timezone=0,before=0,after=0,precision=9,calendarmodel='http://www.wikidata.org/entity/Q1985727')
        self.assertEqual({'date': '2017-01-01T00:00:00+00:00'}, v._as_cell('en',None))

    def test_date_matching(self):
        v = TimeValue(precision=11,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1967-04-05T00:00:00Z')
        self.assertEqual(100, v.match_with_str('1967-04-05', None))
        self.assertEqual(100, v.match_with_str('1967-04', None))
        self.assertEqual(100, v.match_with_str('1967', None))
        self.assertEqual(0, v.match_with_str('1967-04-09', None))
        self.assertEqual(0, v.match_with_str('1967-02', None))
        self.assertEqual(0, v.match_with_str('1978', None))
        self.assertEqual(0, v.match_with_str('1967-04-05-39', None))
        self.assertEqual(0, v.match_with_str('anteurst', None))
        v = TimeValue(precision=10,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1967-04-01T00:00:00Z')
        self.assertEqual(100, v.match_with_str('1967-04-05', None))
        self.assertEqual(100, v.match_with_str('1967-04', None))
        self.assertEqual(100, v.match_with_str('1967', None))
        self.assertEqual(0, v.match_with_str('1967-02', None))
        self.assertEqual(0, v.match_with_str('1978', None))
        v = TimeValue(precision=9,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1967-01-01T00:00:00Z')
        self.assertEqual(100, v.match_with_str('1967-04-05', None))
        self.assertEqual(100, v.match_with_str('1967-04', None))
        self.assertEqual(100, v.match_with_str('1967', None))
        self.assertEqual(0, v.match_with_str('1978', None))




