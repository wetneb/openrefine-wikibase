from .typematcher import *
from .itemstore import *
from .engine import *
from .suggest import *
from .propertypath import *
from .utils import *
from wdreconcile import subfields
from wdreconcile import wikidatavalue

import doctest
def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(subfields))
    tests.addTests(doctest.DocTestSuite(wikidatavalue))
    return tests
