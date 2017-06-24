import requests
import json
from language import language_fallback

class ItemStore(object):
    """
    An interface that caches minified versions
    of Wikidata items.
    """
    def __init__(self, redis_client):
        self.r = redis_client
        self.prefix = 'openrefine_wikidata:items'
        self.ttl = 60*60 # one hour
        self.max_items_per_fetch = 50 # constraint from the Wikidata API

    def get_item(self, qid, force=False):
        """
        Get a single minified item from Wikidata (this is cached).
        It is more efficient to use get_items if you know in advance
        that you will fetch more items.
        """
        result = self.get_items([qid], force=force)
        return result[qid]

    def get_label(self, qid, lang):
        """
        Shortcut to get the label of an item for a specific language
        """
        item = self.get_item(qid)
        return language_fallback(item.get('labels', {}), lang) or qid

    def get_items(self, qids, force=False):
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
        to_fetch = set()

        if force:
            to_fetch = set(qids)
        else:
            # Retrieve values that are already in the cache
            current_values = self.r.mget([
                self._key_for_qid(qid)
                for qid in qids])
            for i, v in enumerate(current_values):
                if v is None:
                    to_fetch.add(qids[i])
                else:
                    result[qids[i]] = json.loads(v)

        if not to_fetch:
            return result

        items = self._fetch_items(to_fetch)

        fetched = {}
        for qid, item in items.items():
            fetched[qid] = self.minify_item(item)

        if fetched:
            self.r.mset({self._key_for_qid(qid) : json.dumps(v)
                         for qid, v in fetched.items()})
        for qid in fetched:
            self.r.expire(self._key_for_qid(qid), self.ttl)

        result.update(fetched)
        return result

    def _fetch_items(self, qids):
        """
        Internal helper, calling the API with batches of the right
        length
        """
        if not qids:
            return {}
        if type(qids) != list:
            qids = list(qids)

        first_batch = qids[:self.max_items_per_fetch]
        r = requests.get('https://www.wikidata.org/w/api.php',
            {'action':'wbgetentities',
            'format':'json',
            'props':'aliases|labels|descriptions|claims',
            'ids':'|'.join(first_batch)})
        print(r.url)
        r.raise_for_status()
        resp = r.json()

        first_items = resp.get('entities', {})
        if len(qids) > self.max_items_per_fetch:
            remaining = qids[self.max_items_per_fetch:]
            first_items.update(self._fetch_items(remaining))

        return first_items


    def minify_item(self, item):
        """
        Simplifies the JSON payload returned by the API,
        for compactness and usefulness downstream in the pipeline
        """
        simplified = {}

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
        aliases = set()
        for lang, lang_aliases in item.get('aliases', {}).items():
            for lang_alias in lang_aliases:
                aliases.add(lang_alias['value'])

        simplified['aliases'] = list(aliases)

        # Add other properties
        for prop_id, claims in item.get('claims', {}).items():
            values = []
            # Get the preferred statement first
            ordered_claims = sorted(claims,
                key=lambda c: 0 if c.get('rank') == 'preferred' else 1)

            for claim in ordered_claims:
                dataval = claim.get('mainsnak', {})
                values.append(dataval)
            simplified[prop_id] = values

        return simplified


    def _key_for_qid(self, qid):
        return ':'.join([self.prefix, qid])


