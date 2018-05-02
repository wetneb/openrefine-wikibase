import requests_cache

requests_cache.install_cache('tests/requests_cache')

from .typematcher import *
from .itemstore import *
from .engine import *
from .suggest import *
from .propertypath import *
from .utils import *
from .wikidatavalue import *

import doctest
def load_tests(loader, tests, ignore):
    from wdreconcile import subfields
    from wdreconcile import wikidatavalue
    from wdreconcile import sitelink
    tests.addTests(doctest.DocTestSuite(subfields))
    tests.addTests(doctest.DocTestSuite(wikidatavalue))
    tests.addTests(doctest.DocTestSuite(sitelink))
    return tests
