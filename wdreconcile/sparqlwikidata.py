import requests
import config

async def sparql_wikidata(http_session, query_string):
    async with http_session.get(
            config.wikibase_sparql_endpoint,
            params={'query': query_string, 'format': 'json'},
            headers={'User-Agent': config.user_agent}
            ) as r:
        results = await r.json()
        return results['results']
