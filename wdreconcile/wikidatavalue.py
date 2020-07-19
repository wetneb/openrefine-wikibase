import dateutil.parser
from urllib.parse import urlparse, urlunparse
import math

from .sitelink import SitelinkFetcher
from .utils import to_q, fuzzy_match_strings, match_ints, match_floats

wdvalue_mapping = {}

def register(cls):
    wdvalue_mapping[cls.value_type] = cls
    return cls

# TODO treat somevalue and novalue differently

class WikidataValue(object):
    """
    This class represents any target value of a Wikidata claim.
    """
    value_type = None

    def __init__(self, **json):
        self.json = json

    async def match_with_str(self, s, item_store):
        """
        Given a string s (the target reconciliation value),
        return a matching score with the WikidataValue.

        An ItemStore is provided to fetch information
        about items if needed.

        Scores should be returned between 0 and 100

        :param s: the string to match with
        :param item_store: an ItemStore, to retrieve items if needed
        """
        return 0

    @classmethod
    def from_datavalue(self, wd_repr):
        """
        Creates a WikidataValue from the JSON representation
        of a Wikibase datavalue.

        For now, somevalues are treated just like novalues:

        >>> WikidataValue.from_datavalue({'snaktype': 'somevalue', 'datatype': 'wikibase-item', 'property': 'P61'}).is_novalue()
        True
        """
        typ = wd_repr['datatype']
        val = wd_repr.get('datavalue', {}) # not provided for somevalue
        cls = wdvalue_mapping.get(typ, UndefinedValue)
        return cls.from_datavalue(val)

    def is_novalue(self):
        return self.json == {}

    def as_string():
        """
        String representation of the value,
        for the old API that only returns strings
        """
        raise NotImplemented

    async def as_openrefine_cell(self, lang, item_store):
        """
        Returns a JSON representation for the
        OpenRefine extend API.

        Subclasses should reimplement _as_cell instead.

        :param lang: the language in which the cell should be displayed
        :param item_store: an ItemStore, to retrieve items if needed
        """
        if self.is_novalue():
            return {}
        return await self._as_cell(lang, item_store)

    async def _as_cell(self, lang, item_store):
        """
        This method can assume that the value is not a novalue

        :param lang: the language in which the cell should be displayed
        :param item_store: an ItemStore, to retrieve items if needed
        """
        raise NotImplemented

    def __getattr__(self, key):
        """
        For convenience:
        """
        return self.json[key]

    def __eq__(self, other):
        if isinstance(other, WikidataValue):
            return (other.value_type == self.value_type and
                    other.json == self.json)
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return ("%s(%s)" %
                (type(self).__name__,
                (",".join([key+'='+val.__repr__()
                 for key, val in self.json.items()]))))

    def __hash__(self):
        val = (self.value_type,
            tuple(sorted(self.json.items(),
                key=lambda k:k[0])))
        return val.__hash__()

@register
class ItemValue(WikidataValue):
    """
    Fields:
    - id (string)
    """
    value_type = "wikibase-item"

    @classmethod
    def from_datavalue(self, wd_repr):
        v = wd_repr.get('value')
        if not v or not 'id' in v:
            return ItemValue()
        else:
            return ItemValue(id=v['id'])

    async def match_with_str(self, s, item_store):
        # Novalue / somevalue case
        if 'id' not in self.json:
            return 0

        # First check if the target string looks like a Qid
        qid = to_q(s)
        if qid:
            return 100 if qid == self.id else 0
        # Then check for a sitelink
        sitelink = SitelinkFetcher.normalize(s)
        if sitelink:
            target_qid = (await item_store.sitelink_fetcher.sitelinks_to_qids(
                [sitelink])).get(sitelink)
            return 100 if target_qid == self.id else 0

        # Then check for a novalue match
        if not s and self.is_novalue():
            return 100

        # Otherwise try to match the string to the labels and
        # aliases of the item.
        item = await item_store.get_item(self.id)
        labels = list(item.get('labels', {}).values())
        aliases = item.get('aliases', [])
        matching_scores = [
            fuzzy_match_strings(s, name)
            for name in labels+aliases
        ]
        if not matching_scores:
            return 0
        else:
            return max(matching_scores)

    def as_string():
        return self.json.get('id', '')

    async def _as_cell(self, lang, item_store):
        if 'id' in self.json:
            return {
                'id': self.id,
                'name': await item_store.get_label(self.id, lang),
            }
        else:
            return None

@register
class UrlValue(WikidataValue):
    """
    Fields:
    - value (the URL itself)
    - parsed (by urllib)
    """
    value_type = "url"

    def __init__(self, **kwargs):
        super(UrlValue, self).__init__(**kwargs)
        val = kwargs.get('value')
        self.parsed = None
        if val:
            try:
                self.parsed = urlparse(val)
                if not self.parsed.netloc:
                    self.parsed = None
                    raise ValueError
                self.canonical = self.canonicalize(self.parsed)
            except ValueError:
                pass

    def canonicalize(self, parsed):
        """
        Take a parsed URL and returns its
        canonicalized form for exact matching
        """
        return urlunparse(
            ('', # no scheme
             parsed[1],
             parsed[2],
             parsed[3],
             parsed[4],
             parsed[5]))

    @classmethod
    def from_datavalue(self, wd_repr):
        return UrlValue(value=wd_repr.get('value', {}))

    async def match_with_str(self, s, item_store):
        # no value
        if self.parsed is None:
            return 0

        # let's see if the candidate value is a URL
        matched_val = s
        try:
            parsed_s = urlparse(s)
            matched_val = self.canonicalize(parsed_s)
        except ValueError:
            pass
        return 100 if matched_val == self.canonical else 0

    def as_string(self):
        return self.json.get('value', '')

    async def _as_cell(self, lang, item_store):
        return {
            'str': self.value
        }

@register
class CoordsValue(WikidataValue):
    """
    Fields:
    - latitude (float)
    - longitude (float)
    - altitude (float)
    - precision (float)
    - globe (string)
    """
    value_type = "globe-coordinate"

    @classmethod
    def from_datavalue(self, wd_repr):
        return CoordsValue(**wd_repr.get('value', {}))

    async def match_with_str(self, s, item_store):
        # parse the string as coordinates
        parts = s.split(',')
        if len(parts) != 2:
            return 0.
        try:
            lat = float(parts[0])
            lng = float(parts[1])
        except ValueError:
            return 0.

        # measure the distance with the target coords
        # (flat earth approximation)
        diflat = lat - self.latitude
        diflng = lng - self.longitude
        dist = math.sqrt(diflat*diflat + diflng*diflng)
        dist_in_km = (dist / 180) * math.pi * 6371 # earth radius

        # TODO take the precision into account
        return 100*max(0, 1 - dist_in_km)

    def as_string(self):
        return str(self.json.get('latitude', ''))+','+str(self.json.get('longitude', ''))

    async def _as_cell(self, lang, item_store):
        return {
            'str': self.as_string()
        }

@register
class StringValue(WikidataValue):
    """
    Fields:
    - value (string)
    """
    value_type = "string"

    @classmethod
    def from_datavalue(cls, wd_repr):
        return cls(
                value=wd_repr.get('value', {}))

    async def match_with_str(self, s, item_store):
        ref_val = self.json.get('value')
        if not ref_val:
            return 0
        return fuzzy_match_strings(ref_val, s)

    def as_string(self):
        return self.json.get('value', '')

    async def _as_cell(self, lang, item_store):
        return {
            'str': self.value
        }


@register
class IdentifierValue(StringValue):
    """
    Fields:
    - value (string)
    """
    value_type = "external-id"

    async def match_with_str(self, s, item_store):
        return 100 if s.strip() == self.value else 0

@register
class QuantityValue(WikidataValue):
    """
    Fields:
    - amount (float)
    - unit (string)
    """
    value_type = "quantity"

    def __init__(self, **values):
        super(QuantityValue, self).__init__(**values)
        self.amount = values.get('amount')
        if self.amount is not None:
            self.amount = float(self.amount)

    @classmethod
    def from_datavalue(cls, wd_repr):
        return cls(**wd_repr.get('value', {}))

    async def match_with_str(self, s, item_store):
        try:
            f = float(s)
            if self.amount is not None:
                return match_floats(self.amount, f)
        except ValueError:
            pass
        return 0

    def as_string(self):
        return str(self.json.get('amount', ''))

    def is_novalue(self):
        return self.amount is None

    async def _as_cell(self, lang, item_store):
        return {
            'float': self.amount
        }

@register
class MonolingualValue(WikidataValue):
    """
    Fields:
    - text (string)
    - language (string)
    """
    value_type = "monolingualtext"

    @classmethod
    def from_datavalue(cls, wd_repr):
        return cls(**(wd_repr.get('value') or {}))

    async def match_with_str(self, s, item_store):
        ref_val = self.json.get('text')
        if not ref_val:
            return 0
        return fuzzy_match_strings(ref_val, s)

    def as_string(self):
        return self.json.get('text') or ''

    async def _as_cell(self, lang, item_store):
        return {
            'str': self.text
        }

@register
class TimeValue(WikidataValue):
    """
    Fields:
    - time (as iso format, with a plus in front)
    - parsed (as python datetime object)
    - timezone
    - before
    - after
    - precision
    - calendarmodel
    """
    value_type = "time"

    def __init__(self, **values):
        super(TimeValue, self).__init__(**values)
        if 'time' not in self.json:
            time = ''
        else:
            time = self.time
        if time.startswith('+'):
            time = time[1:]
        try:
            self.parsed = dateutil.parser.parse(time.replace('-00','-01'))
        except ValueError:
            self.parsed = None

    @classmethod
    def from_datavalue(cls, wd_repr):
        return cls(**wd_repr.get('value', {}))

    async def match_with_str(self, s, item_store):
        # TODO convert to a timestamp
        # TODO compute difference
        # TODO convert to a ratio based on the precision
        if not self.parsed:
            return 0
        try:
            date_parts = [int(part) for part in s.split('-')]
        except ValueError:
            return 0
        if len(date_parts) > 3:
            return 0

        common_date_parts = list(zip(date_parts, [self.parsed.year, self.parsed.month, self.parsed.day]))
        if self.precision == 10:
            common_date_parts = common_date_parts[:2]
        elif self.precision == 9:
            common_date_parts = common_date_parts[:1]

        return 100 if all(x == y for x, y in common_date_parts) else 0

    def as_string(self):
        return str(self.json.get('time', ''))

    def is_novalue(self):
        return self.parsed is None

    async def _as_cell(self, lang, item_store):
        if self.parsed:
            return {
                'date': self.parsed.isoformat()
            }
        else:
            return None

@register
class MediaValue(IdentifierValue):
    """
    Fields:
    - value
    """
    value_type = "commonsMedia"

@register
class DataTableValue(IdentifierValue):
    """
    Fields:
    - value (string)
    """
    value_type = "tabular-data"

class UndefinedValue(WikidataValue):
    """
    This is different from "novalue" (which explicitely
    defines an empty value.
    This class is for value filters which want to return
    an undefined value. It is purposely not registered
    as it does not match any Wikibase value type.
    (The equivalent in Wikibase would be not to state
    a claim at all).
    """
    value_type = "undefined"

    @classmethod
    def from_datavalue(cls, wd_repr):
        return cls()

    async def match_with_str(self, s, item_store):
        return 0

    def is_novalue(self):
        return False

    def as_string(self):
        return ""

    async def _as_cell(self, lang, item_store):
        return {}
