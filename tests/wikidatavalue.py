
import unittest

from wdreconcile.wikidatavalue import TimeValue

class WikidataValueTest(unittest.TestCase):

    def test_year_to_openrefine(self):
        v = TimeValue(precision=9,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1096-01-01T00:00:00Z')
        self.assertEquals({'date': '1096-01-01T00:00:00+00:00'}, v._as_cell('en',None))

        v = TimeValue(time='+2017-00-00T00:00:00Z',timezone=0,before=0,after=0,precision=9,calendarmodel='http://www.wikidata.org/entity/Q1985727')
        self.assertEquals({'date': '2017-01-01T00:00:00+00:00'}, v._as_cell('en',None))



