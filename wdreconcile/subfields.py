from .wikidatavalue import CoordsValue, QuantityValue, UndefinedValue, TimeValue, IdentifierValue, UrlValue


class SubfieldFactory(object):
    """
    An object that stores all registered subfields
    for use in property paths
    """

    def __init__(self):
        self.subfields = {}

    def register(self, name, subfield):
        """
        Registers a subfield with the given name.
        The name has to be made of plain ASCII lowercase letters.
        """
        self.subfields[name] = subfield

    def run(self, subfield_name, value):
        """
        Runs a subfield on a particular value.
        Returns None if the subfield does not exist.
        """
        subfield = self.subfields.get(subfield_name)
        if not subfield:
            return
        return subfield(value)

subfield_factory = SubfieldFactory()

class register(object):
    def __init__(self, name):
        self.name = name
    def __call__(self, cls):
        subfield_factory.register(self.name, cls())
        return cls

class Subfield(object):
    """
    The interface that subfields should implement.
    """

    """
    The list of expected types of value the
    subfield is defined on.
    """
    expects_types = []

    def __call__(self, value):
        """
        This runs the subfield extractor on
        a value extracted from the property path.
        """
        v = self.run(value)
        if v is None:
            return UndefinedValue()
        else:
            return v

    def run(self, value):
        """
        This is the method to be reimplemented by
        subclasses. It takes a WikidataValue as input
        and returns either a transformed WikidataValue,
        or None (in which case an UndefinedValue() will
        be returned by __call__).
        """
        raise NotImplemented

@register('lat')
class LatSubfield(Subfield):
    """
    Extracts the latitude from coordinate locations

    >>> LatSubfield()(CoordsValue(latitude=47.521681,longitude=19.006213))
    QuantityValue(amount=47.521681)
    """
    expects_types = ['globe-coordinate']

    def run(self, val):
        return QuantityValue(amount=val.latitude)

@register('lng')
class LngSubfield(Subfield):
    """
    Extracts the longitude from coordinate locations

    >>> LngSubfield()(CoordsValue(latitude=47.521681,longitude=19.006213))
    QuantityValue(amount=19.006213)
    """
    expects_types = ['globe-coordinate']

    def run(self, val):
        return QuantityValue(amount=val.longitude)

@register('year')
class YearSubfield(Subfield):
    """
    >>> YearSubfield()(TimeValue(time="+1096-01-01T00:00:00Z", precision=9))
    QuantityValue(amount=1096)
    >>> YearSubfield()(TimeValue(time="+1096-01-01T00:00:00Z", precision=8))
    UndefinedValue()
    """
    def run(self, val):
        if val.precision >= 9:
            return QuantityValue(amount=val.parsed.year)

@register('month')
class MonthSubfield(Subfield):
    """
    >>> MonthSubfield()(TimeValue(time="+1896-03-01T00:00:00Z", precision=10))
    QuantityValue(amount=3)
    >>> MonthSubfield()(TimeValue(time="+1896-01-01T00:00:00Z", precision=9))
    UndefinedValue()
    """
    def run(self, val):
        if val.precision >= 10:
            return QuantityValue(amount=val.parsed.month)

@register('day')
class DaySubfield(Subfield):
    """
    >>> DaySubfield()(TimeValue(time="+1996-03-17T00:00:00Z", precision=11))
    QuantityValue(amount=17)
    >>> DaySubfield()(TimeValue(time="+1996-03-17T00:00:00Z", precision=10))
    UndefinedValue()
    """
    def run(self, val):
        if val.precision >= 11:
            return QuantityValue(amount=val.parsed.day)

@register('hour')
class HourSubfield(Subfield):
    """
    >>> HourSubfield()(TimeValue(time="+1996-03-17T04:00:00Z", precision=12))
    QuantityValue(amount=4)
    >>> HourSubfield()(TimeValue(time="+1996-03-17T00:00:00Z", precision=11))
    UndefinedValue()
    """
    def run(self, val):
        if val.precision >= 12:
            return QuantityValue(amount=val.parsed.hour)

@register('minute')
class MinuteSubfield(Subfield):
    """
    >>> MinuteSubfield()(TimeValue(time="+1996-03-17T04:15:00Z", precision=13))
    QuantityValue(amount=15)
    >>> MinuteSubfield()(TimeValue(time="+1996-03-17T04:00:00Z", precision=12))
    UndefinedValue()
    """
    def run(self, val):
        if val.precision >= 13:
            return QuantityValue(amount=val.parsed.minute)

@register('second')
class SecondSubfield(Subfield):
    """
    >>> SecondSubfield()(TimeValue(time="+1996-03-17T04:15:08Z", precision=14))
    QuantityValue(amount=8)
    >>> SecondSubfield()(TimeValue(time="+1996-03-17T04:15:00Z", precision=13))
    UndefinedValue()
    """
    def run(self, val):
        if val.precision >= 14:
            return QuantityValue(amount=val.parsed.second)

@register('isodate')
class IsoDateSubfield(Subfield):
    """
    >>> IsoDateSubfield()(TimeValue(time="+1996-03-17T04:15:08Z", precision=14))
    IdentifierValue(value='1996-03-17')
    >>> IsoDateSubfield()(TimeValue(time="+1996-03-17T04:15:00Z", precision=5))
    IdentifierValue(value='1996-03-17')
    """
    def run(self, val):
        return IdentifierValue(value=val.parsed.date().isoformat())

@register('iso')
class IsoSubfield(Subfield):
    """
    >>> IsoSubfield()(TimeValue(time="+1996-03-17T04:15:08Z", precision=14))
    IdentifierValue(value='1996-03-17T04:15:08+00:00')
    >>> IsoSubfield()(TimeValue(time="+1996-03-17T04:15:00Z", precision=5))
    IdentifierValue(value='1996-03-17T04:15:00+00:00')
    """
    def run(self, val):
        return IdentifierValue(value=val.parsed.isoformat())

@register('urlscheme')
class SchemeSubfield(Subfield):
    """
    >>> SchemeSubfield()(UrlValue(value="https://www.gnu.org/software/emacs/"))
    IdentifierValue(value='https')
    >>> SchemeSubfield()(UrlValue(value="dummy"))
    UndefinedValue()
    """
    def run(self, val):
        if val.parsed:
            return IdentifierValue(value=val.parsed.scheme)

@register('netloc')
class NetlocSubfield(Subfield):
    """
    >>> NetlocSubfield()(UrlValue(value="https://www.gnu.org/software/emacs/"))
    IdentifierValue(value='www.gnu.org')
    >>> NetlocSubfield()(UrlValue(value="dummy"))
    UndefinedValue()
    """
    def run(self, val):
        if val.parsed:
            return IdentifierValue(value=val.parsed.netloc)

@register('urlpath')
class UrlpathSubfield(Subfield):
    """
    >>> UrlpathSubfield()(UrlValue(value="https://www.gnu.org/software/emacs/"))
    IdentifierValue(value='/software/emacs/')
    >>> UrlpathSubfield()(UrlValue(value="dummy"))
    UndefinedValue()
    """
    def run(self, val):
        if val.parsed:
            return IdentifierValue(value=val.parsed.path)


