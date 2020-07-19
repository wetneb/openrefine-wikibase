import re
import math
from fuzzywuzzy import fuzz
from unidecode import unidecode
import config


def to_q(url):
    """
    Normalizes a Wikidata item identifier

    >>> to_q('Q1234')
    'Q1234'
    >>> to_q('<http://www.wikidata.org/entity/Q801> ')
    'Q801'
    """
    if type(url) != str:
        return
    match = config.q_re.match(url.strip())
    if match:
        return match.group(config.q_re_group_id)

def to_p(url):
    """
    Normalizes a Wikidata property identifier

    >>> to_p('P1234')
    'P1234'
    >>> to_p('<http://www.wikidata.org/entity/P801> ')
    'P801'
    """
    if type(url) != str:
        return
    match = config.p_re.match(url.strip())
    if match:
        return match.group(config.p_re_group_id)

def fuzzy_match_strings(ref, val):
    """
    Returns the matching score of two values.
    """
    if not ref or not val:
        return 0
    ref_q = to_q(ref)
    val_q = to_q(val)
    if ref_q or val_q:
        return 100 if ref_q == val_q else 0
    simplified_val = unidecode(val).lower()
    simplified_ref = unidecode(ref).lower()

    # Return symmetric score
    r1 = fuzz.token_sort_ratio(simplified_val, simplified_ref)
    r2 = fuzz.token_sort_ratio(simplified_ref, simplified_val)
    r2 = r1
    return int(0.5*(r1+r2))

def match_ints(ref, val):
    """
    Todo
    """
    return 100 if ref == val else 0

def match_floats(ref, val):
    """
    Todo
    """
    diff = math.fabs(ref - val)
    if diff == 0.:
        return 100
    else:
        logdiff = math.log(diff)
        return 100*(math.atan(-logdiff)/math.pi + 0.5)


