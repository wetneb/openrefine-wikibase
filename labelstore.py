import requests
import json

class LabelStore(object):
    """
    An interface that caches item labels and
    fetches them by batch
    """
    def __init__(self, redis_client):
        self.r = redis_client
        self.prefix = 'openrefine_wikidata_labels'
        self.ttl = 60*60 # one hour

    def get_label(self, qid, lang):
        """
        Get the label of a Wikidata item for a particular language
        """
        cached = self._get_label_from_cache(qid, lang)
        if cached is not None:
            return cached
        result = self.prefetch_labels([qid], lang, force=True)
        return result[qid]

    def prefetch_labels(self, qids, lang, force=False):
        """
        Prefetch labels from the Wikidata API.
        If force is set to True, fetches all the items in the list,
        no matter if they are in the cache or not
        """
        result = {}
        if force:
            to_fetch = qids
        else:
            current_values = self.r.mget([
                self._key_for_label(qid, lang)
                for qid in qids])
            to_fetch = []
            for i, v in enumerate(current_values):
                if v is None:
                    to_fetch.append(qids[i])
                else:
                    result[qids[i]] = v

        if not to_fetch:
            return result

        r = requests.get('https://www.wikidata.org/w/api.php',
            {'action':'wbgetentities',
            'format':'json',
            'props':'labels',
            'languages':lang,
            'ids':'|'.join(to_fetch)})
        print(r.url)
        resp = r.json()
        print(resp)

        fetched = {}
        for k, labels in resp.get('entities', {}).items():
            fetched[k] = labels.get('labels', {}).get(
                                    lang, {}).get(
                                    'value')

        self.r.mset({self._key_for_label(qid, lang) : v
                     for qid, v in fetched.items()}, ex=self.ttl)

        result.update(fetched)
        return result

    def _key_for_label(self, qid, lang):
        return ':'.join([self.prefix, lang, qid])

    def _store_label(self, qid, lang, value):
        self.r.set(self._key_for_label(qid, lang),
                value, ex=self.ttl)

    def _get_label_from_cache(self, qid, lang):
        return self.r.get(self._key_for_label(qid, lang))


