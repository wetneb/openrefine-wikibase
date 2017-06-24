from utils import to_q, fuzzy_match_strings, match_ints, match_floats
import dateutil.parser

wdvalue_mapping = {}

def register(cls):
    wdvalue_mapping[cls.value_type] = cls
    return cls

class WikidataValue(object):
    """
    This class represents any target value of a Wikidata claim.
    """
    value_type = None

    def __init__(self, **json):
        self.json = json

    def match_with_str(self, s, item_store):
        """
        Given a string s (the target reconciliation value),
        return a matching score with the WikidataValue.

        An ItemStore is provided to fetch information
        about items if needed.

        Scores should be returned between 0 and 100
        """
        return 0

    @classmethod
    def from_json(self, representation):
        """
        Creates a WikidataValue from our JSON representation
        """
        return wdvalue_mapping[representation['type']](**representation)

    @classmethod
    def from_datavalue(self, wd_repr):
        """
        Creates a WikidataValue from the JSON representation
        of a Wikibase datavalue.
        """
        typ = wd_repr['datatype']
        val = wd_repr['datavalue']
        cls = wdvalue_mapping.get(typ, self)
        return cls.from_datavalue(val)

    def is_novalue(self):
        return self.json == {}

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
        if not v:
            return ItemValue()
        else:
            return ItemValue(id=v.get('id'))

    def match_with_str(self, s, item_store):
        # First check if the target string looks like a Qid
        qid = to_q(s)
        if qid:
            return 100 if qid == self.id else 0

        # Then check for a novalue match
        if not s and self.is_novalue():
            return 100

        # Otherwise try to match the string to the labels and
        # aliases of the item.
        item = item_store.get_item(self.id)
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

@register
class UrlValue(WikidataValue):
    """
    Fields:
    - value (the URL itself)
    """
    value_type = "url"

    @classmethod
    def from_datavalue(self, wd_repr):
        return UrlValue(value=wd_repr('value', {}))

    def match_with_str(self, s, item_store):
        # TODO more matching modes
        return s == self.value

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

    def match_with_str(self, s, item_store):
        # TODO parse the string as coordinates
        # TODO measure the distance with the target coords
        # TODO convert that to a ratio based on the precision
        return 0.

@register
class IdentifierValue(WikidataValue):
    """
    Fields:
    - value (string)
    """
    value_type = "external-id"

    @classmethod
    def from_datavalue(self, wd_repr):
        return IdentifierValue(
                value=wd_repr.get('value', {}))

    def match_with_str(self, s, item_store):
        return 100 if s.strip() == self.value else 0


@register
class QuantityValue(WikidataValue):
    """
    Fields:
    - quantity (float)
    - unit (string)
    """
    value_type = "quantity"

    def __init__(self, **values):
        super(QuantityValue, self).__init__(**values)
        if 'quantity' in values:
            self.quantity = float(self.quantity)

    @classmethod
    def from_datavalue(self, wd_repr):
        return QuantityValue(**val)

    def match_with_str(self, s, item_store):
        try:
            f = float(s)
            ref = float(self.quantity)
            return match_floats(ref, f)
        except ValueError:
            return 0

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
    - calglobe-coordinateendarmodel
    """
    value_type = "time"

    def __init__(self, **values):
        super(TimeValue, self).__init__(**values)
        time = self.time
        if time.startswith('+'):
            time = time[1:]
        try:
            self.parsed = dateutil.parser.parse(time)
        except ValueError:
            self.parsed = None

    @classmethod
    def from_datavalue(self, wd_repr):
        return TimeValue(**wd_repr.get('value', {}))

    def match_with_str(self, s, item_store):
        # TODO convert to a timestamp
        # TODO compute difference
        # TODO convert to a ratio based on the precision
        return 0

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

    def match_with_str(self, s, item_store):
        return 0

    def is_novalue(self):
        return False
