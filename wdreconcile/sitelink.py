
import re
import aiohttp
from urllib.parse import quote_plus, unquote_plus
from collections import defaultdict

from .utils import to_q
from config import redis_key_prefix, mediawiki_api_endpoint

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
        'wikibooks',
    ])

    wikimedia_sites_without_capitalization = [
        'wiktionary',
    ]

    sitelink_regex = re.compile(
        r'^https?://([a-z]*)\.('+wikimedia_sites+')\.org/wiki/(['+legal_title_chars+']+)$')

    def __init__(self, redis_client, http_session):
        self.r = redis_client
        self.prefix = redis_key_prefix+'sitelinks'
        self.ttl = 60*60 # one hour
        self.http_session = http_session

    @classmethod
    def parse(cls, sitelink):
        """
        Returns a parsed version of the wiki link

        >>> SitelinkFetcher.parse('http://en.wikipedia.org/wiki/cluny')
        ('en', 'wikipedia', 'Cluny')
        >>> SitelinkFetcher.parse(' http://fr.wikipedia.org/wiki/Alan%20Turing ')
        ('fr', 'wikipedia', 'Alan Turing')
        >>> SitelinkFetcher.parse('https://de.wikiquote.org/wiki/Chelsea Manning')
        ('de', 'wikiquote', 'Chelsea Manning')
        >>> SitelinkFetcher.parse('https://de.wikiquote.org/wiki/Brüssel')
        ('de', 'wikiquote', 'Brüssel')
        >>> SitelinkFetcher.parse('https://de.wikiquote.org/wiki/Br%C3%BCssel')
        ('de', 'wikiquote', 'Brüssel')
        >>> SitelinkFetcher.parse('https://www.wikimedia.org/') is None
        True
        >>> SitelinkFetcher.parse('https://fr.wikipedia.org/wiki/') is None
        True

        """
        if not sitelink:
            return None
        sitelink = str(sitelink).strip()
        match = cls.sitelink_regex.match(sitelink)
        if not match:
            return None

        title = match.group(3).replace('%20', ' ').replace('_', ' ')
        title = unquote_plus(title)

        wiki = match.group(2)
        if wiki not in cls.wikimedia_sites_without_capitalization:
            title = title[0].upper()+title[1:]

        lang_code = match.group(1)
        return (lang_code, wiki, title)

    @classmethod
    def wiki_id(cls, lang_code, domain):
        """
        Returns the wiki name in the API given the language code and domain.

        >>> SitelinkFetcher.wiki_id('en', 'wikipedia')
        'enwiki'
        >>> SitelinkFetcher.wiki_id('de', 'wikibooks')
        'dewikibooks'
        """
        domain_fixed = 'wiki' if domain == 'wikipedia' else domain
        return lang_code + domain_fixed

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
        >>> SitelinkFetcher.normalize('https://de.wikiquote.org/wiki/Brüssel')
        'https://de.wikiquote.org/wiki/Br%C3%BCssel'
        >>> SitelinkFetcher.normalize('https://de.wikiquote.org/wiki/Br%C3%BCssel')
        'https://de.wikiquote.org/wiki/Br%C3%BCssel'
        >>> SitelinkFetcher.normalize('https://www.wikimedia.org/') is None
        True
        >>> SitelinkFetcher.normalize('https://fr.wikipedia.org/wiki/') is None
        True
        """
        parsed = cls.parse(sitelink)
        if not parsed:
            return None
        lang_code, wiki, title = parsed

        cleaned_title = quote_plus(title.replace(' ', '_'))

        return 'https://{}.{}.org/wiki/{}'.format(
            lang_code,
            wiki,
            cleaned_title)

    async def get_qids_via_api(self, wiki_id, titles):
        """
        Given a wiki code and a list of titles for that wiki,
        return the list of qids (or Nones) corresponding to these
        titles
        """
        results = [None] * len(titles)
        title_string = '|'.join(titles)
        params =  {'action': 'wbgetentities',
                 'props': 'sitelinks',
                 'sites': wiki_id,
                 'titles': title_string,
                 'format': 'json'}
        try:
            async with self.http_session.get(mediawiki_api_endpoint, params=params, raise_for_status=True) as r:
                json_resp = await r.json()
                for qid, item in json_resp.get('entities', {}).items():
                    own_title = item.get('sitelinks', {}).get(wiki_id, {}).get('title')
                    if own_title:
                        idx = titles.index(own_title)
                        results[idx] = qid

        except aiohttp.ClientResponseError as e:
            print(e)
        except ValueError as e:
            print("Unexpected error in get_qids_via_api")
            raise e
        return results

    async def resolve_redirects_for_titles(self, lang_code, wiki, titles):
        async with self.http_session.get('https://{}.{}.org/w/api.php'.format(lang_code, wiki),
                params={
                    'action': 'query',
                    'format': 'json',
                    'redirects': '1',
                    'titles': '|'.join(titles),
                },
                raise_for_status=True) as r:
            json_response = await r.json()
            response = json_response['query'].get('redirects', [])
            redirect_map = {
                redirect['from']:redirect['to']
                for redirect in response
            }

            results = []
            for title in titles:
                while title in redirect_map:
                    title = redirect_map[title]
                results.append(title)
            return results

    async def get_qids(self, sitelinks):
        """
        Given a list of normalized sitelinks, return a list of
        the Qids they are associated to (or None if they are invalid,
        or not linked yet).
        """
        qids = [None] * len(sitelinks)

        # Group sitelinks by wiki
        by_wiki = defaultdict(list)
        for idx, sitelink in enumerate(sitelinks):
            parsed = self.parse(sitelink)
            if parsed:
                lang_code, wiki, title = parsed
                by_wiki[(lang_code, wiki)].append((idx, title))

        # TODO use gather to run these requests in parallel
        for (lang_code, wiki), titles in by_wiki.items():
            # Resolve redirects
            redirected_titles = await self.resolve_redirects_for_titles(lang_code, wiki, [title for _, title in titles])

            # Resolve qids
            wiki_id = self.wiki_id(lang_code, wiki)
            current_qids = await self.get_qids_via_api(wiki_id, redirected_titles)

            for new_idx, (orig_idx, title) in enumerate(titles):
                qids[orig_idx] = current_qids[new_idx]

        return qids

    def _key_for_sitelink(self, sitelink):
        return ':'.join([self.prefix, sitelink])

    async def sitelinks_to_qids(self, sitelinks):
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
        keys = [
            self._key_for_sitelink(sitelink)
            for sitelink in non_nulls]
        current_values = await self.r.mget(*keys)
        for i, v in enumerate(current_values):
            if v is None:
                to_fetch.add(non_nulls[i])
            else:
                result[non_nulls[i]] = v

        to_fetch = list(to_fetch)
        to_write = {}
        if to_fetch:
            fetched = await self.get_qids(to_fetch)
            for i, v in enumerate(fetched):
                if v:
                    to_write[to_fetch[i]] = v
            result.update(to_write)

        # Write newly-fetched qids to the cache
        if to_write:
            await self.r.mset({self._key_for_sitelink(sitelink) : qid
                    for sitelink, qid in to_write.items()})
        for sitelink in to_write:
            await self.r.expire(self._key_for_sitelink(sitelink), self.ttl)

        return result


