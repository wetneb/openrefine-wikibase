import pytest

pytestmark = pytest.mark.asyncio

async def test_resolve_redirects_for_titles(sitelink_fetcher, mock_aioresponse):
    # Mock http call
    mock_aioresponse.get('https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&titles=Knuth-Bendix%7CLowendal%7CParis',
    payload={'batchcomplete': '', 'query': {'redirects': [{'from': 'Lowendal', 'to': 'Ulrich Friedrich Woldemar von Löwendal'}, {'from': 'Knuth-Bendix', 'to': 'Knuth–Bendix completion algorithm'}], 'pages': {'22989': {'pageid': 22989, 'ns': 0, 'title': 'Paris'}, '614147': {'pageid': 614147, 'ns': 0, 'title': 'Knuth–Bendix completion algorithm'}, '24683124': {'pageid': 24683124, 'ns': 0, 'title': 'Ulrich Friedrich Woldemar von Löwendal'}}}})

    resolved = await sitelink_fetcher.resolve_redirects_for_titles('en','wikipedia', ['Knuth-Bendix','Lowendal', 'Paris'])
    assert resolved == ['Knuth–Bendix completion algorithm', 'Ulrich Friedrich Woldemar von Löwendal', 'Paris']

async def test_get_qids(sitelink_fetcher, mocker, mock_aioresponse):
    # Mock redirection resolution
    async def mocked_resolve_redirects(lang_code, project, titles):
        if (lang_code, project, titles) == ('de', 'wikipedia', ['Chelsea Manning']):
            return ['Chelsea Manning']
        elif (lang_code, project, titles) == ('en', 'wikipedia', ['Knuth-Bendix']):
            return ['Knuth–Bendix completion algorithm']
        else:
            raise ValueError(f'redirect call not mocked: {lang_code} {project} {titles}')

    # Mock HTTP calls
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=sitelinks&sites=dewiki&titles=Chelsea+Manning',
        payload={'entities': {'Q298423': {'type': 'item', 'id': 'Q298423', 'sitelinks': {'dewiki': {'site': 'enwiki', 'title': 'Chelsea Manning', 'badges': []}}}}, 'success': 1})
    mock_aioresponse.get('https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=sitelinks&sites=enwiki&titles=Knuth%E2%80%93Bendix+completion+algorithm',
        payload={'entities': {'Q2835803': {'type': 'item', 'id': 'Q2835803', 'sitelinks': {'enwiki': {'site': 'enwiki', 'title': 'Knuth–Bendix completion algorithm', 'badges': []}}}}, 'success': 1})

    sitelink_fetcher.resolve_redirects_for_titles = mocked_resolve_redirects

    qids = await sitelink_fetcher.get_qids(['https://de.wikipedia.org/wiki/Chelsea_Manning', 'https://en.wikipedia.org/wiki/Knuth-Bendix'])
    assert qids == ['Q298423', 'Q2835803']

async def test_get_no_qids(sitelink_fetcher, mock_aioresponse):
    qids = await sitelink_fetcher.get_qids([None, None]) # no request made
    assert qids == [None, None]

async def test_redis_cached(sitelink_fetcher):
    example_mapping = {
        'https://de.wikipedia.org/wiki/Chelsea_Manning':'Q298423',
        'https://en.wikipedia.org/wiki/Knuth-Bendix':'Q2835803'
    }
    example_sitelinks = ['https://de.wikipedia.org/wiki/Chelsea_Manning', 'https://en.wikipedia.org/wiki/Knuth-Bendix']

    async def mocked_get_qids(sitelinks):
        return [example_mapping.get(sitelink) for sitelink in sitelinks]

    sitelink_fetcher.get_qids = mocked_get_qids

    qids = await sitelink_fetcher.sitelinks_to_qids(example_sitelinks)

    assert (qids == example_mapping)

    # We try again and this time we should hit the cache
    async def noop(sitelinks):
        raise ValueError('get_qids called again')

    sitelink_fetcher.get_qids = noop

    qids = await sitelink_fetcher.sitelinks_to_qids(example_sitelinks)

    assert (qids == example_mapping)
