
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
        Given a list of candidate sitelinks, return a list of
        the Qids they are associated to (or None if they are invalid,
        or not linked yet).

        >>> SitelinkFetcher.get_qids(['https://de.wikipedia.org/wiki/Chelsea Manning', 'http://gnu.org'])
        ['Q298423', None]
        >>> SitelinkFetcher.get_qids(['https://a.com/', 'http://b.org/']) # no request made
        [None, None]
        """
        result = [None] * len(sitelinks)

        normalized_sitelinks = [
            cls.normalize(sitelink)
            for sitelink in sitelinks
        ]

        if all(sitelink is None for sitelink in normalized_sitelinks):
            return result

        sitelink_list = ' '.join(
           '<%s>' % sitelink
            for sitelink in normalized_sitelinks
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
                idx = normalized_sitelinks.index(sitelink)
                result[idx] = qid
            except ValueError:
                print('Normalization error for sitelink: "{}"'.format(sitelink))

        return result

    @classmethod
    def sitelinks_to_qids(cls, sitelinks):
        """
        Same as get_qids, but returns a dictionary from the sitelinks to the qids

        >>> SitelinkFetcher.sitelinks_to_qids(['https://de.wikipedia.org/wiki/Chelsea Manning'])
        {'https://de.wikipedia.org/wiki/Chelsea_Manning': 'Q298423'}
        """
        normalized = list(map(cls.normalize, sitelinks))
        qids = cls.get_qids(normalized)
        return {
            sitelink:qid
            for sitelink, qid in zip(normalized, qids)
        }
