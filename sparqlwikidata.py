from SPARQLWrapper import SPARQLWrapper, JSON

def sparql_wikidata(query_string):
    sparql_endpoint = SPARQLWrapper("https://query.wikidata.org/bigdata/namespace/wdq/sparql")
    sparql_endpoint.setQuery(query_string)
    sparql_endpoint.setReturnFormat(JSON)
    results = sparql_endpoint.query().convert()
    return results['results']
