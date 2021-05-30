import pytest
import re
from wdreconcile.suggest import SuggestEngine, commons_image_url

from aiohttp import ServerTimeoutError

pytestmark = pytest.mark.asyncio

# Helpers

@pytest.fixture
def query(suggest_engine):
    async def _query(typ, query_string, **kwargs):
        kwargs['prefix'] = query_string
        if typ == 'type':
            return await suggest_engine.find_type(kwargs)
        elif typ == 'property':
            return await suggest_engine.find_property(kwargs)
        elif typ == 'entity':
            return await suggest_engine.find_entity(kwargs)
    return _query

@pytest.fixture
def results(query):
    async def _results(*args, **kwargs):
        return (await query(*args, **kwargs))['result']
    return _results

@pytest.fixture
def best_match_id(results):
    async def _best_match_id(*args, **kwargs):
        return (await results(*args, **kwargs))[0]['id']
    return _best_match_id

@pytest.fixture
def preview(suggest_engine):
    async def _preview(**kwargs):
        return await suggest_engine.preview(kwargs)
    return _preview

@pytest.fixture
def propose(suggest_engine):
    async def _propose_properties(resolved_type, **kwargs):
        kwargs['type'] = resolved_type
        if 'lang' not in kwargs:
            kwargs['lang'] = 'en'
        return (await suggest_engine.propose_properties(kwargs))['properties']
    return _propose_properties

# Tests start here

async def test_exact(best_match_id, results, mock_aioresponse):
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=fr&search=V%C3%A9lo+couch%C3%A9&type=item&uselang=fr',
        payload={'searchinfo': {'search': 'Vélo couché'}, 'search': [{'id': 'Q750483', 'title': 'Q750483', 'pageid': 706158, 'repository': 'wikidata', 'url': '//www.wikidata.org/wiki/Q750483', 'concepturi': 'http://www.wikidata.org/entity/Q750483',
'label': 'Vélo couché', 'description': 'Type of bicycle', 'match': {'type': 'label', 'language': 'fr', 'text': 'Vélo couché'}}, {'id': 'Q3564076', 'title': 'Q3564076', 'pageid': 3392974, 'repository': 'wikidata', 'url': '//www.wikidata.org/wiki/Q3564076',
'concepturi': 'http://www.wikidata.org/entity/Q3564076', 'label': 'vélo couché à traction directe', 'description': 'type de vélo couché', 'match': {'type': 'label', 'language': 'fr', 'text': 'vélo couché à traction directe'}}], 'success': 1})

    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=Ringgold+identifier&type=property&uselang=en',
        payload={'searchinfo': {'search': 'Ringgold identifier'}, 'search': [{'id': 'P3500', 'title': 'Property:P3500', 'pageid': 30174486, 'repository': 'wikidata', 'url': '//www.wikidata.org/wiki/Property:P3500', 'datatype': 'external-id', 'concepturi':
'http://www.wikidata.org/entity/P3500', 'label': 'Ringgold ID', 'description': 'identifier for organisations in the publishing industry supply chain', 'match': {'type': 'alias', 'language': 'en', 'text': 'Ringgold identifier'}, 'aliases': ['Ringgold identifier']}], 'success': 1})


    item_results = await results('entity', 'Vélo couché', lang='fr')
    assert (
        item_results[0]['id'] ==
        'Q750483')
    assert (
        item_results[0]['description'] ==
        'Type of bicycle')
    assert (
        await best_match_id('property', 'Ringgold identifier') ==
        'P3500')

async def test_sparql(best_match_id, mock_aioresponse):
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=P17/P297&type=property&uselang=en',
        payload={'success': 1, 'search': []})
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=P17/(P297%7C.)&type=property&uselang=en',
        payload={'success': 1, 'search': []})
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=Len&type=property&uselang=en',
        payload={'success': 1, 'search': []})
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=Afr%7CLfr&type=property&uselang=en',
        payload={'success': 1, 'search': []})
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=qid&type=property&uselang=en',
        payload={'success': 1, 'search': []})
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=SPARQL:+P17/P297&type=property&uselang=en',
        payload={'success': 1, 'search': []})

    assert (
        await best_match_id('property', 'P17/P297') ==
        'P17/P297')
    assert (
        await best_match_id('property', 'P17/(P297|.)') ==
        'P17/(P297|.)')
    assert (
        await best_match_id('property', 'Len') ==
        'Len')
    assert (
        await best_match_id('property', 'Afr|Lfr') ==
        'Afr|Lfr')
    assert (
        await best_match_id('property', 'SPARQL: P17/P297') ==
        'P17/P297')
    assert (
        await best_match_id('property', 'qid') ==
        'qid')

async def test_sparql_not_first_for_pid(results, mock_aioresponse):
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language=en&search=P17&type=property&uselang=en',
        payload={'searchinfo': {'search': 'P17'}, 'search': [{'id': 'P17', 'title': 'Property:P17', 'pageid': 3917520, 'repository': 'wikidata', 'url': '//www.wikidata.org/wiki/Property:P17', 'datatype': 'wikibase-item', 'concepturi': 'http://www.wikidata.org/entity/P17', 'label': 'country', 'description': 'sovereign state of this item (not to be used for human beings)', 'match': {'type': 'entityId', 'text': 'P17'}, 'aliases': ['P17']}], 'success': 1})

    results = await results('property', 'P17', lang='en')
    assert (results[0]['name'] == 'country')

async def test_custom_language(preview, mock_aioresponse, test_app):
    async with test_app.app_context():
        assert ('ville' in
            await preview(id='Q350',lang='fr'))

async def test_single_letter(preview, mock_aioresponse, test_app):
    async with test_app.app_context():
        assert ('È' in await preview(id='Q10008', lang='en'))

async def test_preview_autodesc_down(preview, mock_aioresponse, test_app):
    mock_aioresponse.get(re.compile(r'https://autodesc\.toolforge\.org/.*'), exception=ServerTimeoutError())
    async with test_app.app_context():
        assert ('\u53c2\u4e0e\u5546' in
            await preview(id='Q4830453', lang='zh'))

async def test_propose_property(propose, mock_aioresponse):
    mock_aioresponse.post('https://query.wikidata.org/sparql?format=json',
        body={'query':'\nSELECT ?prop ?propLabel ?depth WHERE {\nSERVICE gas:service {\n    gas:program gas:gasClass "com.bigdata.rdf.graph.analytics.BFS" .\n    gas:program gas:in wd:Q3918 .\n    gas:program gas:out ?out .\n    gas:program gas:out1 ?depth .\n    gas:program gas:maxIterations 10 .\n    gas:program gas:maxVisited 100 .\n    gas:program gas:linkType wdt:P279 .\n}\nSERVICE wikibase:label { bd:serviceParam wikibase:language "fr" }\n?out wdt:P1963 ?prop .\n}\nORDER BY ?depth\nLIMIT 5\n'},
    payload={'results':{'bindings': [{'depth': {'datatype': 'http://www.w3.org/2001/XMLSchema#int', 'type': 'literal', 'value': '0'}, 'prop': {'type': 'uri', 'value': 'http://www.wikidata.org/entity/P17'}, 'propLabel': {'xml:lang': 'fr', 'type': 'literal', 'value':
'pays'}}, {'depth': {'datatype': 'http://www.w3.org/2001/XMLSchema#int', 'type': 'literal', 'value': '0'}, 'prop': {'type': 'uri', 'value': 'http://www.wikidata.org/entity/P131'}, 'propLabel': {'xml:lang': 'fr', 'type': 'literal', 'value': 'localisation administrative'}}, {'depth': {'datatype': 'http://www.w3.org/2001/XMLSchema#int', 'type': 'literal', 'value': '0'}, 'prop': {'type': 'uri', 'value': 'http://www.wikidata.org/entity/P571'}, 'propLabel': {'xml:lang': 'fr', 'type': 'literal', 'value': 'date de fondation ou de création'}}, {'depth': {'datatype': 'http://www.w3.org/2001/XMLSchema#int', 'type': 'literal', 'value': '0'}, 'prop': {'type': 'uri', 'value': 'http://www.wikidata.org/entity/P576'}, 'propLabel': {'xml:lang': 'fr', 'type': 'literal',
'value': 'date de dissolution ou de démolition'}}, {'depth': {'datatype': 'http://www.w3.org/2001/XMLSchema#int', 'type': 'literal', 'value': '0'}, 'prop': {'type': 'uri', 'value': 'http://www.wikidata.org/entity/P856'}, 'propLabel': {'xml:lang': 'fr',
'type': 'literal', 'value': 'site officiel'}}]}})

    # We follow wdt:P279 to find properties higher up:
    # number of students (P2196) is marked on "institutional
    # education", whose "university (Q3918)" is a subclass of.
    results = await propose('Q3918', limit=5, lang='fr')
    assert (len(results) == 5)
    assert ('P571' in [p['id'] for p in results])
    assert ("pays" in [p['name'] for p in results])

async def test_flyout(suggest_engine):
    assert ('humorist' in
        (await suggest_engine.flyout({'id':'Q42','lang':'en'}))['html'])

def test_commons_url():
    assert (commons_image_url('Wikidata-logo-en.svg')).endswith('.png')

