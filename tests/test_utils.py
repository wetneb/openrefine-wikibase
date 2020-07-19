from wdreconcile.utils import fuzzy_match_strings, match_floats

def test_fuzzy_match_strings():
    # Matching identifiers
    assert (
        fuzzy_match_strings('Q1234','R1234') ==
        0)
    assert (
        fuzzy_match_strings('https://www.wikidata.org/entity/Q1234','Q1234') ==
        100)

    # Matching strings with different case and diacritics
    assert (
        fuzzy_match_strings('Février','Fevrier') ==
        100)
    assert (
        fuzzy_match_strings('PEMBERLEY','Pemberley') > 90)

    # Match urls
    assert (
        fuzzy_match_strings('gnu.org', 'http://gnu.org') > 50)

def test_fuzzy_match_strings_symmetric():
    pairs = [('a','b c'),
            ('aa bb', 'b aa'),
            ('a b', 'b c'),
            ('small birch tree','BirchTree'),
            ]
    for a, b in pairs:
        assert (fuzzy_match_strings(a,b) ==
                            fuzzy_match_strings(b,a))

def test_match_floats():
    assert (match_floats(51.837,51.837) == 100)
    assert (match_floats(51.837,51.836) > 50)
    assert (match_floats(51.837,151.836) < 50)
    assert (match_floats(0.837,1509.836) < 20)


