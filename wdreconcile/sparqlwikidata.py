import requests
import config

def sparql_wikidata(query_string):
    results = requests.get(
        config.wikibase_sparql_endpoint,
        {'query': query_string, 'format': 'json'},
        headers={'User-Agent': config.user_agent}
        ).json()
    return results['results']
