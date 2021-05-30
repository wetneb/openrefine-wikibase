
import pytest
import re

pytestmark = pytest.mark.asyncio

async def test_correctness(type_matcher, mock_aioresponse):
    mock_aioresponse.post('https://query.wikidata.org/sparql?format=json',
        body={'query':'\nSELECT ?child WHERE { ?child wdt:P279* wd:Q43229 }\n'},
        payload={
        'results':{'bindings':[
            {'child':{'value':'http://www.wikidata.org/entity/Q3918'}},
            {'child':{'value':'http://www.wikidata.org/entity/Q43229'}}
    ]}})
    assert (await type_matcher.is_subclass('Q3918', 'Q43229'))
    assert not (await type_matcher.is_subclass('Q1234', 'Q43229'))


