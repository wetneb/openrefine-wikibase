import pytest
import json

pytestmark = pytest.mark.asyncio

# Helpers

@pytest.fixture
def query(engine):
    async def _query(query_string, **kwargs):
        kwargs['query'] = query_string
        kwargs['type'] = kwargs.get('typ')
        return await engine.process_single_query(kwargs)
    return _query

@pytest.fixture
def results(query):
    async def _results(*args, **kwargs):
        res = (await query(*args, **kwargs))['result']
        # try to dump it as JSON
        json.dumps(res)
        return res
    return _results

@pytest.fixture
def result_ids(query):
    async def _result_ids(*args, **kwargs):
        return [r['id'] for r in (await query(*args, **kwargs))['result']]
    return _result_ids

@pytest.fixture
def best_match_id(result_ids):
    async def _best_match_id(*args, **kwargs):
        return (await result_ids(*args, **kwargs))[0]
    return _best_match_id

@pytest.fixture
def best_score(results):
    async def _best_score(*args, **kwargs):
        return (await results(*args, **kwargs))[0]['score']
    return _best_score

# Tests start here

async def test_exact(best_match_id, mock_aioresponse):
    assert (
        await best_match_id('Recumbent bicycle') ==
        'Q750483')

async def test_wikidata_search_sucks(best_match_id, mock_aioresponse):
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
    assert (
        await best_match_id('United States', typ='Q6256') ==
        'Q30')

async def test_wikidata_search_does_not_rank_aliases_high_enough(best_match_id, mock_aioresponse):
    """
    Matches on aliases are not ranked high enough by the default search profile.
    """
    assert (
        await best_match_id('GER', typ='Q6256') ==
        'Q183')

async def test_empty(results, mock_aioresponse):
    assert (await results('') == [])

async def test_limit(results, mock_aioresponse):
    assert (len(await results('Cluny', limit=1)) == 1)
    assert (len(await results('Cluny', limit=3)) <= 3)
    assert (len(await results('Cluny', limit=20)) <= 20)

async def test_type(best_match_id, mock_aioresponse):
    assert (
        await best_match_id('Oxford', typ='Q3918') == 'Q34433')
    assert (
        await best_match_id('Oxford', typ='Q3957') == 'Q34217')

async def test_qid(best_match_id, best_score, mock_aioresponse):
    assert (await best_match_id('Q29568422') == 'Q29568422')
    assert (await best_score('Q29568422') == 100)

async def test_sitelink(best_score, best_match_id):
    assert (await best_match_id('https://de.wikipedia.org/wiki/Brüssel') == 'Q9005')
    assert (await best_score('https://de.wikipedia.org/wiki/Brüssel') == 100)
    assert (
        await best_score('Oxford', properties=[{'pid':'P17', 'v':'https://en.wikipedia.org/wiki/Cambridge'}])
        < 90)
    assert (await
        best_score('Oxford', properties=[{'pid':'P17', 'v':'https://en.wikipedia.org/wiki/United Kingdom'}])
        == 100)

async def test_reconciled_properties(best_score, mock_aioresponse):
    """
    For issue #32
    """
    assert (
        await best_score('Oxford', properties=[{'pid':'P17', 'v':{'id':'Q145'}}]) ==
        100)

async def test_shortest_qid_first(best_match_id, mock_aioresponse):
    """
    We could one day want to replace this by something
    more clever like PageRank

    For issue #26
    """
    assert (
        await best_match_id('Amsterdam') ==
        'Q727'
    )

async def test_unique_id(result_ids, best_score, best_match_id, mock_aioresponse):
    """
    We can fetch items by unique ids!
    """
    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0A++++++++SELECT+?qid+?value%0A++++++++(SAMPLE(COALESCE(?best_label,+?fallback_label))+as+?label)%0A++++++++WHERE+%7B%0A++++++++++++?qid+wdt:P214+?value.%0A++++++++++++VALUES+?value+%7B+%22142129514%22+%7D%0A++++++++++++OPTIONAL+%7B%0A++++++++++++++++?qid+rdfs:label+?best_label+.%0A++++++++++++++++FILTER(LANG(?best_label)+%3D+%22en%22)%0A++++++++++++%7D%0A++++++++++++OPTIONAL+%7B+?qid+rdfs:label+?fallback_label+%7D%0A++++++++%7D%0A++++++++GROUP+BY+?qid+?value%0A++++++++LIMIT+4%0A++++++++',
        payload={
        'results':{
            'bindings':[
                {'qid':{'value':'http://www.wikidata.org/entity/Q34433'}, 'value':{'value':'142129514'}}
            ]
        }
    })

    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0A++++++++SELECT+?qid+?value%0A++++++++(SAMPLE(COALESCE(?best_label,+?fallback_label))+as+?label)%0A++++++++WHERE+%7B%0A++++++++++++?qid+wdt:P214+?value.%0A++++++++++++VALUES+?value+%7B+%22142129514%22+%22144834915%22+%7D%0A++++++++++++OPTIONAL+%7B%0A++++++++++++++++?qid+rdfs:label+?best_label+.%0A++++++++++++++++FILTER(LANG(?best_label)+%3D+%22en%22)%0A++++++++++++%7D%0A++++++++++++OPTIONAL+%7B+?qid+rdfs:label+?fallback_label+%7D%0A++++++++%7D%0A++++++++GROUP+BY+?qid+?value%0A++++++++LIMIT+8%0A++++++++',
        payload={
        'results':{
            'bindings':[
                {'qid':{'value':'http://www.wikidata.org/entity/Q34433'}, 'value':{'value':'142129514'}},
                {'qid':{'value':'http://www.wikidata.org/entity/Q1377'}, 'value':{'value':'144834915'}}
            ]
        }
    })

    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0A++++++++SELECT+?qid+?value%0A++++++++(SAMPLE(COALESCE(?best_label,+?fallback_label))+as+?label)%0A++++++++WHERE+%7B%0A++++++++++++?qid+wdt:P214+?value.%0A++++++++++++VALUES+?value+%7B+%22144834915%22+%22142129514%22+%7D%0A++++++++++++OPTIONAL+%7B%0A++++++++++++++++?qid+rdfs:label+?best_label+.%0A++++++++++++++++FILTER(LANG(?best_label)+%3D+%22en%22)%0A++++++++++++%7D%0A++++++++++++OPTIONAL+%7B+?qid+rdfs:label+?fallback_label+%7D%0A++++++++%7D%0A++++++++GROUP+BY+?qid+?value%0A++++++++LIMIT+8%0A++++++++',
        payload={
        'results':{
            'bindings':[
                {'qid':{'value':'http://www.wikidata.org/entity/Q34433'}, 'value':{'value':'142129514'}},
                {'qid':{'value':'http://www.wikidata.org/entity/Q1377'}, 'value':{'value':'144834915'}}
            ]
        }
    })


    mock_aioresponse.get('https://query.wikidata.org/sparql?format=json&query=%0A++++++++SELECT+?qid+?value%0A++++++++(SAMPLE(COALESCE(?best_label,+?fallback_label))+as+?label)%0A++++++++WHERE+%7B%0A++++++++++++?qid+wdt:P1566+?value.%0A++++++++++++VALUES+?value+%7B+%22fictuous+id%22+%7D%0A++++++++++++OPTIONAL+%7B%0A++++++++++++++++?qid+rdfs:label+?best_label+.%0A++++++++++++++++FILTER(LANG(?best_label)+%3D+%22en%22)%0A++++++++++++%7D%0A++++++++++++OPTIONAL+%7B+?qid+rdfs:label+?fallback_label+%7D%0A++++++++%7D%0A++++++++GROUP+BY+?qid+?value%0A++++++++LIMIT+4%0A++++++++',
        payload={
        'results':{
            'bindings':[]
        }
    })

    # The search string does not matter: it is ignored
    # because we found an exact match by identifier.
    assert (
        await result_ids('this string is ignored',
        properties=[{'v':'142129514','pid':'P214'}]) ==
        ['Q34433'])

    # Not proving an id doesn't mess up the reconciliation
    assert (
        await best_match_id('University of Oxford',
        properties=[{'v':' ','pid':'P214'}]) ==
        'Q34433')

    # Providing two conflicting identifiers gives
    # two reconciliation candidates with maximum score.
    # They are therefore not matched automatically.
    assert (
        set(await result_ids('this string is ignored',
        properties=[{'v':'142129514','pid':'P214'},
                    {'v':'144834915','pid':'P214'}])) ==
        {'Q34433','Q1377'})

    # If no unique ID match is found, we fall back on
    # standard matching with same scoring as without
    # the unique ids (so that we can still get 100%
    # matches).
    assert (
        await best_score('Warsaw',
            properties=[{'v':'fictuous id','pid':'P1566'},
                {'v':'PL','pid':'P17/P297'}]) ==
        100)

async def test_items_without_types(results, mock_aioresponse):
    """
    Items without types can be returned only when
    there are no other typed items that match.
    """
    assert (
        len(await results('oxford', typ='Q3918')) ==
        2) # Oxford Brookes university and University of Oxford

async def test_forbidden_type(results):
    assert (len(await results('Category:Oxford')) == 0)

async def test_subfields(best_score, mock_aioresponse):
    # Exact match on the year of birth
    assert (
        await best_score("Steve Clark",
                typ="Q5",
                properties=[{"pid":"P569@year","v":"1943"}]) ==
        100)
    # Inexact match
    assert (
        await best_score("Steve Clark",
                typ="Q5",
                properties=[{"pid":"P569@year","v":"1342"}])
        < 100)

    # Float that is slightly off gets a non-zero score
    score = await best_score("Ramsden",
                typ="Q486972",
                properties=[{"pid":"P625@lat","v":"51.837"}])
    assert (score > 80)


async def test_fetch_values(engine, mock_aioresponse):
    assert (
        await engine.fetch_values({'item':'Q881333','prop':'P213', 'lang':'de'}) ==
        {'prop': 'P213', 'values': ['0000 0004 0547 722X'], 'item': 'Q881333'})
    assert (
        await engine.fetch_values({'item':'Q881333','prop':'P213', 'lang':'de', 'flat':'true'}) ==
        '0000 0004 0547 722X')
    assert (
        await engine.fetch_values({'item':'Q3068626','prop':'P463','label':'true', 'lang': 'fr'}) ==
        {'prop':'P463',
            'values': ['Académie lorraine des sciences'],
            'item':'Q3068626'})

async def test_fetch_properties_by_batch(engine, mock_aioresponse):
    # First, a simple test (two items, two properties)
    assert (
        await engine.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q34433","Q83259"],
                            "properties":[{"id":"P2427"},{"id":"P17/P297"}]}}) ==
        {"rows": {"Q34433": {"P17/P297": [{"str": "GB"}], "P2427": [{"str": "grid.4991.5"}]},
            "Q83259": {"P17/P297": [{"str": "FR"}], "P2427": [{"str": "grid.5607.4"}]}},
            "meta": [{"name": "GRID ID", "id": "P2427"}, {"name": "P17/P297", "id": "P17/P297"}]})

    # Second, a test with counts
    # (number of children of Michael Jackson)
    assert (
        await engine.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q2831"],
                            "properties":[{"id":"P40","settings":{"count":"on"}}]}}) ==
        {"rows": {"Q2831": {"P40": [{"float": 3}]}},
            "meta": [{"name": "child", "id": "P40", "settings" : {"count": "on"}}]})

    # Second, a test with counts and best ranks
    # (number of current currencies in France)
    assert (
        await engine.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q142"],
                            "properties":[{"id":"P38","settings":{"rank":"best","count":"on"}}]}}) ==
        {"rows": {"Q142": {"P38": [{"float": 1}]}},
            "meta": [{"name": "currency", "id": "P38", "settings" : {"count": "on","rank":"best"}}]})

async def test_fetch_qids(engine, mock_aioresponse):
    assert (
        await engine.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q34433"],
            "properties":[{"id":"qid"}]}}) ==
            {"meta": [{"id": "qid", "name": "Qid"}], "rows": {"Q34433": {"qid": [{"str":"Q34433"}]}}}
        )

async def test_fetch_years(engine, mock_aioresponse):
    assert (
        await engine.fetch_properties_by_batch({"lang":"en","extend":{"ids":["Q34433"],"properties":[{"id":"P571"}]}}) ==
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
