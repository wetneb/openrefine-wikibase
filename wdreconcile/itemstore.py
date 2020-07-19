import aiohttp
import asyncio
import json
from .language import language_fallback
from .sitelink import SitelinkFetcher
from config import redis_key_prefix, mediawiki_api_endpoint, user_agent

class ItemStore(object):
    """
    An interface that caches minified versions
    of Wikidata items.
    """
    def __init__(self, redis_client, http_session):
        self.http_session = http_session
        self.r = redis_client
        self.prefix = redis_key_prefix+'items'
        self.ttl = 60*60 # one hour
        self.max_items_per_fetch = 50 # constraint from the Wikidata API
        self.sitelink_fetcher = SitelinkFetcher(redis_client, http_session)
        self.local_cache = {}

    async def get_item(self, qid, force=False):
        """
        Get a single minified item from Wikidata (this is cached).
        It is more efficient to use get_items if you know in advance
        that you will fetch more items.
        """
        result = await self.get_items([qid], force=force)
        return result[qid]

    async def get_label(self, qid, lang):
        """
        Shortcut to get the label of an item for a specific language
        """
        item = await self.get_item(qid)
        return language_fallback(item.get('labels', {}), lang) or qid

    async def get_items(self, qids, force=False):
        """
        Fetch minified items from the Wikidata API, or retrieve them
        from the cache.

        If force is set to True, fetches all the items in the list,
        no matter if they are in the cache or not
        """
        if not qids:
            return {}
        if type(qids) != list:
            qids = list(qids)

        result = {}
        if force:
            to_fetch = qids
        else:
            to_fetch = []
            for qid in qids:
                if qid in self.local_cache:
                    result[qid] = self.local_cache[qid]
                else:
                    to_fetch.append(qid)

        fetched = await self._get_items_redis(qids, force)
        self.local_cache.update(fetched)
        result.update(fetched)
        return result

    async def _get_items_redis(self, qids, force=False):
        """
        Redis-cached version of _fetch_items
        """
        result = {}
        to_fetch = set()

        if force:
            to_fetch = set(qids)
        else:
            # Retrieve values that are already in the cache
            current_values = await self.r.mget(*[
                self._key_for_qid(qid)
                for qid in qids])
            for i, v in enumerate(current_values):
                if v is None:
                    to_fetch.add(qids[i])
                else:
                    result[qids[i]] = json.loads(v)

        if not to_fetch:
            return result

        items = await self._fetch_items(to_fetch)

        fetched = {}
        for qid, item in items.items():
            fetched[qid] = self.minify_item(item)

        if fetched:
            await self.r.mset({self._key_for_qid(qid) : json.dumps(v)
                         for qid, v in fetched.items()})
        for qid in fetched:
            await self.r.expire(self._key_for_qid(qid), self.ttl)

        result.update(fetched)
        return result

    async def _fetch_items(self, qids):
        """
        Internal helper, calling the API with batches of the right
        length
        """
        if not qids:
            return {}
        if type(qids) != list:
            qids = list(qids)

        batch_results = await asyncio.gather(*[
            self._fetch_item_batch(qids[i:i+self.max_items_per_fetch])
            for i in range(0, len(qids), self.max_items_per_fetch)
        ])
        results = {}
        for batch_result in batch_results:
            results.update(batch_result)
        return results

    async def _fetch_item_batch(self, qid_batch):
        """
        Fetches a single batch of items from the Wikibase API
        """
        async with self.http_session.get(mediawiki_api_endpoint,
                params={'action':'wbgetentities',
                'format':'json',
                'props':'aliases|labels|descriptions|claims|sitelinks',
                'ids':'|'.join(qid_batch)},
                headers={'User-Agent':user_agent},
                raise_for_status=True) as r:
            resp = await r.json()
            return resp.get('entities', {})

    def minify_item(self, item):
        """
        Simplifies the JSON payload returned by the API,
        for compactness and usefulness downstream in the pipeline
        """
        simplified = {'id':item['id']}

        # Add labels
        labels = {}
        for lang, lang_label in item.get('labels', {}).items():
            labels[lang] = lang_label['value']
        simplified['labels'] = labels

        # Add descriptions
        descriptions = {}
        for lang, lang_label in item.get('descriptions', {}).items():
            descriptions[lang] = lang_label['value']
        simplified['descriptions'] = descriptions

        # Add aliases (we don't remember the language for these)
        # TODO migrate everything to full_aliases
        aliases = set()
        full_aliases = {}
        for lang, lang_aliases in item.get('aliases', {}).items():
            alias_dct = []
            for lang_alias in lang_aliases:
                aliases.add(lang_alias['value'])
                alias_dct.append(lang_alias['value'])
            full_aliases[lang] = alias_dct

        simplified['aliases'] = list(aliases)
        simplified['full_aliases'] = full_aliases

        # Add other properties
        for prop_id, claims in item.get('claims', {}).items():
            # Get the preferred statement first
            ordered_claims = sorted(claims,
                key=lambda c: c.get('rank'), reverse=True)
            # (ranks are strings but they happen to be lexicographically ordered
            # in the order of precedence!! prefered > normal > deprecated)
            simplified[prop_id] = ordered_claims

        # Add datatype for properties
        simplified['datatype'] = item.get('datatype')

        # Add sitelinks
        simplified['sitelinks'] = {
            key : obj.get('title')
            for key, obj in (item.get('sitelinks') or {}).items()
        }

        return simplified


    def _key_for_qid(self, qid):
        return ':'.join([self.prefix, qid])


