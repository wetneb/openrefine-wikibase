from SPARQLWrapper import SPARQLWrapper, JSON
from utils import to_q

class TypeMatcher(object):
    """
    Interface that caches the subclasses of parent classes.
    Cached using Redis sets, with expiration.
    """

    def __init__(self, redis_client):
        self.r = redis_client
        self.prefix = 'openrefine_wikidata:children'
        self.ttl = 24*60*60 # 1 day
        self.sparql = SPARQLWrapper("https://query.wikidata.org/bigdata/namespace/wdq/sparql")

    def is_subclass(self, qid_1, qid_2):
        """
        Checks if the Wikidata item designated by
        the first QID is a subclass of the second.

        Equivalent SPARQL query:
        ?qid_1 wdt:P279* ?qid_2

        This is done by caching the children of
        the class via the "subclass of" (P279)
        relation.
        """
        self.prefetch_children(qid_2)
        return self.r.sismember(self._key_name(qid_2), qid_1)

    def prefetch_children(self, qid, force=False):
        """
        Prefetches (in Redis) all the children of a given class
        """
        key_name = self._key_name(qid)

        if self.r.exists(key_name):
            return # children are already prefetched

        sparql_query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        SELECT ?child WHERE { ?child wdt:P279* wd:%s }
        """ % qid
        self.sparql.setQuery(sparql_query)
        self.sparql.setReturnFormat(JSON)
        results = self.sparql.query().convert()

        for result in results["results"]["bindings"]:
            child_qid = to_q(result["child"]["value"])
            self.r.sadd(key_name, child_qid)

        # set expiration
        self.r.expire(key_name, self.ttl)

    def _key_name(self, qid):
        return ':'.join([self.prefix, qid])

