from .utils import to_q
from .sparqlwikidata import sparql_wikidata
import config
from string import Template

class TypeMatcher(object):
    """
    Interface that caches the subclasses of parent classes.
    Cached using Redis sets, with expiration.
    """

    def __init__(self, redis_client, http_session):
        self.r = redis_client
        self.http_session = http_session
        self.prefix = config.redis_key_prefix+':children'
        self.ttl = 24*60*60 # 1 day
        self.local_cache = {}

    async def is_subclass(self, qid_1, qid_2):
        """
        Checks if the Wikidata item designated by
        the first QID is a subclass of the second.

        Equivalent SPARQL query:
        ?qid_1 wdt:P279* ?qid_2

        This is done by caching the children of
        the class via the "subclass of" (P279)
        relation.
        """
        cache_key = qid_1+'_'+qid_2
        cache_hit = self.local_cache.get(cache_key)
        if cache_hit is not None:
            return cache_hit
        await self.prefetch_children(qid_2)
        result =  await self.r.sismember(self._key_name(qid_2), qid_1)
        self.local_cache[cache_key] = result
        return result

    async def prefetch_children(self, qid, force=False):
        """
        Prefetches (in Redis) all the children of a given class
        """
        key_name = self._key_name(qid)

        if await self.r.exists(key_name):
            return # children are already prefetched

        for child_qid in await self._fetch_children(qid):
            await self.r.sadd(key_name, child_qid)

        # set expiration
        await self.r.expire(key_name, self.ttl)

    async def _fetch_children(self, qid):
        sparql_query = Template(config.sparql_query_to_fetch_subclasses).substitute(qid=qid)
        results = await sparql_wikidata(self.http_session, sparql_query)
        qids = [to_q(result['child']['value'])
            for result in results["bindings"]]
        return [qid for qid in qids if qid]

    def _key_name(self, qid):
        return ':'.join([self.prefix, qid])

