
import re

from .sparqlwikidata import sparql_wikidata
from .utils import to_q

class SitelinkFetcher(object):
    """
    Fetches Qids by sitelinks.
    """

    # https://www.mediawiki.org/wiki/Manual:$wgLegalTitleChars
    legal_title_chars = " %!\"$&'()*,\\-.\\/0-9:;=?@A-Z\\\\^_`a-z~\\x80-\\xFF+"

    wikimedia_sites = '|'.join([
        'wikipedia',
        'wikisource',
        'wikivoyage',
        'wikiquote',
        'wikinews',
        'wikiversity',
        'wiktionary',
    ])

    wikimedia_sites_without_capitalization = [
        'wiktionary',
    ]

    sitelink_regex = re.compile(
        r'^https?://([a-z]*)\.('+wikimedia_sites+')\.org/wiki/(['+legal_title_chars+']+)$')

    def __init__(self, redis_client):
        self.r = redis_client
        self.prefix = 'openrefine_wikidata:sitelinks'
        self.ttl = 60*60 # one hour

    @classmethod
    def normalize(cls, sitelink):
        """
        Given a candidate sitelink, normalize it,
        or returns None if it does not represent a sitelink.

        >>> SitelinkFetcher.normalize('http://en.wikipedia.org/wiki/cluny')
        'https://en.wikipedia.org/wiki/Cluny'
        >>> SitelinkFetcher.normalize(' http://fr.wikipedia.org/wiki/Alan%20Turing ')
        'https://fr.wikipedia.org/wiki/Alan_Turing'
        >>> SitelinkFetcher.normalize('https://de.wikiquote.org/wiki/Chelsea Manning')
        'https://de.wikiquote.org/wiki/Chelsea_Manning'
        >>> SitelinkFetcher.normalize('https://www.wikimedia.org/') is None
        True
        >>> SitelinkFetcher.normalize('https://fr.wikipedia.org/wiki/') is None
        True
        """
        if not sitelink:
            return None
        sitelink = str(sitelink).strip()
        match = cls.sitelink_regex.match(sitelink)
        if not match:
            return None
        cleaned_title = match.group(3).replace('%20', ' ').replace(' ', '_')
        wiki = match.group(2)
        if wiki not in cls.wikimedia_sites_without_capitalization:
            cleaned_title = cleaned_title[0].upper()+cleaned_title[1:]
        return 'https://{}.{}.org/wiki/{}'.format(
            match.group(1),
            wiki,
            cleaned_title)

    @classmethod
    def get_qids(cls, sitelinks):
        """
        Given a list of normalized sitelinks, return a list of
        the Qids they are associated to (or None if they are invalid,
        or not linked yet).

        >>> SitelinkFetcher.get_qids(['https://de.wikipedia.org/wiki/Chelsea_Manning', None])
        ['Q298423', None]
        >>> SitelinkFetcher.get_qids([None, None]) # no request made
        [None, None]
        """
        result = [None] * len(sitelinks)

        if all(sitelink is None for sitelink in sitelinks):
            return result

        sitelink_list = ' '.join(
           '<%s>' % sitelink
            for sitelink in sitelinks
            if sitelink
        )

        query = """
        PREFIX schema: <http://schema.org/>
        SELECT ?item ?sitelink WHERE {
        ?sitelink schema:about ?item .
        VALUES ?sitelink { %s }
        }
        """ % sitelink_list

        for binding in sparql_wikidata(query)['bindings']:
            qid = to_q(binding["item"]["value"])
            sitelink = binding["sitelink"]["value"]
            try:
                idx = sitelinks.index(sitelink)
                result[idx] = qid
            except ValueError:
                print('Normalization error for sitelink: "{}"'.format(sitelink))

        return result

    def _key_for_sitelink(self, sitelink):
        return ':'.join([self.prefix, sitelink])

    def sitelinks_to_qids(self, sitelinks):
        """
        Same as get_qids, but uses redis to cache the results, and normalizes its input,
        and returns the results as a dictionary..
        """
        normalized_sitelinks = list(map(SitelinkFetcher.normalize, sitelinks))
        non_nulls = [ sitelink for sitelink in normalized_sitelinks if sitelink ]
        result = {}
        to_fetch = set()

        if not non_nulls:
            return result

        # Query the cache for existing mappings
        current_values = self.r.mget([
            self._key_for_sitelink(sitelink)
            for sitelink in non_nulls])
        for i, v in enumerate(current_values):
            if v is None:
                to_fetch.add(non_nulls[i])
            else:
                result[non_nulls[i]] = v

        to_fetch = list(to_fetch)
        fetched = SitelinkFetcher.get_qids(to_fetch)
        to_write = {}
        for i, v in enumerate(fetched):
            if v:
                to_write[to_fetch[i]] = v
        result.update(to_write)

        # Write newly-fetched qids to the cache
        if to_write:
            self.r.mset({self._key_for_sitelink(sitelink) : qid
                    for sitelink, qid in to_write.items()})
        for sitelink in to_write:
            self.r.expire(self._key_for_sitelink(sitelink), self.ttl)

        return result


