import pytest
from wdreconcile.wikidatavalue import TimeValue, CoordsValue

pytestmark = pytest.mark.asyncio

async def test_year_to_openrefine():
    v = TimeValue(precision=9,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1096-01-01T00:00:00Z')
    assert ({'date': '1096-01-01T00:00:00+00:00'} == await v._as_cell('en',None))

    v = TimeValue(time='+2017-00-00T00:00:00Z',timezone=0,before=0,after=0,precision=9,calendarmodel='http://www.wikidata.org/entity/Q1985727')
    assert ({'date': '2017-01-01T00:00:00+00:00'} == await v._as_cell('en',None))

async def test_date_matching():
    v = TimeValue(precision=11,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1967-04-05T00:00:00Z')
    assert (100 == await v.match_with_str('1967-04-05', None))
    assert (100 == await v.match_with_str('1967-04', None))
    assert (100 == await v.match_with_str('1967', None))
    assert (0 == await v.match_with_str('1967-04-09', None))
    assert (0 == await v.match_with_str('1967-02', None))
    assert (0 == await v.match_with_str('1978', None))
    assert (0 == await v.match_with_str('1967-04-05-39', None))
    assert (0 == await v.match_with_str('anteurst', None))
    v = TimeValue(precision=10,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1967-04-01T00:00:00Z')
    assert (100 == await v.match_with_str('1967-04-05', None))
    assert (100 == await v.match_with_str('1967-04', None))
    assert (100 == await v.match_with_str('1967', None))
    assert (0 == await v.match_with_str('1967-02', None))
    assert (0 == await v.match_with_str('1978', None))
    v = TimeValue(precision=9,before=0,timezone=0,after=0,calendarmodel='http://www.wikidata.org/entity/Q1985727',time='+1967-01-01T00:00:00Z')
    assert (100 == await v.match_with_str('1967-04-05', None))
    assert (100 == await v.match_with_str('1967-04', None))
    assert (100 == await v.match_with_str('1967', None))
    assert (0 == await v.match_with_str('1978', None))


async def test_coords():
    v = CoordsValue(latitude=53.3175,longitude=-4.6204)
    assert (int(await v.match_with_str("53.3175,-4.6204", None)) == 100)
    assert (int(await v.match_with_str("53.3175,-5.6204", None)) == 0)

