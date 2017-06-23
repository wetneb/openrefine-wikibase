import dateutil.parser

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
        raise NotImplemented

@register('lat')
class LatSubfield(Subfield):
    """
    Extracts the latitude from coordinate locations

    >>> LatSubfield()({"value": {"latitude": 47.521681,"longitude": 19.006213}})
    47.521681
    """
    expects_types = ['globecoordinate']

    def __call__(self, val):
        return val.get('value', {}).get('latitude')

@register('lng')
class LngSubfield(Subfield):
    """
    Extracts the longitude from coordinate locations

    >>> LngSubfield()({"value": {"latitude": 47.521681,"longitude": 19.006213}})
    19.006213
    """
    expects_types = ['globecoordinate']

    def __call__(self, val):
        return val.get('value', {}).get('longitude')

class TimeSubfield(Subfield):
    """
    Generic subfield to extract stuff from times
    """
    expects_types = ['time']

    def __call__(self, val):
        time = val.get('value', {}).get('time')
        if time.startswith('+'):
            time = time[1:]
        precision = val.get('value', {}).get('precision') or 1
        try:
            return self.run(dateutil.parser.parse(time), precision)
        except ValueError:
            pass

@register('year')
class YearSubfield(TimeSubfield):
    """
    >>> YearSubfield()({"value": {"time": "+1096-01-01T00:00:00Z", "precision": 9}})
    1096
    >>> YearSubfield()({"value": {"time": "+1096-01-01T00:00:00Z", "precision": 8}}) is None
    True
    """
    def run(self, time, precision):
        if precision >= 9:
            return time.year

@register('month')
class MonthSubfield(TimeSubfield):
    """
    >>> MonthSubfield()({"value": {"time": "+1896-03-01T00:00:00Z", "precision": 10}})
    3
    >>> MonthSubfield()({"value": {"time": "+1896-01-01T00:00:00Z", "precision": 9}}) is None
    True
    """
    def run(self, time, precision):
        if precision >= 10:
            return time.month

@register('day')
class DaySubfield(TimeSubfield):
    """
    >>> DaySubfield()({"value": {"time": "+1996-03-17T00:00:00Z", "precision": 11}})
    17
    >>> DaySubfield()({"value": {"time": "+1996-03-17T00:00:00Z", "precision": 10}}) is None
    True
    """
    def run(self, time, precision):
        if precision >= 11:
            return time.day

@register('hour')
class HourSubfield(TimeSubfield):
    """
    >>> HourSubfield()({"value": {"time": "+1996-03-17T04:00:00Z", "precision": 12}})
    4
    >>> HourSubfield()({"value": {"time": "+1996-03-17T00:00:00Z", "precision": 11}}) is None
    True
    """
    def run(self, time, precision):
        if precision >= 12:
            return time.hour

@register('minute')
class MinuteSubfield(TimeSubfield):
    """
    >>> MinuteSubfield()({"value": {"time": "+1996-03-17T04:15:00Z", "precision": 13}})
    15
    >>> MinuteSubfield()({"value": {"time": "+1996-03-17T04:00:00Z", "precision": 12}}) is None
    True
    """
    def run(self, time, precision):
        if precision >= 13:
            return time.minute

@register('second')
class SecondSubfield(TimeSubfield):
    """
    >>> SecondSubfield()({"value": {"time": "+1996-03-17T04:15:08Z", "precision": 14}})
    8
    >>> SecondSubfield()({"value": {"time": "+1996-03-17T04:15:00Z", "precision": 13}}) is None
    True
    """
    def run(self, time, precision):
        if precision >= 14:
            return time.second

@register('isodate')
class IsoDateSubfield(TimeSubfield):
    """
    >>> IsoDateSubfield()({"value": {"time": "+1996-03-17T04:15:08Z", "precision": 14}})
    '1996-03-17'
    >>> IsoDateSubfield()({"value": {"time": "+1996-03-17T04:15:00Z", "precision": 5}})
    '1996-03-17'
    """
    def run(self, time, precision):
        return time.date().isoformat()

@register('iso')
class IsoSubfield(TimeSubfield):
    """
    >>> IsoSubfield()({"value": {"time": "+1996-03-17T04:15:08Z", "precision": 14}})
    '1996-03-17T04:15:08+00:00'
    >>> IsoSubfield()({"value": {"time": "+1996-03-17T04:15:00Z", "precision": 5}})
    '1996-03-17T04:15:00+00:00'
    """
    def run(self, time, precision):
        return time.isoformat()


import doctest
def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite())
    return tests
