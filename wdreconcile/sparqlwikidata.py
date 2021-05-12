import config

async def sparql_wikidata(http_session, query_string):
    async with http_session.post(
            config.wikibase_sparql_endpoint,
            data={'query': query_string},
            params={'format': 'json'},
            headers={'User-Agent': config.user_agent}
            ) as r:
        results = await r.json()
        return results['results']
