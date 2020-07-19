
import doctest
def load_tests(loader, tests, ignore):
    from wdreconcile import subfields
    from wdreconcile import wikidatavalue
    from wdreconcile import sitelink
    tests.addTests(doctest.DocTestSuite(subfields))
    tests.addTests(doctest.DocTestSuite(wikidatavalue))
    tests.addTests(doctest.DocTestSuite(sitelink))
    return tests
